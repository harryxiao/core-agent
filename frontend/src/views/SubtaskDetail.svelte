<script>
  // 子任务只读详情：字段全部取自既有 `task.*` 事件载荷（不接子 Agent 消息流，不建第二数据源）。
  let { view = null, onMain = () => {} } = $props();

  const LABEL = { pending: "待执行", running: "运行中", done: "完成", failed: "失败" };
</script>

{#if view}
  <section class="detail" aria-label="子 Agent 只读详情">
    <p class="task-goal">任务：{view.task.goal}</p>
    <h4>
      {view.subtask.title || `子任务 ${view.subtask.id}`}
      <span class="badge {view.subtask.status}">
        {LABEL[view.subtask.status] ?? view.subtask.status}
      </span>
    </h4>
    {#if view.subtask.acceptance}
      <p class="line">验收：{view.subtask.acceptance}</p>
    {/if}
    {#if view.subtask.milestones.length > 0}
      <ul class="milestones">
        {#each view.subtask.milestones as line}<li>{line}</li>{/each}
      </ul>
    {/if}
    {#if view.subtask.reason}
      <p class="line">判定：{view.subtask.reason}</p>
    {/if}
    {#if view.subtask.reply}
      <pre>{view.subtask.reply}</pre>
    {/if}
    {#if view.subtask.attempt > 1}
      <p class="line">尝试：第 {view.subtask.attempt} 次</p>
    {/if}
    <p class="readonly">只读视图：子 Agent 没有消息通道，输入框仅对主 Agent 生效。</p>
    <button type="button" onclick={onMain}>返回主视图</button>
  </section>
{/if}

<style>
  .detail {
    border: 1px solid #d0d7de;
    border-radius: 6px;
    background: #fff;
    padding: 0.75rem;
  }
  .task-goal {
    color: #59636e;
    font-size: 0.8rem;
    margin: 0 0 0.3rem;
  }
  h4 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0 0 0.5rem;
    font-size: 1rem;
  }
  .badge {
    display: inline-block;
    padding: 0.05rem 0.35rem;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 400;
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
  .line {
    margin: 0.3rem 0;
    font-size: 0.85rem;
    color: #59636e;
  }
  .milestones {
    margin: 0.3rem 0;
    padding-left: 1.2rem;
    color: #59636e;
    font-size: 0.85rem;
  }
  pre {
    margin: 0.4rem 0;
    padding: 0.5rem;
    border-radius: 6px;
    background: #f6f8fa;
    white-space: pre-wrap;
    font: inherit;
    font-size: 0.85rem;
  }
  .readonly {
    color: #59636e;
    font-size: 0.75rem;
  }
  button {
    padding: 0.3rem 0.8rem;
    border-radius: 6px;
    border: 1px solid #1f6feb;
    background: #1f6feb;
    color: #fff;
    cursor: pointer;
  }
</style>
