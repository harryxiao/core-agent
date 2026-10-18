# Tasks 0277 — 记忆内容分区权重（tags 三档）

> 验证目标：高/默认/低三档在同等字段下严格定序；未知标签与大小写漂移落默认档、冲突高档优先；
> 未分档条目相对排序不变；`0261` / `0275` 基准 recall/MRR 1.000、1 万条中位仍 <100ms。

## 1. 规格与测试先行

- [x] 1.1 `specs/memory/spec.md`：ADDED「内容分区权重（tags 三档）」（4 scen）。
- [x] 1.2 新 `tests/test_memory_tiers.py`：三档定序 / 冲突与未知 / 同档不变 / store 端到端。
- [x] 1.3 `tests/test_memory_lexical_scoring.py`：精确值断言补默认档项（`0.15 * 0.5`）。

## 2. 实现

- [x] 2.1 `src/core/memory/relevance.py`：`_W_TIER` / 高低档标签集 / `_tier_weight`；
      `relevance` 叠加加性项；更新模块 docstring 公式。

## 3. 验证

- [x] 3.1 四门禁（ruff / format / pyright / pytest）。
- [x] 3.2 `pytest -q tests/test_memory_quality.py -s`、`tests/test_memory_scale_benchmark.py -s`：
      recall/MRR 1.000、1 万条中位仍 <100ms。
- [x] 3.3 反证：① 摘 tier 项 ⇒ 定序红；② 低档先判 ⇒ 冲突红；③ 未知按低档 ⇒ 未知红；
      复原 `md5sum` 同。
- [x] 3.4 `openspec validate --all` 全绿后归档。

## 4. 文档与登记

- [x] 4.1 ADR-0267（公式、实测、反证、局限）。
- [x] 4.2 台账 E213（`coding-plan/known-risk.md`）。
- [x] 4.3 `doc/04-testing/test-cases.md` §189；`doc/02-modules/memory.md` §3.2；
      `doc/03-interfaces/memory-interface.md` §3（含「rank 不看 tags」句订正）。
- [x] 4.4 `coding-plan/Pending-Arbitration.md`：PA-09 **C 已闭**，D/E 仍开放。
- [x] 4.5 单次提交 `feat(memory): ...` + Co-Authored-By。
