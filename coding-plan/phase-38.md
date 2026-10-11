# Phase 38：对照外部「四维记忆蓝图」查漏补缺（批次 `0200`~`0203`，4 change）

> **状态**：✅ **全闭**（2026-10-11；4 条 change 逐条独立收口：各自 change 目录 / ADR / 规格 delta /
> 四门禁 / 手工归档 / 单次提交）。
> **来源**：2026-10-11 用户提供外部蓝图 `memory-4-layer-architecture.md`（四维记忆矩阵 ＋ 动态滑窗
> 三级压缩 ＋ 上下文窗口黄金配比），提出「**对照当前记忆实现，核心实现看下是否有遗漏，查漏补缺**」。
> 逐条取证（Explore agents ＋ 直接读码）后：**四维能力均已落地**（会话 = `TranscriptStore` ＋ 三层
> 滑窗；语义 = `semantic` 条目三面；程序 = `skills`/SOP，Phase 37 刚收口；情景 = `episodic` L2→L4），
> **但蓝图的「存储介质 / 配比 / 轴口径」层基本未兑现**，且有一处**能力级真缺口**（见 §2 账目）。
> **为什么是一批而非一条**：四个缺口属**三个不同 capability**（`context` × 2 / `memory` × 2）、
> 风险递增且相互隔离 ⇒ 沿 **Phase 34/35/36/37 先例**：**一个批次、多条 change**，每条仍各自
> change / ADR / delta / 四门禁 / 单提交。**执行顺序 = 编号顺序**（风险递增）：`0200` 先钉死「轴」的
> 词汇（后三条都依赖它）；`0201` 先结清事实面预算（`0203` 的关系才不会与关键事实抢未定义的额度）；
> `0202` 独占 `Diagnoser` 相邻面，隔离开。
>
> **红线（全批次）**：主方向封存 `exclude_source_prefixes=("beast.","pet")`（`runtime.py`
> **逐字不动**，phase-26）；密钥**只引用不读取**、**绝不**进日志/记忆（留痕**只报实体名 / 谓词名 /
> 会话键**，**绝不回显取值或正文**）；新脱敏恒 **over-redact**；所有写效应经 `EffectTracker` 可回滚
> （新产物一律与 `compaction.<key>` **同 trace**）；零三方依赖；**每一条新行为缺省关 / UNWIRED ⇒
> 既有路径逐字不变**；`config*.yaml` / `.claude/settings*.json` / `uv.lock` 等**不提交**。

---

## §0 用户裁决的四个设计岔口（AskUserQuestion，2026-10-11）

| # | 岔口 | 裁决 |
|---|---|---|
| 1 | **批次范围** | **四条全做**（实体关系 / 因果链 / 口径裁决 / 五区块配比） |
| 2 | **G2 因果** | **确定性链 + 跨轮时序相邻标注**（**不做** LLM 因果推断）⇒ change `0202` |
| 3 | **G1 接线** | **缺省关、显式开启**（`memory.relation_extract` 缺省 `False`）⇒ change `0203` |
| 4 | **G1 谓词面** | **闭合白名单（中英双语）**，归一化到规范英文谓词 ⇒ change `0203` |

---

## §1 批次总览（执行顺序 = 编号顺序；风险递增）

| # | change（归档目录） | capability | 一句话 | ADR | 台账 | 测试基线 |
|---|---|---|---|---|---|---|
| 1 | `0200-compaction-axis-ruling` | `context` | **口径裁决**：轮轴管跨轮滑窗分层、步轴管轮内压实触发，两轴**不可互换**；蓝图 `0-5/6-20/21+` 字面边界**不采纳**。**零 `src/` 改动** | ADR-0190 | E137 | 2253 → 2255（+2） |
| 2 | `0201-context-block-plan` | `context` | 五区块配比收敛为**确定性纯函数** `plan_blocks` ＋ **唯一消费者**（planner 的字面量 `2048` 改为可注入），**缺省关** ⇒ 今日预算逐字不变 | ADR-0191 | E138 | 2255 → 2263（+8） |
| 3 | `0202-episodic-causal-link` | `memory`（实现面 `loop`，`loop` 规格零改动） | 失败条目增 `after:<prev_trace>` **时序相邻**标注（进程内前序表，零记忆读）＋ `session_chain()` 零效应只读链 | ADR-0192 | E139 | 2263 → 2270（+7） |
| 4 | `0203-entity-relation-extraction` | `memory` | 关键事实之上加**关系三元组**（独立 DI 接缝 ＋ **中英双语闭合谓词白名单** ＋ `relation.*` 条目），补蓝图唯一的能力级缺口 | ADR-0193 | E140 | 2270 → 2294（+24） |

**批次合计**：测试基线 **2253 → 2294**（**+41**；`0203` 含参数化展开，高于立项预估的 +12/+16 ⇒
以实跑为准）；`openspec validate --all` **31 passed / 0 failed**；四门禁（`ruff check` /
`ruff format --check` / `pyright` **0-0-0** / `pytest -q`）**逐条全绿**。

**已实现且强于蓝图（本批不动）**：异步压缩不阻塞、先判断再落库（价值门控 ＋ importance）、
去重/合并、全链可逆。**有意的偏离（不是缺陷）**：蓝图 Tier3「删除原文」→ 迁 L4 归档（守 P2）；
外部时序库 → 单体 JSONL；Tier2 小模型 → 主 LLM 单接缝；`SKILL.md` → `Skill.instructions`。

---

## §2 账目（E137~E140，逐条根因 → 修法）

| 台账 | 根因（一句话） | 修法（一句话） | 归档 |
|---|---|---|---|
| **E137** | **「轮内步数」与「跨轮轮数」两轴关系从未裁决** ⇒「不可互换」无规格约束、误读可复发：两轴**各自有规格**但**关系无处可查**；**有实测前科**（change `0182` / ADR-0173 正是把轮内步数误读作对话轮数的一次诚实化订正）；**复发诱因明确**（`loop.compact_steps` 缺省 `6` 恰落在外来蓝图 §4.1「Tier 2 自第 6 轮开始」之上）；而 loop 中**不存在**用户轮计数器 ⇒「对话第 N 轮」边界**不可计算** | **裁决（零 `src/` 改动）**：① 两轴分工 = 步 → **轮内**压实触发 / 轮 → **跨轮**三层分层，`compact_steps` **只**是步轴阈值；② 蓝图字面 tier 边界 `0-5/6-20/21+` **不采纳**（会与**比率相对**的既有分层构成第二套冲突边界；`三层窗口比例分配` 明禁配额面新增键）⇒ 采其**结构**弃其**数值**；③ 裁决以**规格要求 ＋ 守护测试**双锚固定 | `0200` / ADR-0190 |
| **E138** | **loop 的 token 预算从未到达 planner** ⇒ 注入额度是自 2026 Q1 起未变的**字面量 `2048`**（`LLMPlanner._system_prompt`）；用户改 `llm.context_window` / `loop.output_reserve`，事实注入面**纹丝不动**；全仓三处预算各自为政（`loop_limits()` 总量 / `_window_plan` 的 `// 2` / 上述字面量） | **五区块配比纯函数** `core.context.plan_blocks(total_budget, *, enabled)`（零 I/O、零模型调用，纪律镜像 `plan_window`；**配额面不新增键**）＋ **唯一消费者**：`LoopContext.token_budget` ＋ `LLMPlanner(block_plan=…)`（**不加第 11 个提示词块**、**不给 `ContextPack`/`BudgetManager._measure` 加按块记账** ⇒ 其余四块**仅咨询性**）＋ **20% 缓冲是「上界」靠「不分配」实现**（总预算**已扣**输出预留 ⇒ 再减一次即**双重预留**，写成规格 SHALL NOT）＋ 缺省**关** ⇒ 仍字面 `2048` ⇒ 既有提示词**逐字不变** | `0201` / ADR-0191 |
| **E139** | **跨轮关系面为零** ⇒ 情景记忆只有「点」没有「线」（每轮三条目共享 `trace_id` ⇒ 只有同轮隐式关联；全仓无按会话重建**时序链**的读取面）。**先做诚实评估**：仓内**不存在**确定性**因果**事实 ⇒ 推导它**只能**靠 LLM 推断，而 LLM 推断**不可测正确性 / 非可逆 / 新增脱敏面**（模型生成的失败归因散文正是密钥易泄处）且 `Diagnoser` 现按 `plugin_id` 归因、时序前驱**不增信号** ⇒ **不做 LLM 因果推断**（沿 ADR-0041 同理由拒绝先例） | 两项**确定性**能力：① **跨轮时序相邻标注** `after:<前一已记忆轮 trace>`（ADR 明写语义为**同会话内的时序相邻、不是因果** ⇒ 用机制本名而非 `caused_by:`，沿 ADR-0173 先例；「因果不作推断」写成 **SHALL NOT**）；② **零效应只读链** `MemoryStore.session_chain()`。**存储决策**：标注**挂在既有失败条目**（不新开条目 —— 每次失败多一次写入且会进压实材料；不加 `MemoryEntry` 字段 —— 那是跨后端**线上形状**，需迁移）⇒ **标签**。**前序来源**：进程内 `_last_trace: dict[str, str]`（**刻意不做记忆读**：`read` 会强化 `reuse_count` 是新副作用；`search("")` 返回**写序**而非 `ts` 序）＋ 开关 `loop.causal_links`（缺省 `False` ⇒ 逐字不变） | `0202` / ADR-0192 |
| **E140** | **语义记忆只有「点」没有「边」** ⇒ **唯一的能力级缺口**：结构化抽取（`0155`/G4）落的是**扁平** `keyfact.<slug>`（有**实体**、无**关系**）；全仓对 `MemoryEntry` grep `relation/edge/triple/graph` **零命中**；`MemoryBackend` 只有 `get/put/search/list_index/delete` ⇒ 无**边**的承载面。**谓词开放不可接受**：开放谓词 ⇒ ⓐ 图不可遍历、ⓑ 新增**第四个无界自由文本字段**（新的密钥携带面）、ⓒ 同三元组幂等去重的**基数失控** | **三元组 `Relation(head, predicate, tail)`**：独立类型（**不给 `KeyFact` 加字段** —— 已发布契约，加宽会动摇 `parse_key_facts`/`scrub_key_fact`/`_plan_key_facts` 与全部 30 条关键事实用例）＋ **中英双语闭合谓词白名单 + 归一化**（表外丢弃并留痕）＋ **脱敏 fail-closed 且判据一处定义**（**密钥判定先于谓词归一化** —— 顺序即安全；三段**任一**密钥形状即整条丢弃、**无 ref 逃生口**；留痕 **over-redact**）＋ **落库完全复用 `_write_key_fact` 形状**（`source="relation"`/`kind="semantic"`/`session_id=""`/`trace_id="compaction.<key>"` ⇒ 幂等覆盖 / 同豁免面 / **随压实回滚一并撤销**）＋ `relation_cap` **别名到** `key_fact_cap`（一把旋钮）＋ **注入面复用既有「相关事实」块** ＋ **缺省关 / UNWIRED**（**刻意偏离 `0155` 的无条件接线**） | `0203` / ADR-0193 |

---

## §3 逐条收口（协议一致性）

每条**必走**：spec-first（或**规格中性**判定）→ ADR → 先红测试 → 实现 → 四门禁 → 手工归档
→ 台账 ＋ 记忆 → **单次提交**。**规格 delta** 落点：`0200`→`context`；`0201`→`context`；
`0202`→`memory`；`0203`→`memory`。四条**全是 ADDED delta**（既有 Requirement 一条都不 MODIFY）。

**归档方式**：`openspec archive` 在 symlink+WSL 下**必败** ⇒ 恒为**手工**
（`python3 /tmp/openspec_archive.py <change-dir>`；合并时断言 **0 canonical Requirement-header 丢失 /
0 Scenario-title 丢失**，再移进 `doc/openspec/changes/archive/`）。归档断言：
`0200` `context` scen 24 → **28**、6 req → **7**；`0201` `context` scen 28 → **33**、7 req → **8**；
`0202` `memory` scen 93 → **98**、13 req → **14**；`0203` `memory` scen 98 → **108**、14 req → **15**。

**能力面 canonical 变化**（`doc/openspec/specs/`）：`context`（**压缩轴口径** ＋ **上下文区块配比 /
80-20 安全线**）；`memory`（**情景链（时序相邻标注）** ＋ **实体关系抽取（relations）**）。
逐条 Scenario 计数见各自 change 的 delta 与 `doc/04-testing/test-cases.md` §113~§116。

**逐条反证（防空过，全部实测）**：`0200` 把守护断言改成传轮数 ⇒ **2 红**；`0201` 令 `_fact_budget`
忽略开关 ⇒ 字面 `2048` 逐字锚**1 红**（另有 `test_infomap_wiring.py:48` / `test_phase13.py:185`
两条硬编码 `budget=2048` 的**绊线**在册）；`0202` 令标注忽略开关 ⇒ 逐字锚 **1 红**；
`0203` 摘掉 `_extract_relations` 调用 ⇒ **11 红**、摘掉 `scrub_relation` 密钥判定 ⇒ **2 红**。

**本批次的三条方法论教训（值得记）**：
1. **`0200` 的「零值陷阱」**：初版以 `budget=0` 想排除 token 判据的一侧 ⇒ **转红** ——
   `token_used >= budget` 中 `0 >= 0` **恒真** ⇒ token 维度反而**恒触发**。**隔离一个 `or` 判据的
   单侧须用「不可满足」（极大值）而非「零值」**。且该 change **不产生行为** ⇒ 守护测试的价值
   **全在反证**，不能以「测试是绿的」单独证明任何事。
2. **`0203` 的「`elif` 也是嵌套」**：`_plan_relations` 初版用 `if/elif` 分流丢弃原因 ⇒
   `test_control_flow_nesting_max_three` **转红**（AST 口径把 `elif` 记作一层 `If` ⇒ 嵌套 4 > 3）。
   正解：抽 `_record_relation_drop` 把分流移出循环体。
3. **`0202` 的「摘要是多行串」**：不遮蔽②的**对照**断言初版写成「事实面**不含**步序文本子串」
   ⇒ **转红** —— `failure_digest(trajectory, steps, …)` **自身内嵌**步序文本 ⇒ 子串判定**恒假**。
   正解按**整条内容相等**判定「纯步序条目是否被挡」。

---

## §4 遗留与显式不做（如实登记，不静默膨胀）

- **本批次新增的已知局限**：逐条登记在 `coding-plan/known-risk.md` **§3**（按 ADR 归类
  ADR-0190~0193）—— 例如 `0201` 的 `BlockPlan` 仅**咨询性**（其余四块不参与注入）、`0202` 的
  前序表是**进程内实例状态**（跨进程 / 三路 loop 断链）且 `session_chain` **未进 Protocol**、
  `0203` 每次压实**多一次模型调用**且事实面预算**三分**、双语白名单上线初期仍会在**长尾表达**上 drop。
- **本批次外（显式不做）**：
  - **LLM 因果推断** —— 不可测正确性 / 非可逆 / 新增脱敏面 / 无消费者增量（同 ADR-0041 拒绝先例）；
  - **知识图谱层** —— 不新增 `MemoryBackend` 方法、不加遍历/查询 API、不加图存储、不动
    `IndexEntry`（接口变更 ＋ 迁移成本，且当前**零消费者**）；
  - **第 11 个提示词块** —— 关系搭「相关事实」；独立块是**另一个 change**，且必须在 `0201` **之后**；
  - **按块记账** —— 不给 `ContextPack` / `BudgetManager._measure` 加（会改 `_measure` 语义、打掉两条
    精确增量用例）；
  - **蓝图字面 tier 边界 `0-5/6-20/21+`** —— 会与比率相对方案冲突（违反配比面无新键的规格约束）；
  - **`Diagnoser` 前驱接线** —— 需对 `evolution/spec.md`「对比诊断」做约 36 行逐字 MODIFIED
    （本批最高风险的规格编辑）⇒ 登记为**遗留**；用户裁决的选项只要求 `session_chain` 读取面。
- **`0203` 后仍开账**：**E27**（IM 网关未接线）/ **E55** / **C7**（TTS）/ **E91** / **E100**（余运维
  动词）/ **E101**（hooks 实现）—— **未闭**，仍登记于 `coding-plan/known-risk.md` §1。
- **记忆三面路线图 G1~G5**：**全闭**（G1 `0154` / G2 `0151` / G3 `0153` / G4 `0155` / G5 `0156`）。

---

## §5 关联

- 前置：`coding-plan/phase-37.md`（Procedural Memory，4 change `0196`~`0199`）·
  `coding-plan/known-risk.md`（§1 账目 E137~E140 已闭、§3 已知局限）。
- 逐条细节：`doc/openspec/changes/archive/2026-10-11-0200-compaction-axis-ruling/` …
  `…-0203-entity-relation-extraction/`（各有 `proposal.md` / `tasks.md` / `design.md` / `specs/`）；
  用例与红态证据：`doc/04-testing/test-cases.md` §113~§116。
- 测试锚点：`tests/test_axis_units.py` / `test_context_blocks.py` / `test_loop_causal_link.py` /
  `test_memory_relations.py`（另 `test_memory.py` 的豁免面守护同步登记 `relation`）。
- 外来输入（**只读、不提交**）：`memory-4-layer-architecture.md`。
