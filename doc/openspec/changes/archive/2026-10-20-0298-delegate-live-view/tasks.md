# Tasks — 0298 前台委托子 Agent 的实况标签与只读交互视图

## 1. 规格与测试先行

- [x] 1.1 写 `specs/ui/spec.md` ADDED「前台委托子 Agent 实况视图」
- [x] 1.2 新增 `tests/test_agent_live_events.py`：侧信道先于动作结果；无订阅零事件；
  `_dispatch` 三条生命周期 + 白名单裁剪；无订阅仍走 `arun`；异常路径 `ok=false`
- [x] 1.3 新增 TUI 用例：Agent 标签出现、点击切换、收尾 ✓、回复节选
- [x] 1.4 新增 Web 模型用例：无任务也可有 Agent 标签、选择/详情/收尾/复位
- [x] 1.5 确认新增用例先红（实现前）

## 2. 侧信道与 runtime

- [x] 2.1 `protocol.py` 增 `current_event_sink` 并导出
- [x] 2.2 `DefaultLoop` 动作批次改「任务 + 队列 + 哨兵」，边执行边外发
- [x] 2.3 `runtime` 增标题/节选/白名单中继与 `agent.started/progress/completed`
- [x] 2.4 无订阅方保持 `arun` 原路径

## 3. 呈现层

- [x] 3.1 TUI：`_agent_tabs`、`_add_agent_widget`、`_open_agent` / `_complete_agent`，
  复用焦点与里程碑渲染；任务/会话复位清空
- [x] 3.2 Web：`taskview.js` 委托 reducer / 选择域 / 合成详情；`Chat` 上抛事件并在
  每轮开始复位；`App` 接线
- [x] 3.3 `node --test` 与 `vite build` 通过

## 4. 门禁与文档

- [x] 4.1 `uv run ruff check src tests` / `ruff format --check src tests` / `uv run pyright`
- [x] 4.2 `uv run pytest -q`（含 0297 基线）
- [x] 4.3 反证（`cp` 到 `/tmp` + `md5sum` 复原）：去掉侧信道外发 ⇒ 先于结果用例红；
  去掉白名单 ⇒ 表外字段不出现用例红
- [x] 4.4 `cd doc/openspec && openspec validate --all`
- [x] 4.5 ADR-0288 / known-risk E234 / test-cases §211 / ui-interface / loop-interface
- [ ] 4.6 归档 / 提交（**待用户确认**；0296 / 0297 亦待确认）
