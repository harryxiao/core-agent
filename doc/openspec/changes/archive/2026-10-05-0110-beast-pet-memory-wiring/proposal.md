# proposal — beast / pet「专属记忆命名空间」接线收尾（change 0110 / 账本 E37 + E38 + E39）

## Why

`coding-plan/phase-26.md` 一手复核发现 beast-mode / pet-mode 两条**专属记忆链路**的三处接线缺口
（规格均已在位，实现未跟上）：

- **E37**：`beast-mode` spec `:54` 明文要求神兽「独立记忆命名空间（`MemoryEntry.source = beast.<agent_id>`，
  与主 Agent `source=loop` 隔离）」，但**落记忆路径**是 `DefaultLoop.remember`，其 `source="loop"`
  **硬编码**（`loop/default.py:485`）、`LoopPlugin.__init__` 无 source 注入面（`:114`）⇒ 组合根
  `_beast_loop`（`runtime.py:660`）无从指定命名空间 ⇒ 神兽轨迹以 `source="loop"` **混入主记忆**；
  且 `read` 无 source 过滤（`memory/protocol.py:49` / `store.py:90`）⇒ 主 Agent 上下文装配
  （`context/assembler.py:61`）会读到神兽的中间产物（**污染**）。`TaskHandoff` 无 `session_id`
  字段（`orchestration/models.py:62`）⇒ 神兽条目 `session_id` 空串，压实按会话聚合时与主线未归组
  条目混为一组（二次污染）。
- **E38**：封存「无实现」——**判据订正**（见下）：spec `:89` 把「记忆分区封存」定义为
  `source=beast.*` **不再被主 loop read 命中**，是一条**效果**条款而非新 API 条款。
- **E39**：`pet-mode` spec `:75` 要求宠物追踪主人偏好（`MemoryEntry.source=user` 落 L2 facts 层），
  但 `PetSession.observe` 全仓库无**生产**调用 ⇒ `_preferences` 恒空、`surprise()` 恒 `None`
  ⇒ R6「偏好追踪」/R7「制造惊喜」在生产不可达。

主线（前台重大任务 / 后台自治）未被阻塞，属**承诺已声明、实现未接线**的覆盖完整性收敛。

## What Changes

- **E37（五处接线，一条命名空间原则）**：
  1. `DefaultLoop.__init__` 加 `source: str = "loop"` 注入面（**缺省保持 `"loop"`**，向后兼容），
     `remember` 用注入值替代硬编码；`arun` 已有的 `session_id` 参数不动。
  2. 组合根 `_beast_loop` 注入 `source=beast.agent_id`（即 `beast.<拼音>`，与 `BeastSession.remember`
     的 source 口径**同一写法**）。
  3. `TaskHandoff` 加 `session_id` 字段；`MultiAgentRouter.handoff` 转交子 loop（`arun(..., session_id=…)`）；
     `BeastManager.summon` 传 `beast.agent_id` ⇒ 神兽条目按自身会话归组，不再与主线未归组条目同组压实。
  4. `MemoryStore.read` 加**仅关键字**参数 `exclude_source_prefixes: tuple[str, ...] = ()`，
     在**排名与预算截断之前**过滤候选（被排除项不吃预算、不被 `reuse_count += 1` 强化）；
     **缺省 `()` ⇒ 检索语义逐字不变**（红线）。
  5. `DynamicAssembler` 加同形参数（缺省 `()`），组合根为主 loop 的装配器传 `("beast.",)`
     ⇒ 主 loop read 不命中任何神兽分区。
- **E38（判据订正，无新 API）**：封存 = 上述 ⑤ 的**效果**（`source=beast.*` 不再被主 loop read 命中）
  + `BeastManager.summon` 收尾的 `session.recall()`（已在位）。`beast/models.py:20` 的注释
  「已召回（记忆分区封存）」即该语义的文档；spec 无任何「seal/recall API」条款，故**不新造 API**。
- **E39（判据订正 + 一处接线）**：新增 `PetSession.observe_owner(text)`（**fail-soft**：无记忆后端 /
  写失败 ⇒ 静默跳过，入口不因偏好落库失败而失败），并接在**主人原话**进入宠物的三个入口：
  `PetActivator.activate_from_cli`（`rest`）/ `activate_from_nl`（`user_input`）/
  `PetControl.assign`（`goal`）。**不在 `wake()` 内 observe**：唤醒时宠物只在跑自己的任务，
  没有主人行为可观察；且 `/pet` 斜杠激活的 goal 是**合成文案**（`斜杠命令 pet.gather`），
  观察它等于**谎报**偏好（违反 R7「SHALL NOT 谎报」/ 账本 E26）。

## 判据订正（一手复核，两条）

| 账本原文 | 规格原文 | 订正 |
|---|---|---|
| E38「实现 seal/recall（按 source 冻结一段轨迹 / 召回封存记忆）」 | `beast-mode/spec.md:89`「记忆分区封存（`source=beast.*` 不再被主 loop read 命中）」（无 API 条款） | 封存是**效果**条款：由 E37 的 read 侧排除落地；**不新造 seal/recall API**。召回（复位）早已由 `Manual Recall` + `summon` 收尾的 `recall()` 实现 |
| E39「在 `PetSession.wake`（`:146/149`）及交互反馈路径调用 `observe`」 | `pet-mode/spec.md:231-234`「**生产入口激活**一只宠物**并观察主人偏好** ⇒ 偏好以 `source=user` 写入共享 L2」 | 观察点落在**主人原话入口**（激活 / 换活），**不在 `wake()`**：唤醒无主人行为可观察，且合成 goal 会谎报偏好 |

## Impact

- 受影响 capability：`beast-mode`、`pet-mode`、`memory`、`context`、`loop`、`orchestration`。
- **规格中性**：三条均为「实现回归既有契约」，无新增/修改 Requirement ⇒ `.openspec.yaml` 置
  `skip_specs: true`（同写 `schema`）。
- 行为变化：生产召唤的神兽轨迹由 `source="loop"` 改为 `source="beast.<agent_id>"` 且带
  `session_id`（主线不再命中）；主 loop 的上下文事实不再含 `beast.*`；经**生产入口**激活 /
  换活的宠物会把主人原话以 `source=user` 落 L2（有 `key: value` 形态者同时进 `_preferences`
  ⇒ `surprise()` 有数据）。
- 不影响：`read` 缺省检索语义（逐字不变）；`BeastSession.remember` 的既有 API 与
  `observe` 的异常面（`PET_PREFERENCE_WRITE_FAILED`）不变；斜杠入口（无主人原话）不写偏好。
- **已知局限（明示）**：① 主 loop 与神兽 loop **共享同一** `DynamicAssembler` 实例 ⇒ 神兽自身
  装配亦不命中 `beast.*`（本 spec 只要求主 loop 不命中，且神兽产物在自动回归时即封存，无场景要求
  神兽 recall 自身分区）；② 压实摘要（`_commit_summary`）的 `source` 恒为 `"compaction"`
  （`tests/test_memory.py:275` 已断言该口径）⇒ 神兽分区被压实后的**摘要**仍可被主 loop 读到
  ——按 source 命名空间隔离的**残留缺口**，登记待议，不在本 change 扩大改动面。
