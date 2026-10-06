# tasks — 会话列表面板与 CLI 会话可见面（change 0116 / phase-28 E49，B2）

## 1. 规格（先行）
- [x] 1.1 `specs/cli-ops/spec.md`：ADDED「会话命令族与交互入口续聊」——`session show <id>`（同一转录存储、
      无转录明示、未登记 fail-closed）+ 交互入口 `--session <id>` 续聊（复用不新建、未登记 fail-closed）
- [x] 1.2 `specs/ui/spec.md`：ADDED「Web 会话列表与切换」——列表（派生标题 + 最近活跃降序）+ 点选查看转录
      与继续对话 + 显式新建（不隐式建会话）+ 呈现隔离
- [x] 1.3 `openspec validate 0116-session-list-cli-resume` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_entry.py`：`session show` 打印转录（user/assistant 两行）；无转录 ⇒ 「无对话记录」+ rc 0；
      未登记 ⇒ rc 1 + stderr 提示
- [x] 2.2 同文件：顶层 `--session <id>` 透传至 `CLIBridge`（`_FakeBridge` 捕获 `session_id`）
- [x] 2.3 `tests/test_repl.py`：`build_app(api, session_id=<已登记>)` **不新建**会话（`create_session` 被替换为
      断言失败）且既有转录渲染进时间线
- [x] 2.4 同文件：`build_app(api, session_id=<未登记>)` 抛 `UiError` 且**不静默新建**（注册表仍空）
- [x] 2.5 `tests/test_ui.py`：`CLIBridge(..., session_id=…)` 透传至 `connect_impl(api, session_id)`（既有注入点对齐新签名）

## 3. 实现
- [x] 3.1 `src/core/entry.py`：`_add_global_flags` 增顶层 `--session`（`dest="session_id"`）；
      `_add_session_parser` 增 `show <session_id>`；`_session` 增 `show` 分支（`SessionRegistry.exists` 守门 +
      `TranscriptStore(path=_state_path("messages.jsonl"))`）；`_repl` 透传 `args.session_id` 给 `CLIBridge`
- [x] 3.2 `src/core/ui/cli_bridge.py`：`CLIBridge` 增 `session_id` 字段，`connect_impl` 签名
      `Callable[[UIAPILayer, str], None]`；`_default_connect` 透传
- [x] 3.3 `src/core/ui/repl.py`：`build_app(api, session_id="")` **在懒 import 之前**解析会话
      （续聊 ⇒ `api.session_messages` 守门 + 取历史；缺省 ⇒ `create_session("cli")` 逐字不变）；
      `on_mount` 续聊态渲染既有转录 + 续接提示；`run_repl(api, session_id="")` 透传
- [x] 3.4 `frontend/src/lib/api.js`：`listSessions()`（`GET /sessions`）+ `fetchMessages(sessionId)`
      （`GET /session/{id}/messages`），复用既有 `toJson`
- [x] 3.5 `frontend/src/views/SessionList.svelte`（新）：列表（标题 + 最近活跃）+ 点选 + 「新建会话」
- [x] 3.6 `frontend/src/App.svelte`：会话页两栏（左 ChatGPT/Panel 右列表）；持有 `sessions` / `sessionId`；
      挂载与轮次结束后刷新
- [x] 3.7 `frontend/src/views/Chat.svelte`：改受控（`sessionId` 由父传入）；切会话 ⇒ 拉转录渲染；
      **去掉**惰性 `ensureSession`，未选中会话时提示先新建/选择

## 4. 四门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`（须 0/0/0）
- [x] 4.4 `.venv/bin/pytest -q`（基线 1462 passed）

## 5. 前端构建与端到端（离线，不触网）
- [x] 5.1 `npm run build`（`frontend/`，产物 `dist/` 被 gitignore、不提交）
- [x] 5.2 临时 `CORE_STATE_DIR` 起 `serve`：CLI 建两会话 → 各发一轮（或直写转录）⇒ `GET /sessions` 有
      派生标题且 `GET /session/<id>/messages` 可读；`session show` 与端点所见一致
- [x] 5.3 冒烟：SPA 构建产物挂载下刷新页面，列表/切换/继续对话三动作均可用（人工确认记录在案）

## 6. 文档
- [x] 6.1 `doc/03-interfaces/ui-interface.md`（CLI `session show` / `--session` 续聊；SPA 会话列表面）
- [x] 6.2 `doc/04-testing/test-cases.md` 增 TC 行

## 7. 归档 / 台账 / 提交
- [x] 7.1 delta 合进 2 个 canonical spec（**逐文件对齐排版惯例**）
- [x] 7.2 勾 tasks → `shutil.move` 进 `archive/2026-10-06-0116-session-list-cli-resume/`
- [x] 7.3 `openspec validate --all` ⇒ 30 passed / 0 failed
- [x] 7.4 `coding-plan/phase-28.md` 收口 E49（B1+B2 全闭）+ `coding-plan/README.md`
- [x] 7.5 记忆：`coding-plan-leftover-walkthrough.md` + `MEMORY.md`
- [x] 7.6 单提交 `feat(ui,cli): 会话列表面板与 CLI 会话可见面（change 0116）`
