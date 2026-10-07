# 0162 · 任务清单

> **编号说明**：本 change 原排 `0161`，与当日**已归档**的 `2026-10-07-0161-ui-optional-web-test-guard`
> 撞号 ⇒ 本 change 改号 **`0162`**，计划中的 TUI 只读命令族顺延 `0163`、hooks 架构设计顺延 `0164`
> （ADR 编号 `0153`/`0154`/`0155` 与台账 `E100`/`E101` 序列**不受影响**）。

## 1. 规格与决策（先行）

- [x] 1.1 `specs/cli-ops/spec.md` **ADDED** Requirement「自检诊断（`doctor`）与运行状态（`status`）」+ 4 Scenario
- [x] 1.2 **ADR-0153**（只读诊断源：独立包 / 依赖注入 / 复用 `ValidationResult` / 单一产出多消费面 /
      退出码语义变更 / 密钥面口径 / 不动 dispatcher）+ 变更追踪行
- [x] 1.3 `openspec validate 2026-10-07-0162-doctor-status-diagnostics` ⇒ valid

## 2. 测试先行（红）

- [x] 2.1 新建 `tests/test_diagnostics.py`：`render` 字形与 `Report.ok` 口径（无 fail 即真）
- [x] 2.2 同上：全绿场景（配置可读 + 引用可解析 + 目录可写 + 各注册表可读）⇒ 全部 `ok`
- [x] 2.3 同上：注入失败 —— 引用**不可解析** ⇒ 该项 `fail` 且 `Report.ok is False`；配置缺失 ⇒ `fail` 而不抛
- [x] 2.4 同上：**密钥零泄漏** —— 注入独特值（`sk-DIAG-CANARY`）后，`doctor` / `status` / `/config` 视图
      的**每一行**逐字不含该值；`/mcp` 视图逐字不含 `EndpointRecord.args`（含 `--token` 形态）
- [x] 2.5 同上：`collect_status` 概览含会话数 / 内置工具数 / 已安装资产数 / MCP 端点数 / 模型标识 / 循环预算
- [x] 2.6 `tests/test_entry.py`：`main(["--config", cfg, "doctor"])` 全绿 ⇒ `0`；引用不可解析 ⇒ **非零**；
      `main([..., "status"])` ⇒ `0` 且输出逐字不含密钥值
- [x] 2.7 `tests/test_architecture.py`：`diagnostics` 入 `EXPECTED_PACKAGES` / `CAPABILITY_MODULES`
      （底座模块反向依赖 ⇒ 红；包可导入 ⇒ 绿）
- [x] 2.8 同上：**包边界红线** `test_diagnostics_never_imports_runtime_or_ui`（AST 扫 import 节点）

## 3. 实现（绿）

- [x] 3.1 新建 `src/core/diagnostics/{__init__,models,deps,checks,views}.py`
      （`Check`/`Report`/`render` + `Deps` 依赖注入 + `collect_doctor`/`collect_status` + 列表视图）
- [x] 3.2 `ConfigManager.is_resolvable(ref) -> bool`（`_resolvable` 的**公开**薄封装：跨包不调私有名）
- [x] 3.3 `src/core/tools/builtin.py` 增 `builtin_tools()` 单一真源；`runtime.py` 改用它（行为逐字不变）
- [x] 3.4 `src/core/entry.py`：`_state_dir()` / `_diag_deps(args)` / `_doctor(args)` / `_status(args)`；
      `_HANDLERS` 的 `doctor` / `status` 改指新 handler；`_ops` 只留 `start/stop/restart`
- [x] ~~3.5 `_build_ui` 传入 `diagnostics=_diag_deps(args)`~~ **撤销** —— `UIAPILayer.__init__` 尚无该形参，
      本 change 加进去即为**无人消费的死接线**（投机代码）。改由 change `0163`（TUI 只读命令族）
      与 `UIAPILayer` 的 `diagnostics` 形参**一并**落地。

## 4. 文档

- [x] 4.1 `doc/03-interfaces/cli-ops-interface.md` 补 §5「只读诊断面」
- [x] 4.2 `doc/03-interfaces/configuration-interface.md` §2 补 `is_resolvable`
- [x] 4.3 `doc/03-interfaces/tool-use-interface.md` §3 补 `builtin_tools()`
- [x] 4.4 `doc/04-testing/test-cases.md` 增 `## 76.`（TC-DIAG）
- [x] 4.5 `coding-plan/known-risk.md` §1 增 **E100**（桩已收口；`kill/logs/version/help/install/uninstall/
      list/info/auth/permission-mode/gateway` 仍未注册 ⇒ 该行**挂**）+ §3 ADR-0153 局限行

## 5. 收口

- [ ] 5.1 四门禁：`ruff check` / `ruff format --check` / `pyright`（0/0/0）/ `pytest -q`
- [ ] 5.2 手工归档（本仓 `openspec archive` 必失败）：delta 合进 `specs/cli-ops/spec.md` ⇒ `mv` 至
      `changes/archive/2026-10-07-0162-doctor-status-diagnostics/` ⇒ `openspec validate --all`
- [ ] 5.3 台账 + 记忆（`MEMORY.md` / `coding-plan-leftover-walkthrough.md`）
- [ ] 5.4 单次提交 `feat(cli-ops): doctor/status 真诊断（只读诊断源）`

## 与计划的有意偏离（记录）

- **编号**：`0161` → **`0162`**（撞已归档的 `2026-10-07-0161-ui-optional-web-test-guard`，详见文首说明）。
- 计划把 CLI 退出码用例放 `tests/test_cli_ops.py`；实际放 **`tests/test_entry.py`** ——
  `test_cli_ops.py` 的文章范围是 `CLICommandDispatcher`（本 change **不碰** dispatcher），
  `_doctor` / `_status` 是 entry 的 handler，归 entry 测试更合章法。
- 计划的 `Deps` 列了 `serve` / `memory` / `transcript`；实际**不注入** —— 规格要求的六项概览
  （会话数 / 内置工具数 / 已安装资产数 / MCP 端点数 / 模型标识 / 循环预算）无一项取自它们，
  注入即无人消费的死字段。
- 计划的 `Deps.sessions` 为句柄对象；实际为**可调用**（`Callable[[], list[dict[str, object]]]`）——
  诊断包因此**零 `core.ui` 引用**（`ui` 反向引用它，避免环）。
- 原生「工具数」改为「**内置工具数**」：CLI 面不装配 runtime（装配需要有效配置，恰是诊断要绕开的），
  只注册 `core.tools.builtin_tools()`；TUI 面（`0163`）注入 `runtime.tools` 时即为**全量**工具面。
- **`tests/test_serve.py` 的 ruff 红基线不在本 change 面**（承 commit `9abf30e` 的守卫前置：其后 import 未标
  `noqa: E402` + 尾部重复守卫）⇒ 已在**独立提交** `fix(tests): test_serve 导入守卫漏标 noqa（承 0161）` 修复，
  使本 change 的四门禁自**干净基线**起跑。
