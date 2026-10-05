# design — 熔断阈值/冷却可配

## 决策

1. **落点：`ConfigSpec` 单一真源。**
   两个新键进 `_CONFIG_SPECS` 后，四条通道**零额外代码**齐备：CLI flag 由
   `entry._add_config_flag` 遍历 `config_specs()` 派生、`_cli_overrides` 按 `spec.key`
   派生 dest、env 由 `_apply_env` 按 `spec.env_var` 注入、`config show/set` 面由同一清单驱动。
   **不得**另起一套键名解析（对齐「配置项以 ConfigSpec 为单一真源」）。

2. **不新增结构化段**（沿用 `permission.mode` 先例）。
   `constraints` 段寄居 `extra`，由 `ConfigManager.circuit_breaker()` 访问器收口。
   理由：① `AppConfig` 增字段会牵动 `_STRUCTURED_SECTIONS`，并须改 configuration spec 里
   「五个结构化段 `llm`/`features`/`im`/`pet`/`judgment`」的**逐字枚举**；② `_known_sections()`
   已有「ConfigSpec 声明段」分支（`map_to` 前缀）⇒ `constraints` **自动**进白名单，
   `constraints:` 段不会误报「未知配置段」（change `0064` 的单一真源设计直接复用）；
   ③ `permission` 段是同形的既有先例，改动面最小。

3. **校验期拒绝非法取值**（而非静默兜底）。
   阈值须 ≥1 的整数、冷却须 ≥0 的数值；`bool` 与不可解析字面量一律拒。
   理由：`failure_threshold: 0` 会让**首个失败即熔断**、负冷却会让熔断**永半开失败**，
   静默接受等于把配置错误变成运行时诡异行为 —— 正是 change `0064`（E18）反对的静默劣化。
   报错在 `load()` 期抛出（`ConfigurationError`），阻断启动。

4. **组合根注入，链的身份不变。**
   `build_constraints_chain(failure_threshold=..., cooldown_s=...)`；主 loop 与
   `_agent_loop(provider)` 仍共享**同一个** `ConstraintsChain` 实例
   （阈值随 runtime 固定；熔断态 per-runtime，语义同 change `0052`）。

5. **类型归一在访问器**（env/CLI 传入皆为字符串）。
   `int()` / `float()` 归一；因校验期已保证可解析，访问器不设二次兜底
   （避免为不可能场景写分支）。

## 取舍与否决

- **否决**：做成 `ConstraintsConfig` 结构化段（见决策 2 —— 牵动 spec 逐字枚举，收益仅是「更显式」）。
- **否决**：只加 yaml 段、不接 CLI/env（非 ConfigSpec 面 ⇒ 违反单一真源，且 `config set` 够不着）。
- **接受**：`constraints.failure_threshold` 这类键**不在**既有五段枚举中，故 `config show` 的
  分级呈现里归 `advanced`? —— 不：两项均按 `ConfigExposure.CORE`（影响生产行为，须可发现）。
