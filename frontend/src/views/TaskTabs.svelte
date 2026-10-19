<script>
  // 主/子 Agent 标签栏（聊天区下方、输入框上方）：首位 main，其后当前/最近任务的子任务。
  // 纯呈现：标签模型由 App 经纯 reducer 派生；点击只切换只读视图。
  let { tabs = [], onSelect = () => {} } = $props();
</script>

{#if tabs.length > 0}
  <div class="task-tabs" role="tablist" aria-label="主/子 Agent 视图">
    {#each tabs as tab (tab.key)}
      <button
        type="button"
        role="tab"
        class="tab"
        class:active={tab.active}
        aria-selected={tab.active}
        onclick={() => onSelect(tab.taskId, tab.subtaskId)}
      >
        {tab.label}
      </button>
    {/each}
  </div>
{/if}

<style>
  .task-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    margin: 0.5rem 0;
  }
  .tab {
    padding: 0.2rem 0.6rem;
    border: 1px solid #d0d7de;
    border-radius: 999px;
    background: #fff;
    color: #59636e;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .tab:hover {
    background: #eaeef2;
  }
  .tab.active {
    border-color: #1f6feb;
    background: #ddf4ff;
    color: #1f2328;
    font-weight: 600;
  }
</style>
