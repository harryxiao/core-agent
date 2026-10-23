# Proposal — 冲突裁决的可见性与计数（SDD §5.5 可落地子集）

## Why

对照 `ai-arch/docs/memory-sdd.md` v1.0 §5.5「冲突与取代」与 §11.1 的 `memory.conflicts` 指标：

1. **裁决不可见**：0303 已实现「关键事实取值变化 ⇒ 新增版本 + 旧版 `superseded`，保留历史」
   （SDD §5.5 的硬性要求「保留旧记录、不得物理覆盖」已满足），但**裁决本身没有记录** ——
   盘上只有两条各自独立的条目，无法一次回答「哪两条构成冲突、何时裁决、按什么规则裁决」。
2. **指标缺口**：SDD §11.1 列出 `memory.conflicts`（冲突与 disputed 数），而 0311 的指标面
   显式登记「本仓无冲突概念」未实现；`memory stats` 也没有冲突视图。
3. **运维面缺口**：`memory audit` 只列治理事件（write/delete/forget/export），
   `memory list` 只列条目；没有按「旧值 → 新值」成对展示的入口。

**范围裁决（用户确认）**：只做**观察面收口**（方案 A），不改记忆语义。当前数据模型里
关键事实只有一个证据流（压实抽取），没有 `trust` / `confidence` 字段，也没有「显式用户更正」
信号 ⇒ SDD §5.5 的五级裁决中**只有第 3 级（新证据 > 旧证据）可判定**；同批同实体冲突已在
0172 按「留首条 + 告警」归并（规格已钉住）。因此规则 1/2/4 与规则 5（`disputed`）不可达，
本 change **不**引入 `disputed` 状态（避免死状态），并在 ADR 中登记为延后。

## What Changes

- **裁决记录**：`_supersede` 在置旧版 `superseded` 的同时，向审计日志追加 `op="conflict"`
  事件（`id` = 旧版 id、`target` = 新版 id、`reason="newer_wins"`），并自增进程内指标
  `memory.conflicts`；审计未接线 / 失败 ⇒ fail-open，不影响取代语义。
- **指标**：`FIXED_METRIC_KEYS` 增加 `memory.conflicts`（固定键、未发生为 0）。
- **统计**：`MemoryStats` 增加 `conflicts` 字段（`superseded_by` 非空的条目数，含后来被墓碑化
  的旧版），`memory stats` 的 JSON 与文本输出同步。
- **CLI**：新增 `memory conflicts [--json] [--limit N]` —— 从条目派生冲突链，按新版时间降序
  成对展示 `entity / old_id / new_id / old_ts / new_ts / decision / old_value / new_value`
  （取值为脱敏单行摘要）；只读、零强化、零写入；空库输出「（无冲突记录）」并以 0 退出。
- **规格**：`memory` MODIFIED ×4（关键事实跨压实合并 / 治理审计日志 / 运行指标快照 /
  运维统计）+ ADDED ×1（冲突可见性）。

## Impact

- 代码：`src/core/memory/stats.py`、`src/core/memory/store.py`、`src/core/entry.py`。
- 行为：除新增审计行、指标与 CLI 输出外，**检索 / 写入 / 取代 / 遗忘语义逐字不变**；
  审计关闭时仅指标与 CLI（条目派生）仍可用。
- 兼容：`MemoryStats` 新字段有缺省值；旧审计行（无 `conflict`）被忽略；旧条目
  （`superseded_by` 为空）不计入 `conflicts`。

## Out of Scope（明确不做）

- **不实现 `disputed` 状态与并列注入**：无可达触发条件（见上）；将来若引入 `trust` /
  `confidence` 或显式更正信号，再按 SDD 规则 1/2/4 扩展。
- **不自动合并 / 自动回滚冲突**：裁决仍由「新值写链」完成；本 change 只记录与展示。
- **不改同批归并语义**（0172：同批同 slug 只留首条 + 告警）。
- **不做跨进程冲突计数聚合**：`memory.conflicts` 是实例作用域指标（同 0311）。
