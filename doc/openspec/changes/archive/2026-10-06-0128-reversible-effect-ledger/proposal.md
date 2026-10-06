# 提案 — 可逆效应账的清账与幂等（change 0128 / phase-34 E67）

## 背景

`coding-plan/phase-34.md`（全系统架构走查缺陷账本）登记的 **E67**（中危）：`EffectTracker.rollback`
**只撤不清** ⇒ 同一 trace 重复回滚会**二次撤销**、账目**无界增长**。

| # | 一手事实（2026-10-06 复核，行号已核实） | 后果 |
|---|---|---|
| 1 | `plugin_registry/effect_tracker.py:61-78` `rollback` 撤销成功后**既不移除** `_effects[id]`、**也不清** `_by_trace[trace]` | 账目在回滚后**原样保留** |
| 2 | 同上 ⇒ 对同一 `trace_id` **再调一次** `rollback`，`ordered` 仍含全部 `EffectId` ⇒ **undo 被二次调用** | P2「可逆」退化为**非幂等**：二次撤销可把已回退的文件再回退一次 |
| 3 | 同上 ⇒ 全局回滚 `rollback(None)` 亦不清账；`_effects` 只增不减，**无 `clear` 方法** | 长驻进程（`runtime.py:343` **全进程共用一个 tracker**）内存无界增长 |
| 4 | `effect_tracker.py:76-77` 撤销失败者仅计入 `undo_failed`，**保留在账**（该行为保留） | 失败项留账是**期望**语义，但缺规格钉住 |
| 5 | 规格面：`grep -rn EffectTracker doc/openspec/specs/` **仅** `evolution/spec.md` 间接提及；`plugin-registry/spec.md` **无**效应账条目 | 该能力**无 canonical 归属** ⇒ 本 change 补 **ADDED Requirement**（非 `skip_specs`） |

**触发面（可达）**：`fault_tolerance.py:138` `Rollback.on_failure` 按 `ctx.trace_id` 回滚；`loop/default.py:284`
与 `:523` 在中断 / 收尾路径各调一次 `self._tools.rollback(trace_id)`；`durability/manager.py:148`
`TimeTravel.rollback` 亦按 trace 回滚 —— 任何**同一 trace 被回滚两次**的路径（重试、恢复、
中断后收尾）都会走到「二次撤销 + 账目残留」。

## 变更目标

`plugin-registry/spec.md` **ADDED Requirement「可逆效应追踪（清账与幂等）」**（4 个 Scenario）：

1. **撤销成功即出账** —— `EffectId` 从账移除、trace 映射同步清理（trace 键清空即删）⇒ 同 trace
   **重复回滚 SHALL NOT 二次撤销**；账目 SHALL NOT 无界增长。
2. **不可逆效应不参与撤销**，随清账一并出账。
3. **撤销失败者留账隔离** —— 仍在账、由 `undo_failed` 报告，SHALL NOT 静默丢弃；单条失败不中断其余。
4. **显式清账 `clear(trace_id=None)`** —— 只清账、不触发 undo。

## Non-goals

- **不改 undo 栈序**：仍按记录序**逆序**撤销（LIFO），本 change 不动顺序语义。
- **不改调用方**：`fault_tolerance` / `loop` / `durability` / `tools.provider` 的调用点**逐字不变** ——
  清账在 tracker 内部完成。
- **不改 `replay` / `audit` 签名**：`audit` 在回滚后自然返回**空列表**（清账的必然结果，不是新分支）；
  已出账的 `EffectId` 再 `replay` 抛 `KeyError`（与「未知 id」同型，不另立错误码）。
- **不动 `Effect` 结构**（含 `reversible` 字段语义）。
- **不做「按 trace 的账目上限 / TTL 淘汰」**：未回滚的 trace 仍按原设计留账（另见「已知局限」）。

## 判据与取舍

**「清账」放在 `rollback` 内部（隐式），并另给 `clear`（显式）。** 理由：回滚的语义就是「这一轮到此
结束」——账目留着既无待撤销项、又会让幂等性失效；而 `clear` 覆盖「只想丢弃账目、**不想执行撤销**」
的场景（如调用方已另行恢复现场），两者职责不同、不可互相替代。

**撤销失败者清账时**：其 trace 映射**不删**（该键仍指向失败项），仅当该 trace 已无未了结项时删键 ——
使「留账隔离」既可见于 `audit`、又不让空键残留。

**不可逆效应随清账出账**（而非永久留账）：它从未被撤销、也无失败可隔离；留下只会让
「账目 SHALL NOT 无界增长」在**最易触发**的路径（每次 `code_run` 记一条不可逆效应）上失效。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 既有「回滚后仍能 audit / replay」的用法被打破 | 生产代码**无** `audit` / `replay` 消费者（仅测试用）；唯一相关测试 `test_plugin_registry.py:144-179` 的断言按**新语义**前置到回滚前（保序断言不变） |
| 撤销中途异常导致半清账 | 逐条「先 undo、成功即出账」；异常被捕获计入 `undo_failed`（该条**不出账**）⇒ 账目与真实世界一致 |
| 线程安全 | `_forget` 复用既有 `threading.RLock`（与 `record` 同锁），快照列表在锁内取出、undo 调用点保持**不持锁**（避免撤销闭包重入死锁） |

## 兼容性

- `record` / `rollback` / `replay` / `audit` **签名零变更**；新增 `clear` 为**纯增量** API。
- 一次回滚（trace 从未被重复回滚）的**可观测行为逐字不变**：`reverted` / `undo_failed` 的成员与顺序
  不变，唯一差别是**回滚后账目已空**（这正是本 change 的目的）。
- `RollbackReport` 结构零变更。
