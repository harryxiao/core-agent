# loop token 记账口径（loop token accounting）· change 0152 · 账本 E96

## 为什么

`DefaultLoop` 的预算闸门（`token_budget` → `TOKEN_BUDGET_EXCEEDED`）比的左值是**猜测值**
`ctx.token_used`，而该值**只累加三样**：

1. 本轮 user 输入 `len(user_input) // 4`（`src/core/loop/default.py:466`）；
2. 回灌历史 `_history_tokens`（`default.py:120-126`，逐条 `content` 取 `len // 4`）；
3. 每步工具输出 `len(str(result.data)) // 4`（`default.py:527`）。

**完全不计**：planner 装配的 **system prompt 全块**（宪法规则 / 常驻笔记 / 相关事实 / 笔记 digest /
技能 / **工具 schema**，装配见 `src/core/loop/planner.py:152-203`）、助手 **action JSON**
（`default.py:502-514`）、observation JSON 包装、模型回复。⇒ 记账的是**远小于真实提示词**的子集。

两个后果：

- **固定前缀整块不计** ⇒ 前缀越大（常驻 ≤4000 + 事实 ≤2048 + digest ≤1200 + 工具 schema…），漏得越多；
- `len // 4` 对 **CJK 约 4× 低估**（1 汉字 ≈ 1+ token，被算作 0.25）。

⇒ 合成结果：**闸门偏晚、甚至不触发**，真实风险是撞厂商 `context_length_exceeded` 400，
而非优雅的 `TOKEN_BUDGET_EXCEEDED`。另注：`_should_compact` 比的 `ctx.rounds` 是**工具步数**
（上限 `max_rounds`）而非对话轮数 ⇒ 「按轮触发压实」**基本是死的**，实践唯一真触发是 token 阀。

这是**一条记账口径缺陷**，非行为违约 —— 规格（`doc/openspec/specs/loop/spec.md:179-217`）只写了
「累计 token 消耗超过预算即终止」，**未**规定记账口径。

## 改什么

**让记账看得见真实提示词**（两条接缝，均零三方依赖）：

- **planner 侧探针**：`LLMPlanner` 记录「最近一次装配的提示 token 观测」并暴露
  `last_prompt_tokens()` —— **provider 实报优先**（非流式响应 `usage.prompt_tokens`），否则按
  **装配全量估算**（全部消息 + 工具 schema）。
- **loop 侧口径**：`DefaultLoop` 的记账改为**全量装配估算**（本轮消息含动作 / 观察回灌 + 回灌历史），
  并以 planner 探针值为**下界**（`max(估算, 实报)`）。⇒ 系统提示与工具 schema **计入**，且 provider
  实报时可自动纠正 `len // 4` 的 CJK 偏差。探针缺失 / 异常 ⇒ 退化为既有估算（**零回归**）。

### 设计原则（与架构同向）

- **记账须覆盖所装配者** —— 闸门的语义是「别把提示词撑爆模型窗口」；不覆盖全量装配即**测不准**。
- **实测优先、估算兜底** —— provider 的 `usage.prompt_tokens` 是**权威数字**（`StdlibLLMProvider`
  本就已解析，此前**零消费**）；取作**下界**既不引三方 tokenizer，又天然纠正估算偏差。
- **契约最小** —— 探针走 duck-typing（`getattr(planner, "last_prompt_tokens", None)`），与既有
  `getattr(planner, "astream", None)`（`default.py:237`）**同型** ⇒ 既有替身 / 缺省回显 planner
  **零改动**。

## 规格

- `loop` **MODIFIED Requirement「错误与预算控制」**：追加**记账口径**条款（覆盖全量装配 + provider
  实报为下界）+ 2 Scenario（「记账计入系统提示与工具 schema」/「provider 实报为记账下界」）。
- 其余 Requirement / Scenario **逐字不变**（零回归）；窗口派生规则与阈值语义**不改**。

本项**非** `skip_specs`（行为变更、可见契约）⇒ 走规格先行、**不写** `.openspec.yaml`。

## 非目标（明确不做）

- **不改**共享估算器 `context.budget.estimate_tokens` —— 它会波及 context 打包与转录切片口径（`BudgetManager`
  裁剪、`transcript._tokens`），属另一个面，**另议**。
- **不做**「模型真实窗口动态获取 / known-model 窗口表」—— **另立账 E97**；本 change 只做**记账**。
- **不改** 窗口派生规则（`llm.context_window - loop.output_reserve`；ADR-0091 维持）。
- **不引** 三方 tokenizer（承「核心零三方运行时依赖」）。
- **不改** `_should_compact` 的**触发条件**（`ctx.rounds` = 工具步数 而非对话轮数一处，**另议**）。

## 风险与红线

- **密钥红线**：探针只读**装配后消息文本的长度**，不落任何新内容面；工具 schema 来自 `ToolDef`
  （无凭据）。**绝不**读取 / 记录密钥。
- **零回归**：既有 `tests/test_loop.py` / `test_loop_budget_config.py` / `test_context_compaction.py` /
  `test_history_replay.py` / `test_llm_config_hot_update.py` / `test_serve.py` 用例逐字不动、全绿。
- **行为变更面**：记账值变**大**（计入固定前缀）⇒ 预算终止与压实**更早触发**（这正是修正目的）；
  阈值数字（`token_budget`）与派生规则**不变**。

## 影响面

改动 `src/core/loop/default.py`（记账口径 + 探针消费）、`src/core/loop/planner.py`
（`last_prompt_tokens` 探针 + 装配估算）。测试 `tests/test_loop_token_accounting.py`（新增）。
文档 `doc/02-modules/loop.md`、`doc/03-interfaces/loop-interface.md`、`doc/04-testing/test-cases.md`
（新 `## 68.` TC-TOKACC）、`doc/01-architecture/adr.md`（ADR-0144）、`coding-plan/known-risk.md`
（E96 → 已修）。
