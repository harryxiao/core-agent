<script>
  import Chat from "./views/Chat.svelte";
  import Settings from "./views/Settings.svelte";

  // 两页签而已，一个状态足够 —— 不引路由库（最小职责）。
  let tab = $state("chat");
</script>

<main>
  <nav>
    <button class:active={tab === "chat"} onclick={() => (tab = "chat")}>会话</button>
    <button class:active={tab === "settings"} onclick={() => (tab = "settings")}>设置</button>
  </nav>
  {#if tab === "chat"}
    <Chat />
  {:else}
    <Settings />
  {/if}
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    color: #1f2328;
    background: #f6f8fa;
  }
  main {
    max-width: 860px;
    margin: 0 auto;
    padding: 1rem;
  }
  nav {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }
  nav button {
    padding: 0.4rem 1rem;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    background: #fff;
    cursor: pointer;
  }
  nav button.active {
    background: #1f6feb;
    border-color: #1f6feb;
    color: #fff;
  }
</style>
