# Spec Delta — memory（0305 结晶 / 溶解钩子）

## ADDED Requirements

### Requirement: 技能结晶与溶解钩子的可用性

`Crystallizer.crystallize(skill_entry, *, force=False)` SHALL 按复用证据决定是否产出插件候选：
`skill_entry.reuse_count >= CRYSTALLIZE_MIN_REUSE`（常量 3，对齐「技能晋级至少 3 次成功」）或
`force=True`（显式用户要求 / 已获人工批准）时 SHALL 返回 `PluginCandidate`；否则 SHALL 返回
`None`。产出的候选字段保持既有口径：`plugin_id == f"skill.{skill_entry.id}"`、`generation == 1`、
`schema["content"] == skill_entry.content`、`source_entry_id == skill_entry.id`。

`Crystallizer.dissolve(plugin_id)` 返回的 L3 教训条目 SHALL 携带**非空** `trace_id`，使
`MemoryStore.write("L3", entry)` SHALL 接受并落盘（既有「无行动不记忆」拒收空 `trace_id` 的规则
不变）；条目 `id` / `layer` / `tags` / `content` 口径不变。

两个钩子 SHALL 保持纯函数：SHALL NOT 自行写入 `MemoryStore` 或技能库；落盘由调用方决定。
`force` 的前提（确属显式要求 / 已批准）SHALL 由调用方保证，钩子无审批上下文、SHALL NOT 自行
校验该前提。

#### Scenario: 复用不足不产出候选

- **GIVEN** 一条 `reuse_count=2` 的 L3 技能条目
- **WHEN** 以缺省参数调用 `crystallize`
- **THEN** 返回 `None`（不产出插件候选）

#### Scenario: 复用达到阈值产出候选

- **GIVEN** 一条 `reuse_count=3` 的 L3 技能条目
- **WHEN** 调用 `crystallize`
- **THEN** 返回 `PluginCandidate`，`source_entry_id` 指向该条目

#### Scenario: 显式请求豁免复用阈值

- **GIVEN** 一条 `reuse_count=0` 的 L3 技能条目
- **WHEN** 以 `force=True` 调用 `crystallize`
- **THEN** 返回 `PluginCandidate`（显式用户要求 / 已获人工批准同样构成晋级依据）

#### Scenario: 溶解教训可被存储接受

- **GIVEN** 任一插件 id
- **WHEN** 调用 `dissolve` 并把返回条目交给 `MemoryStore.write("L3", entry)`
- **THEN** 写入成功（返回该条目），`audit()` 可按其 id 查到该教训；`trace_id` 非空
