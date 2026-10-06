# 提案 — 按会话隔离记忆（change 0114 / phase-28 E47）

## 背景

用户要求（原话）：「webUI…可以选择开启 1 个对话框后，继续开启第 2 个，第 3 个…每一个主题都不一样…
CLI 类似，但是**不同会话之间会话内容肯定隔离的**…WebUI 右边是会话列表管理…相互独立」。
用户裁决：**严格隔离 + 保留全局层**；**历史落盘 + 回灌 prompt**（→ Change B）；**拆两个 change**；
写入侧 **核心链路 + 同批全修**；`notes` **显式定为全局层**。

一手核实（本窗口逐文件精读）——账本 E47 原记「读侧不过滤会话」只说到一半，实际缺口是**一个读侧 + 五处写侧**：

| # | 位置 | 一手事实 | 后果 |
|---|---|---|---|
| R | `memory/store.py:90` `read(query, budget, *, exclude_source_prefixes=())` | 唯一过滤是 **source 前缀**（生产只接 `("beast.",)`，`runtime.py:564`）；`session_id` 写入侧一直在写（`loop/default.py:491`、`store.py:363`），**读侧从不消费** | **A 会话沉淀的事实进 B 会话的 system prompt** |
| W1 | `context/compactor.py:87/100` | 压实产物 `id=compaction.fact.{i}` **每次压实从 0 重数**，且无 `session_id` | 后一次压实**静默覆盖**前一次；产物全局层 |
| W2 | `skills/router.py:132` `_record_miss` | 把**本轮任务原文**写成 `id=skills.miss.{n}`、`session_id=""`；生产 `SkillRouter(..., memory=memory)`（`runtime.py:407`）经 `planner._skill_hints` **每轮推理**触达 | **普通聊天每轮的任务原话都进全局记忆** |
| W3 | `pet/core/session.py:149/:254` + `runtime.py:892` `_pet_loop` | `self._loop.run(goal)` 不带会话；`_pet_loop` 未传 `source` | 宠物轨迹落 `source="loop", session_id=""`，**与主线未归属条目同形不可区分** |
| W4 | `orchestration/scheduler.py:375` + `ui/api.py:160` | `profile.loop.arun(goal)` 无会话；`run_task` **手里有 `session_id` 却丢弃** | 编排子任务轨迹全局化 |
| W5 | `loop/default.py:312` → `notes/store.py:139` | `ctx.notes` 通道**绕过 `MemoryStore.read`**（`digest(query)` 签名只有 query） | 会话隔离对其**零覆盖** |

规格侧：`context/spec.md` 零处提 session；`memory/spec.md` 只要求**写入**带 `session_id` 并按会话归组
（压实/固化/遗忘）；`ui/spec.md` 的「会话记忆按会话读取」只约束**展示面** `get_memory`。⇒ 读侧隔离是**能力缺口**，
按 SDD 必须**规格先行**。

**不可推翻的约束**：phase-19 E2 / change `0048` 已裁决「会话标识透传 + 单店按会话归组」，**明确否决**
「每会话独立 `(loop, memory)` 实例」⇒ 本 change 只给既有读写路径补会话维度，**不得为每会话建实例**。

## 变更目标

1. **读侧加会话维度**：`MemoryStore.read` 在**排名与预算之前**按会话过滤（与既有 `exclude_source_prefixes` 同点、
   同口径：被滤项不吃预算、不被 `reuse_count` 强化）；标识**非空**时只返回「本会话条目 + **全局层**」，
   **空标识不过滤**（与既往逐字一致，fail-open）。
2. **全局层边界写死**：全局层 = 未归属（`session_id=""`）条目 + L0 人格 + **文档化笔记层** + 宠物 `source="user"`
   主人偏好（**刻意知识**）。
3. **写入侧归属闭合（同批全修）**：W1–W4 四处**执行轨迹**一律按**发起会话**归属；条目 id 带会话键
   （沿用 store 内既有 `key = session_id or "default"` 口径），消跨会话覆盖。
4. **`notes` 显式定为全局层**：不改行为，规格 + ADR **明写**，并加守护用例钉住（不让读者误以为它被隔离了）。
5. **兼容不破**：默认（未归属）调用路径的**调用形态逐字不变**——`read(query, budget)` 仍两参、
   `perceive(user_input)` 仍一参、`digest(query)` 仍一参。

## Non-goals / 已否决

- **不建每会话实例**：change `0048` 已裁，本 change 不翻案。
- **不隔离 `notes`**：用户裁决「显式定为全局层」（笔记是**被有意文档化的知识库**，不是对话残留）。
- **不改 `get_memory` 展示面**：`ui/spec.md` 明写「其他会话与**未归属条目**不出现在结果中」——展示面**严于**推理面
  （推理面必须保留全局层，否则人格/笔记/偏好进不了 prompt），此不对称是**有意**的，写进 ADR。
- **不给 CLI `task` 造会话**：`entry.py:1501` 不带会话 = 未归属 = 既有语义，兼容。
- **不修同会话内连续压实 / 跨进程重启的 id 复用**：既有缺陷，本 change 只消**跨会话**面，残留登记台账。
- **不做 Change B**（对话历史落盘/回灌 + 会话列表 UI）。

## 风险

| 风险 | 缓解 |
|---|---|
| fail-open：忘记传 `session_id` 的调用方看到全库 | **承认并写进 ADR**（与既有「缺省空 ⇒ 逐字一致」同构）；生产链路上唯一入口 `ui/api.run_loop` 已透传，本 change 补上 `perceive`/planner/compactor/pet/scheduler 五处断点 |
| 改调用形态打破既有替身 | 默认路径**不新增实参**（空标识仍走两参 `read` / 一参 `perceive` / 一参 `digest`）；`skill_router` 注解放宽为 `Callable[...,]` 而非 Protocol（既有 1 参 lambda 替身仍可赋值） |
| 条目 id 口径变更加剧测试面 | `tests/test_loop.py:551-552` 的 `compaction.fact.0 → compaction.fact.default.0`（id 口径变更，非放宽语义）；其余 id 断言核对后应全绿 |
| 宠物轨迹归属后主 Agent「看不见宠物学到的东西」 | 宠物有**专属结果查询面**（change `0113`）作为对外通道；「偏好」（刻意知识）**仍留全局**，主 Agent 照常可见 |
