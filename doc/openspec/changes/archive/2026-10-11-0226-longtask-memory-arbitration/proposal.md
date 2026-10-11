# 0226 — 长任务 × 记忆：待裁决项登记（PA-08~PA-12）

## Why

2026-10-11 用户问「**现在的 core-agent 四层记忆光谱 ＋ 四类记忆模式，满足长任务要求了吗**」。
两路只读取证（要求侧规范 / 实现侧现状）＋ 主代理对**真实运行配置与 state** 的经验核验，得出：

- **四类记忆的能力位已落地接线**（官方成文映射见 `coding-plan/phase-38.md:7-8`）；
- 但长任务的三条硬要求里，**两条无对应机制**、另有一批**无立项**：
  1. **阶段/里程碑锚定不存在** —— 半自动提升产物 `pin=False`（`src/core/runtime.py:570-572` ＋
     `src/core/notes/promote.py:30`）⇒ 「越界即落常驻」的直觉不成立，硬约束只能靠人 `notes pin`
     （ADR-0142①「显式触发 ⇒ 无人在场的长任务仍不自动落 canonical」）；
  2. **检索面三处降级 ＋ 无图** —— 无分区权重、`doc/02-modules/memory.md:313-316`「无图存储 /
     无遍历 API」、缺省无 `llm.embedding_model`（memory 走词法、rag 走 `HashEmbedder`）、
     区块配比**只生效 1/5**（唯一消费者是事实面预算）、**L1 层为空**（`grep '"L1"' src/` 零命中）、
     **RAG 对循环不可达**（`grep rag src/core/tools src/core/loop` 零命中）；
  3. **M4 无测量** —— `doc/00-product/product-definition.md:83` 写明「基准任务序列测量」，
     该 harness **不存在**。
- 另有两处**登记/索引级**缺口，且其中一处**已实际造成返工成本**：
  4. `coding-plan/README.md:3` 自述「36 份（`phase-0`~`phase-34`）」，实测已有 `phase-41` ⇒
     **本轮差点漏掉** `phase-36`（长任务硬化）与 `phase-38`（对照外部四维记忆蓝图查漏补缺）
     两册最相关的账，从而把**已裁决过的事项**重报为缺口；
  5. `phase-38` 的批内 `G1`/`G2` 与「记忆三面路线图 `G1`/`G2`/`G3`」**同名不同义**。

**外部材料的效力须先界定**：`Agent-Memory.md` / `Agent-Memory-LongTask.md` /
`memory-4-layer-architecture.md` 三份均为**未跟踪文件**，前两份自标「百度AI生成，内容仅供参考」；
台账定位为「外部参考审查…取精华弃糟粕」，并**明写不取**其「里程碑永久删除 / 单库无隔离 / 三方依赖」
（`coding-plan/known-risk.md:269`）；ADR-0190 已裁「蓝图字面 tier 边界 `0-5/6-20/21+` **不采纳**…
**采其结构弃其数值**」（`known-risk.md:106`）。⇒ 蓝图的**数值承诺不作判据**。

## What Changes

- **`coding-plan/Pending-Arbitration.md` 拆两轮**：
  - `§0.1`/`§1.1` = 第一轮（提词收紧，PA-01~PA-07 全闭，原样保留）；
  - `§0.2`/`§1.2` = **第二轮**（长任务 × 记忆）＋ 新增 **PA-08~PA-12**，每条带
    现象 / 证据（`file:line`）/ 可选项与代价 / 建议 / 落地面；
  - 新增 **§5 取证附录**：三层证据（要求侧 / 实现侧 / 实测）＋ **可重跑**的配置与 state 复核命令。
- **新 `tests/test_arbitration_ledger.py`**：结构守卫 —— 两轮分节 / 总表↔逐条一致 /
  闭项必带 change 号 / 开放项五要素齐。
- **台账回填**：本 change ＋ ADR-0216 ＋ `known-risk.md` §1 E163／§3 ＋ `test-cases.md` §139。

## Impact

- **规格中性**（`skip_specs: true`）：改动全在**文档面**与**测试面** ⇒ **零 `src/` 改动**
  （`git diff --stat src/` 为空）。
- **登记 ≠ 裁决**：PA-08~PA-12 **全部保持开放**（本 change 不实现其中任何一项）。
- **密钥红线**：§5 的实测命令**只统计结构**（id 前缀 / layer / 计数），**绝不回显正文或取值**
  （守 `requirements.md:339` CORE-NFR-SEC1）；`.env` 复核**只列变量名、不读值**。
- 向后兼容：第一轮的 PA-01~PA-07 条目**逐字保留**，仅其所在分节标题更名（`§0`→`§0.1`、`§1`→`§1.1`）。
