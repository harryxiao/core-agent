# 任务 · 0170 未闭合动作载荷：识别面收紧 + 失败可见 + 原始产出可诊断

## 1. 规格（先行，已完成）

- [x] `specs/loop/spec.md` —— **MODIFIED**「推理动作解析与失败可见」：新增形态 4（未闭合动作载荷）
      与判据、失败态携带 `raw_output` 与成因措辞；既有 5 条 Scenario **逐字保留**，新增 3 条。
- [x] `specs/llm-provider/spec.md` —— **ADDED**「流式增量携带终止原因」（2 Scenario）。
- [x] `specs/ui/spec.md` —— **ADDED**「TUI 折叠呈现未能解析的模型原始输出」（2 Scenario）。
- [x] `openspec validate 2026-10-08-0170-unparsed-action-visible` ⇒ valid

## 2. 测试（红 → 绿）

- [x] `tests/test_loop_output_protocol.py` 新增：
  - 未闭合动作载荷 ⇒ 失败态终止动作、`reply` 不含 `"tool_id"`、`raw_output` 非空且含 `tools.file_write`；
  - 未闭合载荷经**端到端**循环 ⇒ `LoopResult.failed=True`、`LoopResult.raw_output` 非空、
    `"tool_id"` **不在** `result.reply`、**不在**记忆沉淀（`_RecordingMemory` 替身）；
  - `raw_output` 有界（超长输入 ⇒ 长度 ≤ 上界）；
  - `finish_reason="length"` ⇒ 提示含「截断」；缺省 ⇒ 提示为「未闭合」，两者 `failed` 同为真；
  - **零回归**：闭合的尾部对象（含/不含 `tool_id`）仍为答复（既有 5 条用例不动）。
  - **红态证据**：改 `planner.py` 前跑新用例 ⇒ 必红（当前实现落 `failed=False` 的兜底）。
- [x] `tests/test_llm_provider.py`：`_map_chunk` 映射 `finish_reason`（末块 `length` ⇒ 字段为
      `"length"`；缺失 ⇒ `""`），且 `content`/`tool_calls`/`thinking` 逐字不变。
- [x] `tests/test_repl.py`：`loop.result` 携带 `raw_output` ⇒ 时间线新增**一个缺省收起**的
      `Collapsible`（展开后正文含原始产出）；`raw_output` 为空 ⇒ **零新增**。

## 3. 实现

- [x] `src/core/loop/planner.py`：`_RAW_OUTPUT_MAX`、`_UNPARSED_TRUNCATED` / `_UNPARSED_UNCLOSED`、
      `_unclosed_action_payload()`、`_parse(..., *, finish_reason="")` 形态 4 分支 + 起始 `{` 分支补
      `raw_output`；`_complete` / `astream` 透传 `finish_reason`（`astream` 累积末个非空值）。
- [x] `src/core/loop/protocol.py`：`Action.raw_output: str = ""`（尾字段）、`LoopResult.raw_output: str = ""`。
- [x] `src/core/llm_provider/models.py`：`LLMChunk.finish_reason: str = ""`；
      `stdlib_provider._map_chunk` 映射 `choices[0].finish_reason`。
- [x] `src/core/loop/default.py`：终止失败时取 `action.raw_output`；`loop_finished` trace 载荷**有则加**
      `raw_output`；`LoopResult(..., raw_output=...)`。
- [x] `src/core/ui/repl.py`：`_StepBlock.__init__(..., collapsed=False)`；`_run_turn` 新增
      `loop.result` + `raw_output` 分支（置于 `_format_event` 之前）+ `_add_raw_output_widget`。

## 4. 门禁（直连二进制，禁 `uv run`）

- [x] `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] `/home/harry/.praisonai/venv/bin/pyright` ⇒ **0 / 0 / 0**
- [x] `.venv/bin/pytest -q` ⇒ 全绿（基线 **1954**（本 change 实跑 **1962 passed**，+8），记增量）

## 5. 文档 / 台账

- [x] `doc/01-architecture/adr.md` **ADR-0161**（判据取舍 / 为何不用 `raw_decode` 位置 / 三处一致性 /
      `raw_output` 通道与不变量 / `finish_reason` 消费与不发 `max_tokens` 的取舍 / 呈现面 / 5 条局限）
      + 变更追踪行。
- [x] `doc/03-interfaces/loop-interface.md`：`Action.raw_output`、`LoopResult.raw_output`、
      `_parse` 的 `finish_reason` 形参与形态 4。
- [x] `doc/03-interfaces/llm-provider-interface.md`：`LLMChunk.finish_reason`（§2 类图 + 字段说明）。
- [x] `doc/03-interfaces/ui-interface.md`：§2 补段（不可解析收尾的折叠块）。
- [x] `doc/04-testing/test-cases.md` **`## 83.`**（TC-UNPARSED-ACTION，约 6 用例 + 红态证据）。
- [x] `coding-plan/known-risk.md`：§1 新行 **E107**（未闭合动作载荷静默成正文 —— 0170 收口）+ §3
      ADR-0161 局限行；**E97** 补注（`finish_reason` 已消费；`completion_tokens` 仍未消费；`max_tokens` 未下发）。

## 6. 收口

- [x] `openspec validate <change-id>` ⇒ valid ⇒ **手工归档**（delta 合进 3 份 canonical ⇒ `mv` 到
      `doc/openspec/changes/archive/2026-10-08-0170-unparsed-action-visible/`）⇒ `openspec validate --all`
- [x] 台账 + 记忆（`MEMORY.md` + `coding-plan-leftover-walkthrough.md`）+ **单次提交**
      （`fix(loop): 未闭合动作载荷不再当正文 …（change 0170 / ADR-0161 / 台账 E107）`）

## 7. 端到端目视（用户）

- [ ] TUI 复现场景：让模型回「解释 + 未闭合动作 JSON」⇒ 正文只显示**可读提示**（不再是 JSON 原文），
      下方一个**缺省收起**的「⚠ 未能解析的模型原始输出」块，点标题可展开看原文。
