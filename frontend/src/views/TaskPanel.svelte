<script>
  import { runTask } from "../lib/api.js";

  // 任务区（右栏，与会话列表**并列不混池**）：任务是**在途**运行态、会话是**持久**记录。
  // 任务状态由 App 持有（纯 reducer 派生）；本组件只保留输入/忙态/传输错误。
  // 子任务行点击与聊天区标签栏选中**同一**只读视图（不建第二数据源）。
  let {
    sessionId = "",
    tasks = [],
    notice = "",
    selected = null,
    onEvent = () => {},
    onSelectAgent = () => {},
  } = $props();

  let goal = $state("");
  let busy = $state(false);
  let error = $state("");

  const LABEL = { pending: "待执行", running: "运行中", done: "完成", failed: "失败" };

  function isSelected(taskId, subtaskId) {
    return Boolean(selected && selected.taskId === taskId && selected.subtaskId === subtaskId);
  }

  async function start() {
    const text = goal.trim();
    if (!text || busy) return;
    if (!sessionId) {
      error = "请先新建或选择会话";
      return;
    }
    error = "";
    goal = "";
    busy = true;
    try {
      for await (const ev of runTask(sessionId, text)) onEvent(ev);
    } catch (exc) {
      error = String(exc.message || exc);
    } finally {
      busy = false;
    }
  }
</script>

<section class="panel">
  <h3>任务</h3>
  {#if sessionId}
    <form
      onsubmit={(e) => {
        e.preventDefault();
        start();
      }}
    >
      <input bind:value={goal} placeholder="任务目标，如「调研并汇总」" disabled={busy} />
      <button type="submit" disabled={busy}>{busy ? "运行中…" : "启动任务"}</button>
    </form>
  {:else}
    <p class="hint">请先新建或选择会话</p>
  {/if}
  {#if error}<p class="error">{error}</p>{/if}
  {#if notice}<p class="notice">{notice}</p>{/if}
  {#if tasks.length === 0}
    <p class="hint">无在途任务</p>
  {/if}
  {#each tasks as task (task.taskId)}
    <article class="task">
      <header>
        <span class="goal">{task.goal}</span>
        <span class="id">{task.taskId}</span>
      </header>
      <ul>
        {#each task.subtasks as st (st.id)}
          <li>
            <div
              class="row"
              class:selected={isSelected(task.taskId, st.id)}
              role="button"
              tabindex="0"
              onclick={() => onSelectAgent(task.taskId, st.id)}
              onkeydown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelectAgent(task.taskId, st.id);
                }
              }}
            >
              <span class="badge {st.status}">{LABEL[st.status] ?? st.status}</span>
              <span class="title">{st.title || `子任务 ${st.id}`}</span>
            </div>
            {#if st.acceptance || st.milestones.length > 0 || st.reason || st.reply}
              <details>
                <summary>详情</summary>
                <ul class="detail">
                  {#if st.acceptance}<li>验收：{st.acceptance}</li>{/if}
                  {#each st.milestones as line}<li>{line}</li>{/each}
                  {#if st.reason}<li>判定：{st.reason}</li>{/if}
                  {#if st.reply}<li>{st.reply}</li>{/if}
                </ul>
              </details>
            {/if}
          </li>
        {/each}
      </ul>
    </article>
  {/each}
</section>

<style>
  .panel {
    width: 100%;
  }
  h3 {
    font-size: 0.9rem;
    margin: 0 0 0.5rem;
  }
  form {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  input {
    padding: 0.4rem 0.5rem;
    border: 1px solid #d0d7de;
    border-radius: 6px;
  }
  form button {
    padding: 0.4rem;
    border-radius: 6px;
    border: 1px solid #1f6feb;
    background: #1f6feb;
    color: #fff;
    cursor: pointer;
  }
  .hint {
    color: #59636e;
    font-size: 0.8rem;
  }
  .error {
    color: #cf222e;
    font-size: 0.8rem;
  }
  .notice {
    color: #1a7f37;
    font-size: 0.8rem;
  }
  .task {
    margin-top: 0.5rem;
    padding: 0.5rem;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    background: #fff;
  }
  header {
    display: flex;
    flex-direction: column;
  }
  .goal {
    font-size: 0.85rem;
  }
  .id {
    color: #59636e;
    font-size: 0.7rem;
  }
  ul {
    list-style: none;
    padding: 0;
    margin: 0.4rem 0 0;
  }
  li {
    margin-bottom: 0.3rem;
    font-size: 0.8rem;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.15rem 0.25rem;
    border-radius: 4px;
    cursor: pointer;
  }
  .row:hover {
    background: #f6f8fa;
  }
  .row.selected {
    background: #ddf4ff;
  }
  .badge {
    display: inline-block;
    min-width: 3.2rem;
    padding: 0.05rem 0.3rem;
    border-radius: 4px;
    text-align: center;
    font-size: 0.7rem;
    background: #eaeef2;
  }
  .badge.running {
    background: #ddf4ff;
  }
  .badge.done {
    background: #dafbe1;
  }
  .badge.failed {
    background: #ffebe9;
  }
  summary {
    color: #59636e;
    font-size: 0.75rem;
    cursor: pointer;
  }
  .detail {
    margin: 0.2rem 0 0 0.6rem;
    color: #59636e;
  }
</style>
