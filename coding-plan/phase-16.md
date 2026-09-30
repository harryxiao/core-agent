# Phase 16 — 插件/工具链路缺口补齐（CLI 执行入口 + 插件安装接线 + coeffect Resolver 接线）

> 里程碑：**M9 修复补丁**（不新增里程碑，修复 Phase 13 装配后暴露的三处链路断裂）
> 位置：横切 `plugin_registry`（installable / coeffect_resolver）× `tools`（builtin / provider）× `runtime`（组合根）
> 上游：Phase 0–13 已落地；本 Phase 仅接线修复，不新增 capability、不新增三方依赖

---

## 1. 范围与定位

Phase 13 组合根装配后，外部插件（skill / mcp / cli）与内置文件工具的链路存在三处断裂，导致：

- **CLI 类插件**有定义、无执行通道（安装后无法被调用）；
- **插件安装**的 resolve/install 两钩子是空壳，未按 kind 分发到真实执行层；
- **内置 file_read / file_write / file_patch** 在 `resolve(coeffects)` 阶段被空壳 `CoeffectResolver` 拦下，`COEFFECT_MISSING` 全部不可用（最严重，直接瘫痪文件读写闭环）。

本 Phase 补三处接线，使「外部插件安装 → 按 kind 分发 → 可被 ToolProvider 调用」与「内置文件工具 → coeffect 来源可解析 → 可执行」两条链路贯通。不引入新抽象层，复用已有 `SkillLibrary` / `MCPToolAdapter` / `CoeffectResolver` 的既有接口。

---

## 2. 契约红线（实证现状 vs 契约）

### 2.1 已就绪契约（无需重造）

| 契约 | 实证落点 | 结论 |
|---|---|---|
| 插件三元种类枚举 | `src/core/plugin_registry/installable.py` `PluginKind = SKILL/MCP/CLI` | 已就绪，勿改枚举 |
| skill 注册入口 | `src/core/skills/library.py:30` `SkillLibrary.register(skill)` | 已就绪 |
| mcp 工具适配层 | `src/core/mcp/adapter.py:17` `MCPToolAdapter` → `ToolProvider.call_tool` | 已就绪 |
| 工具统一执行门 | `src/core/tools/provider.py` `ainvoke`（validate → resolve → gate.confirm → call） | 已就绪 |
| coeffect 解析器 | `src/core/plugin_registry/coeffect_resolver.py` `resolve` / `register` / `resolve_secret` | 接口已就绪，但从未注入来源（见 2.2-③） |

### 2.2 契约缺口（本 Phase 补齐）

**① CLI 插件执行入口缺失**

- 现状：`PluginKind.CLI` 仅在 `installable.py` 枚举定义，全项目无任何消费点（`subprocess` 仅存在于 `permission/sandbox.py` 终端沙箱与 `git/backend.py` git 后端，与插件执行无关）。
- 对照：skill → `SkillLibrary.register`；mcp → `MCPToolAdapter` + `ToolProvider.call_tool`；**cli → 无适配层**。
- 补齐：新增 CLI 插件适配层（如 `src/core/plugins/cli_adapter.py`），把 CLI 插件包装为 `Tool`，handler 走 subprocess 真进程执行（对齐 `sandbox.py` 的 subprocess 后端模式），产出结构化 `ToolResult`，错误不向调用方抛裸异常。

**② 插件安装接线（resolve/install 空壳）**

- 现状：`installable.py` 中 `_default_resolve` 直接抛 `SOURCE_NOT_FOUND`，`_default_install` 无副作用 `return None`；`PluginInstaller.__init__` 以 `source_resolver or _default_resolve`、`installer or _default_install` 注入。
- 结果：真实安装从未发生——`discover` 拿不到 `InstallableAsset`，`install` 不落任何东西。
- 补齐：执行层按 `PluginKind` 分发真实 installer/resolver：skill → `SkillLibrary.register`；mcp → MCP 客户端注册；cli → CLI 适配器注册。组合根注入真实实现，替换空壳默认值。

**③ coeffect Resolver 空壳（最严重，直接瘫痪内置文件工具）**

- 现状：`builtin.py` 声明 `file_read` coeffects=`["filesystem:read"]`（L62）、`file_write`（L90）/ `file_patch`（L119）coeffects=`["filesystem:write"]`；但 `provider.py:57` `self._resolver = coeffect_resolver if coeffect_resolver is not None else CoeffectResolver()`（默认空）；`provider.py:107` `self._resolver.resolve(coeffects)` 遇缺失即抛 `CoeffectMissing` → 返回 `COEFFECT_MISSING`。
- 结果：`runtime.py:87` `tools = ToolProvider(gate=guard)` **只传 gate，未传 coeffect_resolver，也未向任何 resolver register coeffect 来源** → 内置三个文件工具在 resolve 阶段全部被拦下。
- 补齐：组合根构造并注册 coeffect 来源（至少 `filesystem:read` / `filesystem:write`），经 `ToolProvider(coeffect_resolver=...)` 注入；必要时复用 `ConfigurationManager` 的 keychain 作为密钥来源。

---

## 3. 验收口径（M9 修复补丁）

- **CLI 执行**：一个 CLI 插件经安装后出现在 `ToolProvider` 工具表中，`ainvoke` 能真实起进程并返回结构化结果；错误码承载，无裸异常上抛。
- **安装分发**：`PluginInstaller.discover/install` 按 `PluginKind` 命中真实实现（skill 进 `SkillLibrary`、mcp 进 MCP 注册、cli 进 CLI 适配器），`_default_install` 空壳不再被组合根使用。
- **coeffect 贯通**：`core-agent run --prompt "读 xxx"` 走 file_read 真实链路，`resolve(coeffects)` 返回非空 `ResolvedContext`，不再抛 `COEFFECT_MISSING`；`file_write` / `file_patch` 同理可执行。
- **无回归**：`gate.confirm` 权限门仍先于执行；密钥仍经 `resolve_secret` 明文仅用于构造，不落日志/记忆/轨迹。

---

## 4. 首步任务（开工前）

1. **读接口原文**：`plugin_registry/installable.py`、`coeffect_resolver.py`、`tools/provider.py`、`tools/builtin.py`、`skills/library.py`、`mcp/adapter.py` 的构造签名与调用面为唯一真源，不复述重造。
2. **定 CLI 适配层边界**：`CLIAdapter` 如何把 `InstallableAsset`（含 command/args）包装为 `ToolDef` + handler；subprocess 超时/退出码如何映射 `ToolErrorCode`（复用 `sandbox.py` 的 timeout 处理模式）。
3. **定安装分发点**：真实 installer/resolver 由组合根注入 `PluginInstaller`；按 kind 分发的映射表单点维护，不散落各处。
4. **定 coeffect 来源**：`CoeffectResolver.register(source)` 的 source 形态（键 → 值映射），组合根注册 `filesystem:read/write`；确认 `resolve` 的 `missing` 判定逻辑后补来源即可，不改 `resolve` 本体。

---

## 5. 依赖与顺序

```
installable.py(PluginKind) ──┐
skills.library / mcp.adapter ─┼─► 安装分发(真实 installer/resolver) ─► PluginInstaller ─► 组合根注入
CLI 适配层(新增) ─────────────┤
builtin.py(coeffects 声明) ───┼─► CoeffectResolver.register(filesystem:read/write) ─► ToolProvider(coeffect_resolver=...) 
```

- **硬依赖**：`SkillLibrary.register`、`MCPToolAdapter`、`CoeffectResolver.register/resolve` 接口已就绪；本 Phase 零新增三方依赖。
- **顺序**：③ coeffect 接线（打通内置工具，修复面最大）→ ② 安装分发（真实 installer/resolver 注入）→ ① CLI 适配层（依赖安装分发就绪后收口）。
- **并行**：③ 与 ② 可并行；① 依赖 ② 的按 kind 分发表定型后接入。

---

## 6. 里程碑验收清单

- [x] 组合根向 `ToolProvider` 注入已注册 `filesystem:read/write` 的 `CoeffectResolver`，内置三文件工具可执行
- [x] `PluginInstaller` 由组合根注入真实 resolver/installer，按 `PluginKind` 分发，空壳默认值不再生效
- [x] CLI 插件适配层落地，CLI 插件可安装、可被 `ToolProvider.ainvoke` 真实调用
- [x] `resolve(coeffects)` / 插件安装 / CLI 执行三条链路各有一条真实断言测试通过

---

## 7. 测试要点

- **coeffect 贯通测试**：构造已注册 `filesystem:read/write` 的 resolver → `ToolProvider.ainvoke(file_read)` 断言 `ok=True`、`ResolvedContext` 非空；未注册来源时断言返回 `COEFFECT_MISSING`（保留空壳行为语义）。
- **安装分发测试**：`discover`（fake source）按 SKILL/MCP/CLI 分别断言命中 `SkillLibrary.register` / MCP 注册 / CLI 适配器注册；`install` 断言 `InstallableAsset` 落表。
- **CLI 执行测试**：fake command（如 `echo`）断言 `ToolResult` 结构化承载 stdout/退出码；非零退出码 → 错误码承载，不抛裸异常。
- **门控回归**：`gate.confirm` 仍先于执行；`confirm/deny` 分支语义不变。

---

## 8. 提交规范

- 单次提交：`fix(plugin-tool-chain): 补齐 CLI 执行入口 / 插件安装分发 / coeffect 来源接线`
- 变更范围：`src/core/plugin_registry/`、`src/core/tools/`、`src/core/runtime.py`、新增 CLI 适配层文件；测试同步。
- 提交前 `ruff` 全绿；不触碰 `_default_install` 空壳的公开语义（保留 fallback，仅组合根不再依赖它）。
