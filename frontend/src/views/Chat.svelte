<script>
  import { fetchMessages, runStream } from "../lib/api.js";

  // 会话由父组件持有（右栏列表同一真源）；本组件只负责该会话的呈现与发送。
  let { sessionId = "", onTurnEnd = () => {} } = $props();

  let input = $state("");
  let lines = $state([]);
  let busy = $state(false);
  let error = $state("");

  // 切会话 ⇒ 拉该会话转录并按追加次序渲染（竞态守门：回来时目标会话已变则丢弃）。
  $effect(() => {
    const sid = sessionId;
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
    lines = [...lines, { role: "user", text }];
    try {
      for await (const ev of runStream(sessionId, text)) {
        if (ev.type === "error") {
          error = `${ev.payload.code}: ${ev.payload.message}`;
        } else if (ev.type === "loop.result" || ev.type === "loop.error") {
          const reply = ev.payload.reply ?? ev.payload.message ?? JSON.stringify(ev.payload);
          lines = [...lines, { role: "agent", text: String(reply) }];
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
