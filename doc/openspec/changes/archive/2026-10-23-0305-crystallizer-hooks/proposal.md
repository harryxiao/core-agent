# Proposal — 0305 结晶 / 溶解钩子可用化

## Why

对照 `ai-arch/docs/memory-sdd.md` v1.0 走查 **P1-7**：记忆层「技能结晶 / 溶解」钩子空转。

1. **`Crystallizer.crystallize()` 不看复用次数** —— `MemoryEntry.reuse_count` 注释写明是「结晶
   阈值依据」，但实现无条件返回候选；`doc/02-modules/memory.md` §3.3 声称「复用超过阈值 → 提升
   为插件」，代码无此门。
2. **产物被丢弃** —— `EvolutionEngine._crystallize_plugin()` 调用钩子后直接丢弃
   `PluginCandidate`，结局只有 `accepted`；调用方拿不到本该交 L4 Validator 的产物。
3. **`dissolve()` 产物必被拒收** —— 返回的条目 `trace_id=""`，而 `MemoryStore.write()` 对空
   `trace_id` 拒绝（「无行动不记忆」）⇒ 该钩子的产品无法入库，失败教训静默丢失。

## What Changes

- `Crystallizer.crystallize(skill_entry, *, force=False) -> PluginCandidate | None`：
  `reuse_count >= CRYSTALLIZE_MIN_REUSE`（3，对齐 SDD「技能晋级至少 3 次成功」）或 `force=True`
  （显式用户要求 / 已获人工批准）才产出候选，否则返回 `None`。
- `EvolutionEngine._crystallize_plugin()`：以 `force=True` 调用（架构级候选已过 `confirm`
  人工确认），并把产物随 `EvolutionOutcome.artifact` 返回；`status` 语义不变（仍 `accepted`）。
- `Crystallizer.dissolve()`：`trace_id` 改为非空（`evolution.dissolve.<plugin_id>`），返回条目
  可被 `write()` 接受并落盘。
- 文档订正：`memory.md` §3.3 的 `MemoryStore.crystallize/dissolve` 与「可逆效应」表述改为
  实际钩子形态与能力边界。

## Non-goals

- 不把溶解钩子接进 `EvolutionEngine.dissolve()`（该路径已写 L2 教训；双写会产生重复条目）。
- 不给 `Crystallizer` 加存储依赖 / 自动落盘（钩子保持纯函数，落盘由调用方决定）。
- 不新增配置键：阈值是模块常量；`force` 仅由已确认路径使用。
- 不改技能库侧 `SkillCrystallizer`（其阈值语义属 evolution/skills 面，另行评估）。

## Impact

- 代码：`src/core/memory/crystallizer.py`、`src/core/evolution/models.py`、
  `src/core/evolution/engine.py`。
- 行为：直接调用 `crystallize()` 且复用不足时由「恒返回候选」变为 `None`；引擎路径产物可见。
- 规格：`memory` **ADDED** ×1、`evolution` **ADDED** ×1。
- 测试：新增 `tests/test_memory_crystallizer.py`；既有结晶用例按 `artifact` 增补断言。
