# Proposal 0199 — Procedural 端到端门禁（测试，规格中性）

## Why（缺口）

批次 `Phase 37` 前三条（`0196`~`0198`）各自修了「任务过程 → 技能资产」链路的一环，但**没有
任何端到端锚**把两端接起来 —— 三段**各自**只有单元锚：

| 环节 | 既有锚 | 缺口 |
|---|---|---|
| `0196` 完成回调卸载 | `test_orchestration.py` 断言回调跑在**工作线程**（线程 ident） | 只测**执行线程**，不测语义 |
| `0197` 任务级采集 | `test_task_sop.py` 单测纯函数 `compose_task_steps` | 纯函数层，**未接**真编排器 / 真组合根 |
| `0198` 发布前质量门 | `test_skills.py` 单测 `SopExtractor` 的门分支 | 单测层，**未接**真提炼器实例 |

⇒ 「**真 `TaskScheduler` 跑完一个成功任务后，真组合根装配的任务级提炼器真的把 SOP 入进真技能库**」
**无用例断言**；回归时「哪一环断了」无法从端到端视角发觉。

## What Changes

**零 `src/` 改动**，新增 `tests/test_procedural_e2e.py`（4 个端到端用例）+ ADR-0189。

**真材实料**：真组合根（`build_runtime`）+ 真 `TaskScheduler` + 真 `MemoryStore`（任务过程步序
走**真实写入路径**）—— 只桩**两个外部面**（模型接缝 `llm.completion`、子 Agent 执行单元
`LoopPlugin`）；被测链路的任何一环**都不桩**。

**四条锚（含防空过断言）**：

1. **任务过程 → 技能资产**：3 次成功 `DONE` ⇒ 任务级 SOP 入库（`instructions` = 提炼文本、
   `task_types[0]` 带 `task::` 命名空间前缀）；并断言**未达阈值（2 次）前不入库**（防空过）。
2. **质量门在真链路上生效**：注入拒绝门 + JEV 配置 ⇒ 全程**无**技能入库，且**有**一次「质量门
   未过」留痕。
3. **无门 ⇒ 发布路径不变**：无 JEV 配置 ⇒ 与今日一致地发布（与锚 2 成对 ⇒ **门**是唯一差异）。
4. **过程取自记忆步序、非 `reply`**：捕获真实投喂提炼器的 prompt ⇒ 断言含 `loop.steps.<trace>`
   条目正文，且**不含** `SubtaskOutcome.reply`（ADR-0187 决策「读 L2 而非 reply」的代码化反证）。

**反证（门禁非空过的证明）**：逐条**临时回退**目标行为并确认对应用例转红 —— ① `_finalize` 去掉
`observe` ⇒ 锚 1/2/3/4 转红；② 任务级实例去 `namespace="task"` ⇒ 仅锚 1 转红（`task::` 断言）；
③ 任务级实例 `gate=None` ⇒ 仅锚 2 转红（无留痕）；④ `compose_task_steps` 改读 `outcome.reply`
⇒ 仅锚 4 转红（prompt 含 reply）。复原后 4 绿。

**规格中性判定**：本 change **不改任何行为**，只补测试锚 ⇒ 无 spec delta，`.openspec.yaml`
`skip_specs: true`（沿 `0156` / `0189` / `0195` 先例）。

## Impact

- **代码**：**零 `src/` 改动**（`git diff --stat src/` 为空）。
- **测试**：+4（`tests/test_procedural_e2e.py`），基线 2249 → **2253**。
- **不做**：不重复 `0196` 的线程 ident 锚（`test_orchestration.py` 已承载）；不重复 `0197` 的纯
  函数边界锚（`test_task_sop.py` 已承载）；不引入新依赖、不触网（桩模型 + 桩子 Agent）。
