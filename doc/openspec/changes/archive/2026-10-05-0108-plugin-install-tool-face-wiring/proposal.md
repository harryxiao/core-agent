# proposal — 插件安装链路「工具面闭环」（change 0108 / 账本 E33 + E34 + E35）

## Why

`coding-plan/phase-25.md` §1 一手复核发现三处**接线不一致**（规格均已在位，实现未跟上）：

- **E33**：`tool-use` spec `:91` 明文要求系统提供 `install` / `uninstall` / `list` 三个插件安装
  工具，但 `runtime.py` 组合根只注册 5 个内置工具与 `tools.delegate`，**三工具从未接进生产工具面**
  ⇒ 规格承诺的对外能力在生产不可达。
- **E34**：`CLIAdapter.adapt` 产出的 `cli.*` 工具 `coeffects=[]`，而 handler 走 `subprocess.run`
  **真派生进程** ⇒ 声明不实，且空 coeffect 被 MCP 默认暴露面判据视为只读 ⇒ `cli.*` 工具**默认进
  对外暴露面**（与 change 0076「跨边界能力默认不出」的收窄意图相反）。
- **E35**：`entry._plugin_install` 只走 `discover → install → register`，**跳过 `verify` / `activate`**，
  而 `plugin-registry` spec `:58` 与 `installable` 声明的是七步链、同链路的 `tools.install` 走全链
  ⇒ 两条路径语义分叉。

主线（M4 自进化 / 基础工具面）未被阻塞，属**覆盖完整性**收敛。

## What Changes

- **E33**：组合根注册 `tools.install` / `tools.uninstall` / `tools.list`，与 `Runtime.installer`
  **同一实例**（否则装进一次性注册表 = 谎报）；并给 `Runtime.installer` 补上**对称的 `uninstaller`**
  （`dispatcher.uninstall`），否则 `tools.uninstall` 无法做 kind 分发的真实回退（skill 移除 / tool 摘除）。
- **E34**：`cli_adapter.py` 工具声明由 `coeffects=[]` 改为 `coeffects=["process:spawn"]`
  （对齐 `code_run` 规范拼写）；**只改声明、不改 handler 行为**，不顺带加 `filesystem:write`。
- **E35**：`entry._plugin_install` 在 `install` 前补 `verify`、在 `register` 后补 `activate`，
  与 `tools.install` 同链；**CLI 一次性进程仍适用**（`installable.activate` = `load` + `activate`，`StubPlugin` 两侧 no-op）。

## Impact

- 受影响 capability：`tool-use`、`plugin-registry`、`mcp`（默认暴露面口径的**事实**变化，契约不变）。
- **规格中性**：三条均为「实现回归既有契约」，无新增/修改 Requirement ⇒ `.openspec.yaml` 置
  `skip_specs: true`（同写 `schema`）。
- 行为变化：生产工具面新增 3 个只读/写类工具（`tools.list` 为只读，现按 `mcp/spec.md:114` 场景
  出现在 MCP 默认暴露面 —— 该场景此前只在测试夹具里成立，现于生产成立）；`cli.*` 工具
  不再默认对外暴露；CLI `plugin install` 走完整生命周期（今日 verifier 缺省恒真，故净效果是补齐链条）。
- 不影响：`tools.install` / `tools.uninstall` 的 `coeffects=["filesystem:write"]` + `reversible=False`
  不变 ⇒ 经 `SafetyGate` 仍走**写 + 不可逆**确认门（非交互入口 fail-closed）。
- **不做**：E36（`plugin install --kind cli|mcp` 持久化）—— 规格无持久化条款，须**规格先行**、
  单独立项。
