# Tasks

## 1. M1 — plugin-registry 统一安装抽象（P0，本 Phase）

- [ ] 1.1 `InstallableAsset`（kind/source/manifest/lifecycle）+ `PluginSource` 枚举（local-path/git-repo/market-registry/mcp-endpoint）
- [ ] 1.2 生命周期 discover → verify → install → register → activate → deactivate → uninstall
- [ ] 1.3 错误码 SOURCE_NOT_FOUND / SIGNATURE_INVALID / INSTALL_FAILED
- [ ] 1.4 skillhub 签名校验/多源路由语义上提为 registry 层可复用原语

## 2. M2 — mcp 安装/移除（P0，本 Phase）

- [ ] 2.1 `mcp add(source)` 复用 PluginSource(mcp-endpoint)，安装后进入现有连接管理
- [ ] 2.2 `mcp remove(name)` 释放连接资源
- [ ] 2.3 add 走 discover→verify→install→register；remove 走 deactivate→uninstall

## 3. M3 — tool-use 插件安装工具（契约层，代码随 Phase 3）

- [ ] 3.1 install / uninstall / list 三工具定义
- [ ] 3.2 经 SafetyGate + 权限审批流约束（危险操作走审批）
