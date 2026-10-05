# 提案 — 插件安装账本落盘（change 0109 / 账本 E36）

## 背景与缺陷

`coding-plan/phase-25.md` §1.4 记 E36：`plugin install --kind cli|mcp` 的安装结果**进程内即失**，
规格**无**持久化条款 ⇒ 当时判「未接线/取舍」、**规格先行**、单独立项（未随 change `0108` 动代码）。

一手复核后**比账本记载更宽**（`/tmp/e36` 实测，2026-10-05）：

| 操作（跨进程） | 实际 | 证据 |
|---|---|---|
| `plugin install --kind skill` | ✅ 写 `skills.json` | 状态目录出现该文件 |
| `plugin install --kind cli` | ✅ rc 0 但**不落任何文件** | 状态目录只有 `skills.json` |
| `plugin list` | ❌ 恒「（无已安装资产）」 | 账本 `PluginInstaller._assets` 是**进程内字典** |
| `plugin uninstall <id>` | ❌ 恒 `UNINSTALL_NOT_FOUND` | 同上 |

即缺口不限于 cli/mcp 的**物化**：**安装账本整体不落盘** ⇒ `list` / `uninstall` 对**所有** kind
都跨进程失效（skill 只是「物化」侥幸落进 `skills.json`，账本仍空）。

## 用户裁决（2026-10-05，AskUserQuestion）

1. **mcp 真源 = 委派**：新账本只记 skill / cli；`kind=mcp` 委派既有 `mcp-endpoints.json`
   （与 `mcp add` 同一真源）；`plugin list` 合并两视图。
2. **装配期 = 重建物化**：`build_runtime` 读回账本并经同一安装管线重建（否则 `list` 说「已安装」
   而运行时工具面没有 = 谎报，违背本仓反复钉的诚实口径）。

## 变更目标

让「已安装」成为**跨进程可证**的事实，且与运行时可见一致：

1. **账本落盘**：新 `$CORE_STATE_DIR/plugin-installs.json`（单文件 JSON、原子写、损坏降级告警、
   **状态非配置**）；形状照 `mcp-endpoints.json`（change `0074` / ADR-0071）。
2. **按 kind 路由的单一视图**：`PluginInstallStore` —— mcp → `mcp-endpoints.json`，其余 → 本账本；
   `records()` 合并两处 ⇒ `list` / `uninstall` / `installed()` 共用一份真源。
3. **写入点收在 `PluginInstaller`**：`register` → `store.put`，`uninstall` → `store.remove`，
   构造期从 store 水合 `_assets`。⇒ **CLI 与运行时（`tools.install`）两条入口自动一致**，
   不再有「CLI 装了、Agent 装了、只有一个跨进程可见」的分叉。
4. **装配期重建物化**：`build_runtime` 读回账本 → 逐条经 `InstallDispatcher` 重建（skill 注册 /
   cli 工具注册）；单条失败告警跳过（照 mcp 端点先例）。
5. **幂等卸载**：`InstallDispatcher._uninstall_skill` 容忍技能已不在（账本条目可能陈旧），
   使 `uninstall` 满足规格「卸载干净、无悬空引用」而非抛裸 `KeyError`。

## 不做（明示）

- **不**把 `mcp-endpoints.json` 并入本账本（用户选委派而非统一收敛；ADR-0071 设计保留）。
- **不**改 `mcp add` / `mcp list` / `mcp remove` 的 CLI 面语义（重名仍拒绝、仍先握手再落盘）。
- **不**新增 capability、不改 `PluginInstaller` 既有公开签名（只加可选 `store=`）。
