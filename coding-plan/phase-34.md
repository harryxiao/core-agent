# Phase 34：全系统架构走查（跨模块 + 模块内）设计缺陷 / 缺失账本

> **状态**：🚧 **实施中（全修）**（**缺陷账本 + feature**；2026-10-06 全系统**只读**走查产出：25 条新账 **E63~E87** + §3 已知账目复述 + §4 有意取舍 + **§6.5 phase-32 ∥ phase-34 统一优先级排序**。**2026-10-06 用户裁决「全修」** ⇒ E63~E87 缺陷账 + phase-32 E56~E60 feature 全做，拆 **20 个 change**（`0126`~`0145`），落地进度见 **§9**）
> **来源**：用户指令「整个 Agent 快完工了，整体走查下各模块之间、模块内部，是否依然还存在设计缺陷或漏掉的设计」⇒ 10 份并行只读审计 + 主代理逐条读码复核（复核口径见 §0）。**`phase-32`（Think 回显 E56~E60）** 原按指令排除，2026-10-06 用户指令「phase-32/34 一起排」后**已并入 §6.5 统一优先级排序**（仍不计入 §1/§2 缺陷栏 —— 其为**新能力 feature**，非缺陷）。
> **定性**：核心链路（L0 可逆基底 / L2 记忆 / L3 循环 / L4 进化验证门 / L5 解析）**结构与门禁成立**，未发现「门拦不住」或「核心断裂」。缺陷集中在三类：① **接线面未收口**（契约方法已备、生产无调用方）；② **多写场景下的可逆 / 收尾语义**（P2 在最常用工具上崩坏、回滚不清账）；③ **规格写了、实现只落一半**。
> **红线（全账）**：本 Phase 仅**登记**，不实施；任何后续实施须**逐条裁决 → 规格先行 → ADR → 测试先行**，**不得**以缺陷修复名义 `skip_specs` 强推。密钥只引用不读取、绝不进日志/记忆；`exclude_source_prefixes=("beast.",)` 主方向排除不动。

---

## §0 复核口径与证据强度

| 标记 | 含义 |
|---|---|
| ✅ **亲验** | 主代理读码坐实（行号逐条核对） |
| ○ 转述 | 并行审计代理转述，**未**独立复核（行号来自代理，**立账前须二次核**） |

**本账 25 条：✅ 亲验 24 条、○ 转述 1 条**（E85，`core-profile` 题词模板，doc-only 低危）。全账**未跑任何测试 / 命令**（只读走查铁律），判定均为**静态阅读**；测试覆盖仅按文件名 + 少量 grep 判，未逐一核对每条 Scenario↔断言映射。

---

## §1 真缺陷（**生产可达**，严重度降序）

| # | 严重度 | 缺陷 | 证据（行号坐实） | 性质 | 复核 |
|---|---|---|---|---|---|
| **E63** | **高** | `scheduler` **丢弃子任务失败态** ⇒ **假成功**并向下游接力失败结果 | `orchestration/scheduler.py:440-443` 只取 `collect_result(...)` 与 `verify(subtask, result.reply)`，**从不读 `result.failed`**；`:462-466` 在 `verify.passed` 时把 `result.reply` 写进 `self._results`（经 `_handoff_goal` 喂下游）。对照正解 `runtime.py:797` `_dispatch` = `{"ok": not result.failed}`。触发链：`default.py:295-297/316-319` 撞限产 `loop_failed` + **非空合成 reply**（`"…本轮终止"`）⇒ `failed=True` 但 reply 非空 ⇒ `decomposer.verify:54-62` 无 verifier 时「非空即通过」⇒ **合成错误串被当成功接力** ⇒ **已落地（change `0126` / ADR-0119）** | P2/P3 判定断裂 | ✅ |
| **E64** | **高** | `file_write` / `file_patch` **共用一份 `snap`** ⇒ 多写后回滚恢复**错文件** | `tools/builtin.py:102-130`（write）与 `:133-147`（patch）在**工具级**建**一个** `snap`，每次调用覆写 `snap["path"]/["before"]`；`undo()` = `_restore(snap)` 读**同一共享 dict**。`runtime.py:397` 五个内置工具**只构造一次、跨 loop 复用** ⇒ 同 trace 内两次写不同文件，回滚只还原**最后一次**。**P2 崩于最常用工具** ⇒ **已落地（change `0129` / ADR-0122）** | P2 可逆性断裂 | ✅ |
| **E65** | 中高 | Web 前端 `reply_delta` **渲染破碎**（逐帧打印 JSON） | `ui/api.py:20-37` 把 `reply_delta` 映射到 `loop.result`；`frontend/src/views/Chat.svelte:44-51` 对 `loop.result` 取 `payload.reply ?? message ?? JSON.stringify(payload)` 并**追加新行** ⇒ delta 帧 `{text:…}` 无 `reply` ⇒ 每帧渲染一段 JSON。TUI 正解：`ui/repl.py:69-79 _event_delta` ⇒ **已落地（change `0132` / ADR-0125）：增量帧改**专类型** `loop.delta`（`_EVENT_MAP`），与终态 `loop.result` 分型；`repl.py::_event_delta` / `_format_event` / `entry.py::_stream` 判据随型更新（呈现逐字不变）；`Chat.svelte` 增量**尾部追加**、终态原位收口** | 前端渲染 | ✅ |
| **E66** | 中 | `/session/compact` **压实全部会话**（**会话隔离外泄**） | `ui/api.py:211-215` `compact(session_id)` 调 `self._memory.compact(session_id)`；`memory/store.py:200-224` `compact(query, budget)` 只用 `query` 打分，`:222-223` 直接 `self._summarize_sessions()`；`:298-312` 该方法**无 session 形参**，遍历 `self._episodic_groups().items()` **全量** ⇒ **已落地（change `0131` / ADR-0124）：`compact` 增仅关键字形参 `session_id`，非空只聚合该会话、空串保全量；`ui/api.py` 改传 `session_id=session_id`（不再当 `query`）** | 会话隔离破坏 | ✅ |
| **E67** | 中 | `EffectTracker.rollback` **不清账** ⇒ 重复回滚**二次撤销** + `_effects` **无界增长** | `plugin_registry/effect_tracker.py:61-78` 回滚后既不移除 `_effects` 也不清 `_by_trace`，且**无 clear 方法** | P2 可逆性 + 内存 | ✅ ⇒ **已落地（change `0128` / ADR-0121）** |
| **E68** | 中 | `write_patch` **绕过可逆性**（磁盘 yaml 不可按 trace 回退） | `configuration/manager.py:555-569` `tmp.write_text(_dump_yaml(raw))` + `os.replace`，**无 `EffectTracker.record`**；对照 `apply_change:538-548` 的 undo 只回滚**内存态** ⇒ 按 trace 回滚时**磁盘不回退** ⇒ **已落地（change `0130` / ADR-0123）** | P2 可逆性 | ✅ |
| **E69** | 低 | `executor.commit` **不校验 `record.gated`**（fail-open 崩溃窗口） | `evolution/models.py:80-81` 明写「`commit` 只认前者（`gated=True`）为真者」；`evolution/executor.py:183` 走 `staged()`（`:215-218` **仅滤 `committed`**），`:178-211` **从不读 `gated`**；全仓 `gated` **只有写**（`:171/:205`）**无读**。窗口：门禁失败回滚后、`clear_implementation` 前**崩溃** ⇒ 重启后 `commit` 可放行**未过门**制品 ⇒ **已落地（change `0127` / ADR-0120）** | fail-open（潜伏） | ✅ |
| **E70** | 低 | composition `apply_patch` 接受 **bool** 当 generation | `composition/resolver.py:129` `isinstance(override, int)`——**bool ⊂ int**，YAML `true` 生成 `PluginRef(id, True)`（`PluginRef(plugin_id, override)` `:134`） ⇒ **已落地（change `0136` / ADR-0129）：`apply_patch` 判据补 `or isinstance(override, bool)`，布尔按 `PATCH_CONFLICT` 拒绝（不静默落为 1/0）** | 类型边界 | ✅ |
| **E71** | 中 | **L1 索引是空壳**（`read` 从不查 `_index`，全库扫描） | `memory/store.py:110-115` `read()` 用 `backend.search(query)` **全扫** + `_hot`，**从不碰 `_index`**；`:191-192` `index()` 仅调 `list_index()`。规格 `memory/spec.md:26-29` 要求「命中 L1 索引 → 非全库扫描」 | 规格漂移（性能面） | ✅ |
| **E72** | 中 | 技能安装后 **`draft` 死胡同**（装完**永不被路由**） | `skillhub/client.py:66` 下载后 `skill.status = "draft"`；`skills/router.py:98` 只放行 `s.status in ("active","gray")`；**无 draft→active 迁移路径** ⇒ **已落地（change `0133` / ADR-0126）：`SkillLibrary.activate(skill_id, *, effect_tracker=None)`（幂等 / 未知 id 抛 `KeyError` / 可选可逆效应）+ CLI `skill activate <name>`；路由**放行集不变**（仍 active/gray），不自动启用** | 设计缺失（链路断裂） | ✅ |
| **E73** | 低 | `TimeTravel.rollback` **不可达** | 检查点**持久化**在用（`--resume` 依赖，E12 指此路径），但**时间旅行回滚**无任何生产调用方（见 §5 订正） | 设计缺失（死面） | ✅ |

---

## §2 设计缺失 / 规格漂移（**未登记**，建议立账）

| # | 类别 | 缺口 | 证据 | 复核 |
|---|---|---|---|---|
| **E74** | 规格漂移 | **beast「三入口」仅 CLI 接线**：`/summon` 斜杠与 WebUI 自然语言**生产不可达** | `beast/activator.py:45-55` 声明 `activate_from_slash` / `activate_from_nl`（及其 recall 孪生 `:57-67`），**全仓无调用方**；`ui/api.py:223` 只接**宠物** `activate_from_nl`；`entry.py:417-435` 构造 `UIAPILayer` **未注入 `beast_activator`**；`ui/repl.py` 斜杠命令只有 `/focus` `/main`。spec `beast-mode/spec.md:123-139`「Three-Entry Activation」两个 Scenario 不可达（`phase-17.5.md:45` 标「三入口已实现」实为**契约方法层**；`_resolve_nl:29-36` 自注「Agent 理解意图 deferred」） ⇒ **已落地（change `0137` / ADR-0130）：`UIAPILayer` 增 `beast_activator` 注入面 + `activate_beast`（NL，async）/ `beast_command`（斜杠 `/summon` `/recall`）；`repl.py` 补 `_parse_beast_command` + 分发 + `_run_beast_turn`（状态行 + 有结果才打印）；`entry.py` 注入 `runtime.beast_activator`；领域错误在 API 边界分码归一（`OrchestrationError` ⇒ `UI_BEAST_NOT_FOUND`；`BeastError` ⇒ `UI_BEAST_STATE_INVALID`）。无 delta（spec 早已硬 SHALL）⇒ `skip_specs`** | ✅ |
| **E75** | 设计缺失 | composition **「可逆 / 可回退」无兑现** | `composition/resolver.py:106-108` 覆盖前分层结果被 `apply_patch` 丢弃、override 值只存进 `ResolvedSet.overrides`（`:108`）；全包**无任何 revert/undo API** ⇒ spec `composition/spec.md:51-57`「回退到覆盖前状态」**无路径可达**（`models.py:51` 注释亦仅声明数据形状） ⇒ **已落地（change `0136` / ADR-0129）：`ResolvedSet` 增必填 `layered`（覆盖前分层结果）、`resolve` 原样携带；新增 `ProfileResolver.revert`（纯函数 / 幂等 / 不改实参）并门面透出 `CompositionEngine.revert`；规格「层叠解析」补「保留覆盖前分层结果 + 回退幂等」与 2 Scenario** | ✅ |
| **E76** | 规格漂移 | permission **子串匹配**（违反「分词 / 完整词元」）＋ `APPROVAL_REQUIRED` **定义无人 `raise`** | `permission/policy.py:53,61,63` 用裸子串 `tok in op_l`；spec `permission/spec.md:9,19,26-29` 要求语义分词且 **namespace-子串 SHALL NOT 判读**；`permission/errors.py:18` 定义 `APPROVAL_REQUIRED`，**`src/` 零 `raise`**（死码） ⇒ **已落地（change `0135` / ADR-0128）：`classify` 改**词元集合**命中（`_tokens` 按 `._:-/` 切词，操作**与目标**两侧；三表转 `frozenset`，顺序逐字不变）—— `tools.target`／`tools.category_sync` 由误判 `read` 收敛为 `HIGH_RISK`（fail-closed 兜底归位）；`APPROVAL_REQUIRED` 的 raise 落点订正为**高危 git 审批门** `GitClient._require_approval`（原误用 `PERMISSION_DENIED`；`authorize` 一侧仍以 `Decision(approval_required=True)` 供审批通道，**不**改抛异常）** | ✅ |
| **E77** | 设计缺失 | **信息地图不可达**（构造了却从不查） | `context/assembler.py:54-75` `build()` **从不读** `_info_map`（`:32` 只在 ctor 存下）；`fetch_detail():69-75` **零调用**；`context/info_map.py:90-100 _linear_scan` **死码**（`index()` 恒同写 `_docs`+`_maps`） ⇒ **已落地（change `0140` / ADR-0133）：三级链路接通** —— ① `build()` 读地图 ⇒ `ContextPack.pointers` 目录层（每文档上界 8）+ `planner` 渲染「文档目录」块；② 新只读工具 `tools.context_read`（取数器**注入**，工具层不依赖 context 层）作模型侧唯一取详情通道；③ `InfoMap.register()`（仅原文）复活 `_linear_scan`，段数上界 20 ⇒ spec「**受控**」落为常量；④ `build_runtime` 把 Core.md 项目信息段索引为 `core-profile` ⇒ 产线**非空转**（零回归：缺省空目录层）** | ✅ |
| **E78** | 规格漂移 | memory **规格三档（热 / 温 / 冷）vs 实现两档（hot + cold）** | 实现无温层载体；spec `memory/spec.md:31-32` 写三档 ⇒ **已落地（change `0131` / ADR-0124）：规格改**热/冷两档**，删温层条文** | ✅ |
| **E79** | 规格漂移 | git **「断线重试 / 指数退避」无实现** ＋ **删远程分支 / 历史改写**原语缺失 | `git/subprocess_backend.py:141-154` `pull`/`push`（及 `clone`）单次 `_run`，`_run:158-163` **无 retry/backoff**；`git/client.py:86-101` 仅 force-push 走审批，13 原语**无**「删远程分支 / 历史改写」。spec `git/spec.md:69-91` 有对应 Scenario（C2 的「偏离原记」`phase-20.md:93` 只记「不装配 CLI 入口」，**未记**此二缺口） ⇒ **已落地（change `0138` / ADR-0131）：`_run_remote` 瞬态网络失败按指数退避重试（`attempts=3`/`backoff=0.5`，可注入 `sleep`；认证失败 / 超时 / 冲突 / 非瞬态不重试）；`GitClient` 补 `delete_remote_branch` / `rewrite_history` 原语，复用同型审批门（`_require_approval(op, reason)`，三处 op id 互异），非交互默认拒** | ✅ |
| **E80** | 规格漂移 | skillhub **「回退官方源」只报错**（**spec 自相矛盾**） | `skillhub/index.py:134-140` `_ensure_healthy` 直接 `raise SOURCE_UNHEALTHY`（文本却写「（回退官方源）」），**无回退动作**；`tests/test_skillhub.py:42` 亦断报错。spec `skillhub/spec.md:34-38` **同句**既写「回退官方源」又写「返回 `SOURCE_UNHEALTHY`」⇒ 实现/测试选了后半句 ⇒ **已落地（change `0134` / ADR-0127）：规格拆句为「不健康 ⇒ 回退官方源**并以其结果响应**（标记该源不健康）；官方源亦不可用 ⇒ `SOURCE_UNHEALTHY`」；`_ensure_healthy` 改返回**可用源名**，`list`/`route` 用其取结果** | ✅ |
| **E81** | 设计缺失 | deployment `reap` **无心跳刷新 `last_seen`** ⇒ 活跃客户端可能被误回收 | `deployment/host.py:56` `last_seen` **仅 `accept` 赋值**，`reap:78-88` 据其判超时，全类**无 touch / heartbeat** 更新 ⇒ **已落地（change `0139` / ADR-0132）：新增 `HarnessHost.touch(session_id) -> bool`（只认在连会话刷 `last_seen`；未知 / 已断线 / 已回收返 `False` 且**不复活**；成功即持久化）⇒ 「无活动」才计超时；`touch`/`reap` 生产驱动今日仍缺（登记为残留口径）** | ✅ |
| **E82** | 规格漂移 | **pet / beast Web 面缺失**：12 个 HTTP 端点**无** pet/summon/recall | `ui/fastapi_serve.py:194-206` 共 12 条 `add_api_route`，**无** pet/summon/recall（与 E74 同源：UIAPILayer 有 `activate_pet`/`pet_command` 方法但未暴露为端点，`api.py:223` 仅内部接宠物） | ✅ |
| **E83** | 设计缺失 | **Desktop 交付面不完整** | `src-tauri/tauri.conf.json:15` **硬编码** `url: http://127.0.0.1:8000`（`src-tauri/src/main.rs:48-51` 却尊重 `CORE_PORT`）＋ `:22-24` `bundle.active=false` ⇒ **无安装包**（phase-20 C8 只记「壳二进制打包未验证」，未记端口硬编码） ⇒ **已落地（change `0139` / ADR-0132）：`tauri.conf.json` 端口**移出配置**（`app.windows` 清空）、`bundle.active=true` + `targets="all"`；`main.rs` 端口经 `resolve_port()`**单点**（`CORE_PORT`，缺省 8000）**同时**供 sidecar 与 `WebviewWindowBuilder` 开窗 ⇒ 壳与内核同源端口、漂移不可能；**壳编译**与安装包产出**均属手工验收**（`cargo check` 本轮未跑通：缓存依赖树与 `Cargo.lock` 版本不一致 + 联网取包未成功，非门禁）** | ✅ |
| **E84** | 设计缺失 | composition vs deployment **两套「发布 bundle」哈希口径分歧** | CLI `release` 走 `ReleaseManager`，哈希**退化为版本名哈希**（`entry.py:1014-1016` `sha256(version)[:16]`，自注「CLI 无真实制品内容」）；composition 真内容哈希 `composition/packager.py:18-21 content_hash`（对 `plugin_id@generation` 哈希）**零引用**（composition 零接线）。spec 两 capability 概念重叠但口径不一致 | ✅ |
| **E85** | 规格漂移 | core-profile **「题词规范 / 题词模板」doc-only**，**无骨架文件、无专门测试** | 代理 `find` 未命中模板文件；规格自述无对应产出物 | ○ |
| **E86** | **账目失真** | `phase-9.md:114` **假绿**：勾选「Web 断线重连」但**前端未实现重连** | `coding-plan/phase-9.md:114` 已 `[x]`：`serve：HTTP 端点 CRUD + SSE 流式事件 + 断线重连 + …` | ✅ |
| **E87** | 设计缺失 | `doc/10-codebase-engine/` **有文档无实现** | 目录存在，`src/` **无**对应模块（`doc/` 与实现两分） | ✅ |

---

## §3 已登记账目复述（**已知、不重复立账**）

> 仅复述现状，**不**在本 Phase 重新立账；处理时回对应 Phase。

- **E27** — IM 网关逻辑齐备但**零生产装配**（`im/gateway.py` 测试全绿，无真实 Provider 接线）。
- **E55** — 主 loop 丢弃多余 `tool_call`（`planner.py:222-225`，单工具协议取首个）；与 E62 同源不同层，**保持待议**。
- **C7** — TTS 为抽象能力、后端未接（`ui-interface.md:18-19` barge_in 注释）。
- **composition / distributed 整包零生产接线**（README §2 标 ✅ 与事实不符，属**已知**；distributed 的 oauth2/mTLS/oidc 仅字段声明、多设备拓扑无代码）。
- **evolution 留出评测生产 runners 未接** ⇒ 候选恒 `frozen`（ADR-0112）。
- **ci-cd `publisher` 发布通道 `CHANNEL_UNREACHABLE`**（phase-20 C 类）、**deployment 真实制品仓库未接**、**GitClient 零生产消费者**（phase-20 C2 偏离）。
- **cli_ops 若干子命令为 stub**（`entry.py` 运维命令面）。

---

## §4 有意取舍（**不算缺陷**）

1. **Web 无焦点视图**（`ui-interface.md:195`）—— phase-33 明裁沿用 `TaskPanel`，**有意不对称**。
2. **distributed 契约层先行** —— 先立协议模型（AgentCard 签名 / 绑定表 / 连接管理）再接真实传输。
3. **HashEmbedder 为降级基线** —— 语义走 `LLMEmbedder`，不引本地语义模型。
4. **E62 维持确定性三判据** —— 已销账，非缺口。

---

## §5 复核订正 / 证伪（主代理推翻或收窄的代理结论）

- **证伪（代理的 durability 越界主张）**：有代理称 E12「生产已接线」为**伪**。复核后**订正**：E12（`phase-19.md:420-440`）指**检查点持久化**路径（**在用**，`--resume` 依赖），**不是** `Runtime.recover()`；durability 规格的崩溃恢复 Scenario 允许「重启**或触发恢复**」⇒ **仅 `TimeTravel.rollback` 真不可达**（**E73**），该代理的整体框架**不成立**。
- **收窄（E84）**：composition 与 deployment 确有两套 bundle 哈希口径，但 **wired 的一方（deployment）是退化哈希** —— 不是「双实现冲突」，而是「**真口径孤置**」。
- **降级（E80）**：非实现缺陷，实为 **spec 自身一句内自相矛盾**（「回退官方源」+「返回 `SOURCE_UNHEALTHY`」并存），实现 / 测试选后半句。

---

## §6 建议优先级与落地切分（**待裁决**）

| 档 | 项 | 理由 |
|---|---|---|
| **P0（真缺陷 · 建议先修）** | **E63** 假成功、**E64** 写回滚错文件、**E66** compact 全场、**E67** 回滚不清账、**E68** write_patch 无逆 | 均**生产可达**且触 **P2 / P3 红线**；**E63 / E64 影响面最大** |
| **P1（用户可见）** | **E65** Web delta、**E71** 索引空壳、**E72** 技能死胡同 | 前端渲染 / 检索性能 / 技能可用性 |
| **P2（接线收口）** | **E74** beast 三入口、**E76** permission、**E77** 信息地图、**E82** pet Web 面 | 「契约备、接线缺」——**销账或修**择一 |
| **P3（账目校准，纯文档）** | **E86** 假绿、§3 README ✅ 订正、**E84 / E85** | 台账可信度，不涉运行时 |
| **单点小修（随批）** | **E69 / E70 / E73 / E75 / E78 / E79 / E80 / E81 / E83 / E87** | 逐条小面，可与上档合批 |

**切片建议（若裁决实施）**：

- **切片 A（可逆性 / 判定语义）**＝E63 + E64 + E66 + E67 + E68（同主题，**同一 change 或拆二**：判定面 E63 独立；可逆面 E64/E66/E67/E68 同批）。
- **切片 B（用户可见）**＝E65 + E71 + E72。
- **切片 C（接线收口）**＝E74 + E76 + E77 + E82。
- **切片 D（账目校准）**＝E86 + C 栏 README 订正 + E84 + E85（**纯文档 / 规格中性**，可 `skip_specs`）。

---

## §6.5 phase-32 ∥ phase-34 统一优先级排序（2026-10-06，用户指令「phase-32/34 一起排」）

> **口径**：本表把 `phase-32`（Think 回显 **E56~E60**，**新能力 feature**）与本 Phase（缺陷账本 **E63~E87**）**并入同一优先级序列**。用户已撤销原「phase-32 整体排除」指令（§0/§7）。
> **性质区分**：缺陷 / 漂移（E63~E87，**须规格先行 → ADR → 测试先行**） vs **新能力 feature**（E56~E60，**链式五段不可拆** ⇒ 作为**一个切片组**参与排序）。

| 序 | 源 | 账 | 性质 | 严重度 | 切片 |
|---|---|---|---|---|---|
| 1 | 34 | **E63** 假成功（scheduler 丢 `failed`） | 真缺陷·判定 | **高** | A1 |
| 2 | 34 | **E64** 回滚错文件（共享 `snap`） | 真缺陷·可逆 | **高** | A2 |
| 3 | 34 | **E66** compact 压实全会话 | 真缺陷·隔离 | 中 | A2 |
| 4 | 34 | **E67** `rollback` 不清账 | 真缺陷·可逆 | 中 | A2 |
| 5 | 34 | **E68** `write_patch` 无逆 | 真缺陷·可逆 | 中 | A2 |
| 6 | 34 | **E65** Web `reply_delta` 破碎 | 用户可见 | 中高 | B |
| 7 | 34 | **E71** L1 索引空壳 | 用户可见·性能 | 中 | B |
| 8 | 34 | **E72** 技能 `draft` 死胡同 | 用户可见 | 中 | B |
| 9 | 34 | **E74** beast 三入口仅 CLI | 接线收口·漂移 | 中 | C |
| 10 | 34 | **E76** permission 子串 + 死码 | 接线收口·漂移 | 中 | C |
| 11 | 34 | **E77** 信息地图不可达 | 接线收口·缺失 | 中 | C |
| 12 | 34 | **E82** pet/beast Web 面缺 | 接线收口·漂移 | 中 | C |
| 13 | 34 | **E86** `phase-9.md:114` 假绿 | 账目失真 | 低 | D |
| 14 | 34 | **E84** 双 bundle 哈希口径 | 账目校准 | 低 | D |
| 15 | 34 | **E85** 题词模板 doc-only（○） | 账目校准 | 低 | D |
| 16 | 34 | E69 / E70 / E73 / E75 / E78 / E79 / E80 / E81 / E83 / E87 | 单点小修 | 低 | 随批 |
| **F1** | **32** | **E56~E60** Think 回显（provider → planner → loop → UI 映射 → 三端） | **新能力 feature**（链式五段） | 取决需求 | **32-A / 32-B / 32-C** |

**推荐执行序**：

- **缺陷主线（phase-34）**：`A1(E63)` → `A2(E64+E66+E67+E68)` → `B(E65+E71+E72)` → `C(E74+E76+E77+E82)` → `D(E86+E84+E85，纯文档)`；单点小修（序 16）随相近切片合批（见 §6）。
- **feature 支线（phase-32）**：`32-A(数据面 E56+E57，先实测 glm-5.3 流式字段)` → `32-B(事件面 E58+E59)` → `32-C(呈现面 E60)`；**可与缺陷主线并行**（模块不重叠 —— phase-32 §4 已声明不触 phase-28/29/31 与 change `0115`；phase-34 §7 不触 phase-33/已落地件）。
- **排序依据**：缺陷（尤其 **E63 / E64** 触 P2/P3 红线）**优先于**新能力；feature 因其为用户点名需求、且与主线无依赖 ⇒ **单列支线并行**，不阻塞、不被阻塞。

**红线（沿用 §6/§7）**：两源实施**均须**逐条裁决 → 规格先行 → ADR → 测试先行；**不得**以缺陷修复 / 能力新增名义 `skip_specs` 强推（规格中性者除外）；phase-32 **切片 A 必须先实测 glm-5.3 实际流式字段**（不得照抄 OpenAI 文档口径）。

---

## §7 去重边界与红线

- **`phase-32`（Think 回显 E56~E60）**：原「整体排除」指令已由用户「一起排」撤销 ⇒ **仅并入 §6.5 排序**；实现面仍**互不触碰**（phase-32 §4 的边界照旧）。
- **不重复** §3 已登记账目（E27 / E55 / C7 / C 类 / ADR-0112 / phase-20 各项）。
- **不重开** §4 有意取舍（Web 焦点视图 / distributed 契约层 / HashEmbedder / E62）。
- **不触碰** `phase-33` 已落地（change `0125` / ADR-0118）。
- **红线**：仅登记不改码；实施须**裁决 → 规格先行 → ADR → 测试先行**；**不得**以缺陷修复名义 `skip_specs` 强推（规格中性者除外）；`exclude_source_prefixes=("beast.",)` **逐字不动**；密钥只引用不读取、绝不进日志/记忆。

---

## §8 登记

- **本 Phase 为「全系统走查」首份**：25 条新账 **E63~E87**，严重度降序（§1 真缺陷 → §2 缺失 / 漂移 → §3 复述 → §4 取舍）。
- **复核口径**：25 条 **✅ 亲验 24 / ○ 转述 1**（E85）；未跑测试，全为静态阅读 —— **立账前建议对 ○ 条二次核**。
- **关联**：`README.md` §2 总览表 + 文档清单待补 Phase 34 行；`contracts_summary.md` 无涉（本账不改契约）。
- **下一步**：**已裁决 = 全修**（2026-10-06，用户）— E63~E87 + phase-32 E56~E60 全做，按 §6/§6.5 切分走 SDD 全流程；落地台账见 **§9**。

---

## §9 落地台账（**全修** 执行，2026-10-06 起）

> 用户 2026-10-06 裁决「**全修**」⇒ 缺陷账 **E63~E87** + feature **E56~E60** 全做，拆 **20 个 change**（`0126`~`0145`），每 change 独立走「规格先行 → ADR → 测试先行（红→绿）→ 实现 → 四门禁 → 手工归档 → 台账 → 单次提交」。**排序**见 §6.5（缺陷主线 A1→A2→B→C→D + feature 支线）。

| change | 账 | 状态 | ADR |
|---|---|---|---|
| `0126` | E63 | ✅ 已落地（2026-10-06） | ADR-0119 |
| `0127` | E69 | ✅ 已落地（2026-10-06） | ADR-0120 |
| `0128` | E67 | ✅ 已落地（2026-10-06） | ADR-0121 |
| `0129` | E64 | ✅ 已落地（2026-10-06） | ADR-0122 |
| `0130` | E68 | ✅ 已落地（2026-10-06） | ADR-0123 |
| `0131` | E66 + E78 | ✅ 已落地（2026-10-06） | ADR-0124 |
| `0132` | E65 | ✅ 已落地（2026-10-06） | ADR-0125 |
| `0133` | E72 | ✅ 已落地（2026-10-06） | ADR-0126 |
| `0134` | E80 | ✅ 已落地（2026-10-06） | ADR-0127 |
| `0135` | E76 | ✅ 已落地（2026-10-06） | ADR-0128 |
| `0136` | E75 + E70 | ✅ 已落地（2026-10-06） | ADR-0129 |
| `0137` | E74 | ✅ 已落地（2026-10-06） | ADR-0130 |
| `0138` | E79 | ✅ 已落地（2026-10-07） | ADR-0131 |
| `0139` | E81 + E83 | ✅ 已落地（2026-10-07） | ADR-0132 |
| `0140` | E77 | ✅ 已落地（2026-10-07） | ADR-0133 |
| `0141` | E86+E82+E87+E71+E84-b | ⏳ 待实施 | — |
| `0142` | E85 | ⏳ 待实施 | — |
| `0143` | E84-a | ⏳ 待实施 | — |
| `0144` | E73 | ⏳ 待实施 | — |
| `0145` | E56~E60 | ⏳ 待实施 | — |

**终裁（本轮锁定，2026-10-06）**：范围 = 含 Think 回显（全做）；E73 / E77 死面 = 都补齐接线；E78 = 规格改两档；E80 = 回退成功即返回官方源结果。
