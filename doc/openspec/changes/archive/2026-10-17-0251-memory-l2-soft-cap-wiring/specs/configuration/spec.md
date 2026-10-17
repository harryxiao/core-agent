# Configuration Specification Delta

## ADDED Requirements

### Requirement: 记忆容量配置

系统 SHALL 将 L2 活跃层容量纳入 ConfigSpec 单一真源：`memory.l2_soft_max_entries`
（L2 活跃层软上限条目数，缺省**未设置** = 不启用）。该键 SHALL 经 CLI flag
`--memory-l2-soft-max-entries` / env `CORE_MEMORY_L2_SOFT_MAX_ENTRIES` / config.yaml
`memory:` 段三面一一对应生成，参与优先级链（CLI flag > env > config.yaml > 默认值）。
取值 SHALL 为 **≥1 的整数**；`bool` / 小数 / 非数值 / `0` / 负数 SHALL 归一为**未启用**
（`None`）。`memory` 段为非结构化段 ⇒ 非法取值 SHALL NOT 阻断启动（与同段其余键同口径）。
配置值 SHALL 由组合根注入 `MemoryStore(l2_soft_max_entries=...)`；未配置或归一为未启用时
SHALL NOT 注入上限，写入路径行为与引入本键前逐字一致。

#### Scenario: 容量键经 ConfigSpec 声明
- **GIVEN** 配置了 `memory.l2_soft_max_entries`
- **WHEN** 系统启动加载配置
- **THEN** 该键经 ConfigSpec 单一真源解析，CLI flag / env / yaml 三面一一对应、无第二真源

#### Scenario: 缺省未启用
- **GIVEN** `memory` 段未配置 `l2_soft_max_entries`
- **WHEN** 系统启动装配记忆
- **THEN** 组合根以 `l2_soft_max_entries=None` 构造 `MemoryStore`，写入不受任何上限检查

#### Scenario: 配置值注入组合根
- **GIVEN** `memory.l2_soft_max_entries` 经任一面设为 `128`
- **WHEN** 系统启动装配记忆
- **THEN** 组合根以 `l2_soft_max_entries=128` 构造 `MemoryStore`，写入后按软上限收口

#### Scenario: 非法取值归一为未启用
- **GIVEN** `memory.l2_soft_max_entries` 取 `0` / 负数 / 布尔 / 小数 / 非数值
- **WHEN** 系统启动加载配置
- **THEN** 该键归一为未启用（`None`），启动不阻断，写入路径与未配置时一致
