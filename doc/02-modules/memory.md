# 模块设计：分层记忆（L2 Layered Memory）

> 对应规格：`doc/openspec/specs/memory/spec.md` ｜ 接口：`doc/03-interfaces/memory-interface.md`

---

## 1. 模块定位

记忆是 CORE 的"大脑皮层"，负责**记什么、怎么取、如何沉淀**。核心隐喻：

> **记忆即光谱**——从模糊经验到稳定代码是一个连续光谱。想法先以经验进入（L4），稳定后结晶为技能（L3），
> 足够稳定则提升为插件（代码）；失败则可逆卸载、降级回记忆。**记忆与代码是同一光谱的两端。**

---

## 2. 五层模型

| 层 | 名称 | 内容 | 生命周期 | 迁移方向 |
|---|---|---|---|---|
| **L0** | 元规则 | 宪章、记忆管理 SOP、不可违反的约束 | 极稳定，几乎不变 | ——（最上层） |
| **L1** | 索引 | 指向 L2/L3 的最小索引（what→where） | 随 L2/L3 变动同步 | ↓ 精简 |
| **L2** | 事实 | 具体事实、环境信息、教训条目 | 半稳定，可修正 | ↑ 提炼 / ↓ 归档 |
| **L3** | 技能/SOP | 可复用的操作流程、技能、SOP | 稳定，版本化 | ↑ 结晶为插件 |
| **L4** | 归档 | 被压实/遗忘归档的原条目（检索**降权** L4=0.2，仍可审计） | 只增不改 | ↓ 长期沉淀 |

**迁移规则**：
- **结晶（Crystallize）**：L3 技能被复用超过阈值 → 提升为插件（代码），进入 L0/L1 工具层。
- **溶解（Dissolve）**：插件反复失败/退化 → 卸载，回退为 L3 记忆（保留"为何失败"的教训）。

---

## 3. 关键设计

### 3.1 读写接口（统一抽象）

```
MemoryStore
├── read(query, budget, *, exclude_source_prefixes, allow_source_prefixes, session_id)
│     -> 相关记忆（排序 + token 上界）
├── write(layer, entry) -> 写入（带 trace_id、来源、时间戳）
├── migrate(src_layer, dst_layer, entry_id) -> 层间迁移（结晶/溶解）
├── index() -> L1 索引（最小化）
└── audit() -> 审计（谁在何时写了什么）
```

### 3.2 检索与上下文上界

- 相关性打分：`relevance = f(关键词/向量相似度, 新鲜度, 复用次数, 层权重)`。
- **硬性 budget**：`read` 返回的总 token 不超过预算；超限按 `layer_priority × relevance` 截断。
- 层权重默认：L0 > L3（相关技能）> L2（相关事实）> L1 > L4。

### 3.2.1 按会话隔离的检索（change `0114`／ADR-0107）

- **一张店、按会话归组**：不给每个会话建独立 `(loop, memory)` 实例（change `0048` 已裁否决）；
  会话维度作为 `read`/`write` 的可选参数穿透，条目按 `session_id` 归属。
- `read(session_id=…)` **非空**时只返回「归属该会话的条目 + **全局层**」（`session_id == ""`
  的未归属条目，含 L0 人格与文档化笔记层）；**空串**（未归属调用者）⇒ 不过滤，与既往逐字一致。
- 会话过滤在**排名与预算之前**生效（被滤项不吃预算、不被 `reuse_count` 强化），与
  `exclude_source_prefixes` 同点同口径，二者可叠加。
- **来源排除的例外面**（`allow_source_prefixes`，change `0117`／ADR-0110）：命中排除**且未**
  命中放行的条目才剔除（同点、同「排名/预算之前」）；缺省空 ⇒ 语义逐字不变，排除面为空时
  放行面无效果。封存是**读取面**语义 —— 条目本体照常留存，不得以删除/迁移实现。
- **归属原则**：执行轨迹按**发起会话**归属（主/子/神兽/宠物 loop、压实产物、路由未命中）；
  **刻意知识留全局层**（L0 人格、文档化笔记、`pet.observe` 的主人偏好）。
- **压实同样按会话收窄**（change `0131`／ADR-0124／账本 E66）：`compact(session_id=…)` **非空**
  时只聚合**该会话**的 L2 episodic 条目（提炼/归档/打分写回都只覆盖它），**空串**保持全量语义
  （循环内节拍压实不传该形参）。会话维度与 `read` 同构穿透，**不**新建存储实例。
- **摘要为滚动合并**（change `0148`／ADR-0140／账本 E90）：该会话已有摘要时，`compact` 把
  **既有摘要 + 新增 episodic 条目**一并投喂摘要器 ⇒ 更新摘要**融合既有结论与新增事实**，早期结论
  **不被静默丢弃**。滚动的是**内容**，摘要条目 `id` 与「每会话至多一条、不增长」口径**不变**。
- **摘要只读访问器**（change `0150`／ADR-0142／账本 E94）：`MemoryStore.summary_for(session_id)`
  按会话取回既有摘要条目（口径同压实写入），**只读** —— 零写入、零效应、不动
  `reuse_count` / `importance` / `updated_at`。供上层（CLI `notes promote`）取数做提升。
- **摘要越界的提升钩子**（change `0153`／ADR-0145／路线图 G3）：滚动合并上界 `MAX_SUMMARY_CHARS`
  是既有摘要**投喂时的节选上限** ⇒ **越界即下一轮滚合并开始截断既有内容**（信息不可逆销毁）。
  `MemoryStore` 支持注入 `summary_promoter`（契约 `(session_id, MemoryEntry) -> object`，缺省 UNWIRED）；
  某会话摘要**首次越过**上界时把**本次产出的**摘要条目交付钩子**一次**（供上层落 canonical），
  **已越界**不再交付（免以已稀释的后继摘要覆写）。memory **只报边界**、**不** import notes（钩子注入，
  零反向依赖）⇒ 落盘由组合根注入的闭包完成（§ 组合根）。钩子 UNWIRED ⇒ 不交付（零回归）；
  抛错 ⇒ 降级（`warnings.warn` 留痕，不牵连压实的写回与迁移）；`session_id` 空串 ⇒ 不交付。

### 3.2.2 对话转录（**非**记忆层级，change `0115`／ADR-0108）

- **转录不是 L0–L4 里的任何一层**：它是原始对话流（谁在何时说了什么），**不经** `MemoryStore.read`
  取出，**不**参与温度分层检索、排名、`reuse_count` 强化、压实、固化与遗忘。混淆二者会同时
  破坏时序（L2 排名无时序保证）与记忆语义（历史回放会反复强化条目）。
- **落盘**：`$CORE_STATE_DIR/messages.jsonl` **单文件**（单店 + `session_id` 列，不翻案 change
  `0048`）；`os.open(O_APPEND)` + 单次 `os.write` 整行 ⇒ 跨进程并发追加不写坏行。
- **只存 (user 原话, 最终回复)**：不存 `ctx.messages` —— 后者含 `role="tool"` 观察，回放给
  OpenAI 兼容端点大概率 400（wire 格式），且体积与标题抽取都更差。
- **未归属（`session_id == ""`）不落盘**：避免所有无会话调用挤进同一个 `""` 桶变成幻影会话。
- **分层切分读取**（change `0178`／ADR-0169）：`TranscriptStore.window(session_id, *, short_turns,
  mid_turns, short_tokens)` **一次** `read()` 同时返回**短带原文**（末 `short_turns` 轮，沿用既有
  「按 token 从新到旧截断 + 丢弃开头孤儿 assistant 行」语义）与**中带原文**（其前 `mid_turns` 轮，
  **不**按 token 截断）；两带**不重叠**；`short_turns <= 0` ⇒ 两带皆空。切分**只读不写**、不经
  `MemoryStore`（转录不是记忆层级）。
- 细节见 `03-interfaces/memory-interface.md` §1.1。

### 3.3 结晶与溶解（与 L4 进化联动）

- 结晶由 L4 进化引擎触发：`Proposer` 产出技能→插件补丁，`Validator` 通过后 `MemoryStore.crystallize`。
- 溶解由 L4 诊断触发：插件失败归因后 `MemoryStore.dissolve`，把插件语义 + 教训回写为 L3 技能。
- 二者都走**可逆效应**：结晶可回滚（卸载插件恢复技能），溶解可回滚（重装插件）。

### 3.4 结构化关键事实抽取（key_facts，change `0155`／ADR-0147／路线图 G4）

- **动机（账本 E92）**：既有记忆只有 `kind ∈ {episodic, semantic}` + `tags`，无结构化实体面。
  外部参考件 M4 提四类（偏好 / 工程约束 / 完成任务 / 关键事实），**本仓只取 `key_facts`** —— 其余三类
  **各有既有归属**（分别归 `notes` 常驻笔记 / `notes.observe_turn` / L0 Core Profile），不重复建面。
- **接缝**：`MemoryStore(key_fact_extractor=...)`，契约
  `KeyFactExtractor = Callable[[list[MemoryEntry]], list[KeyFact]]`（缺省 UNWIRED）；新增
  `core/memory/extract.py`（`KeyFact` / `build_extract_prompt` / `parse_key_facts` / `extract_with(llm)`）
  —— 照 `summarize.summarize_with` 先例，**memory 不 import LLM / rag 抽象**，模型调用由组合根注入。
  触发点在 `compact` 的会话循环内（与摘要**同材料、同门控、同 trace**），但**与摘要互不依赖**
  （循环在「摘要器**或**抽取器」注入时运行）。
- **落库形态**：`id="keyfact.<实体 slug>"`（**同实体至多一条**、覆盖式更新、条目不增长）、
  `kind="semantic"`、`source="extraction"`、`trace_id="compaction.<sid>"`（**与压实同 trace** ⇒
  一并可撤销）、`tags=["key_fact","entity:<slug>",("ref:…")?,("session:<sid>")?]`。
  **属全局层**（`session_id` 置空、不参与会话隔离 —— 实体事实是**跨会话**长期知识）；产生它的会话
  只作 `tags` 溯源标注。
- **密钥红线（本能力的核心）**：**密钥只引用不读取、绝不进记忆**。脱敏由 memory 侧在**落库前**对
  抽取器返回的**每一条**结果**无条件**执行 —— 注入的抽取器**不构成信任边界**（「靠 prompt 让模型
  别写密钥」不可审计）。规则：① `value` 呈密钥形态（前缀族 / 私钥块 / JWT / `key[:=]value` /
  长随机串兜底）⇒ **强制** `<redacted>`；② **仅当 `ref` 形如 `coeffect:<名称>`** 才视为「给出引用」
  ⇒ `value` **一律** `<redacted>`；**非该形态**的 `ref`（含模型自造的出处说明，如 `round1:…` /
  `会话事件`）**视为无引用** —— 弃用该 `ref`、不落 `ref:` 标签、取值回**裸值**判据
  （change `0173`：实测 **16/24** 条正常取值因模型自造引用被抹，属**纯自伤**）；③ **裸密钥无可用引用
  ⇒ 整条丢弃** + `warnings.warn` 留痕（含实体名、**不含**取值；「无可用引用」含空串**与**非
  `coeffect:` 形态）。⇒ 方向恒为 **over-redact**（拿不准即多脱敏）。**先脱敏后截断**（截断不得使明文逃逸）。
  `ref` 形态判据 `_is_coeffect_ref` 一并**覆盖**了旧的「像密钥的 `ref` 弃用」（密钥形态必然不满足
  `coeffect:` 形态）⇒ 一条判据两义。
- **有界**：单次条数 **自适应** `key_fact_cap(n)`（`n` = 本次压实聚合的 episodic 条数；
  `= clamp(ceil(n × KEY_FACTS_RATIO=0.25), KEY_FACTS_MIN=8, KEY_FACTS_MAX=16)` —— change `0177`／ADR-0168）；
  下限取**既有死值 8** ⇒ **任何会话长度下名额都不收紧、只放宽**；`MAX_KEY_FACTS_PER_COMPACT` 保留为
  兼容别名（= 下限）。`entity` / `ref` 长度 `_MAX_FACT_CHARS`(200) 头部截断，`value` 超长时**首尾保留**
  （头 / 尾各半、中以 `…` 连接，总长仍 ≤ 上限；取值常「头定名、尾定值」—— change `0172`）。
  **同批同 slug 归并**：一批内 `slug_entity` 相同者归并为一条、**只留首条**（后至者不挤占额度；
  归并后条数计额 = 本次 `cap(n)` 名额，**不重复占用**），被归并者经 `warnings.warn` 留痕（含实体名、
  不含取值；与因密钥丢弃的留痕各自独立）。
  **整批归一化后再落库**（归一化失败 ⇒ 整批不写，不留半批）；抽取器抛错 ⇒ **降级为不抽取**（不牵连
  摘要写回与条目迁移）；返回不可解析 ⇒ 同样不抽取 + 留痕，且 `extract_with` 判据为「**有输出但无
  JSON 数组**」（合法空数组 `[]` 不告警），留痕**不含**模型输出正文（可能含明文密钥 —— change `0172`）。
- **材料含「行动序列条目」**（change `0173`）：`loop` 侧把本轮**行动与结果**序列另立为一条 L2 条目
  （`loop.steps.<trace_id>`：有界 + 写入前逐行脱敏）⇒ 抽取材料除轨迹条目外**另含**它（内容口径归
  `loop`「执行循环」，本能力只消费）。**另立而非合并**：抽取器对**每条** L2 条目只取前
  `_MAX_ENTRY_CHARS`(400) 字符入 prompt，而该能力的实体历来产自轨迹条目的**散文** ⇒ 合并会把散文
  顶出窗口。公开脱敏判据 `looks_like_secret` / `redact_secrets`（`core.memory` 导出）由 loop 侧
  复用 —— **一处定义、两处消费**。
- 落库走既有唯一写路径 `MemoryStore.write()`（记可撤销效应），不另开第二写路径。
- **失效条目的运维修复**（change `0174`／ADR-0165）：判据修好了（上条 ②）**止不住既有污染** ——
  生产库里 **16/24** 条取值已被抹的条目仍在被检索命中（`keyfact.榴莲` 的 `reuse_count` 达 **36**）。
  `MemoryStore.repair_stale_key_facts(*, dry_run=False) -> RepairReport` 提供显式修复：
  **识别**（`_stale_key_facts`：`tags` 带 `ref:` 且**非** `coeffect:` 形态 + 取值 `<redacted>`）
  → **按会话**取**全层**材料（`_material_for_session`：`kind == "episodic"`，**去掉 L2 层过滤** ——
  当年材料压实后已归档 L4）→ 重抽（复用本能力 prompt / 脱敏 / 有界，判据**无第二份**）→ 备份 →
  落新 → 删该会话**全部旧** keyfact（**排除本次已写入的 id**：同 slug 即覆盖式更新，否则自删）。
  三处 **fail-closed**：抽取器未注入 / 该会话重抽抛错 / 备份写入失败 ⇒ **均不删**。删除**不迁 L4**
  —— 实测 `search()` 无层过滤、层权重是**加性**而 `reuse_count` 是**乘性**，归档止不了血；可逆性由
  `$CORE_STATE_DIR/memory.repair.<时间戳>.jsonl`（同目录同格式）承担。幂等；`dry_run` 只读。
  **不自动触发**（只在 `core-agent memory repair-keyfacts` 显式入口发生）。局限性见 ADR-0165。
- **备份「一次操作**恰好一份**」**（change `0175`／ADR-0166）：`0174` 的实跑暴露 —— 备份/删除原在
  **每会话循环体**内 ⇒ 备份文件数 = 会话数，而 `RepairReport.backup_path` 是**标量**（后写覆盖前写）
  ⇒ 报告只显示最后一份、第一份成孤儿；且两次调用落在**同一秒**时**同一路径**、后一份**静默覆盖**前一份。
  故 `repair_stale_key_facts` 提为**三段式**：① **收集**（`_collect_session`：每会话重抽 + 落新，
  返回是否成功）→ ② **备份**（`_doomed_key_facts` 一次扫描求各成功会话待删条目的**并集** ⇒
  `_repair_backup_path()` **只调一次**、**一个**时间戳、**一份**文件）→ ③ **删除**（统一，
  `_backup_then_delete`）。**失败语义按「作用域是否等于操作的作用域」分**：抽取失败是**会话级**
  （该会话不落库不删、其余照常），备份失败是**操作级** ⇒ **跨会话一并阻断**（`skipped["backup_failed"]`
  列出**全部**会话，一条都不删 —— 这份备份就是整次操作的回滚面）。`doomed` 求值推迟到全部落新之后
  （`written` 跨会话累积 ⇒ 只会**更少删**、不会误删）。文件名/格式/报表字段/CLI **零改动**。

### 3.5 记忆质量闭环（change `0177`／ADR-0168／账本 E114）

补齐「**入口不筛、出口不保、容量不随规模伸缩**」三处缺口（`importance` 此前只在检索 / 遗忘评分被**消费**、
**写入路径从不生产**）：

- **写入侧重要度闸门**：`MemoryStore(importance_scorer=...)`，契约
  `ImportanceScorer = Callable[[MemoryEntry], float]`（缺省 UNWIRED ⇒ 写入**逐字不变**）。与
  `summarizer` / `key_fact_extractor` / `summary_promoter` 同一「缺省不启用」纪律；memory **不 import**
  任何 LLM/rag 抽象（ADR-0045 依赖方向不变），评分器由 L5 组合根注入。三分支（阈值为常量、无 LLM
  二次判断）：分 < `_IMPORTANCE_FLOOR`(0.2) ⇒ **拒收**（不写、无效应、`warnings.warn` 留痕，返回 `None`）；
  `[0.2, 0.4)` ⇒ **降层 L4**；≥ `_IMPORTANCE_AMBIT`(0.4) ⇒ 按**意向层**入库并**写回** `importance`
  （可逆）。**降层两步双 trace**：`EffectTracker.rollback` 按**逆序**撤销 ⇒ 同 trace 会先迁回再**删除**；
  故先按意向层 `write`（条目自身 trace），再 `migrate(意向层→"L4", trace_id=f"gate.<id>")` —— 回滚
  `gate.<id>` 即把条目**迁回原意向层**。评分器抛错 / 返回界外值 ⇒ **降级放行**（正常写入 + 留痕，
  不牵连主流程）。留痕**只报条目 id**、绝不回显正文（密钥红线）。
- **复用强化衰减**：遗忘评分 `store._decay_score` 的 freshness 项改
  `freshness ** (1 / (1 + log1p(reuse_count)))`（复用越多、衰减越慢）。**调制只落 `_decay_score`** ——
  `relevance.recency_decay` 是**检索（`rank`）与遗忘共用**的函数，若在此处调制会连带改变检索排序；
  `recency_decay` / `rank` **逐字不动**（`reuse_count=0` 时 `pow(x,1.0)==x` 逐位相等、无需特判）。
- **抽取上限自适应**：见 §3.4「有界」——`key_fact_cap(n)` 只放宽不收紧。

### 3.6 三层会话滑窗的记忆面（change `0178`／ADR-0169／账本 E115）

会话历史的三层滑窗（短 = 转录原文 / 中 = 滚动摘要 / 长 = 会话整体摘要）在记忆侧只新增**一条**产物 ——
**中期摘要**，并由既有压实通道产出：

- **`summarize_slice(session_id, entries, *, max_chars) -> str | None`**：收上层从转录切出的**临时桩**
  `MemoryEntry`（`id=f"transcript.{i}"`、`source="transcript"`、**不在库中**），经**既有摘要器**滚合并为
  **一条** `kind="semantic"` 条目，id 与 `trace_id` 均为 `compaction.mid.<key>`（`key = session_id or
  "default"`）、`source="compaction"`。**只读桩、绝不落库**；**不 migrate** 任何来源（区别
  `_commit_summary` 把来源迁 L4）。写前无条件 `redact_secrets`（与关键事实抽取**同源**、方向 over-redact），
  并按 `max_chars` 截断（越界丢尾、不再累积增长）。**滚动合并**：该会话已有中期摘要时，把**既有中期摘要
  内容**作为材料**首条**一并投喂摘要器（同 `_summarize_sessions` 形态）。**降级**：摘要器 UNWIRED /
  桩为空 / `max_chars` 非正 ⇒ 返回 `None`、**零写入零效应**。写入走 `EffectTracker.record`（可撤销）。
- **`mid_summary_for(session_id) -> MemoryEntry | None`**：按会话**只读**取回既有中期摘要，无则 `None`；
  **不**产生写入或效应，**不**变更 `reuse_count` / `importance` / `updated_at`。
- **长层不新增产物**：直接复用既有只读 `summary_for(session_id)`（`compaction.summary.<session>`）。
- **`_entry_by_id(entry_id)`**：把「按 id 取条目」提为单一实现，`summary_for` / `mid_summary_for` /
  `_existing_summary` 共用（id 约定单一真源）。

### 3.7 后端可插拔

- MVP：文件后端（`memory/*.md` 与 `memory/*.jsonl`），可审计、无外部依赖。
- 未来：向量库后端（同一 `MemoryStore` 接口，`read` 换检索实现）。

---

## 4. 记忆写入规范（"无行动不记忆"的落地）

| 场景 | 写哪层 | 内容示例 |
|---|---|---|
| 每轮循环结束 | L2/L4 轨迹 | 本轮做了什么、结果如何 |
| 学到新经验/教训 | L2 事实 | "X 方法对 Y 问题有效/无效" |
| 沉淀可复用流程 | L3 技能 | SOP：步骤 1→2→3 |
| 长期归档 | L4 | 完整会话原始记录 |

**禁止**：密钥/敏感内容进入任何记忆层（只存引用）。

**压实材料的排除面**（change `0179` / ADR-0170）：带 `_PRESERVE_TAGS`（现为 `{"failure"}`）标签的
L2 条目**不入选** `_episodic_groups()` —— 该函数是打分（`_score_importance`）、摘要（`summarizer`）、
结构化关键事实抽取（`_extract_key_facts`）**三者的唯一材料源**，故一处 `continue` 三处生效：
失败条目**不被摘要吸收**、**不随压实迁 L4**（`_commit_summary` 的迁移列表不含它），
其 id 也**不进**摘要条目的 `from:` 出处。判据用 **tag** 而非 `source` 前缀：`rank` / `_decay_score`
**完全不看 tags** ⇒ 零排序副作用，且不触碰 `exclude_source_prefixes=("beast.","pet")` 命名空间红线。
**遗忘路径不受此豁免**：`forget()` 逐字不动 ⇒ 失败条目仍按自然衰减（`_FORGET_THRESHOLD`）归档 L4（有界）。

---

## 5. 错误处理与边界

| 场景 | 行为 |
|---|---|
| 检索超预算 | 按优先级截断，记录被截断项供上层决定 |
| 写入失败 | 重试 1 次，仍失败则记入本地队列，不阻塞 loop |
| 结晶后插件退化 | L4 评测触发溶解，回退 L3，保留教训 |
| 索引与事实不一致 | 写后异步同步 L1 索引，保证最小且一致 |

---

## 6. 关联

- 规格：`doc/openspec/specs/memory/spec.md`
- 进化联动：`doc/02-modules/evolution.md`
- 接口：`doc/03-interfaces/memory-interface.md`
- 测试：`doc/04-testing/test-cases.md`（MEM 系列）
