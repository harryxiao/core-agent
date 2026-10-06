<script>
  import Chat from "./views/Chat.svelte";
  import SessionList from "./views/SessionList.svelte";
  import Settings from "./views/Settings.svelte";
  import TaskPanel from "./views/TaskPanel.svelte";
  import { createSession, listSessions } from "./lib/api.js";

  // 两页签（不引路由库）；会话页两栏 —— 会话列表与会话标识由本层持有（同一真源）。
  let tab = $state("chat");
  let sessions = $state([]);
  let sessionId = $state("");
  let error = $state("");

  async function refresh() {
    try {
      sessions = await listSessions();
    } catch (exc) {
      error = String(exc.message || exc);
    }
  }

  async function newSession() {
    error = "";
    try {
      const body = await createSession();
      sessionId = body.session_id;
      await refresh();
    } catch (exc) {
      error = String(exc.message || exc);
    }
  }

  $effect(() => {
    if (tab === "chat") refresh();
  });
</script>

<main>
  <nav>
    <button class:active={tab === "chat"} onclick={() => (tab = "chat")}>会话</button>
    <button class:active={tab === "settings"} onclick={() => (tab = "settings")}>设置</button>
  </nav>
  {#if tab === "chat"}
    <div class="columns">
      <Chat {sessionId} onTurnEnd={refresh} />
      <div class="rail">
        <!-- 任务区与会话列表同处右栏、**各自独立**（在途运行态 vs 持久记录，不混池） -->
        <TaskPanel {sessionId} />
        <SessionList {sessions} {sessionId} onSelect={(id) => (sessionId = id)} onNew={newSession} />
      </div>
    </div>
    {#if error}<p class="error">{error}</p>{/if}
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
    max-width: 1100px;
    margin: 0 auto;
    padding: 1rem;
  }
  .columns {
    display: flex;
    gap: 1rem;
    align-items: flex-start;
  }
  .rail {
    width: 260px;
    flex: none;
    display: flex;
    flex-direction: column;
    gap: 1rem;
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
  .error {
    color: #cf222e;
  }
</style>
