<script>
  // 会话列表（右栏）：数据来自 `GET /sessions`，标题与最近活跃由后端派生。
  let { sessions = [], sessionId = "", onSelect = () => {}, onNew = () => {} } = $props();

  // 最近活跃降序属**呈现层**排序，不要求后端改变响应形状（见 change 0116 ui spec）。
  const ordered = $derived(
    [...sessions].sort((a, b) => (b.updated_at ?? 0) - (a.updated_at ?? 0)),
  );

  function title(entry) {
    return entry.title || "（暂无消息）";
  }

  function when(ts) {
    return ts ? new Date(ts * 1000).toLocaleString() : "";
  }
</script>

<aside>
  <button class="new" onclick={onNew}>＋ 新建会话</button>
  {#if ordered.length === 0}
    <p class="empty">暂无会话</p>
  {/if}
  <ul>
    {#each ordered as entry (entry.session_id)}
      <li>
        <button
          class="item"
          class:active={entry.session_id === sessionId}
          onclick={() => onSelect(entry.session_id)}
        >
          <span class="title">{title(entry)}</span>
          <span class="meta">{entry.mode} · {when(entry.updated_at)}</span>
        </button>
      </li>
    {/each}
  </ul>
</aside>

<style>
  aside {
    width: 260px;
    flex: none;
  }
  .new {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid #1f6feb;
    border-radius: 6px;
    background: #1f6feb;
    color: #fff;
    cursor: pointer;
  }
  .empty {
    color: #59636e;
    font-size: 0.85rem;
  }
  ul {
    list-style: none;
    padding: 0;
    margin: 0.5rem 0 0;
  }
  li {
    margin-bottom: 0.4rem;
  }
  .item {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    width: 100%;
    text-align: left;
    padding: 0.5rem 0.75rem;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    background: #fff;
    cursor: pointer;
  }
  .item.active {
    border-color: #1f6feb;
    background: #ddf4ff;
  }
  .title {
    font-size: 0.9rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .meta {
    color: #59636e;
    font-size: 0.75rem;
  }
</style>
