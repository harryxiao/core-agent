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
  时只聚合**该会话**的 L2 episodic 条目（提炼/归档/打分写回都只覆盖它），**空串**保持全量语义。
  **口径订正**（change `0192`／ADR-0182／账本 E129）：空串全量语义**保留给显式调用**（CLI / 运维
  命令面）；**循环内路径**（轮内压实 `DefaultLoop._compact` 与维护节拍 `_maintain`）**一律**以本轮
  会话标识收窄（此前轮内压实裸调 = 全量，与节拍口径相反 ⇒ 跨会话串扰，已修）。会话维度与 `read`
  同构穿透，**不**新建存储实例。
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
- **越界节选首尾保留（尾部不销毁）**（change `0193`／ADR-0183／账本 E130）：投喂摘要器的既有摘要槽
  由**纯头截断**（`prior.content[:MAX_SUMMARY_CHARS]`，会**无声销毁尾部** = 最新结论所在）改为
  **首尾保留** —— 未越界**逐字**全文；越界渲染「首部 ＋ 省略标记（标明中略字数）＋ 尾部
  （`_SUMMARY_TAIL_CHARS=800`）」，三段相加**恰为上界** ⇒ 上界（token 有界）**不破**且尾部逐字保真。
  **触发判据逐字不动**：`_deliver_promotion` 仍读 `len(prior.content)`（**全体长度**）而非节选 ⇒
  首尾保留**不触碰**提升触发；`_commit_summary` 落库**仍不截断**（canonical 全文 / 投喂有界，两界正交）。
- **价值门控跳过留痕**（change `0193`／ADR-0183）：`_summarize_sessions` 因 `_below_gate` 跳过会话时
  补 `warnings.warn`，**只报会话键**（`{sid!r}`），**绝不**回显摘要 / 事件正文（承「密钥只引用不读取」
  红线）；门控**判据与结果**逐字不变（仅补留痕，免「为何我的会话没产摘要」无从判断）。

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
  **生产接线 + 内部产物豁免面**（change `0181`／ADR-0172／账本 E118）：评分器经新模块
  `memory/importance.py` 的 `score_with(llm)` 构造（与 `summarize_with` / `extract_with` **同一** `str→str`
  接缝，memory 不 import LLM 抽象）；**失败方向恒为放行** —— 无可用数值抛 `ValueError`（交闸门异常路径）、
  界外值**原样返回**（交闸门界外路径），工厂**不**兜底/不 clamp（静默成 0 分会误杀）。豁免面
  `_GATE_EXEMPT_SOURCES = frozenset({"compaction", "context", "extraction"})`（系统管道派生产物：会话摘要与
  中层摘要 / 压实产物 / 结构化关键事实）⇒ `write()` 在**调用点短路**（`score = None if source in 豁免面
  else self._gate_score(entry)`），与 UNWIRED **逐字同路径**；`_gate_score` / 阈值常量**逐字不动**。配置键
  `memory.importance_gate`（缺省 **false** ⇒ 行为逐字不变），组合根在 true 时注入 `score_with(_llm_text)`。
- **复用强化衰减**：遗忘评分 `store._decay_score` 的 freshness 项改
  `freshness ** (1 / (1 + log1p(reuse_count)))`（复用越多、衰减越慢）。**调制只落 `_decay_score`** ——
  `relevance.recency_decay` 是**检索（`rank`）与遗忘共用**的函数，若在此处调制会连带改变检索排序；
  `recency_decay` / `rank` **逐字不动**（`reuse_count=0` 时 `pow(x,1.0)==x` 逐位相等、无需特判）。
- **复用强化落盘**（change `0187`／ADR-0178／账本 E124）：命中条目的 `reuse_count` 递增**写回持久后端**
  （`read()` 末尾 `_reinforce(selected)`：自增 → `_backend.put` → 记可撤销效应 `trace=reuse.<id>`）。
  原实现只改内存对象（`FileBackend.search` 返回**同引用**、从不 `_persist()`）⇒ 磁盘 JSONL 恒为旧值、
  跨会话强化全丢、遗忘曲线重启后退化。**写回只覆盖 `_truncate` 选中**的条目 ⇒ 写放大有界于选中集
  （非选中候选**不**写、**不**强化，原语义逐字不变）；undo 把 `reuse_count` **还原为强化前的值**
  （幂等，非 `-= 1`）。**不**把读条目插入 `_hot`（避免读路径使热字典无界增长）。`summary_for` /
  `mid_summary_for` 是**不同的**只读取数面（不经 `read()`）⇒ 其零写入 / 零效应契约逐字不动。
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

### 3.8 情景链（时序相邻标注与只读链，change `0202`／ADR-0192／账本 E139）

跨轮关系面此前为零（每轮三条目共享 `trace_id` ⇒ 只有同轮隐式关联）。本 change 补两项**确定性**能力，
**不做** LLM 因果推断（仓内无确定性因果事实；推断它不可测正确性 / 非可逆 / 新增脱敏面，且 `Diagnoser`
现按 `plugin_id` 归因、时序前驱不增信号 ⇒ 沿 ADR-0041 同理由拒绝）。

- **标注（写入面，缺省关）**：`loop.failure.<trace_id>` 的 `tags` 追加 `after:<前一已记忆轮 trace>`。
  **语义是同会话内的时序相邻、不是因果**（故用机制本名而非 `caused_by:`；「因果不作推断」在规格里是
  **SHALL NOT**）。前序取自 `DefaultLoop._last_trace: dict[str, str]`（按 `session_id`），在 `remember`
  **末尾**登记（登记的是**上一**轮 ⇒「上一已记忆轮」口径由此钉死；`remember` 只有**一个调用点**）。
  **刻意不做记忆读**：`read` 会强化 `reuse_count`（新副作用），`search("")` 返回**写序**而非 `ts` 序。
  开关 `loop.causal_links`（构造参 + 配置，缺省 `False`）⇒ 关时失败条目 `tags` **逐字不变**；
  `_last_trace` 的维护零 I/O 零效应 ⇒ **不受门控**（会话中途开启亦立即可用）。
- **不遮蔽（两处必断言）**：`failure` 标签仍在 ⇒ `_episodic_groups`（材料源唯一入口）**仍排除**
  该条目；无 `steps` 标签 ⇒ 失败条目**仍进**「相关事实」注入面。新标签**不得**意外遮蔽任一面。
- **只读链（读取面，恒可用）**：`MemoryStore.session_chain(session_id="") -> list[ChainNode]` —— 按
  `ts` **主序**（同 `ts` 保写入序）重建该会话情景链；`ChainNode` 只携带链路语义
  （`entry_id / trace_id / ts / failed / after`），**不含正文**。走 `_all_entries()`（冷 + 热）而**非**
  `read()` ⇒ 零 `_reinforce`、零效应。**未**并入 `MemoryStore` Protocol（与 `repair_stale_key_facts`
  同处置 —— 读面为具体类方法）。
- **已知局限**：前序表是**进程内实例状态** ⇒ 跨进程重启、以及三路 loop 实例（main/sub/beast）之间
  **链路会断**；`Diagnoser(predecessor_lookup=…)` 接线**未做**（需对 `evolution/spec.md` 做约 36 行
  逐字 MODIFIED）⇒ 登记为遗留。详见 `coding-plan/known-risk.md` §3 ADR-0192 行。

### 3.9 实体关系抽取（relations，change `0203`／ADR-0193／账本 E140）

§3.4 的结构化抽取落的是**扁平** `keyfact.<slug>`（有**实体**、无**关系**）—— 语义记忆只有「点」
没有「边」。本 change 补三元组 `Relation(head, predicate, tail)`，**独立于 `KeyFact`**（给已发布契约
加字段会动摇 `parse_key_facts` / `scrub_key_fact` / `_plan_key_facts` 与全部关键事实用例；独立类型是
**加法**）。

- **谓词 = 中英双语闭合白名单 + 归一化**：`RELATION_PREDICATES` 的规范谓词为英文
  （`depends_on / part_of / uses / causes / blocks / owns / implements / related_to`），中文变体
  （`依赖 / 属于 / 导致 / 使用 …`）经 `normalize_predicate` **归一化到规范值**后落库；表外 ⇒
  **丢弃并留痕**。谓词若开放，则（a）图不可遍历、（b）新增**第四个无界自由文本字段**（新的密钥
  携带面）、（c）同三元组幂等去重的基数失控。
- **脱敏 fail-closed，判据一处定义**：`scrub_relation` 复用 `extract.py` 的 `looks_like_secret` /
  `redact_secrets` / `slug_entity`，返回原因码 `""`/`empty`/`predicate`/`secret`。**密钥判定先于
  谓词归一化** —— 顺序即安全（否则密钥形状的**原始谓词**会走「未知谓词」分支、被原样回显进留痕）。
  `head`/`tail`/`predicate` **任一**呈密钥形态 ⇒ **整条丢弃**（**无 ref 逃生口** —— 关系没有
  `coeffect:` 可引用之物）。**留痕恒 over-redact**：`_relation_label` 对三段**一律** `redact_secrets`
  —— 与 `_plan_key_facts` 的**有意不对称**（keyfact 的实体名不可能是丢弃原因，而关系的**实体名
  正是**原因之一）。
- **存储复用 `_write_key_fact` 形状**：`id = f"relation.{slug(head)}--{pred}--{slug(tail)}"`、
  `content = f"{head} --{pred}--> {tail}"`、`tags = ["relation", "entity:…", "predicate:…"]`
  （+ `session:<key>` 溯源标注）、`source="relation"`、`kind="semantic"`、`session_id=""`、
  `trace_id=f"compaction.{key}"` ⇒ **同 `id` 幂等覆盖**、同豁免面（`_GATE_EXEMPT_SOURCES` 补
  `"relation"`）、同 `Effect(op="memory.write", trace_id="compaction.<key>")` ⇒ **回滚压实连带
  撤销关系**。必须走 `MemoryStore.write`，**不开新写入路径**。
  `kind="semantic"` 是**承重**的：`_episodic_groups` 只收 `kind=="episodic" and layer=="L2"`
  ⇒ 关系**不回喂**压实材料。
- **有界**：`relation_cap` **别名到** `key_fact_cap`（`0.25/8/16`）⇒ 全仓**一把调参旋钮**；批内按
  完整三元组去重、keep-first。
- **注入面复用既有「相关事实」块**：`_gather_facts` 以 `exclude_fact_sources=("compaction",)` 读 L2，
  关系是 `source="relation"` ⇒ **自动**被检索并经 `planner.py` 既有的「相关事实：」块渲染 ——
  **不加第 11 个提示词块**、零管线改动。代价：关系与关键事实**争同一份额度**，提示词中除 `-->`
  渲染外不可区分（要分开须另立 change，且应在 §3.3 区块工作**之后**）。
- **DI 接缝 + 配置门（缺省关）**：`MemoryStore(relation_extractor=…)` 缺省 `None` ⇒ UNWIRED ⇒
  压实**逐字不变**；配置 `memory.relation_extract` 缺省 `False`，组合根
  `relation_extractor=extract_relations_with(_llm_text) if config.relation_extract() else None`。
  **这刻意偏离 §3.4 的无条件接线**（`key_fact_extractor` 恒在）：代价是开箱即用时该能力**惰性**，
  换来「无配置 ⇒ 既有路径逐字不变」。
- **已知局限**：每次压实**多一次模型调用**（2× 抽取延迟，压实是冷路径）；事实面预算**三分**
  （关键事实 / 关系 / 摘要各争同一 cap）；双语白名单上线初期仍会在**长尾表达**上 drop —— 这正是
  **预期的可观测信号**；**无图存储 / 无遍历 API**（不做 `MemoryBackend` 扩展）。详见
  `coding-plan/known-risk.md` §3 ADR-0193 行。

### 3.10 语义遗忘面（派生事实参与遗忘，change `0204`／ADR-0194／账本 E141）

`forget()` 的旧守卫是 `kind != "episodic" or layer != "L2" ⇒ continue` ⇒ `kind="semantic"` 条目
**永不遗忘**（规格写死的：`memory/spec.md` 原文「semantic 条目 … SHALL 不受遗忘影响」）。结果
是语义一类**只增不减** —— 派生事实（`keyfact.*` / `relation.*`）持续占注入预算。本 change
**收窄**该豁免面（**首次对既有 Requirement 做 MODIFIED / 全量替换**）。

- **豁免边界（二分 `_GATE_EXEMPT_SOURCES` 的四个来源）**：**摘要类** semantic
  （`source ∈ {compaction, context}`）**永久豁免** —— 它们是「已准入材料的**骨架**」，遗忘会丢结构；
  **派生事实类**（`source ∈ {extraction, relation}`）**可参与** —— 是可再抽取、可衰减的**细节层**。
  **关键澄清**：**豁免评分（`_GATE_EXEMPT_SOURCES`）≠ 豁免遗忘** —— 前者管「写入时过不过
  importance 闸门」，后者管「衰减时归不归档」，二者是**不同面**（二集合恰好二分同一组来源）。
- **复用同一判据**：派生事实的归档仍走 `_decay_score`（新鲜度 × 复用 × 重要度）+ 同阈值
  `_FORGET_THRESHOLD` + `migrate` → L4 + `forgetting.<id>` 效应 ⇒ **零新评分逻辑、零新去向、
  零新撤销面**；改动面仅**一处布尔守卫**。开关**不**表达「多老算老」（配比 / 判据面不加键）。
- **守卫用短路布尔**：`forgettable = kind=="episodic" or (self._semantic_forgetting and
  kind=="semantic" and source in _FORGETTABLE_SEMANTIC_SOURCES)` —— 缺省关时首项即假 ⇒ 退化为旧守卫
  （**逐字等价**），且**不新增 `If` 嵌套层级**（守架构门禁）。常量
  `_FORGETTABLE_SEMANTIC_SOURCES = {extraction, relation}` 与 `_GATE_EXEMPT_SOURCES` 并列。
- **DI 接缝 + 配置门（缺省关）**：构造参 `MemoryStore(semantic_forgetting=False)` + 配置
  `memory.semantic_forgetting`（缺省 `False`）⇒ 派生事实与摘要类**同**不受影响（既有路径**逐字
  不变**）；组合根 `semantic_forgetting=config.semantic_forgetting()`。**`forget()` 签名不动** ⇒
  三处零参调用点（`loop/default.py` / `entry.py`）逐字不变。
- **已知局限**：归档 **≠** 移出注入面（`read()`/`_gather_facts` 无层过滤，L4 仅加性降权 0.2）；
  只归档「不再被重抽」的事实（活跃重抽的 `ts` 被刷新 ⇒ 永不陈旧，且重抽**重置 `reuse_count`**）；
  缺省关使能力**惰性**。详见 `coding-plan/known-risk.md` §3 ADR-0194 行。

### 3.11 后端落盘耐久（原子写 + 逐行容错，change `0206`／ADR-0196／账本 E143）

`FileBackend` 是动态记忆主库（每轮 `remember`/压实/抽取都写），此前却是全仓唯一「写非原子 +
读不容错」双无防护面 ⇒ 半写崩溃即 `build_runtime` 起不来。本 change 补两项**缺省生效**的耐久承诺：

- **原子写**：`_persist` 改 **tmp ＋ `os.replace`**（镜像 `persistence.write_state` / `CheckpointStore._persist`
  的写法；**不复用 `write_state` 本体**——它对 payload 做 `json.dumps`，JSONL 已是拼接串）。失败点从
  **目标文件**移到 **tmp 文件** ⇒ 目标不动、既有条目集合不受半写影响。
- **逐行容错**：`_load` 逐行 `try/except (ValueError, TypeError)` 跳坏行（`JSONDecodeError ⊂ ValueError`
  覆盖半行；`MemoryEntry(**)` 的 `TypeError` 覆盖结构不符行），`_load` 末尾**汇总一次**告警
  （`损坏 N 行`＋文件名）。**不收 `OSError`**——读失败仍炸启动（环境问题 ≠ 数据损坏）；**不回显行内容**
  （条目可能含敏感信息）。
- **缺省生效、无开关**（本批唯一例外）：这是**缺陷修复**而非新行为——完好文件行为**逐字不变**，
  损坏文件从「启动崩溃」变「跳过坏行」；给「起得来」加开关等于允许把客户端关成砖。
- **已知局限**：`.tmp` 残骸不清理（同 CheckpointStore 口径）；告警每次构造后端一次、不去重；
  坏行寿命 = 到下次写为止（任一写即以完好集合覆盖）。详见 `coding-plan/known-risk.md` §3 ADR-0196 行。

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
