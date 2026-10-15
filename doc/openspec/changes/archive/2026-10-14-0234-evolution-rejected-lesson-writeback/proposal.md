# Proposal 0234: 未过门候选教训回写（spec–实现一致性修复）

## Why

`evolution/spec.md`「验证门」Requirement 的 `未过门丢弃` 场景承诺：

> **GIVEN** 候选未通过验证门 **WHEN** Validator 判定失败
> **THEN** 丢弃候选，**教训写回 L2/L3**

但 `engine.py::run_cycle` 的 rejected 分支实际只执行 `self._pending.record(candidate, gate)`
后返回 `status="rejected"`，**没有向 L2/L3 写入任何教训**——候选携带的诊断（issue）、门禁结论
（review 判定 / 各门结果）在丢弃时全部丢失，经验不回流，规格承诺未兑现。

对照：`dissolve` / 人工 `reject` 只写 **L2**；若 L2/L3 **同文双写**，会把门禁负样本全文灌进
L3（技能/程序知识面），污染检索与结晶。本 change **补实现且收口语义**：L2 承载完整教训，
L3 只写**短指针**（兑现「写回 L2/L3」、不复制全文）。

## What Changes

1. `run_cycle` rejected 分支：门禁未过时，除 `pending.record` 外，经 `_write_rejected_lesson`
   写入记忆后端：
   - **L2** `evolution.gate_rejected.<candidate_id>`：完整教训（目标插件、**有界** issue、
     review、各门结果）；issue 截断上界 `_MAX_ISSUE_CHARS = 400`（与 diagnoser note 同口径）；
     写前 `redact_secrets`。
   - **L3** `evolution.gate_rejected.l3.<candidate_id>`：**短指针**（指向 L2 id + target +
     review 判定词），**SHALL NOT** 与 L2 同文；写前同样脱敏。
   - 内存后端未注入 ⇒ 静默跳过；**不**调用 `memory_crystallizer.crystallize`。
2. 封装 `_write_rejected_lesson(candidate, gate)`；其余分支逐字不变。
3. spec delta ADDED「未过门教训写回」（分层内容语义 + 有界 issue + 场景）。

## Impact

- **规格**：ADDED「未过门教训写回」；不删原「未过门丢弃」场景。
- **代码**：`engine.py`（rejected 分支 + 私有方法；`redact_secrets`）。
- **兼容**：未注入时逐字一致；注入时新增 L2（全文）+ L3（指针）；与
  `evolution.rejected.*` / `dissolve.*` 前缀错开。
- **测试**：见 tasks.md。

## Non-goals

- 不删「未过门丢弃」既有承诺。
- 不动 `dissolve` / 人工 `reject` 既有写回。
- 不改 Crystallizer / accepted 路径落盘债。
- 不做诊断信号面增强（0236 等另议）。

## Risks

- issue 含敏感形态：写前 `redact_secrets`；另有字符上界防灌库。
- `memory.put` 抛错：与 dissolve 一致——未注入跳过，后端抛错冒泡。
