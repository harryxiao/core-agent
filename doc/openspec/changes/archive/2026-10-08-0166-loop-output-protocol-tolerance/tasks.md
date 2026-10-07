# 0166 · 任务清单

> 触发：用户 2026-10-08 实测（模型回了正确动作 JSON，core-agent 未执行且记成功）。
> 证据：`~/.core/state/traces.jsonl` 轮 `14683edf49554534a414f7695dfa3797`（无 `tool_call` 记录）。

## 1. 规格与决策（先行）

- [x] 1.1 `specs/loop/spec.md` **ADDED** Requirement「推理动作解析与失败可见」+ 5 Scenario
- [x] 1.2 **ADR-0156**（尾部动作 JSON 容错 / 只认严格形态不猜 / `Action.failed` 的边界 /
      不改工具失败口径 / 系统提示加严）+ 变更追踪行
- [x] 1.3 `openspec validate 2026-10-08-0166-loop-output-protocol-tolerance` ⇒ valid

## 2. 测试先行（红）

- [x] 2.1 `tests/test_loop_output_protocol.py`（新）：**混写正文的尾部动作 JSON ⇒ 工具动作**
      （`tool_id`/`args` 正确、不入回复）
- [x] 2.2 同上：围栏包裹的尾部动作 JSON ⇒ 工具动作
- [x] 2.3 同上：非动作 JSON 的答复**不误判**（纯文本 / 正文中夹带示例 / 文末示例但无 `tool_id`）
- [x] 2.4 同上：`_parse` 各失败分支 ⇒ `LLM_PLAN_PARSE_FAILED` **且** `action.failed is True`
- [x] 2.5 同上：普通文本答复 / 合法动作 / 合法回复对象 ⇒ `action.failed is False`（零回归）
- [x] 2.6 同上（端到端）：planner 产失败态终止动作 ⇒ `LoopResult.failed is True`、
      `loop_finished.failed is True`、收尾观察者收到 `ok=False`
- [x] 2.7 同上：正常轮 ⇒ `LoopResult.failed is False`、观察者 `ok=True`（零回归）
- [x] 2.8 红态确认：`.venv/bin/pytest -q tests/test_loop_output_protocol.py` ⇒ 失败数与预期一致
      （实测 12 失败 / 1 通过 —— 唯一通过者是「纯文本回复零回归」）

## 3. 实现（绿）

- [x] 3.1 `src/core/loop/protocol.py`：`Action` 增 `failed: bool = False`
- [x] 3.2 `src/core/loop/planner.py`：`_trailing_json_object` 纯函数 + `_parse` 接入尾部动作分支
- [x] 3.3 同上：各 `_PARSE_FAILED` / `LLM 调用失败` 分支置 `failed=True`
- [x] 3.4 同上：`_SYSTEM_PROMPT` 加严（单独成块 / 不混写 / 不围栏包裹）
- [x] 3.5 `src/core/loop/default.py`：`act()` 终止分支透出 `failed`；`arun` 收尾标记
      并入 `_notify_turn(ok=…)` 与 `loop_finished.failed`

## 4. 文档

- [x] 4.1 `doc/02-modules/loop.md` 补段（推理输出解析的三形态 + 失败可见）
- [x] 4.2 `doc/03-interfaces/loop-interface.md` §2（`Action.failed`）+ §3.1（planner）补段
- [x] 4.3 `doc/04-testing/test-cases.md` 新节 `## 78.`（TC-PARSE，9 用例）
- [x] 4.4 `coding-plan/known-risk.md`：§1 新行 **E102**（缺陷 + 修法）+ §3 ADR-0156 局限行

## 5. 门禁与收口

- [x] 5.1 `ruff check` / `ruff format --check` / `pyright`（0/0/0）/ `pytest -q` 四门禁直连全绿
      （pytest：1936 通过 / 1 失败 —— 唯一失败 `test_diagnostics.py::test_render_notes_columns_aligned`
      属**另一在途 change `0165`** 的未提交工作，与本 change 无关，未触碰）
- [x] 5.2 `openspec validate 2026-10-08-0166-…` ⇒ valid ⇒ 手工归档（delta 并入 canonical + `mv`）
      ⇒ `openspec validate --all` ⇒ 32/0
- [x] 5.3 台账回填 + 记忆更新 + **单次提交**
