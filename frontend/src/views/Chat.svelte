<script>
  import { fetchMessages, runStream } from "../lib/api.js";
  import { labeledTitle, thinkingTitle, titleFromAction, toolName } from "../lib/activity.js";

  // 会话由父组件持有；本组件负责该会话时间线呈现与发送（ui-scheme：TUI/Web 一套）。
  let { sessionId = "", onTurnEnd = () => {} } = $props();

  let input = $state("");
  /** @type {Array<Record<string, unknown>>} */
  let timeline = $state([]);
  let busy = $state(false);
  let phase = $state("idle"); // idle | thinking | awaiting_approval
  let error = $state("");

  // 切会话 ⇒ 拉转录；思考/工具为纯呈现态，不入转录，切走即丢。
  $effect(() => {
    const sid = sessionId;
    if (!sid) {
      timeline = [];
      phase = "idle";
      return;
    }
    (async () => {
      try {
        const body = await fetchMessages(sid);
        if (sid !== sessionId) return;
        timeline = (body.messages ?? []).map((m) => ({
          kind: m.role === "user" ? "user" : "agent",
          text: m.content,
        }));
      } catch (exc) {
        if (sid === sessionId) error = String(exc.message || exc);
      }
    })();
  });

  function settleThinking() {
    const now = performance.now();
    timeline = timeline.map((item) => {
      if (item.kind !== "thinking" || !item.active) return item;
      const started = Number(item.startedAt);
      const ms = Number.isFinite(started) ? Math.max(0, Math.round(now - started)) : undefined;
      return { ...item, active: false, ms };
    });
  }

  function appendThinking(text, round) {
    const roundId = Number.isFinite(Number(round)) ? Number(round) : null;
    const idx = [...timeline]
      .map((item, i) => ({ item, i }))
      .reverse()
      .find(({ item }) => item.kind === "thinking" && item.round === roundId)?.i;
    if (idx !== undefined) {
      const cur = timeline[idx];
      timeline = [
        ...timeline.slice(0, idx),
        { ...cur, text: String(cur.text || "") + text, active: true },
        ...timeline.slice(idx + 1),
      ];
      return;
    }
    settleThinking();
    timeline = [
      ...timeline,
      { kind: "thinking", round: roundId, text, active: true, startedAt: performance.now() },
    ];
  }

  function startAction(payload) {
    settleThinking();
    const toolId = payload.tool_id;
    const args = payload.args ?? {};
    timeline = [
      ...timeline,
      {
        kind: "action",
        toolId,
        round: payload.round,
        title: titleFromAction(toolId, args),
        output: "",
      },
    ];
  }

  function completeAction(payload) {
    const toolId = payload.tool_id;
    const round = payload.round;
    let found = -1;
    for (let i = timeline.length - 1; i >= 0; i--) {
      const item = timeline[i];
      if (item.kind === "action" && item.toolId === toolId && item.round === round) {
        found = i;
        break;
      }
    }
    if (found < 0) {
      for (let i = timeline.length - 1; i >= 0; i--) {
        if (timeline[i].kind === "action" && timeline[i].toolId === toolId) {
          found = i;
          break;
        }
      }
    }
    if (found < 0) return;
    const cur = timeline[found];
    // 完成事件常无完整 args：保留进行中标题的括号摘要，只换完成后缀。
    const base = String(cur.title).replace(/\s·\s.*$/, "");
    const done = titleFromAction(toolId, {}, {
      ok: Boolean(payload.ok),
      ms: payload.duration_ms,
    });
    const suffix = done.includes(" · ") ? done.slice(done.lastIndexOf(" · ")) : "";
    timeline = [
      ...timeline.slice(0, found),
      {
        ...cur,
        title: base + suffix,
        output: payload.output != null ? String(payload.output) : cur.output,
      },
      ...timeline.slice(found + 1),
    ];
  }

  function appendDelta(delta) {
    const last = timeline[timeline.length - 1];
    if (last && last.kind === "agent" && last.streaming) {
      timeline = [
        ...timeline.slice(0, -1),
        { ...last, text: String(last.text || "") + delta },
      ];
    } else {
      timeline = [...timeline, { kind: "agent", text: delta, streaming: true }];
    }
  }

  function finalizeReply(reply, rawOutput) {
    settleThinking();
    const last = timeline[timeline.length - 1];
    if (last && last.kind === "agent" && last.streaming) {
      timeline = [
        ...timeline.slice(0, -1),
        { kind: "agent", text: String(reply) },
      ];
    } else if (reply !== undefined && reply !== null && String(reply).length) {
      // 已流式过则上面收口；非流式终态补一行
      if (!(last && last.kind === "agent" && !last.streaming && last.text === String(reply))) {
        timeline = [...timeline, { kind: "agent", text: String(reply) }];
      }
    }
    if (rawOutput) {
      timeline = [
        ...timeline,
        { kind: "raw", text: String(rawOutput) },
      ];
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    if (!sessionId) {
      error = "请先新建或选择会话";
      return;
    }
    error = "";
    busy = true;
    phase = "thinking";
    input = "";
    timeline = [...timeline, { kind: "user", text }];
    try {
      for await (const ev of runStream(sessionId, text)) {
        if (ev.type === "error") {
          error = `${ev.payload.code}: ${ev.payload.message}`;
        } else if (ev.type === "loop.delta") {
          appendDelta(String(ev.payload.text ?? ""));
        } else if (ev.type === "loop.reasoning") {
          appendThinking(String(ev.payload.text ?? ""), ev.payload.round);
        } else if (ev.type === "loop.action_started") {
          startAction(ev.payload ?? {});
        } else if (ev.type === "loop.action_completed") {
          completeAction(ev.payload ?? {});
        } else if (ev.type === "loop.result" || ev.type === "loop.error") {
          const reply =
            ev.payload?.reply ?? ev.payload?.message ?? JSON.stringify(ev.payload);
          finalizeReply(reply, ev.payload?.raw_output);
          phase = "idle"; // 终态即闲置（收尾后台不得占「思考中」）
          busy = false;
        }
      }
    } catch (exc) {
      error = String(exc.message || exc);
    } finally {
      settleThinking();
      phase = "idle";
      busy = false;
      onTurnEnd();
    }
  }
</script>

<section>
  <p class="meta">会话：{sessionId || "（尚未选择）"}</p>
  {#if phase === "thinking"}
    <p class="phase" aria-live="polite">思考中…</p>
  {/if}
  <ul class="timeline">
    {#each timeline as item}
      {#if item.kind === "user"}
        <li class="user"><strong>user</strong> {item.text}</li>
      {:else if item.kind === "agent"}
        <li class="agent"><strong>agent</strong> {item.text}</li>
      {:else if item.kind === "thinking"}
        <li class="step">
          <details>
            <summary
              >{labeledTitle("Thinking", thinkingTitle(Boolean(item.active), item.ms))}</summary
            >
            <pre>{item.text}</pre>
          </details>
        </li>
      {:else if item.kind === "action"}
        <li class="step">
          <details>
            <summary>{labeledTitle(toolName(item.toolId), item.title)}</summary>
            {#if item.output}<pre>{item.output}</pre>{/if}
          </details>
        </li>
      {:else if item.kind === "raw"}
        <li class="step">
          <details>
            <summary>{labeledTitle("raw", "未能解析的模型原始输出")}</summary>
            <pre>{item.text}</pre>
          </details>
        </li>
      {/if}
    {/each}
  </ul>
  {#if error}<p class="error">{error}</p>{/if}
  <form
    onsubmit={(e) => {
      e.preventDefault();
      send();
    }}
  >
    <input bind:value={input} placeholder="说点什么…" disabled={busy} />
    <button type="submit" disabled={busy}>{busy ? "思考中…" : "发送"}</button>
  </form>
</section>

<style>
  section {
    flex: 1;
    min-width: 0;
  }
  .meta {
    color: #59636e;
    font-size: 0.85rem;
  }
  .phase {
    color: #59636e;
    font-size: 0.9rem;
    margin: 0.25rem 0;
  }
  ul.timeline {
    list-style: none;
    padding: 0;
    min-height: 4rem;
  }
  li {
    padding: 0.5rem 0.75rem;
    margin-bottom: 0.4rem;
    border-radius: 6px;
    background: #fff;
    border: 1px solid #d0d7de;
    white-space: pre-wrap;
  }
  li.user {
    background: #ddf4ff;
  }
  li.step {
    background: #f6f8fa;
    color: #59636e;
    font-size: 0.9rem;
  }
  li.step details summary {
    cursor: pointer;
  }
  li.step pre {
    margin: 0.3rem 0 0;
    white-space: pre-wrap;
    font: inherit;
    color: #59636e;
  }
  .error {
    color: #cf222e;
  }
  form {
    display: flex;
    gap: 0.5rem;
  }
  input {
    flex: 1;
    padding: 0.5rem;
    border: 1px solid #d0d7de;
    border-radius: 6px;
  }
  button {
    padding: 0.5rem 1rem;
    border-radius: 6px;
    border: 1px solid #1f6feb;
    background: #1f6feb;
    color: #fff;
    cursor: pointer;
  }
</style>
