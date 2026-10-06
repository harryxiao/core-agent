<script>
  import { fetchMessages, runStream } from "../lib/api.js";

  // 会话由父组件持有（右栏列表同一真源）；本组件只负责该会话的呈现与发送。
  let { sessionId = "", onTurnEnd = () => {} } = $props();

  let input = $state("");
  let lines = $state([]);
  let busy = $state(false);
  let error = $state("");
  // 思考回显（change 0145 / ADR-0137）：**纯呈现**态 —— 独立于 `lines`（不落转录、不参与
  // 会话回放），单轮归并到同一折叠块、终态帧不改写；未开启时恒为空串（不渲染任何块）。
  let thinking = $state("");

  // 切会话 ⇒ 拉该会话转录并按追加次序渲染（竞态守门：回来时目标会话已变则丢弃）。
  $effect(() => {
    const sid = sessionId;
    thinking = ""; // 切会话 ⇒ 丢弃上一会话的思考块（呈现态，不入转录）
    if (!sid) {
      lines = [];
      return;
    }
    (async () => {
      try {
        const body = await fetchMessages(sid);
        if (sid !== sessionId) return;
        lines = (body.messages ?? []).map((m) => ({
          role: m.role === "user" ? "user" : "agent",
          text: m.content,
        }));
      } catch (exc) {
        if (sid === sessionId) error = String(exc.message || exc);
      }
    })();
  });

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    if (!sessionId) {
      error = "请先新建或选择会话";
      return;
    }
    error = "";
    busy = true;
    input = "";
    thinking = ""; // 新一轮 ⇒ 思考块重新起（同轮增量归并到同一块）
    lines = [...lines, { role: "user", text }];
    try {
      for await (const ev of runStream(sessionId, text)) {
        if (ev.type === "error") {
          error = `${ev.payload.code}: ${ev.payload.message}`;
        } else if (ev.type === "loop.delta") {
          // 流式增量（专类型，载荷 {text}）：追加到**同一条**回复尾部 —— 首帧新建行，
          // 其后原地拼接（不逐帧新建行、不渲染 JSON 载荷）。与 TUI _show_delta 同语义。
          const delta = String(ev.payload.text ?? "");
          const last = lines[lines.length - 1];
          if (last && last.role === "agent" && last.streaming) {
            lines = [...lines.slice(0, -1), { ...last, text: last.text + delta }];
          } else {
            lines = [...lines, { role: "agent", text: delta, streaming: true }];
          }
        } else if (ev.type === "loop.reasoning") {
          // 思考回显（专类型，载荷 {text}）：追加到**同一**折叠块 —— 不逐帧新建块、不渲染
          // JSON 载荷；纯呈现层（不落 `lines`），终态帧不改写该块。
          thinking += String(ev.payload.text ?? "");
        } else if (ev.type === "loop.result" || ev.type === "loop.error") {
          // 终态帧：若本轮有流式行则**原位收口**为完整回复（不重复一行），否则新建行。
          const reply = ev.payload.reply ?? ev.payload.message ?? JSON.stringify(ev.payload);
          const last = lines[lines.length - 1];
          if (last && last.role === "agent" && last.streaming) {
            lines = [...lines.slice(0, -1), { role: "agent", text: String(reply) }];
          } else {
            lines = [...lines, { role: "agent", text: String(reply) }];
          }
        }
      }
    } catch (exc) {
      error = String(exc.message || exc);
    } finally {
      busy = false;
      onTurnEnd(); // 最近活跃变化 ⇒ 刷新右栏排序
    }
  }
</script>

<section>
  <p class="meta">会话：{sessionId || "（尚未选择）"}</p>
  <ul>
    {#each lines as line}
      <li class={line.role}><strong>{line.role}</strong> {line.text}</li>
    {/each}
  </ul>
  {#if thinking}
    <details class="thinking">
      <summary>思考</summary>
      <pre>{thinking}</pre>
    </details>
  {/if}
  {#if error}<p class="error">{error}</p>{/if}
  <form
    onsubmit={(e) => {
      e.preventDefault();
      send();
    }}
  >
    <input bind:value={input} placeholder="说点什么…" disabled={busy} />
    <button type="submit" disabled={busy}>{busy ? "运行中…" : "发送"}</button>
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
  ul {
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
  .error {
    color: #cf222e;
  }
  details.thinking {
    margin-bottom: 0.4rem;
    color: #59636e;
    font-size: 0.9rem;
  }
  details.thinking summary {
    cursor: pointer;
  }
  details.thinking pre {
    margin: 0.3rem 0 0;
    white-space: pre-wrap;
    font: inherit;
    color: #59636e;
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
