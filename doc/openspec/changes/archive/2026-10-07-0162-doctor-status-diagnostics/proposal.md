# 0162 · `doctor` / `status` 真诊断（只读诊断源）

## Why

**规格已承诺、实现没追上**：`cli-ops` 规格的「运维命令集」→ Scenario「状态查询命令」明写
`status` / `doctor` **返回运行状态 / 健康诊断**（`doc/openspec/specs/cli-ops/spec.md:20`）；
而实现是**桩** —— `src/core/cli_ops/dispatcher.py:87-93` 对 `status` / `doctor` 一律 `return "ok"`，
`src/core/entry.py:498-504` 的 `_ops` 直接 `print`。今天 `core-agent doctor` 对**任何**环境都打印 `ok`，
既无诊断价值，也无法作为脚本的退出码判据。

用户 2026-10-07 的诉求（TUI `/` 浮层要能看到并执行 `doctor` / `status` 等只读命令）**以本 change 为数据底座**：
浮层命令要落真东西，先得有一份**只读、可复用、零副作用**的诊断源。

## What Changes

- **新建只读诊断包 `src/core/diagnostics/`**：`Check` / `Report` / `render`（纯数据 + 纯渲染）+ `Deps`
  （**依赖注入**的全部只读句柄）+ `collect_doctor` / `collect_status` + 列表视图
  （sessions / config / mcp / skills / notes）。
- **`Deps` 只由调用方构造**：包内**不猜路径**、**不 import `core.runtime` / `core.ui` / `core.entry`**
  （`test_architecture.py::test_runtime_is_sole_composition_root` 是硬红线）。
- **CLI 接上真实现**：新增 `_diag_deps(args)` / `_doctor(args)` / `_status(args)`；
  `_HANDLERS` 的 `doctor` / `status` 改指新 handler；`_ops` 只留 `start/stop/restart`。
  `doctor` **有失败项 ⇒ 退出码 1**；`status` 恒 0。
- **复用既有形状**：配置检查复用 `ConfigManager.validate_schema` → `ValidationResult`
  （`configuration/models.py:87-93`），**不发明**第二套校验。
- **安全**：诊断输出 **SHALL NOT 含任何密钥值**；只呈现 `${VAR}` 引用名与「可解析 / 不可解析」
  （经 `ConfigManager._resolvable`，`manager.py:402` —— 只返回 bool）。

## Non-goals

- **不实现**其余未注册的运维动词（`kill` / `logs` / `version` / `help` / `install` / `uninstall` / `list` /
  `info` / `auth` / `permission-mode` / `gateway`）—— 记入台账遗留（E100）。
- **不改不删** `cli_ops/dispatcher.py` 与 `cli-ops-interface.md`：其 `status()` 的 `"ok"` 分支自此不再被
  CLI 触达，但它与 `tests/test_cli_ops.py` 仍是既有面（动它属越界）。
- **不做 TUI 命令**（浮层接入属 change `0162`）；**不做** Web / Desktop 面。
- **不引三方库**；**不建**常驻进程、**不建**外部连接（只读诊断）。

## 风险

1. **诊断面误读密钥**：任何「把配置打印出来看看」的实现都极易带出明文密钥 ⇒ 诊断项**只**经
   `_resolvable(ref) -> bool` 与引用名呈现；`/mcp` 视图**不打印 `EndpointRecord.args`**
   （`mcp/endpoints.py:53-65`，其 `args` 可能含 `--token` 形态）。有专门测试断言输出**逐字不含**注入值。
2. **配置缺失时的崩溃**：`ConfigManager.load()` 在 LLM 段缺失时抛 `ConfigurationError` ⇒ 诊断
   **必须把它落成一条 `fail` 项**而不是向上抛（`doctor` 的职责正是报告「不可用」）。
3. **退出码语义变更**：`core-agent doctor` 从「恒 0」变为「有失败项即 1」—— 若既有脚本依赖恒 0，
   会被影响。这是**规格要求**的行为（诊断要有判据），在 ADR 明示为**有意**变更。
4. **红线**：新包不得 import `core.runtime`（否则 `test_runtime_is_sole_composition_root` 红）；
   不得被 `plugin_registry` / `configuration` / `observability` / `core_profile` 反向依赖。
