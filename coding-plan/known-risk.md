# known-risk.md · 已知风险登记簿

> **用途**：把散落在各 Phase 文档、ADR「已知局限」、接口注释里的**已知风险 / 有意取舍 / 已知局限**
> 汇总成**单一、可持续登记**的表面，与「Phase 账本」（如 `phase-34.md`，已闭）**互补**：
> Phase 账本记**一次走查**的缺陷账；本簿记**长期**未闭项与**有意不做**的口径。
>
> **新缺陷立项口径**：本轮起，新发现的缺陷/风险在**本簿**取 `E<n>` 编号（续 Phase 34 的 `E87`，
> 故本簿首立 `E88`）**持续登记**；如需成批走查仍可另开 Phase 账本。**只汇总与转引**，不改各源
> 文档；每条**必须**带 `file:line` 或 ADR / change 号，避免二次失真。
>
> **与 `phase-34.md` 的关系**：`phase-34.md` §1~§2 的真缺陷（`E63`~`E87`）已**全闭**（20 change
> `0126`~`0145`）；本簿 §1 只收「**未闭**账」（含 `E27`/`E55`/`C7` 等 phase-34 §3 复述项），§2 搬
> phase-34 §4 的**有意取舍**，§3 收各 change/ADR 的**已知局限**。**不重复**记已闭项。

---

## §1 未闭账（outstanding）

> 现状：**能力已存在但生产不可达**，或**后端未接**。开工须先读「开工口径」——部分账**绑定**前置。

| 编号 | 领域 | 现状（`file:line`） | 开工口径 / 来源 |
|---|---|---|---|
| **E27** | IM 网关 | `IMGateway` 逻辑齐备但**零生产装配**（`src/core/im/gateway.py` 仅自身模块 + 单测 + 配置 spec 映射 + 接口文档；im 规格「分平台接入」要求真实平台 Provider：Telegram/飞书/企业微信…） | **必须与第一个真实 Provider 一并做** —— 单独落代码半（组合根装配 + `im serve`）= 一个「**可启动但永远收不到消息**」的**假入口**，生产上无人往里发消息、宿主侧无从验证。来源：`phase-19.md:104`（E27 行）、`phase-20.md:40-45`（开工口径段）。**前置**：真实平台凭证 + 联网 |
| **E55** | 主 loop | 主 loop **丢弃多余 `tool_call`**（单工具协议只取**首个**，其余静默丢） | `src/core/loop/planner.py:222-225`。与 `E62`（L3 前置，已销账）**同源不同层** ⇒ **保持待议**（是否支持多工具同轮需再裁决）。来源：`phase-34.md:65` |
| **C7** | UI / 语音 | **TTS 后端未接** —— `barge_in` 为**抽象能力**，语音输出无实现 | `doc/03-interfaces/ui-interface.md:19`（`barge_in` docstring：「语音输出为抽象能力（TTS 后端未接）」）。来源：`phase-34.md:66` |
| **—** | composition / distributed | **整包零生产接线** —— distributed 的 oauth2/mTLS/oidc 仅**字段声明**、多设备拓扑**无代码**；composition 于运行时**无生产消费方** | 来源：`phase-34.md:67`、`coding-plan/README.md` §2（标 ✅ 与事实不符，属**已知**）。**注**：composition 的**真内容哈希**口径已由 change `0143` 接通 CLI（见 §3），但**整包**接线仍未落 |
| **—** | evolution | **留出评测生产 runners 未接** ⇒ 候选**恒 `frozen`** | ADR-0112。来源：`phase-34.md:68` |
| **—** | ci-cd | `publisher` **发布通道 `CHANNEL_UNREACHABLE`**（无真实发布通道） | 来源：`phase-20.md`（C 类）、`phase-34.md:69` |
| **—** | deployment | **真实制品仓库未接** | 来源：`phase-34.md:69` |
| **—** | git | `GitClient` **零生产消费者**（phase-20 C2 偏离） | 来源：`phase-34.md:69`。**注**：高危原语（删远程分支 / 历史改写）已由 change `0138` 补齐，但**消费接线**仍未落 |
| **—** | cli-ops | **若干子命令为 stub** | `src/core/entry.py`（运维命令面）。来源：`phase-34.md:70` |
| **E88** | UI / TUI | **TUI 流式 Markdown 表格按行拆断**（渲染为竖线原文，非表格） | **已修（change `0146` / ADR-0138）**。根因：`src/core/ui/repl.py` `_show_delta` 按行固化（`repl.py:485`：`len(text) >= _TAIL_SPLIT` 或 `endswith("\n")` 即 `_freeze_tail`），把表头行拆成孤立块 ⇒ 表格永拼不齐；围栏已有同类保护（`_in_open_fence`，`repl.py:491`）**唯独没覆盖表格**。修：新增 `_in_open_table`（`repl.py:497`）+ `_TAIL_TABLE_CAP`（`repl.py:34`）+ 表格分支（`repl.py:478-484`）。**已知局限**：① 散文行含 ≥2 个 `|` 会**过度延后**固化（有界）；② **Web 端不渲染 Markdown**（`Chat.svelte` 纯文本）属**另一端、不在本 change 面** |
| **E89** | UI / TUI | **流式回显「阶梯式」+ 表格逐行绘制（不够丝滑）** | **已修（change `0147` / ADR-0139）**。根因：① `src/core/ui/repl.py` `_show_delta` **逐 delta** 走 `_touch_tail` → `Markdown.update()`（Textual **整篇 re-parse + 全量 re-layout** 且被 `Markdown.lock` 串行化）⇒ 尾段 O(n²)、渲染队列积压；② 未闭合表格每拍重绘 + 表格**列宽按内容自适应** ⇒ 逐行抽动。修：**合帧节流**（delta 只入缓冲，`_TAIL_FLUSH_S = 0.04` 懒启动 timer 合并渲染一次）+ **表格整块延后渲染**（未闭合不渲染，闭合/超 `_TAIL_TABLE_CAP` 后一次成型）+ `_add` **时序闸**（挂非尾 widget 前先提交挂起尾段）。**已知局限**：① 未闭合长表格有「无可见进度」窗口（>8000 或流尽才显形）；② 40ms 节拍为**常量非配置项**；③ Web/APP 端**不适用** |

---

## §2 有意取舍（**不算缺陷**）

> 「**有意不做**」的设计决定，非遗漏；若将来要改须**先改规格**。

| # | 取舍 | 口径 / 来源 |
|---|---|---|
| 1 | **Web 无焦点视图** | 沿用 `TaskPanel`，**有意不对称**（`doc/03-interfaces/ui-interface.md:195` 附近；phase-33 明裁）。来源：`phase-34.md:78` |
| 2 | **distributed 契约层先行** | 先立协议模型（AgentCard 签名 / 绑定表 / 连接管理）再接真实传输。来源：`phase-34.md:79` |
| 3 | **HashEmbedder 为降级基线** | 语义检索走 `LLMEmbedder`，**不引**本地语义模型（见记忆 `rag-offline-embedder-decision`）。来源：`phase-34.md:80` |
| 4 | **E62 维持确定性三判据** | 已销账，**非**缺口。来源：`phase-34.md:81` |
| 5 | **deployment `release` 退化哈希（E84-b）** | CLI `release` 无真实制品内容 ⇒ 旧为 `sha256(version)[:16]`；**规格未对 deployment 侧 bundle 哈希设 SHALL**（哈希口径 SHALL 属 composition）⇒ 非违约。**真口径已由 change `0143` 接通**（私有退化哈希已删，改读制品清单经 `composition.packager` 内容哈希发布）；**仍属取舍的只剩** `ReleaseInfo.hash` **无消费方**（写进去的是真口径，但无一处校验它）。来源：`phase-34.md:82`、ADR-0135 |
| 6 | **L1 索引一阶路由未落（E71）** | 规格「跨层检索」（`doc/openspec/specs/memory/spec.md:26-29`）指索引**热路径**；实现为「全库扫描 + 热度加权」= **常驻降级态**（spec「检索失败降级」`memory/spec.md:49-52` 明文允许）⇒ 属**性能面待优化**，非行为违约。来源：`phase-34.md:83` |

---

## §3 已知局限（按 change / ADR 归类）

| 来源 | 局限（`file:line`） |
|---|---|
| **ADR-0136**（change `0144` 时间旅行回滚生产入口） | ① 规格措辞「沿快照**差异**逆序撤销副作用」与实现「按快照 `state["trace_ids"]` 集回滚」**未完全对齐** —— 系统无「检查点之后的 trace」判据（`doc/01-architecture/adr.md` ADR-0136「已知局限①」）；② `Effect.undo` 是**进程内闭包、不可持久化** ⇒ 一次性 CLI 进程内撤销循环**空转**（快照恢复与失败语义仍生效；撤销协同在同进程入口 `serve`/REPL/同 runtime `task` 生效） |
| **ADR-0137**（change `0145` Think 回显） | ① **真端点字段取证被凭据物化阻断**（密钥只引用不读取、绝不回显）⇒ 双键归一按**公开口径**落地、实测转手工验收（`04-testing/test-cases.md` §61 手工项 1）；② **`Chat.svelte` 无 JS 门禁** ⇒ 手工验收（同上手工项 2/3）；③ 思考原文**不进**转录 / 记忆 / 日志 / 事件持久化（`doc/01-architecture/adr.md` ADR-0137「已知局限」） |
| **change `0143`**（E84-a bundle 内容哈希归一） | `ReleaseInfo.hash` 仍**无消费方**（只保证写进去的是真口径）。来源：`phase-34.md:82`、ADR-0135 |
| **change `0140`**（E77 信息地图装配） | `ContextPack.token_used` **口径不变** ⇒ 信息地图的 token 计入未单独切分。来源：ADR-0133 |
| **change `0139`**（E81/E83 Host 心跳 + Desktop 交付面） | ① `touch`/`reap` 今日仍**无生产驱动**（本账补的是规格 SHALL 的**能力面**）；② **Rust 面无门禁** ⇒ 壳编译未经验证，Tauri 打包与壳行为归**手工验收**（`04-testing/test-cases.md` §55）。来源：ADR-0132 |
| **change `0142`**（E85 core-profile 题词模板） | **未取 CLI scaffold**（落盘语义 + 会触碰 30 动词 CLI 基线 ⇒ YAGNI）。来源：ADR-0134 |
| **change `0145`**（同上 ADR-0137） | Web (Svelte) / APP 面**无自动门禁** ⇒ 手工验收（见上） |
| **ADR-0139**（change `0147` TUI 合帧节流 + 表格延后渲染） | ① **未闭合长表格有「无可见进度」窗口**（自表头到达至闭合、或超 `_TAIL_TABLE_CAP`=8000 之间屏幕上不出现该表；出路是加占位 `Static`，**不**回退 `_touch_tail`）；② **40ms 节拍为常量非配置项**（无 CLI/env 面，YAGNI）；③ **Web / APP 端不适用**（`Chat.svelte` 纯文本）。来源：`doc/01-architecture/adr.md` ADR-0139「已知局限」 |

---

## §4 非门禁面（手工验收索引）

> 以下面**无自动门禁**（前端 JS / Rust 壳 / 真端点实测 / 真终端目视），以**手工验收**覆盖。

| 手工项 | 位置 |
|---|---|
| Tauri 打包 + Desktop 壳行为（`CORE_PORT` 单点解析、程序化开窗） | `doc/04-testing/test-cases.md` §55（TC-DEPLOY） |
| Think 真端点字段取证 / Web `<details>` / APP 同构 | `doc/04-testing/test-cases.md` §61（TC-THINK）手工项 1~3 |
| TUI 流式表格目视（表格整块 / 围栏回归） | `doc/04-testing/test-cases.md` §62（TC-TABLE）手工项 1~2 |
| TUI 流式回显丝滑化目视（不再阶梯 / 表格一次成型 / 时序不乱） | `doc/04-testing/test-cases.md` §63（TC-SMOOTH）手工项 1~3 |

---

## §5 关联

- Phase 账本（已闭）：`coding-plan/phase-34.md`（`E63`~`E87` 全闭）、`coding-plan/phase-32.md`（`E56`~`E60`）
- 架构取舍：`doc/01-architecture/adr.md`（各 ADR「已知局限」）
- 测试索引：`doc/04-testing/test-cases.md`
- 未闭账复述源：`phase-34.md` §3、`phase-19.md:104`、`phase-20.md:40-45`
