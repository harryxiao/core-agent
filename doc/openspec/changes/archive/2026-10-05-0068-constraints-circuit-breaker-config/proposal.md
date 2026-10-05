# 熔断阈值/冷却可配（constraints-circuit-breaker-config）

## Why

账本 **E15**（`coding-plan/phase-19.md` §1；触发前提「E10 配置门控」已由 change `0067` 达成）。

熔断的构造面**早就可注入**（`doc/03-interfaces/constraints-interface.md:62`：`failure_threshold=5` /
`cooldown_s=30.0` / `clock`），但**唯一的构造调用点** `src/core/runtime.py:431`
`build_constraints_chain()` **一个参数都没传** ⇒ 阈值与冷却在生产**写死为类默认**；
`configuration/` 无 `constraints` 段，`config show/set`、env、CLI flag 三条通道都够不着它。
运维要调（评测期把阈值压到 2、线上把冷却拉长）**只能改代码**。

## What Changes

- `src/core/configuration/manager.py`
  - `_CONFIG_SPECS` 增两项：`constraints.failure_threshold`（缺省 5）与
    `constraints.cooldown_s`（缺省 30.0）—— 经 `ConfigSpec` 单一真源，CLI flag
    `--constraints.failure-threshold` / `--constraints.cooldown-s`、env
    `CORE_CONSTRAINTS_FAILURE_THRESHOLD` / `CORE_CONSTRAINTS_COOLDOWN_S`、yaml
    `constraints:` 段、「未知配置段」白名单**四者自动获得**（均由 `config_specs()` 派生）。
  - 新增访问器 `circuit_breaker() -> tuple[int, float]`（缺省 `(5, 30.0)`），
    沿用 `permission_mode()` 的「寄居 `extra` + 访问器」先例。
  - `validate_schema` 增校验：阈值须为 **≥1 的整数**、冷却须为 **≥0 的数值**，
    拒 `bool` 与非数值字面量；非法取值**阻断启动**并给出可读错误。
- `src/core/runtime.py`：`build_constraints_chain(failure_threshold=..., cooldown_s=...)`
  从配置取值（主 loop 与子 agent loop 仍共享**同一**链）。
- `tests/test_constraints_config.py`（新）：缺省 / yaml 覆盖 / env 覆盖 yaml / CLI 覆盖 env /
  非法取值阻断 / `constraints:` 段不致「未知配置段」告警 / 组合根注入 /
  **端到端**（阈值为 2 时第 3 次调用即 `CIRCUIT_OPEN` 短路）。
- 文档：`doc/03-interfaces/constraints-interface.md`（构造面记配置路径）、
  `doc/03-interfaces/configuration-interface.md`（段与访问器）、
  `doc/02-modules/constraints.md`、`doc/01-architecture/adr.md`（ADR-0066 + 映射表行）、
  `doc/04-testing/test-cases.md`（用例号）。

## 规格 delta

`constraints` spec「容错中间件」**MODIFIED**：正文增「阈值与冷却 SHALL 可经配置覆盖
（约束键 / 缺省值 / ConfigSpec 单一真源 / 校验期拒绝非法取值）」；新增两个场景
（阈值与冷却可经配置覆盖 / 非法取值校验期拒绝并阻断启动）。

`configuration` spec **不改**：段与键是 `ConfigSpec` 的**新实例**，「配置项以 ConfigSpec 为单一真源」
「取值受所属能力规格约束的配置项 SHALL 在校验期拒绝非法取值」两条既有 Requirement 已完整覆盖，
新增段经 `map_to` 前缀**自动**进已知段白名单（E18 的单一真源设计）。

## 明确不在本变更内（仍记账）

- **B5** `permission.sandbox.host_allowlist`（同族配置化，属 mcp/permission 面，另记）；
- 重试 / 降级 / 回滚的配置化（规格未细列；`Fallback` 无生产 `fallback_fn`，见 E1 关闭注）；
- 半开试探次数、成功率窗口等更细粒度参数（无需求，YAGNI）。
