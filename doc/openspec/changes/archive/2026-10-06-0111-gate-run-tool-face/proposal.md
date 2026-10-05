# 提案 — 质量门禁工具面（change 0111 / phase-27 切片 S1）

## 背景

`coding-plan/phase-27.md` §5.4 的切片 **S1**。初稿把 E42 记为「门禁**工具**缺位」，一手复核后**订正**
（§3.1）：门禁**执行器早已存在** —— 单一真源 `ci_cd/pipeline.py:25` `GATE_COMMANDS`＋生产执行器
`SubprocessGateExecutor` / `build_gate_executor`（ADR-0086 / change `0091`）＋结构化结果 `GateResult`。
真缺口只有一处：**这些件没有工具面**，Agent 无法经工具调用通道触发门禁（`runtime.py` 连 `ci_cd` 都未引用）。

## 变更目标

1. **填空缺，不造第二套**：新增原子工具 `tools.gate_run`，按**门禁名**路由到既有执行器。
   门禁名与命令取自单一真源 `GATE_COMMANDS`，**不另立门禁命令表**（否则即 change `0105` 删 `_published`、
   `0103` 收窄 `replay` 时反复钉的「双真源」反模式）。
2. **层级不破**：`tools` 是 L1、`ci_cd` 是 L5 ⇒ 执行器经**构造参数注入**，工具层**不 import** 交付流水线层；
   结果面只需 `passed` / `reason` 两个属性（结构协议），故 L1 也不必反向依赖 L5 模型。
3. **声明诚实**（change `0108`/E34 同判据）：跑门禁＝spawn 子进程 + 写 `__pycache__`/`.pytest_cache` 等
   ⇒ coeffects **诚实声明** `["process:spawn","filesystem:write"]`、`reversible=False` ⇒ 照旧过确认门。
   **不**走「白名单命令 ⇒ 只读免审批」：白名单的是**命令名**，不是**被执行的代码**（`pytest` 即执行仓库任意代码）。

## 非目标 / 已否决

- **不新写门禁执行器**：不复制 `GATE_COMMANDS`、不复制 subprocess 执行逻辑（ADR-0086 单一真源）。
- **不做 S0**：`EvolutionExecutor` 与 `features.evolution_executor` 装配裁剪属切片 **S0**，须先 §5.2 规格
  ＋ ADR-0104（phase-27 §5.4 顺序说明）；本 change **不触碰** `evolution/spec.md:203/215` 的边界。
- **不做 S2**：`proposer` delta 的 `suggested_patch`/`acceptance` 见下方「S2 改判」。
- **不扩暴露面**：`tools.gate_run` 只注册进**主**工具面；子 Agent / 宠物 loop 的 `builtin_tools` 注入点不动
  （无越界扩散；`_pet_tools` 白名单本就将其排除）。

## S2 改判（同批复核，登记不改代码）

phase-27 §5.4 把 S2（`proposer` delta 补 `suggested_patch` / `acceptance`）记为「✅ 中性」。复核后**改判：不纳入**，理由三条（一手）：

1. **无消费者＝空转**：`delta` 现只被 `engine._crystallize_skill` 读 `issue` 与 `schema` 两键
   （`engine.py:250-252`）；新增键**没有任何读取方** ⇒ 与 phase-19 §5 E31「不给出空转生命周期」同型。
2. **`suggested_patch` 无规格依据、无生产者**：`proposer` 是 `DiagnosisReport` 的纯函数
   （`target_plugin`/`issue`/`evidence`/`confidence`），没有任何 patch 建议来源。
3. **真消费方是 S0**：patch 建议与验收判据是**执行器**的输入 ⇒ 并入 S0 一并定字段与其消费者，
   避免现在造「写而不读」的字段（`evolution/spec.md:38-47`「生成带验收标准的单元」的落地口径随 S0 定）。

> 同批复核另见两条**判据订正**（不改代码，登 `phase-27.md` §3.2 / §5.4）：`module_id` 无需新增
> （`GenerationCandidate.target_plugin` 即模块身份）；`delta["schema"]` 是**读而不写**的既有键
> （`proposer.py:38` 不产出），归入 S0 的候选字段口径一并定。

## 风险

| 风险 | 缓解 |
|---|---|
| 门禁耗时远超一般工具（全量 `pytest`） | `ToolDef.timeout_s=660s` > 执行器内部 600s 上界；执行器自身超时已归一为 `passed=False` |
| 工具被误当「只读」而绕过审批 | coeffects 诚实声明 + `reversible=False` ⇒ 确认门；用例显式断言 `IRREVERSIBLE_BLOCKED` |
| 门禁名白名单失效（`Validator` 不校验 `enum`） | 处理器内**自行**判白名单，未知门禁 fail-closed，且断言**不触达**执行器 |
