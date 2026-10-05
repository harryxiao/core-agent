<script>
  import { createSession, runStream } from "../lib/api.js";

  let sessionId = $state("");
  let input = $state("");
  let lines = $state([]);
  let busy = $state(false);
  let error = $state("");

  async function ensureSession() {
    if (sessionId) return sessionId;
    const body = await createSession();
    sessionId = body.session_id;
    return sessionId;
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    error = "";
    busy = true;
    input = "";
    lines = [...lines, { role: "user", text }];
    try {
      const sid = await ensureSession();
      for await (const ev of runStream(sid, text)) {
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
    }
  }
</script>

<section>
  <p class="meta">会话：{sessionId || "（发首条消息时创建）"}</p>
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
