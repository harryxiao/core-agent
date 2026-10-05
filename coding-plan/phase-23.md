# Phase 23 — 新增「文档化记忆（notes）」capability（canonical Markdown 真相层 + Consult→Build→Update 循环）

> **定位**：把开源项目 [operator-memory](https://github.com/aerovato/operator-memory) 的「Markdown 文档化记忆」机制，作为 core-agent 的**新 capability `notes`** 第一方落地。该机制**无需 RAG / embedding**：Agent 用**人类可读的 canonical Markdown 文件**持续记录「决策记录 / 研究笔记 / 提交记录 / 解决过程」，按主题**覆盖式更新**（去重、精炼、保持权威），并沿 **Consult（先读笔记）→ Build（干活）→ Update（写回笔记）** 循环运转。
>
> **结论总览（一手核实）**：
> - **不能直接安装 operator-memory 本体**：它是 TypeScript + npm 分发，仅适配 Claude Code / Codex 等**外部 harness**（通过 MCP / CLI 协议注入）；而 core-agent 的 `plugin_registry` 是**进程内注册表**（内存登记 `plugin_id → 实例`），**无外部插件加载路径**，无法挂载 TS 插件。强行装会破坏「聊天数据解构」，且与 core-agent 自身的 memory / loop 生命周期割裂。
> - **应新增 capability `notes`**：复用三处现成基建——① `MemoryBackend` Protocol（`memory/protocol.py` 可插拔后端，新增 `MarkdownBackend` 实现）；② `Skill.instructions`（`skills/models.py:24`，承载循环指令文本，注入「先 Consult 后 Update」的作业纪律）；③ `SkillLibrary` / `SopExtractor` 先例（已有「从任务提炼技能/流程」的落库通路可仿照）。
> - **与现有 RAG memory 并列互补，不推翻现有基建**：RAG memory（`MemoryStore` + `FileBackend`）负责**语义召回**（episodic/semantic 片段）；`notes` 负责**权威真相层**（人类可读、可 diff、可 review 的 canonical 文件）。二者不互斥，各司其职。
>
> **去重口径**：本 Phase 是**新增能力**，不涉及 phase-20（C 类后端接线）/ phase-21（evolution 归因）/ phase-22（observability/rag/skillhub 缺陷）的任何已列项；也不修改现有 `MemoryStore` / `FileBackend` / RAG 链路语义。

---

## 0. 参照设计（Operator-Memory 官方 docs 提取）

> 摘自官方 [docs/comparison.md](https://github.com/aerovato/operator-memory/blob/main/docs/comparison.md) 与 [docs/architecture.md](https://github.com/aerovato/operator-memory/blob/main/docs/architecture.md)，是 `notes` 的**权威设计依据**。claude 落地时**逐条对齐**，但必须按 §0.3「落地映射」做 core-agent 化适配（**不机械照搬** TS 目录/三分区）。

### 0.1 comparison.md — 为何不用 RAG（「replay 失败」论据，支撑 §2/§4 决策）

1. **市面所有 memory 插件同构流水线**：遍历会话记录 → 生成记忆片段 → 插入 RAG 库 → 每次 prompt 检索 top-k 注入 → 不够再给搜索工具。所有「多层记忆分类 / 后台合并去重 / 梦境重写 / 持续压缩 / 重排器」都是**架在同一坏地基上的脚手架**。
2. **Replay 失败五因**（逐条对应 §2 缺口现象）：
   - **相似度召回**：过时决策与它的替代决策并列返回，模型自己猜哪个 current——系统不知道哪个最新。
   - **无上下文存储**：片段容量有限，提取时已丢弃动机/教训/约束/理由，检索永远补不回没存过的信息。
   - **过去当真相**：记忆反映捕获时刻；代码天天变，store 不变，nothing supersedes anything。
   - **搜不到「不知道」的**：搜索工具要求 agent 先意识到缺上下文、再拼出能命中的 query；agent 不知道它不知道什么。
   - **不可审计**：数千 embedding 躺在库里，看不见哪些 stale、哪些从未被检索、哪些在悄悄影响行为。
3. **叠床架屋的失败**：snippet 捕获（到手即损、从此陈旧，矛盾累积成竞争记录而非唯一真相）；memory CRUD 工具（让 agent 管理数据库，而一篇文档表达得更好）；压缩（historian 在上下文压力下重写，沉淀零可审真相）；后台维护（dreamer/curator/verifier 全天烧 quota，维护打不开、不可审、不可信记录）。
4. **Operator 反其道**：`AGENTS.md` 方向对但单文件不够——agent 需要**整个 brain** + 工作流里的写入位置；循环从 `prompt → build → forget` 改为 `prompt → consult → build → update`；memory 从「bolt-on 数据库」变成「**可读、可编辑、可 commit、可分享的 workspace**」；**确定性加载、失败可见、知识与代码同进 Git**。
   > 无向量库、无 embedding、无 summarizer/curator/dreamer、无黑盒检索。**「RAG agents recall. Operator understands.」**

### 0.2 architecture.md — The Brain 与确定性加载（支撑 §2/§3 修复方向）

1. **The Brain = 磁盘知识空间**，按 ownership 分三区：
   - `~/.operator/user/` — 用户/全局分区（偏好、标准、可复用技能）
   - `.operator/` — 项目私有分区（首次 setup 即 Git-ignored）
   - `.operator-shared/` — 项目共享分区（随仓库发布，激活时才建）
   - 指令冲突层级：**Private > User > Shared**。
   - **Memory 不是独立数据库，是持续文档化产生的 durable knowledge。**
2. **What Loads（preamble 轻量入口）**：每次会话启动确定性加载——Operator Guidance（固定框架规则）、Operator Instructions（各分区 `operator.md` 按 authority 合并）、Partition Catalogs（各分区 `catalog.md`）、主 Project Index（`index/index.md`）、warnings/diagnostics。**其余 specs/plans/research/guides 留盘、按需 deliberate read**——同一启动产生同一 orientation，不靠相似度挑片。
3. **The Maps（两种路由）**：**Partition Catalogs map the Brain**（每条说明某文档覆盖什么、何时打开）；**Project Indexes map the codebase**（每条带 description + `read_if` 条件，条件命中才开子索引）。Freeform 文档经 catalog 引导读取，**绝不自动选择注入**。
4. **No RAG**：用 coherent documents + explicit maps 替代，无需 embedding / 向量库 / reranker / 自动语义注入。
5. **Failure Is Visible**：Brain 会 stale（上游大改或 agent 忘记更新），但失败留在普通文件里——**可审、可纠正**。

### 0.3 落地映射（claude 实现时照此适配，勿机械照搬）

| 官方机制 | core-agent `notes` 落地 |
|---|---|
| The Brain 三分区（user/private/shared + Private>User>Shared 层级） | MVP 简化为**单一 canonical 目录**（对齐 §1.2「单 Agent 单工作区」）；多分区与权威层级列为后续扩展点，**不照搬三区** |
| Preamble 确定性加载（Guidance+Instructions+Catalogs+Index） | 映射为 **loop 任务前 Consult 钩子**：确定性读 `NoteStore.consult(query)` 命中的 note + `list()` 清单，**不自动全量注入**，与官方「留盘按需读」同构 |
| Partition Catalog（map the Brain） | 映射为 `NoteStore.list()`（canonical 文件清单）+ 每个 note 头部 metadata（title/tags/`## Search Queries`）；可选一张 `notes/catalog.md` 索引，MVP 不强制 |
| Project Index（map the codebase） | **不重复造**：core-agent 已有代码索引/导航能力，notes 层只管文档化真相，避免职责重叠 |
| No RAG / 无 embedding | `MarkdownBackend.search` 走标题/tags/头部 `Search Queries` 关键词匹配，**不建向量库**（对齐 §1.2） |
| Failure Is Visible | `put` 覆盖式 + 原子写 + 可 git diff，陈旧/漏更以普通文件呈现，**可审可纠正** |
| Consult→Build→Update 循环 | 内置 `skills.notes.consult_build_update` Skill，`instructions` 承载纪律（见 §3） |

---

## 1. 范围与定位

- **分层图位置**：L2（记忆层）新增「**文档化真相层**」——与既有 RAG 语义召回层（L2 memory）并列；L3（运行时装配 / runtime capability）装配 `NoteStore` 插件 + 循环指令注入。
- **覆盖 capability**：新增第 30 个 capability `notes`（文档化记忆 / canonical Markdown 真相层）。复用 `contracts_summary.md` §memory（`MemoryStore`/`Crystallizer`/`MemoryBackend`）与 §skills（`SkillLibrary`/`SkillRouter`）的既有接口。

### 1.1 范围（3 个缺口 + 复用/新建点）

| # | 缺口 | 严重度 | 现象（一手核实，含行号） |
|---|---|---|---|
| **1** | **无「文档化真相层」**：记忆只有 RAG 扁平片段，无权威 canonical 文件 | **P1** | 现有 memory 只有 `MemoryStore`（`read/write/migrate/compact/forget`，语义召回）+ `FileBackend`（RAG 落盘）。`MemoryEntry` 是扁平条目（`id/layer/content/tags/source/trace_id/reuse_count/ts/session_id/importance/kind`），**无「按主题覆盖式更新的 Markdown 文件」这一形态**——决策/研究/解决过程散落在语义片段里，无法人类 review、无法 diff、无法跨会话权威沉淀。 |
| **2** | **无 Consult→Build→Update 循环指令载体** | **P1** | loop 主循环（`loop/default.py`）只有 `_trace`/`_maintain` 等生命周期，**没有「任务前先读相关笔记、任务后把新发现写回笔记」的纪律注入点**。operator-memory 的核心价值不在存储，而在**这套循环纪律**——缺它，笔记层即使建起来也不会被 Agent 自觉 Consult/Update。 |
| **3** | **外部插件不可装载**（为何不能直接装 operator-memory） | **P0（决策前置）** | `plugin_registry` 是进程内注册表（内存 `plugin_id → 实例`），**无外部插件加载路径**；operator-memory 是 TS+npm 分发、适配 Claude Code/Codex 等外部 harness 的 MCP/CLI 协议，**与 core-agent 的 Python 运行时 + 进程内插件契约不兼容**。结论：不硬塞外部插件，改为第一方 capability。 |

### 1.2 明确不做

- **不安装 / 不包装 operator-memory 本体**（TS 运行时、外部 harness 协议均不引入；不搞「进程桥接 TS」）。
- **不改现有 RAG memory 语义**：`MemoryStore` / `FileBackend` / `LLMEmbedder`（`runtime.py:84/272`）照旧，`notes` 与之**并列**而非替代。
- **不引入 RAG/embedding 到 notes 层**：`notes` 走 Markdown 文件 + 关键词/标题匹配（必要时可复用既有 `search` 接口做轻量检索，但**不建向量库**），保持「人类可读、可 diff、可 review」的第一性。
- **不碰 phase-20 / phase-21 / phase-22 已列项**（E27/B2/C7/C8、evolution 归因、observability/rag/skillhub 缺陷）。
- **不做多用户 / 分布式文件锁之外的协作语义**：单 Agent 单工作区为 MVP 边界（文件并发只做进程内 + 原子写）。

---

## 2. 缺口 1 — 无「文档化真相层」（canonical Markdown 缺失，P1）

### 2.1 现象与根因

- **现象**：决策记录 / 研究笔记 / 提交记录 / 解决过程只能进 RAG 语义片段，**没有「一个主题一个权威 Markdown 文件、内容覆盖式更新」的真相层**。跨会话后「上次怎么定的、结论是什么、为什么」散落在 embedding 里，既不能人类直接读，也不能 diff 追溯。
- **根因**：memory 契约只声明了「语义读写（`read/write/search`）+ 生命周期（`migrate/compact/forget`）」这一套 **RAG 式模型**；`MemoryBackend` Protocol（`memory/protocol.py`）虽**可插拔**，但 MVP 只实现了 `FileBackend`（RAG 落盘），**从未实现「文件即真相、覆盖式更新」的 Markdown 后端**。

### 2.2 修复方向

- **模块（新建）**：`src/core/notes/`（models.py / backend.py / store.py / __init__.py）。
- **数据模型**：`NoteEntry`（`note_id` / `path`（canonical 文件相对路径）/ `title` / `content` / `tags` / `updated_at` / `source`）——独立于 `MemoryEntry`（后者是 RAG 条目，二者职责不同，不强求同构）。
- **后端**：`MarkdownBackend` **实现既有 `MemoryBackend` Protocol**（复用 `get/put/search/list_index/delete` 签名），底层为文件系统操作：
  - `put` = **覆盖式更新**指定主题的 canonical Markdown 文件（不是 append 日志；保留头部 `## Search Queries` / `### Search Result` 结构，供关键词命中）。
  - `list_index` = 列出所有 canonical 文件（`IndexEntry` 映射为文件清单）。
  - `search` = 标题 / tags / 头部 `Search Queries` 关键词匹配（**不建向量库**，必要时可调既有 embedding 做标题级召回，但 MVP 不强制）。
  - 原子写：先写临时文件再 `os.replace`，避免半截写入。
- **存储门面**：`NoteStore`（实现 Plugin 契约，供 runtime 装配），暴露 `consult(query)` / `update(note)` / `ensure(topic)` / `list()`。
- **验收**：
  - 一条单测：`put` 同主题两次 → 断言文件内容为**第二次**（覆盖式，非两段拼接）；`list_index` 返回文件清单；`search` 命中头部 `Search Queries` 关键词。
  - 一条集成测试：`NoteStore.consult` → `update` → 再次 `consult` 能读到更新后的内容（读写闭环）。
  - 原子写测试：并发/异常路径下 canonical 文件不出现半截内容。
- **官方参照**：§0.1（replay 失败五因）+ §0.2（The Brain / No RAG）+ §0.3 映射（单一 canonical 目录 / 覆盖式 put / Failure Visible）。

---

## 3. 缺口 2 — 无 Consult→Build→Update 循环指令载体（P1）

### 3.1 现象与根因

- **现象**：即便 §2 的笔记层建好，loop 也不会**自觉**「先读笔记再干活、干完把新发现写回」。operator-memory 的真正价值在**循环纪律**，而非存储。
- **根因**：loop 主循环（`loop/default.py`）无「任务前 Consult / 任务后 Update」的纪律注入点；而 core-agent **已有**承载「怎么做一件事」的载体——`Skill.instructions`（`skills/models.py:24`，`instructions: str = ""`）——只是从未用它注入**笔记循环纪律**。

### 3.2 修复方向

- **内置循环 Skill**：注册一个内置技能 `skills.notes.consult_build_update`，`instructions` 承载循环指令文本（任务前 `NoteStore.consult` 相关主题 → 执行任务 → 任务后 `NoteStore.update` 把「决策/结论/解决过程」覆盖式写回 canonical 文件）。
- **接线**：loop 主循环的**任务前 / 任务后钩子**（具体行号由落地时定位，参照 `loop/default.py` 现有 `_trace`/`_maintain` 生命周期）注入该 Skill 的 Consult/Update 动作；`SkillRouter`（`contracts_summary.md` §skills）负责按 `task_types` 命中该循环技能。
- **仿照先例**：`SopExtractor` / `SkillLibrary` 已有「从任务提炼技能并落库」通路，本 Phase 的循环纪律可仿照其「提炼 → 落库 → 后续命中」模式接入。
- **验收**：
  - 一条集成测试：驱动 loop 跑一个「含新结论」的任务 → 断言任务前触发了 `consult`、任务后触发了 `update`，且对应 canonical 文件内容含新结论。
  - 断言 `skills.notes.consult_build_update` 的 `instructions` 非空且含「先 Consult、后 Update」两段纪律。
  - `ruff`/`pyright`/`pytest` 全绿。
- **官方参照**：§0.1.4（prompt→consult→build→update 循环）+ §0.2.2（preamble 确定性加载）+ §0.3 映射（Consult 钩子 / 不自动全量注入）。

---

## 4. 缺口 3 — 外部插件不可装载（为何不能直接装 operator-memory，P0 决策前置）

### 4.1 现象与根因

- **现象**：用户期望「直接安装 operator-memory 开源项目」满足需求。
- **根因（一手核实）**：
  1. operator-memory 是 **TypeScript + npm** 分发，通过 MCP / CLI 协议注入 **Claude Code / Codex 等外部 harness**，**不是** Python 库，也**不是** core-agent 的进程内 Plugin。
  2. core-agent 的 `plugin_registry` 是**进程内注册表**（内存 `plugin_id → 实例`），**无外部插件加载路径**——没有「加载并运行一个 TS 插件」的能力。
  3. 即便硬桥接 TS 运行时，也会与 core-agent 的 loop / memory 生命周期割裂，并破坏用户已在意的「聊天内容数据解构」。

### 4.2 修复方向（结论：第一方 capability，而非外部插件）

- **决策**：**不引入外部插件加载**（phase-23 不扩展 `plugin_registry` 的外部装载能力——那属于另一个更大议题），改为**第一方 capability `notes`**，按 §2 / §3 落地。
- **理由**：core-agent 已有承载所需能力的全部基座（可插拔 `MemoryBackend` + `Skill.instructions` 循环载体 + `SkillLibrary`/`SopExtractor` 落库通路），第一方落地的成本远低于「引入 TS 运行时 + 外部插件协议」，且与既有 loop/memory 生命周期同构、可被 evolution 体系覆盖（plugin 维度）。
- **验收**：无需「加载外部插件」的验收；以 §2 / §3 的验收点为准，外加「`plugin_registry` 不改动」的守护（git diff 证明未引入外部装载路径）。
- **官方参照**：§0.1（replay 失败五因佐证「不 RAG」的正当性）+ §0.3 映射（无向量库 / 无 embedding）。

---

## 5. 契约对齐

新增 capability `notes` 属**新契约**，按 SDD「先出 spec delta 再写代码」：

- **spec delta（ADDED）**：新增 `doc/openspec/specs/notes/spec.md`，声明 Purpose「为 Agent 提供人类可读、可 diff、可 review 的文档化权威真相层，覆盖式更新 canonical Markdown 文件，沿 Consult→Build→Update 循环运转」；明确 Requirement 覆盖 `NoteStore.consult/update/ensure/list`、`MarkdownBackend` 实现 `MemoryBackend` Protocol、循环 Skill 注入。
- **接口文档**：新增 `doc/03-interfaces/notes-interface.md`，声明 `MarkdownBackend` 复用 `MemoryBackend` Protocol 签名（`get/put/search/list_index/delete`）与 `NoteStore` 门面接口 + 错误码（如 `NOTE_NOT_FOUND` / `TOPIC_EXISTS`）。
- **速查表**：`contracts_summary.md` 追加 `30. notes` 行（capability id / 接口 / 数据类型 / 错误码），标注「文档化记忆（canonical Markdown 真相层 + Consult→Build→Update 循环）」。
- **复用既有契约（不改）**：`MemoryBackend` Protocol（`memory/protocol.py`）与 `Skill.instructions`（`skills/models.py:24`）**只复用、不修改**；`SkillLibrary`/`SkillRouter` 契约不变。

> **口径**：顺序为「spec delta（ADDED notes）→ 接口文档 → 代码（`src/core/notes/`）→ 速查表同步」。新增能力**不得**先写代码后补规格。

---

## 6. 门禁验收

- [x] `ruff check` 全绿。
- [x] `pyright` 0 errors。
- [x] `pytest` 全绿（新增用例覆盖 §2.2 / §3.2 各验收点）。
- [x] **本 Phase 专属校验**：
  - 新增 `doc/openspec/specs/notes/spec.md`（ADDED delta）+ `doc/03-interfaces/notes-interface.md` 已落盘。
  - `MarkdownBackend` 实现 `MemoryBackend` Protocol，且 `put` 为**覆盖式**（同主题二次 put 不产生拼接）。
  - 内置 `skills.notes.consult_build_update` 技能已注册，`instructions` 含「先 Consult、后 Update」纪律，loop 任务前/后钩子已接线。
  - `contracts_summary.md` 已追加 `29. notes` 节 + 总览行（**计划书写 30 有误**：仓内实际最后一节为
    `28. judgment`，取实际空位 29）。
  - git diff 证明 `plugin_registry` / 现有 `MemoryStore` / `FileBackend` / RAG 链路**未被改动**（外部插件装载路径未引入）。
