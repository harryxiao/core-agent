# CORE-Harness 架构微调计划
## 补齐 CLI 命令集 / 启动参数映射 / 三方插件统一安装

> **销账状态（2026-10-04 走查）**：M1/M3/M4/M5/M6 微调点**均已由后续 Phase 补齐**（`plugin_registry/installable.py` / `tools/install_tools.py` / `entry.py` 子命令 / `runtime.py` config.permission_mode）；**仅 M2 的 mcp 安装-移除生命周期**仍随 Phase 12 DEFERRED —— 见 `phase-19.md` B1 与 G 类。
>
> 配套 `architecture-audit.md`。本计划只描述**微调点**，不直接改 spec/ADR/interface，
> 落成 openspec change 时按 openspec_sop 走 delta 双写 + ADR 追加。

---

## 0. 微调原则

1. **不新增分层**：保持 L0-L5 + 横切，通过「新增 1 个横切能力 + 扩展 L0 来源抽象 + 补参数映射模型」实现
2. **最小侵入**：skillhub 保持 skill 专属语义（4 Requirement 不动），其"签名校验/多源路由"**语义上提到统一层复用**，避免"泛化 skillhub"的大改
3. **单一真源**：ConfigSpec 驱动 CLI/yml/env 三层生成，保证"一一对应"不漂移
4. **对齐现有风格**：spec 双格式（原文+机器可读）+ interface 骨架 + ADR 追加 + delta 双写

---

## 1. 微调点清单

### M1｜L0 plugin-registry 增加 PluginSource + InstallableAsset 统一抽象
- 改哪：`openspec/specs/plugin-registry/spec.md` 新增 Requirement「插件来源与安装」
- 内容：
  - `InstallableAsset{ kind: skill|mcp|cli, source, manifest, lifecycle }`
  - `PluginSource = local-path | git-repo | market-registry | mcp-endpoint`
  - 生命周期：`discover → verify(签名) → install → register → activate → deactivate → uninstall`
- 复用：skillhub 的"签名校验 / 多源路由"语义上提到此统一层

### M2｜横切 mcp 补"安装/移除"生命周期
- 改哪：`openspec/specs/mcp/spec.md` 追加 Requirement「MCP Server 安装与移除」
- 内容：`mcp add/remove` 复用 PluginSource（mcp-endpoint），install 后进入现有"连接管理"

### M3｜L1 tool-use 增加 install/uninstall 工具（AI 对话安装通道）
- 改哪：`openspec/specs/tool-use/spec.md` 追加 Requirement「插件安装工具」
- 内容：`install / uninstall / list` 三工具，经 SafetyGate + 权限审批流约束（危险操作走审批）

### M4｜新增横切能力 cli-ops（CLI 命令集 + 启动参数映射）
- 改哪：新建 `openspec/specs/cli-ops/spec.md`（第 26 spec）+ `03-interfaces/cli-ops-interface.md`
- 命令集（分组）：
  - 生命周期：start / stop / restart / kill
  - 状态：status / doctor / logs / version / help
  - 资产：install / uninstall / list / info
  - 连接：mcp add / mcp remove / mcp list
  - 安全：auth / permission-mode
  - 网关：gateway
- 参数映射模型：优先级链 `CLI flag > env > config.yaml > 默认值`；
  `--foo.bar=value ↔ config.foo.bar ↔ CORE_AGENT_FOO_BAR`

### M5｜configuration 增加 CLI 参数覆盖层 + ConfigSpec 单一真源
- 改哪：`openspec/specs/configuration/spec.md` 扩展 Requirement「配置源与分层」
- 内容：新增 CLI 覆盖层（最高优先级）；ConfigSpec 每项声明 `cli_flag / env_var / default / map_to`

### M6｜permission 增加 permission-mode 启动开关
- 改哪：`openspec/specs/permission/spec.md` 追加 Requirement「权限模式」
- 内容：`read-only / interactive / auto-approve / high-risk-block`，映射 `config.permission.mode`，CLI `--permission-mode`

---

## 2. 建议 change 拆分

| change | 包含 | 对应维度 |
|---|---|---|
| **0028-plugin-install** | M1 + M2 + M3 | 维度 A（三方插件统一安装） |
| **0029-cli-ops** | M4 + M5 + M6 | 维度 B/C（命令面 + 参数映射） |

> 推荐拆 2 个：资产安装 与 运维命令面 边界清晰，可独立落地、独立验证。

---

## 3. 影响面

- **specs**：plugin-registry(+1) / mcp(+1) / tool-use(+1) / cli-ops(新) / configuration(扩) / permission(+1)
- **interface**：cli-ops-interface.md（新）
- **ADR**：追加 ADR-0037、ADR-0038
- **architecture-overview**：组件表 + 目录树 +（若 cli-ops 计为横切，横切 5→6）
- **requirements**：1.x 清单追加
- **design-completeness-eval**：模块数字口径 25→26

---

## 4. 决策点（已拍板）

- **D1**：拆 **2 个** change —— `0028-plugin-install`（M1+M2+M3）/ `0029-cli-ops`（M4+M5+M6）
- **D2**：cli-ops 作为「**新增横切能力**」—— 横切 5→6，**不并入 ui**
- **D3**：skillhub 语义上提为 plugin-registry 统一抽象 —— registry 层统一（`InstallableAsset{kind}`）+ 执行层按 kind 适配，不合并执行实现
- **D4**：permission-mode **四档先落地** —— dangerous-permission 走配置层 spec（危险 action 声明 risk），CLI 侧暂不加专用 flag
- **D5**：参数映射「**全量声明 + 暴露面分级**」—— ConfigSpec 每项声明 `cli_flag/env_var/default/map_to`；CLI 暴露面按 core/advanced/hidden 分级
