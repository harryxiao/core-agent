# Proposal 0207 — 恢复扫描入口全覆盖（缺省生效）

## 为什么

`0191` 立了「启动扫描未完成任务并呈现」的能力（`_surface_incomplete`，`entry.py:436-448`），
但**只接了两个入口**：`serve`（`:507`）与 `task` fresh（`:1766`）。**REPL / `run` / `app` /
`mcp serve` 四个入口启动时静默**——用户从 REPL 或桌面壳（`app`）进入时，看不到「上次有任务没
跑完」。这正是六能力走查中「重启恢复」一项的**硬伤②**：能力在，接线不全。

`_build_ui` 早已有 `surface_recovery` 旗（`:452/:469-470`）⇒ 三个走 `_build_ui` 的入口
（repl/run/app）**一旗即成**；`mcp serve` 自建 runtime（`:770-775`）⇒ 显式补一次调用。

## 做什么

- `repl`（`:499`）/ `run`（`:1687`）/ `app`（`:523`）三处 `_build_ui(..., surface_recovery=True)`。
- `mcp serve`（`:775` 后）显式 `_surface_incomplete(runtime)`——**只打 stderr**（stdio transport 的
  stdout 是协议流，呈现 SHALL NOT 污染之）。
- **仍不自动重执行**（守 P2 / `durability/spec.md:23` 纯扫描语义）：只告警 + 提示 `task --resume`。

## 规格影响

`durability` **MODIFIED**「崩溃恢复」—— narrative 补「全部交互入口」句 + **ADD** Scenario
「全部交互入口启动扫描呈现」（全量替换该 Requirement，其余 7 Scenario 逐字保留）。
canonical req **4 → 4**（MODIFIED 不增 Requirement）、scen **13 → 14（+1）**。其余 3 条
Requirement 逐字保留。

## 风险

- **stderr 噪音**：无未完成任务时 `_surface_incomplete` 立即返回（`if not handles: return`）⇒
  正常启动零输出。有未完成任务才告警。
- **mcp serve 的 stdout**：呈现走 stderr，协议流不受影响（既有 `print(..., file=sys.stderr)` 口径）。
- **重复呈现**：`task --resume` 路径（`:1766`）与新增入口互不叠加（`task` 是独立子命令，不走
  repl/run/app 的 `_build_ui`）——无双重输出。
