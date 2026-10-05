# tasks — 插件安装账本落盘（change 0109 / 账本 E36）

## 1. 规格（先行）
- [x] 1.1 `specs/plugin-registry/spec.md`：ADDED「插件安装持久化」（账本落盘 / 按 kind 路由单一视图 /
      装配期重建 / list·uninstall 真源 / 7 场景）
- [x] 1.2 `openspec validate 0109-plugin-install-persistence` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_plugin_installs.py`（新）：`PluginInstallRegistry` 往返 / 原子写中断不损坏 /
      损坏与残缺降级（`pytest.warns`）/ 同 id 覆盖
- [x] 2.2 同上：`PluginInstallStore` 按 kind 路由（mcp 落端点表、**不**进本账本）+ `records()` 合并视图
- [x] 2.3 同上：`PluginInstaller(store=…)` —— `register` 落盘 / `uninstall` 清条目 / 构造期水合
      （新实例 `installed()` 即见既有记录，且 `uninstall` 可用）
- [x] 2.4 `tests/test_entry.py` 追加：**CLI 端到端跨进程** —— `plugin install --kind cli` ⇒ 重开进程
      `plugin list` 命中 ⇒ `plugin uninstall` 成功且账本条目清除 ⇒ 再 `list` 为空
- [x] 2.5 `tests/test_entry.py` 追加：`plugin install --kind mcp` 委派（落 `mcp-endpoints.json`、
      本账本不含该条目、`plugin list` 合并显示）
- [x] 2.6 `tests/test_install_tools.py` 追加：装配期重建 —— 预置账本记录 ⇒ `build_runtime` 后
      `cli.*` 工具出现在生产工具面；坏记录告警跳过不阻断
- [x] 2.7 运行确认**红**（新增用例失败、既有用例全绿）

## 3. 实现
- [x] 3.1 `src/core/plugins/installs.py`（新）：`plugin_installs_path()` / `InstallRecord` /
      `PluginInstallRegistry` / `PluginInstallStore`（kind 路由 + 合并视图）
- [x] 3.2 `src/core/mcp/endpoints.py`：`MCPEndpointRegistry.put()`（upsert，供 store 路由；
      `add()` 的重名拒绝语义不变）
- [x] 3.3 `src/core/plugin_registry/installable.py`：`PluginInstaller(store=…)` —— `register` →
      `store.put`、`uninstall` → `store.remove`、构造期经 `store.records()` 水合 `_assets`
- [x] 3.4 `src/core/plugins/install.py`：`_uninstall_skill` 幂等（技能已不在不抛 `KeyError`）
- [x] 3.5 `src/core/plugins/__init__.py`：导出新符号
- [x] 3.6 `src/core/entry.py`：`_build_installer` 注入 store；`_plugin` 三入口走 store；
      `plugin install --kind mcp` 委派端点注册表（转 `EndpointRecord` → 与 `mcp add` 同一落盘链路）
- [x] 3.7 `src/core/runtime.py`：装配期读回账本 → 逐条 `dispatcher.install`，单条告警跳过

## 4. 文档
- [x] 4.1 `doc/01-architecture/adr.md`：**ADR-0102**（账本形状 / 为何按 kind 委派而不统一收敛 /
      为何写点收在 `PluginInstaller` / upsert 语义）+ 末尾映射表行
- [x] 4.2 `doc/03-interfaces/plugin-registry-interface.md` §8：账本与 store 口径
- [x] 4.3 `doc/04-testing/test-cases.md`：新增 TC-PLUGIN-07/08/09

## 5. 收尾
- [x] 5.1 门禁四件套全绿（`ruff check` / `ruff format --check` / `pyright` 0/0/0 / `pytest`）
- [x] 5.2 手工归档（delta 合进 `doc/openspec/specs/plugin-registry/spec.md`，`shutil.move` 进
      `doc/openspec/changes/archive/2026-10-05-0109-plugin-install-persistence/`）
- [x] 5.3 `openspec validate --all` 全绿
- [x] 5.4 账本回填（`phase-25.md` §0 现状列 + §3 验收 + §6 收口；`README.md` §2 第 25 行）
- [x] 5.5 记忆更新 + 单个 `feat(...)` commit
