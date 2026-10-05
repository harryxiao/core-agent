# tasks — 插件安装链路「工具面闭环」（change 0108 / E33 + E34 + E35）

## 1. 规格（先行）
- [x] 1.1 **规格中性**：`tool-use`（`:91` 三工具）/ `plugin-registry`（`:58` 七步链）/
      `mcp`（`:104` 默认暴露面）均已要求本 Phase 变更的内容 ⇒ 无 spec delta，`.openspec.yaml`
      置 `schema: spec-driven` + `skip_specs: true`
- [x] 1.2 复核：不新增 / 不修改任何 Requirement，仅实现回归契约

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_install_tools.py`：组合根装配后 `tools.install` / `uninstall` / `list`
      三 id 在 `runtime.tools.active_tools()`（**E33 生产可达**）
- [x] 2.2 同文件：注册进组合根的 install 工具与 `Runtime.installer` **同一实例**（调用工具
      handler 后 `runtime.installer.installed()` 反映该次安装）
- [x] 2.3 同文件：`Runtime.installer` 能**对称卸载** cli 资产（`cli.<name>` 真从 `runtime.tools`
      摘除）—— 证明 `uninstaller` 已接
- [x] 2.4 `tests/test_phase16.py`：`CLIAdapter.adapt` 产出工具 `coeffects == ["process:spawn"]`，
      且**不进** MCP 默认暴露面（**E34**）
- [x] 2.5 `tests/test_entry.py`：CLI `plugin install` 走完整生命周期（`verify` 与 `activate`
      均被调用，顺序正确）—— **E35**
- [x] 2.6 `tests/test_phase13.py`：组合根工具 id 精确集合断言补入三个安装工具（既有断言编码的是旧现实）
- [x] 2.7 运行确认**红**（新增用例失败、其余全绿）

## 3. 实现
- [x] 3.1 `cli_adapter.py:75`：`coeffects=[]` → `["process:spawn"]`（+ import 注释对齐）
- [x] 3.2 `runtime.py:464`：`PluginInstaller(..., uninstaller=dispatcher.uninstall)`；
      其后注册三工具（`install_tool(installer)` / `uninstall_tool(installer)` / `list_tool(installer)`），
      **须排在 installer 构造之后**
- [x] 3.3 `runtime.py`：`from core.tools import (...)` 补三个工厂名
- [x] 3.4 `entry.py:_plugin_install`：`install` 前补 `installer.verify(item, signature)`、
      `register` 后补 `installer.activate(plugin_id)`
- [x] 3.5 四门全绿（直连二进制，不用 `uv run`）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/tool-use-interface.md` §3：补三工具行 + 生产工具面注册口径
      （该节为示例清单；`plugin-registry-interface.md` 无工具面清单，未改）
- [x] 4.2 `doc/01-architecture/adr.md`：**ADR-0101**（插件安装链路工具面闭环：三工具接线 +
      `cli.*` 声明补正 + CLI 全生命周期；含「接线 E33 会让 E34 变活」的耦合说明）+ 末尾映射表行
- [x] 4.3 `doc/04-testing/test-cases.md`：补相应用例登记

## 5. 收口
- [x] 5.1 手工归档（无 delta ⇒ 直接 `shutil.move` 进
      `doc/openspec/changes/archive/2026-10-05-0108-plugin-install-tool-face-wiring/`；tick tasks）
- [x] 5.2 `openspec validate --all` 全绿
- [x] 5.3 账本回填（`phase-25.md` §0 现状列 + §3 验收勾选 + §6 收口；`README.md` §2 第 25 行状态列）
- [x] 5.4 记忆更新 + 提交（`feat(...)`，一个 Phase 一个 commit）
