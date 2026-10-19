# 任务 — 0294 主/子 Agent 视图标签栏

## 1. 规格

- [x] 1.1 `specs/ui/spec.md`：MODIFIED「TUI 子 Agent 焦点视图」——标签栏、点击切换、
      点击折叠块标题进入焦点、收尾快照与重置语义；新增四个 Scenario。
- [x] 1.2 同 delta：MODIFIED「任务编排的 HTTP 面与 Web 任务区」——聊天区标签栏、
      只读子任务详情、任务区行选中、收尾快照；改写「不做焦点切换」的排除句；
      新增四个 Scenario。
- [x] 1.3 `openspec validate 2026-10-19-0294-agent-view-tabs` 全绿。

## 2. 测试先行

- [x] 2.1 `tests/test_repl.py`：标签自动出现（main + 主题缩写）、点击子任务标签/`main`
      切换且主时间线逐字不变。
- [x] 2.2 同文件：点击子任务 `CollapsibleTitle` 进入焦点视图（展开语义保留）。
- [x] 2.3 同文件：收尾保留终态标签与焦点；下一次 `/task` 的 `task_started` 重置为仅 main；
      `/resume` 清空标签。
- [x] 2.4 同文件：长 goal / 换行 / markup 字符 / 空 goal 的标签有界与回退。
- [x] 2.5 新建 `frontend/src/lib/taskview.test.js`：`abbreviateGoal` / `replyExcerpt`、
      reducer 全事件序列、收尾快照、选择校验、旧任务事件隔离、`milestoneLine`。
- [x] 2.6 定向运行确认红（TUI 用例与 `npm test`）。

## 3. 实现

- [x] 3.1 TUI：`_tab_label`、`_TaskTab`、`_SubtaskBlock`、`#task-tabs`、`_task_tabs` /
      `_refresh_tabs` / `_select_agent`，接入事件与 `_set_focus`。
- [x] 3.2 Web：新建 `lib/taskview.js`（纯 reducer/模型）；`App.svelte` 上提状态；
      `TaskPanel.svelte` 改为受控 + 行选中。
- [x] 3.3 Web：新建 `views/TaskTabs.svelte`、`views/SubtaskDetail.svelte`；
      `Chat.svelte` 接入标签、只读详情与保留挂载的视图切换。

## 4. 文档与台账

- [x] 4.1 `doc/01-architecture/adr.md`：ADR-0284（设计、被拒方案、局限）。
- [x] 4.2 `coding-plan/known-risk.md`：E230 行 + ADR-0284 局限索引。
- [x] 4.3 `doc/04-testing/test-cases.md`：§207（TC-AGENT-TABS，TUI + Web）。
- [x] 4.4 `doc/03-interfaces/ui-interface.md`：更新 TUI 焦点视图 / Web 任务区两段。
- [x] 4.5 `doc/03-interfaces/ui-scheme.md`：补标签/视图模型与只读约束。

## 5. 门禁

- [x] 5.1 `.venv/bin/ruff check src tests`
- [x] 5.2 `.venv/bin/ruff format --check src tests`
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright`
- [x] 5.4 `.venv/bin/pytest -q`（记录基线 → 新增后数量）
- [x] 5.5 `cd frontend && npm test && npm run build`
- [x] 5.6 反证 3/3（cp 到 /tmp，禁 `git checkout`；复原后 md5sum 一致）。
- [x] 5.7 `openspec validate --all` 全绿（归档前）。
- [ ] 5.8 真实冒烟：TUI 任务标签点击；Web 标签/任务区行点击与只读详情。

## 6. 收尾（待用户确认）

- [x] 6.1 `openspec archive -y 2026-10-19-0294-agent-view-tabs`
- [x] 6.2 仅暂存本 change 路径与实现/测试/文档路径并提交（不 `git add -A`）。
