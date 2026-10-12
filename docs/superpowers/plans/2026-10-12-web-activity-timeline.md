# Web 活动时间线对齐 Implementation Plan

> **For agentic workers:** Use task-by-task execution. Steps use checkbox syntax.

**Goal:** 让 Web Chat 与 TUI 共用 `doc/03-interfaces/ui-scheme.md` 的活动时间线、标题语法与相位（缺省收起、Thinking 按 round、`loop.result` 即闲置）。

**Architecture:** 抽出纯函数 `frontend/src/lib/activity.js`（与 `repl.py` 标题表对齐）→ `Chat.svelte` 改为统一 `timeline[]` 渲染 → `TaskPanel` 里程碑复用同一标题函数。不改 SSE 事件面。

**Tech Stack:** Svelte 5、Vite、Node 原生 `node --test`（无 vitest）。

**Spec:** `doc/03-interfaces/ui-scheme.md` §2–5；TUI 真源 `src/core/ui/repl.py` 标题表。

---

### Task 1: 共享标题纯函数 + 测试

**Files:**
- Create: `frontend/src/lib/activity.js`
- Create: `frontend/src/lib/activity.test.js`

- [x] 实现 `toolName` / `toolTarget` / `actionTitle` / `fmtMs` / `thinkingTitle`（口径对齐 repl.py）
- [x] `node --test frontend/src/lib/activity.test.js` 全绿

### Task 2: Chat 时间线重构

**Files:**
- Modify: `frontend/src/views/Chat.svelte`

- [x] `timeline` 项：`user` | `thinking` | `action` | `agent` | `raw`
- [x] 处理 `loop.reasoning`（按 `round` 归并，标题 `Thinking`/`Thinking…`，`<details>` 缺省收起）
- [x] 处理 `loop.action_started` / `loop.action_completed`
- [x] `loop.result`：收口回复、落 `raw_output` 块、相位回 idle（`busy=false`）
- [x] 状态条：busy 时显示「思考中…」

### Task 3: TaskPanel 标题对齐

**Files:**
- Modify: `frontend/src/views/TaskPanel.svelte`

- [x] `milestone` 用 `actionTitle`，去掉 `▸`/`tool_id` 裸露

### Task 4: 验证

- [x] `node --test frontend/src/lib/activity.test.js`（9 passed）
- [ ] `npm run build`：当前环境 Node `v20.11.1` < Vite 8 要求（`^20.19 || >=22.12`），需升级 Node 后再验；与本次 UI 改动无关
