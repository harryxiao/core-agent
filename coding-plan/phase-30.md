# Phase 30：Phase 28 遗留三条收口 —— 会话维度产物 id 唯一性（E48）＋「压缩续聊」取向（E44）＋ 主↔兽记忆隔离方向（E45-隔离 · 残留重判）

> **状态**：✅ **已闭（2026-10-06，change `0117`／ADR-0110）** —— 落地＝**§3 分支 A**（**E48-b ＋ E54 同批修**，规格先行：`skills` MODIFIED + `memory` ADDED + `beast-mode` MODIFIED）＋ **三条销账登记**（E48-a / E44 / E45-隔离(i)，零代码改动，见 §2 各条与 §7）。四门禁全绿（**1477 passed**，基线 1470 + 新增 7）。
> **定性**：承接 Phase 28 收口后的**全部剩余项**（Change A/B 已全闭，E46/E47/E49 已闭；余 E44 / E45-隔离 / E48）。三条**均非规格违约** ⇒ 沿用 Phase 28 口径：**不得以缺陷修复名义 `skip_specs` 强推**，实施与否须先裁决、再规格先行。
> **本 Phase 的一手增量**：复核时发现两条原判需要订正 —— ① **E45-隔离** 的「兽可读主」在 change `0114`（会话维度检索过滤）之后已被收窄为「**仅全局层**」，不再是「兽可读主全部记忆」；② 由此**浮现**真正的残留缺口 —— **兽读不到自己的 `beast.*` 轨迹**（原记于 ADR-0103 已知局限①，从未立账）⇒ 转正为 **E54**。行号均为 2026-10-06 复核值。

## 0. 一手核实（证据与行号）

| 编号 | 判据 | 代码实况（已逐字核实） |
|---|---|---|
| E48-a 压实产物 id 重数 | 同会话连续压实**静默覆盖** | `context/compactor.py:88-92`：`for i, line in enumerate(c.conclusions + c.decisions)` ⇒ `id=f"compaction.fact.{key}.{i}"` —— `i` **每次压实从 0 重数**；`MemoryStore.write` 为同 id **upsert** ⇒ 第二次压实的 fact 覆盖第一次。change `0114` 只补了**会话键** `key = session_id or "default"`（`:87`），**未**消同会话内覆盖 |
| E48-b `skills.miss` 计数器 | 进程内计数 + 跨会话共享 + 无上界 | `skills/router.py:65` `self.misses: list[str] = []`（**进程内、无上界**）+ `:147` append + `:150-154` `key = session_id or "default"` ⇒ `id=f"skills.miss.{key}.{len(self.misses)}"`。计数器是**全局** list ⇒ 进程重启从 0 重数 ⇒ **同名覆盖**；且 `misses` 随会话数**线性涨内存** |
| E44 压实 ≠ 压缩 | 单轮内 `ctx.messages` 零截断 | `loop/default.py:298` 触发 `_should_compact`（`:392` 定义）→ `_compact` 三步（persist/compact/forget）**全程不碰 `ctx.messages`**；`planner._build_request` 每轮发**全量** `ctx.messages`、**零截断** ⇒ 撞窗口是 `TOKEN_BUDGET_EXCEEDED` **强制终止本轮**，非「压缩续聊」。预算裁剪**存在于另一面**：`context/budget.py:25` `enforce(pack, budget)` 只裁**装配包**（system / facts），**不作用于对话历史** |
| E45-隔离 残留（重判后） | 方向性与实际可见面 | 主方向：`runtime.py:566` 主 loop 装配器传 `exclude_source_prefixes=("beast.",)` ⇒ **主不读兽**（phase-26 裁决，不动）。反方向：`_beast_loop`（`runtime.py:700-738`）**共用同一 `assembler`**（`:715` 派生）且**不额外排除** loop。**但** `beast/manager.py:72` `TaskHandoff(task=…, session_id=beast.agent_id)` → `orchestration/router.py:59` `profile.loop.arun(handoff.task, session_id=handoff.session_id)` ⇒ 兽的 `ctx.session_id` = `beast.<agent_id>`（**非空**）⇒ `0114` 的会话过滤生效（`context/assembler.py:69-73` → `memory/store.py:95`）⇒ 兽只能看到 **自身会话条目 + 全局层（`session_id == ""`）**，**看不到**主 loop 的会话级事实 |
| **E54（转正）** 兽读不到自身轨迹 | 前缀排除对 `beast.<agent_id>` 同样命中 | `memory/store.py:111-115`：`entry.source.startswith(exclude_source_prefixes)`（前缀元组匹配）；主装配器的排除前缀 `("beast.",)` **覆盖所有** `beast.<agent_id>` ⇒ 兽**自己**的 `source=beast.<agent_id>` 轨迹被**同一**排除挡掉 ⇒ **神兽无法召回自己的过往经验**（原记 ADR-0103 已知局限①，本次转正立账） |

**已裁决不动、不在本 Phase 范围**：E45-TCP 半条（`llm_provider/http_pool.py` `threading.local` 池）＝ADR-0064 有意取舍，登记已知局限，**不列为缺陷**。

## 1. 范围与定位

- **分层**：L2 记忆**写入面**（E48）／ L3 loop **上下文组装**（E44）／ L2 记忆**读取面**（E45-隔离、E54）。
- **不在范围**：不重建对话转录（change `0115`/`0116` 已闭）；**不破** `exclude_source_prefixes=("beast.",)` 的**主方向**排除（phase-26 E37/E38/E39 的隔离语义）；**不动** TCP 连接池；不给每个会话/每只兽建独立 `(loop, memory)` 实例（phase-19 E2 / change `0048` 已裁否决）。

## 2. 三条现状、残留与建议取向

### 2.1 E48 —— 会话维度产物 id 不唯一（**两个子面，取向不同**）

- **子面 (a) 压实产物 `compaction.fact.{key}.{i}`**：`i` 每次压实重数 ⇒ 同会话第二次压实覆盖第一次。
  **建议：判为「刷新式派生」⇒ 覆盖是意料之中，登记销账**。理由：facts 由**当前**记忆重新派生（`c._conclusions/c._decisions`）⇒ 新批次**取代**旧批次是刷新语义，而非丢失；保留旧批次会把**过时结论**重新喂进检索，污染装配面。
  反向若裁决「保留历史」⇒ **必须同时引入有界淘汰**，否则 L2 随压实次数线性膨胀（与 change `0115` / ADR-0108 已知局限②同类问题）。
  **✅ 已销账（2026-10-06 裁决「销账」）**：登记为**有意行为**（ADR-0110 登记项①），**零代码改动**。重开条件：若裁决「保留历史」，须**同批**引入有界淘汰。
- **子面 (b) `skills.miss.{key}.{len(self.misses)}`**：计数器**进程内**（重启归 0 ⇒ 覆盖）+ **跨会话共享**（`misses` 是单一全局 list）+ **无上界**（内存线性涨）。
  **建议：修**。理由：misses 是**事件记录**（「路由未命中: <任务原话>」），被覆盖即**真丢数据**（与 (a) 的刷新语义不同）；且 list 无上界是独立的内存问题。
  修法（择一，实施时定）：id 改**内容/时间派生**（`hash(content)` 或随库落盘的单调序号）；`misses` 改**有界**（`deque(maxlen=N)` 或计数随库落盘）。
  **✅ 落地（change `0117`）**：id 取 **`blake2b(task, digest_size=8)` 内容派生**（**不**用 `hash()` —— str 有逐进程随机盐 `PYTHONHASHSEED` ⇒ 跨进程不稳定＝没修；先例同包 `skills/sop.py:_skill_id_for`）；`misses` **保留 `list`** 只做**原地裁剪**至 `_MISS_WINDOW = 64`（换 `deque` 会静默打断 6 处 `== [...]` 断言）。同会话重复未命中**同一任务** ⇒ **幂等刷新同一条**（未命中清单本就按任务去重、供沉淀）。

### 2.2 E44 —— 压实 ≠ 压缩（**建议销账，登记为有意行为**）

- **现状**：`_compact` 是**记忆维护**（persist/compact/forget），**不裁 `ctx.messages`**；`_build_request` 每轮发全量 `ctx.messages`、零截断 ⇒ 超窗口时**强制终止本轮**（「抢救 + 强制终止」）。
- **与 change `0115` 的关系（须写清，避免误判「已被 E49 消解」）**：E49 补的是**跨轮**历史（`LoopContext.history` + `loop.history_turns`，且自身有 `min(最近 N 轮, token_budget//2)` **双上界**）；E44 指的是**单轮内** `ctx.messages` 无截断。**两者不同面，E44 的问题面未因 0115/0116 减弱。**
- **建议：登记为有意行为销账**（先例：phase-19 E6「压实启发式为有意行为」订正）。四条理由：
  1. **预算已可配**：`llm.context_window` / `loop.output_reserve` / `loop.max_rounds` 三层可配（change `0098`/ADR-0091）⇒ 窗口与预算可由用户放宽，「终止」不再是唯一出路；
  2. **跨轮失忆已解**：`0115` 的有界历史回灌使多轮连贯不再依赖单轮全量历史；
  3. **摘要替换引入不可复现的二次生成与信息损失** —— 与「记忆先行、代码后置」及「不谎报（落盘模型原话）」的既有取向相冲突；
  4. 现状**不静默**：超预算以 `TOKEN_BUDGET_EXCEEDED` 显式终止并落痕，非无声截断。
- **若裁决「真做压缩续聊」**（修法备查）：`_build_request` 前对 `ctx.messages` 做摘要替换（保留 system + 压缩中段 + 尾部近窗），或 `_compact` 中把旧历史替换为 compactor 产出的摘要 Message；须**规格先行**（`loop` spec 增条款）+ 明确摘要的**可追溯性**与**不落盘为模型原话**的红线。
- **✅ 已销账（2026-10-06 裁决「销账」）**：登记为**有意行为**（ADR-0110 登记项②），**零代码改动**；§3 分支 B **不开工**。重开条件：若裁决「真做压缩续聊」，按上条修法备查走独立 change。

### 2.3 E45-隔离 —— 残留重判（**大部分已闭，余两条**）

- **判据订正**：Phase 28 §0 记「`_beast_loop` 不排除主 loop 记忆 ⇒ 兽可读主」。经复核，change `0114` 之后该表述**过宽** —— 兽的 `ctx.session_id` 非空（`beast/manager.py:72` → `router.py:59`），会话过滤生效 ⇒ 兽**读不到主 loop 的会话级事实**。
- **残留 (i) 全局层共享**：主与兽**同读**全局层（`session_id == ""`：L0 人格规则、`notes`、未归属存量条目）。这是用户「**严格隔离 + 保留全局层**」裁决的**有意结果** ⇒ **建议登记销账**（不重复裁决）。
  **✅ 已销账（2026-10-06 裁决「销账」）**：登记为**有意行为**（ADR-0110 登记项③），**零代码改动**。
- **残留 (ii) 兽读不到自身轨迹**：**转正为 E54**（见 §2.4）。
- **TCP 半条**：已裁决不改（ADR-0064）。

### 2.4 E54（本 Phase 转正）—— 神兽无法召回自身过往轨迹

- **缺陷**：主装配器的排除前缀 `("beast.",)` 是**前缀匹配**（`memory/store.py:111-115`），把**所有** `beast.<agent_id>` 一并挡掉；而 `_beast_loop` **共用同一个 assembler**（`runtime.py:715`，装配器在 `:560-567` 一次性构造）⇒ **兽自己也检索不到自己的轨迹**。
- **定性**：**非规格违约**（`beast-mode` spec 要求的是「神兽轨迹**不进主 Agent** 检索」，未要求「兽读不到自己」）；属**接线副作用**（ADR-0103 已知局限①，本次立账）。
- **建议：修**。修法（择一）：① 兽用**独立装配器**（排除集按兽裁剪 —— 排除 `loop` 与**他兽**前缀，放行 `beast.<自身 agent_id>`）；② 排除面从「前缀元组」升为「**谓词**」（`memory/store.py` 的 `exclude_source_prefixes` 语义扩展，须评估对既有调用方的影响）。
- **红线**：修 E54 **不得**放宽「主不读兽」（`exclude_source_prefixes=("beast.",)` 在主装配器上逐字不动 —— 那会破 phase-26 的 E37/E38/E39 隔离语义）。
- **✅ 落地（change `0117`）**：采修法①的**最小面** —— 记忆读取面新增 `allow_source_prefixes`（排除面的**例外面**，「命中排除**且未**命中放行 ⇒ 剔除」），神兽经 `DynamicAssembler.with_allow_source_prefixes(beast.agent_id)` **派生**装配器（排除面逐字继承、放行面 = 自身 `agent_id`）。**判据订正**：原修法①含「排除 `loop`」一项，**不纳入** —— ① 不解决 E54；② 只能摘掉主 loop 一个来源（主 L2 事实还来自 `context`/`skills`/`orchestration`/`pet`）⇒ 隔离面不一致；③ 与 `memory/spec.md`「按会话隔离的检索」（推理面**必须保留全局层**）相悖。**未**采用修法②（谓词）—— 前缀元组 + 例外面已够，谓词会把排除语义从数据升为可执行对象，扩大调用方影响面。

## 3. 落地拆解（按裁决结果分支）

> 顺序（若实施）：裁决 → **规格先行**（按命中的 spec 改条款）→ 测试先行（红）→ 实现 → 四门禁全绿 → 手工归档 → `openspec validate --all` 30-0。

### 3.1 分支 A：E48-b（`skills.miss` id 唯一化 + 有界）＋ E54（兽可读自身轨迹）—— **✅ 已落地（change `0117`／ADR-0110）**
- 体型相近、互不耦合、两者**均可独立修**（无需先裁决隔离语义）⇒ 可作**同一 change** 落地。
- spec 触点：E48-b ⇒ `skills` spec（未命中记录的 id 唯一性/有界）；E54 ⇒ `beast-mode` spec（神兽可召回自身经验）+ 可能的 `memory` spec（排除面语义）。**非 `skip_specs`**。
- 测试：E48-b ⇒ 同会话多轮未命中不互相覆盖 + 计数器有界；E54 ⇒ 兽检索**含**自身 `beast.<agent_id>` 条目、**不含**他兽与主 `loop` 条目（双向守门）。
- **实际落地（3 份 delta 均为规格先行，非 `skip_specs`）**：`skills`（MODIFIED「技能路由」—— bullet「未命中记录的归属与唯一性」+ 3 场景）、`memory`（ADDED「来源前缀排除与放行（读取面）」+ 4 场景）、`beast-mode`（MODIFIED「Independent Sub-Agent with Shared Capability」—— bullet「自身轨迹可召回」+ 2 场景）。实现：`memory/store.py`（`allow_source_prefixes`）、`memory/protocol.py`（**顺带补 `session_id` 骨架漂移**）、`context/assembler.py`（构造参数 + `with_allow_source_prefixes` 派生方法）、`runtime.py`（神兽装配器改派生）、`skills/router.py`（`blake2b` id + `_MISS_WINDOW` 原地裁剪）。7 个新用例**先红后绿** ⇒ 四门禁全绿 **1477 passed**。
- **判据订正（照实记，收尾已明示用户）**：测试口径「不含主 `loop` 条目」收窄为「不含主 loop 的**会话级**条目」—— 依 §2.4 的同一理由（推理面**保留全局层**；且主 L2 事实还有 `context`/`skills`/`orchestration`/`pet` 四个来源，单独排除 `loop` 会造成隔离面不一致）。

### 3.2 分支 B：E44（若裁决「真做压缩续聊」）
- **独立 change**（改的是 LLM 可见语义，风险面最大）：`loop` spec 新增压缩续聊条款 + 摘要可追溯性裁定；`planner._build_request` / `_compact` 改造。
- 测试：超窗口轮次**不再终止**而走摘要替换；摘要来源可追溯；`history_turns=0` 等既有路径逐字不变。

### 3.3 分支 C：三条均裁「销账」（E48-a / E44 / E45-隔离(i)）
- **零代码改动**，只做**登记**（回填本 Phase + Phase 28 §7 红线 + ADR 已知局限）⇒ 走规格中性 `skip_specs`（`.openspec.yaml` 须同写 `schema` + `skip_specs: true`）。

### 3.4 门禁（任分支）
- `.venv/bin/ruff check src tests` / `.venv/bin/ruff format --check src tests` / `/home/harry/.praisonai/venv/bin/pyright`（**0/0/0**）/ `.venv/bin/pytest -q`；**直连二进制，禁 `uv run`**。
- 有 spec 改动 ⇒ `openspec validate --all` 须 30 passed / 0 failed（归档前后各一次）。

## 4. 裁决点（须用户拍板，未拍板不得开工）

| # | 裁决点 | 建议取向 |
|---|---|---|
| 1 | **E48-a** 压实产物：刷新式覆盖（销账）vs 保留历史（须**有界淘汰**） | **销账**（刷新式派生，保留会污染检索） |
| 2 | **E48-b** `skills.miss`：修（内容/时间派生 id + 有界）vs 维持 | **修**（事件记录被覆盖即真丢数据 + list 无上界） |
| 3 | **E44**：「压缩续聊」真做 vs 登记为**有意行为**销账 | **销账**（预算已可配 + 跨轮已解 + 摘要违「不谎报」+ 先例 phase-19 E6） |
| 4 | **E45-隔离(i)** 全局层共享：登记销账 vs 追加隔离 | **销账**（0114 用户裁决的有意结果，不重复裁决） |
| 5 | **E54** 兽可召回自身轨迹：修 vs 登记为已知局限 | **修**（现为接线副作用，兽实为「无自身经验」） |

**裁决结果（2026-10-06，用户「全部按建议」）**：① **销账** · ② **修** · ③ **销账** · ④ **销账** · ⑤ **修**
⇒ 落地＝**§3 分支 A**（**E48-b ＋ E54 同一 change**，规格先行）+ **E48-a / E44 / E45-隔离(i) 三条登记为有意行为**（无代码改动，随该 change 一并回填 ADR 与 Phase 28 §7）。

## 5. 去重边界

- **不重复** phase-28 已闭三条（E46 结果可见性 / E47 会话隔离 / E49 转录落盘，均 change `0113`–`0116`）；本 Phase 只接**剩余** E44 / E45-隔离 / E48。
- **不重复** phase-26（E37/E38/E39：`source` 命名空间**写入侧注入 + 读取侧排除**）—— 本 Phase 的 E54 是同一装配面的**副作用残留**，**不动**主方向排除语义。
- **不重复** phase-29（E50–E53：编排**运行态**与导航）—— 那是调度/可见性维度，本 Phase 是记忆/上下文维度。
- **不重复** phase-27（进化引擎原生执行器）。
- **不重复** E47 与 E48 的边界说明（"归属" vs "id 唯一性"）已在 phase-28 §5.1/§6 写清。
- **不转正为缺陷**：E45-TCP 半条（ADR-0064 有意取舍）。

## 6. 收口（2026-10-06，全部完成）

1. ✅ §4 **五处裁决点**已拍板（用户「全部按建议」）。
2. ✅ 落地 **§3 分支 A**（**E48-b + E54**，change `0117` 单 commit）；**§3 分支 B 不开工**（E44 已销账）；**§3 分支 C 三条登记**已随 ADR-0110 与 §2 各条回填。
3. ✅ 已回填 `README.md` 总索引与 `phase-28.md` §7/§8 指针。
4. ✅ 四门禁全绿（1477 passed，基线 1470 + 新增 7）；`openspec validate --all` 归档后 **30 passed / 0 failed**。

## 7. 账本（本 Phase 收口后的状态）

| 项 | 处置 | 落点 |
|---|---|---|
| **E48-b**（`skills.miss` 计数器） | **已修**（内容派生 id + 有界窗口） | change `0117` / ADR-0110 决策①②；spec `skills` MODIFIED |
| **E54**（神兽读不到自身轨迹） | **已修**（排除面的例外面 + 派生装配器） | change `0117` / ADR-0110 决策③④⑤；spec `memory` ADDED + `beast-mode` MODIFIED |
| **E48-a**（压实产物重数） | **销账**（刷新式派生，有意行为） | ADR-0110 登记项① |
| **E44**（压实 ≠ 压缩） | **销账**（有意行为；分支 B 不开工） | ADR-0110 登记项② |
| **E45-隔离(i)**（全局层共享） | **销账**（用户「保留全局层」裁决的有意结果） | ADR-0110 登记项③ |
| **E45-TCP 半条** | 不动（ADR-0064 有意取舍） | 见 §0 尾注 |
| **顺带闭合** | `memory/protocol.py` 的 `read` **协议骨架漂移**（change `0114` 只改实现未同步 Protocol） | change `0117` 实现 |
| **新登记（观察项，用户裁决前挂账）** | 宠物 loop（`_pet_loop`，`runtime.py:890-922`）的 `LLMPlanner`（`:903-909`）**共用主装配器 `assembler`**（`:907`）且 `DefaultLoop`（`:902`）**不传 `source=`** ⇒ 宠物记忆以默认 `source="loop"` 落库、进**主命名空间**（phase-26 为神兽建的命名空间隔离，宠物**未**接） | 见 `phase-28.md` §9「遗留清单」（**待裁决**） |

## 8. 遗留清单（Phase 30 全闭后仍在册项）

**A. 待裁决（唯一未决项）**

| 项 | 内容 | 决策点 |
|---|---|---|
| 宠物记忆命名空间 | `_pet_loop`（`runtime.py:890-922`）`DefaultLoop`（`:902`）**不传 `source=`** ⇒ 宠物轨迹以默认 `source="loop"` 落库，**进主命名空间**（主 Agent 检索得到），且无「宠物专属分区」；对照神兽（`source=beast.<agent_id>` + 装配器排除/放行）。**契约面上 `pet-mode` spec 未要求独立命名空间** ⇒ **非违约**，属**接线缺口**。 | ① **立账并修**（宠物接 `source="pet.<pet_id>"` + 与神兽同形的派生装配器；须**规格先行**，且注意 `pet-mode` spec `:249`/`:255` 的隐私条款）；② **销账**（判「宠物记忆**有意**与主人共享」——今天宠物主人偏好走全局层，若共享是设计意图则只须**补一句 ADR 说明**）。**建议**：先裁「宠物记忆**是否应与主人隔离**」，再决定修法 |

**B. 已知局限（有意行为 / 已裁决不改，非缺陷）**

| 项 | 出处 | 内容 |
|---|---|---|
| 放行面是**前缀**匹配 | ADR-0110 局限① | 若未来出现「一个 `agent_id` 是另一个的前缀」的命名，放行自身会连带放行他者 ⇒ 须改精确匹配（今天 `beast.<拼音>` 不会） |
| 内容派生后**丢「未命中次数」频次** | ADR-0110 局限② | 同会话对同一任务只留一条；本来无人消费，如需要须另立计数列（**不复用 id**） |
| `misses` 窗口裁剪后**全量未命中不可回溯** | ADR-0110 局限③ | 诊断面牺牲；事件面以 L2 条目为准 |
| 神兽仍读不到**他兽**命名空间 | ADR-0110 局限④ | **有意**（与封存同向） |
| E45-TCP 半条 | ADR-0064 | 「跨线程同一条 TCP」非规格要求，**已裁决不改** |

> **登记项（本 change 零代码改动）**：E48-a 销账 / E44 销账 / E45-隔离(i) 销账 —— 见 §7 表与 ADR-0110 登记项①②③。
