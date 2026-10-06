# 0145 · 任务清单（Think 思考过程回显链路）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> 四个 delta：`llm-provider`「默认实现与配置归一化」／`loop`「异步流式执行」／
> `ui` ADDED「思考过程回显（Think）」／`configuration`「LLM 提供商配置（必选）」。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/llm-provider/spec.md`：MODIFIED「默认实现与配置归一化」—— 响应/增量携 `thinking`；两家口径归一；不掺 `content`（+2 Scenario）
- [x] 1.2 `specs/loop/spec.md`：MODIFIED「异步流式执行」—— `Thinking(delta)` 通道 ＋ 开关开启方 emit `loop.reasoning` ＋ 非流式终态思考 ＋ 持久面/子任务回流红线（+3 Scenario，既有 8 Scenario 逐字保留）
- [x] 1.3 `specs/ui/spec.md`：ADDED「思考过程回显（Think）」—— 三端折叠块默认收起、同轮归并、关闭不呈现、复用既有 SSE（+3 Scenario）
- [x] 1.4 `specs/configuration/spec.md`：MODIFIED「LLM 提供商配置（必选）」—— 可选子项 `show_thinking`（缺省 `false`，取值口径与 feature flag 同集）（+2 Scenario）
- [x] 1.5 `openspec validate 0145-thinking-echo-chain` ⇒ valid；`validate --all` ⇒ 31 passed / 0 failed
- [x] 1.6 ADR-0137（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 `tests/test_llm_provider.py`：`_map_response` / `_map_chunk` 归一 `reasoning_content` 与 `reasoning`；无字段 ⇒ 空串且既有字段零变化
- [x] 2.2 `tests/test_loop_planner.py`（或 `test_phase13.py` 就近）：`astream` 在开启时产出 `Thinking` 增量；关闭时不产；无 `astream` 提供方降级路径产终态 `Thinking`
- [x] 2.3 `tests/test_loop.py`（或 `test_phase*.py` 就近）：`_reason_events` 把 `Thinking` 转 `loop.reasoning`；关闭时事件面零新增；`streamed` 判据只认 `reply_delta`（思考事件不吞终态补发）
- [x] 2.4 `tests/test_ui.py`：`_EVENT_MAP` 登记 `loop.reasoning`（identity）且映射不改变其它类型
- [x] 2.5 `tests/test_repl.py`：TUI 消费 `loop.reasoning` ⇒ **单个**缺省收起折叠块、增量更新到同一块、可展开
- [x] 2.6 `tests/test_configuration.py`（或就近）：`llm.show_thinking` 缺省 False、真值集合归一为开、非法取值 `ConfigurationError` 阻断
- [x] 2.7 红线断言：`loop.reasoning` ∉ `_PROGRESS_FIELDS`；编排回流不外发该类型
- [x] 2.8 红态确认：新增用例在实现前**失败**（红），实现后转绿

## 3. 实现

- [x] 3.1 数据面：`llm_provider/models.py`（`LLMResponse.thinking` / `LLMChunk.thinking`）＋ `stdlib_provider.py`（`_map_response` / `_map_chunk` 归一，helper `_thinking_text`）
- [x] 3.2 通道：`loop/protocol.py` 增 `Thinking(delta)`；`loop/planner.py` 增 `show_thinking` 开关、`astream` 外发 `Thinking`、`_complete` 携带终态思考（`__call__` / 降级分支共用）
- [x] 3.3 事件面：`loop/default.py::_reason_events` 转 `loop.reasoning`；`astream` 的 `streamed` 判据收窄为 `reply_delta`
- [x] 3.4 映射：`ui/api.py::_EVENT_MAP` 登记 `loop.reasoning`（identity，注明为**有意**透传）
- [x] 3.5 呈现：`ui/repl.py` 思考折叠块（`_add_reasoning_widget`，`▸ 思考`，缺省收起、增量更新同一块）；`frontend/src/views/Chat.svelte` `<details>` 块（增量追加、终态不改写）
- [x] 3.6 开关装配：`configuration/models.py` `LLMConfig.show_thinking`；`manager.py` `_build_config` / `_merge_patch` 双处读取 ＋ `_llm_show_thinking` 取值归一（非法即 `ConfigurationError`）；`runtime.py` 主 planner 注入（子任务 / 神兽 planner **不注入** ⇒ 思考不上子任务链）
- [x] 3.7 `entry.py::_stream`（非交互 `run`）对 `loop.reasoning` 与 `loop.delta` 同处置（不逐段刷屏）

## 4. 文档同步

- [x] 4.1 `doc/03-interfaces/llm-provider-interface.md`：`LLMResponse` / `LLMChunk` 增 `thinking` 字段说明
- [x] 4.2 `doc/03-interfaces/loop-interface.md`：`Thinking(delta)` item 与 `loop.reasoning` 事件语义
- [x] 4.3 `doc/03-interfaces/ui-interface.md`：事件表补 `loop.reasoning`（三端折叠块）
- [x] 4.4 `doc/00-product/user-guide.md`：`llm.show_thinking` 开关说明（缺省关）
- [x] 4.5 `doc/04-testing/test-cases.md`：TC-THINK-01…0N ＋ 手工验收项（**真端点字段取证**、`Chat.svelte` 渲染）

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ **0 errors, 0 warnings, 0 informations**
- [x] 5.4 `.venv/bin/pytest -q` ⇒ **1729 passed**（基线 1697 + 32）
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical ⇒ `shutil.move` 至 `archive/2026-10-07-0145-thinking-echo-chain/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/phase-34.md` §1/§2 登记（E56~E60 feature 支线落点）＋ §9 落地台账行
- [x] 6.2 `coding-plan/README.md` 索引（3 处）
- [x] 6.3 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.4 单次提交：`feat(loop): Think 思考过程回显链路（change 0145）`
