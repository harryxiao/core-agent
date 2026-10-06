<script>
  import { runTask } from "../lib/api.js";

  // 任务区（右栏，与会话列表**并列不混池**）：任务是**在途**运行态、会话是**持久**记录。
  // 数据全部来自 `POST /task` 的 `task.*` 事件载荷（不建第二数据源；子 agent 会话流无数据源）。
  let { sessionId = "" } = $props();

  let goal = $state("");
  let tasks = $state([]); // 在途任务；收尾即移出（任务区回落）
  let notice = $state(""); // 终态一次性提示（任务不进入会话列表）
  let busy = $state(false);
  let error = $state("");

  const LABEL = { pending: "待执行", running: "运行中", done: "完成", failed: "失败" };

  function updateSubtask(taskId, subtaskId, fn) {
    tasks = tasks.map((t) =>
      t.taskId === taskId
        ? {
            ...t,
            subtasks: t.subtasks.map((s) => (s.id === subtaskId ? fn(s) : s)),
          }
        : t,
    );
  }

  /** 里程碑事件 → 详情行（载荷已由后端按内层类型白名单化）。 */
  function milestone(ev) {
    const d = ev.payload.data ?? {};
    if (ev.payload.event === "action_started") return `▸ 第 ${d.round} 轮：${d.tool_id}`;
    if (ev.payload.event === "action_completed") {
      return `${d.ok ? "✓" : "✗"} 第 ${d.round} 轮：${d.tool_id}（${d.duration_ms}ms）`;
    }
    return `· 第 ${d.round} 步${d.failed ? "（失败）" : "完成"}`;
  }

  function apply(ev) {
    const p = ev.payload ?? {};
    switch (ev.type) {
      case "task.task_started":
        tasks = [...tasks, { taskId: p.task_id, goal: p.goal, subtasks: [] }];
        break;
      case "task.plan_ready":
        tasks = tasks.map((t) =>
          t.taskId === p.task_id
            ? {
                ...t,
                subtasks: (p.subtasks ?? []).map((s) => ({
                  id: s.id,
                  title: s.goal,
                  status: "pending",
                  detail: s.acceptance ? [`验收：${s.acceptance}`] : [],
                })),
              }
            : t,
        );
        break;
      case "task.subtask_started":
        updateSubtask(p.task_id, p.subtask_id, (s) => ({ ...s, status: "running" }));
        break;
      case "task.subtask_progress":
        updateSubtask(p.task_id, p.subtask_id, (s) => ({
          ...s,
          detail: [...s.detail, milestone(ev)],
        }));
        break;
      case "task.subtask_completed":
        updateSubtask(p.task_id, p.subtask_id, (s) => ({
          ...s,
          status: p.ok ? "done" : "failed",
          detail: p.reason ? [...s.detail, p.reason] : s.detail,
        }));
        break;
      case "task.task_finished": {
        const task = tasks.find((t) => t.taskId === p.task_id);
        const n = (p.outcomes ?? []).filter((o) => o.ok).length;
        notice = `任务完成：${n}/${(p.outcomes ?? []).length} 子任务通过（${task?.goal ?? ""}）`;
        tasks = tasks.filter((t) => t.taskId !== p.task_id); // 收尾 ⇒ 移出在途列表
        break;
      }
      case "task.task_failed":
        notice = `任务失败：${p.code} ${p.reason ?? ""}`;
        tasks = tasks.filter((t) => t.taskId !== p.task_id);
        break;
      case "error":
        error = `${p.code}: ${p.message}`;
        break;
    }
  }

  async function start() {
    const text = goal.trim();
    if (!text || busy) return;
    if (!sessionId) {
      error = "请先新建或选择会话";
      return;
    }
    error = "";
    notice = "";
    goal = "";
    busy = true;
    try {
      for await (const ev of runTask(sessionId, text)) apply(ev);
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
            <span class="badge {st.status}">{LABEL[st.status] ?? st.status}</span>
            <span class="title">{st.title}</span>
            {#if st.detail.length > 0}
              <details>
                <summary>详情</summary>
                <ul class="detail">
                  {#each st.detail as line}<li>{line}</li>{/each}
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
  button {
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
