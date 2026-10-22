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
| **L1** | 索引 | 后端维护的 `id → layer` 映射（`list_index()`），供迁移/审计定位；**不参与检索打分** | 随写入 / 迁移同步更新 | ↓ 精简 |
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

- 相关性打分：`relevance = 0.5·sim + 0.2·layer_priority + 0.15·tier`；时间 / 复用 / 重要度由 `rank` 乘性调制。
- **词法 IDF/长度归一**（change `0252`／ADR-0242）：未注入 embedder（或调用失败）时，相似度按
  BM25 口径计算——罕见词元权重更高、长文档被长度惩罚；`read` 对**过滤后的候选集**构建一次
  语料统计（分词缓存），排序阶段不再重复分词。注入 embedder 的余弦相似路径与 `stats=None` 的
  原重叠公式均逐字不变；无有效 embedding 模型（未配置且端点未命中 / 推导关闭）时 CLI 启动向
  stderr 提示一次「词法匹配」；仅经端点表推导出模型时提示一次「按端点自动选用 …」
  （change `0271`／ADR-0261）。
- **批量语义相似**（change `0290`／ADR-0280／台账 E226）：`read` 排序前调用
  `relevance.batch_similarities`，候选（含 query）按 64 条一批向量化，调用数 O(N/64) 而非
  O(N)；query 恒在第一块 ⇒ 每次检索至多嵌入一次，余弦算完即弃（不驻留 10k 向量）。空候选集
  **不调用** embedder。任一异常 / 数量或维度不符 ⇒ 本次检索**整体**降级 BM25，不混合尺度。
  同步薄壳在运行中事件循环内改经一次性工作线程桥接（ADR-0280 D1）—— 修复了此前
  `asyncio.run` 嵌套失败导致的**粘性** `_embed_failed`（本进程后续检索全走词法）。
  仍阻塞事件循环、连接不复用、4096 条 FIFO 向量缓存仍会抖动（局限见 ADR-0280）。
- **硬性 budget**：`read` 返回的总 token 不超过预算；超限按 `layer_priority × relevance` 截断。
- 层权重默认：L0 > L3（相关技能）> L2（相关事实）> L1 > L4。
- **内容分区权重**（change `0277`／ADR-0267／台账 E213）：按条目 `tags` 三档加性加权 ——
  `milestone`/`decision` ⇒ `tier = +1`、`log`/`transcript` ⇒ `tier = −1`、其余（含未知 / 无标签）
  ⇒ `0`，系数 `0.15`。精确小写匹配、冲突高档优先、只看 `tags`（不看 `source`/`kind`）；默认开启、
  无配置开关。**默认档零偏移**是硬约束：`rank` 乘复用/重要度调制，正常量偏移会被放大（初版
  `+0.075` 使 1 万条基准 recall@5 由 1.000 降至 0.45），居零后未分档条目得分与分档前逐位相同。
- **检索质量离线回归门**（change `0261`／ADR-0251／台账 E197）：`tests/test_memory_quality.py`
  以 26 条固定合成语料（L2 当前事实 / L3 技能 / L4 归档 / 跨会话 / `bench.stale` 陈旧冲突 /
  诱饵）＋ 12 条带 gold 查询做**纯离线、确定性**基准：**recall@5 ≥ 0.9**、**MRR@5 ≥ 0.7**、
  **stale_hits = 0**（陈旧条目排名高于对应当前事实的查询数）。每条查询**新建 store 重放**，
  规避 `_reinforce` 改写 `reuse_count` 的顺序耦合；`ts` 固定未来值使 `recency_decay` 恒 1.0。
  另验 `exclude_source_prefixes=("bench.stale",)` 的真实排除面与两次重放的 top-5 一致性。
  阈值 / 语料变更视为**显式重定基线**（须记录原因），不得为变绿静默放宽 —— BM25 公式、分词或
  层权重的改动须先过此门。
- **规模基准（1 万条）**（change `0275`／ADR-0265／台账 E211；延迟修复 `0276`／ADR-0266／E212）：
  `tests/test_memory_scale_benchmark.py` 以 **10 000** 条确定性合成事实（L2/L3/L4 分布、唯一锚点
  `zqNNNNN`）× **20** 条带 gold 查询，度量 **recall@5 / MRR@5**（阈值 ≥ 0.9 / ≥ 0.7，实测均 1.000）
  与**逐查询延迟**；纯内存、零网络。`0275` 首测中位 **≈657ms**（`estimate_tokens` 逐字符判定 +
  每次检索全量重分词）；`0276` 修复后参考机中位 **85.8ms** / p95 125.5ms —— **满足**
  CORE-NFR-PERF2（`< 100ms` / 1 万条，中位口径）。产品目标仍**只报告、不作跨机门禁**；回归上限
  `p95 < 1000ms`。语料生成无随机源，两次重放逐条一致；层权 / BM25 / 分词改动须同时过 26 条质量门
  与本规模门。
- **词元缓存与估算提速**（change `0276`／ADR-0266）：`estimate_tokens` 的 CJK 计数改为预编译
  正则 `sub`（口径逐位不变，10k 条 ≈546→39ms）；`MemoryStore` 持**按内容校验**的有界词元缓存
  （`_TOKEN_CACHE_MAX = 20_000`，FIFO），同 id 覆写内容自动失效，未变条目跨检索复用词元集
  （第二次检索只对查询分词）。排序 / 打分 / 预算语义零变化；冷启动首读仍约 220ms。

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
- **临时会话（ephemeral）**（change `0245`／ADR-0233）：`MemoryStore(ephemeral_sessions=(…,))`
  命中的会话（当前仅基准执行会话 `bench`，由组合根在执行面门控开启时登记）压实**只做会话级
  摘要与归档**，SHALL NOT 写全局层派生（关键事实/关系/episodic）或交付 canonical 提升 ——
  基准内容不得污染用户全局检索面。缺省空集 ⇒ 压实逐字不变。
- **摘要为滚动合并**（change `0148`／ADR-0140／账本 E90）：该会话已有摘要时，`compact` 把
  **既有摘要 + 新增 episodic 条目**一并投喂摘要器 ⇒ 更新摘要**融合既有结论与新增事实**，早期结论
  **不被静默丢弃**。滚动的是**内容**，摘要条目 `id` 与「每会话至多一条、不增长」口径**不变**。
- **摘要只读访问器**（change `0150`／ADR-0142／账本 E94）：`MemoryStore.summary_for(session_id)`
  按会话取回既有摘要条目（口径同压实写入），**只读** —— 零写入、零效应、不动
  `reuse_count` / `importance` / `updated_at`。供上层（CLI `notes promote`）取数做提升。
- **摘要越界的提升钩子**（change `0153`／ADR-0145／路线图 G3）：滚动合并上界 `MAX_SUMMARY_CHARS`
  是既有摘要**投喂时的节选上限** ⇒ **越界即下一轮滚合并开始截断既有内容**（信息不可逆销毁）。
  摘要 prompt 的字数要求与同一常量**同源**（change `0242`）：`summarize_with` 渲染时直接取
  `MAX_SUMMARY_CHARS`（缺省 2000），不再写死 800 —— 此前 prompt 只要 800 字，模型被提示产出
  约四成于存储上界的长度，与「越界才节选」的设计意图漂移。
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

- **结晶钩子**：`Crystallizer.crystallize(skill_entry, *, force=False) -> PluginCandidate | None`
  按 `reuse_count >= 3`（`CRYSTALLIZE_MIN_REUSE`）或显式 `force` 产出插件候选，交 L4 Validator；
  未达标返回 `None`。L4 引擎在人工确认后的架构级分支以 `force=True` 调用，产物随
  `EvolutionOutcome.artifact` 返回（change `0305`／ADR-0295）。
- **溶解钩子**：`Crystallizer.dissolve(plugin_id)` 返回 L3 教训条目，`trace_id` 非空、可被
  `MemoryStore.write()` 接受。观察期溶解走 `EvolutionEngine.dissolve()`（写 L2 教训 + 弃用技能），
  与钩子不双写。
- **能力边界**：两个钩子都是**纯函数** —— 不自行落盘、不注册可逆效应；回滚（卸载插件 / 重装插件）
  由调用方（进化引擎 / 技能库）负责。

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
  兼容别名（= 下限）。**缺省抽取 prompt 的条数要求与同一旋钮同源**（change `0242`）：
  `build_extract_prompt` 未显式覆盖时按 `key_fact_cap(n)`、`build_relation_prompt` 按
  `relation_cap(n)`，prompt 不再写死独立数字（此前固定 8，聚合条数多时 prompt 与落库名额漂移）。
  `entity` / `ref` 长度 `_MAX_FACT_CHARS`(200) 头部截断，`value` 超长时**首尾保留**
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
  **成本登记**（change `0302`／P2-6）：开启后评分在**写入路径同步执行** —— 每条非豁免条目一次
  LLM 调用，写入延迟随模型往返上升（豁免面 `compaction` / `context` / `extraction` 不受影响）。
  这是刻意的取舍：入口筛选换来更干净的 L2；批量化 / 异步化不在本账内。
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
- **只读呈现面（消费者，change `0211`／ADR-0201／账本 E148）**：只读诊断源加视图 `render_chain`
  （`core/diagnostics/views.py`）⇒ TUI `/chain` 与 CLI 诊断面**同一产出**。取数走**注入的可调用**
  `Deps.chain`（`ChainHandle = Callable[[str], list[ChainNode]]`，沿 `SessionsHandle` 先例）——
  诊断包**不建 store 实例、不引 `core.runtime`**；生产接线 = `entry._memory_chain()` 的**裸店**
  （免 runtime，先例 `_memory_summary`）。呈现**有界**（单会话最近 `_MAX_CHAIN_ROWS = 20` 节）且
  **只含链路语义**（节点无正文 ⇒ 无需脱敏闸）；按会话分组取自 `Deps.sessions`，缺失则退化为
  不过滤的一节。**本模块零改动** —— 零效应由 `session_chain` 既有实现原样承载，视图只是消费方。
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
  完整三元组去重、keep-first。**prompt 与同一旋钮同源**（change `0242`）：`build_relation_prompt`
  未显式覆盖时要求的名额即 `relation_cap(n)`；谓词表由公开的 `RELATION_PREDICATES` **渲染**
  （每个规范谓词列出全部中英文变体），既有 prompt 只写英文规范名 ⇒ 中文变体虽可归一化落库、
  模型却从未被提示可用。
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
- **归档 ≠ 移出注入面**（本条由 change `0301` 闭合）：`forget()` 现在迁移的同时打
  `forgotten` 标签，`read()` / `failure_lessons()` 缺省排除（见 §3.16）；**旧数据**（0301 之前
  已遗忘的 L4 条目）无标签 ⇒ 仍可召回，无法追溯，登记于 known-risk。
- **已知局限**：只归档「不再被重抽」的事实（活跃重抽的 `ts` 被刷新 ⇒ 永不陈旧，且重抽**重置
  `reuse_count`**）；缺省关使能力**惰性**。详见 `coding-plan/known-risk.md` §3 ADR-0194 行。

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
- **跨进程合并**（change `0301`）：以上原子/容错语义保留，`_persist` 另在锁内先读盘合并
  变更集（不再是内存快照覆盖）—— 见 §3.16。
- **已知局限**：`.tmp` 残骸不清理（同 CheckpointStore 口径）；告警每次构造后端一次、不去重；
  坏行寿命 = 到下次写为止（任一写即以完好集合覆盖）。详见 `coding-plan/known-risk.md` §3 ADR-0196 行。

### 3.12 失败教训只读读面（change `0217`／ADR-0207／台账 E154）

- 新**零效应只读** `MemoryStore.failure_lessons(session_id, *, limit=5) -> list[MemoryEntry]`：
  只收 `tags` 含 `failure` 的条目（本仓该标签**唯一**生产者是 loop 的轮级失败条目
  `loop.failure.<trace_id>`，见 §3.10 同源判据），`ts` **降序**、**至多 `limit` 条**（产物有界）；
  `session_id` 缺省空串 ⇒ 不按会话过滤（口径同 `session_chain`）。
- **层无关**：失败条目**仍走遗忘**（`_PRESERVE_TAGS` 只豁免**压实**、不豁免遗忘）⇒ 会迁 L4；本读面
  **不按层过滤** —— 否则「教训已积累但被归档」的会话恰在最需要时看不见自己的教训。
- **绝不走 `read()`**：后者命中即经 `_reinforce` **+1 `reuse_count` 并落盘可撤销效应**（§3.5 同源）；
  本读面**每轮推理都跑**（供 loop 的「既往失败教训」块）⇒ 必须零效应、且**不变更**任何条目字段。
- 消费面：组合根闭包渲染为有界块（每条折叠一行、不暴露条目 id）→ `loop.failure_lessons_consult`
  （见 `doc/02-modules/loop.md` §3.6.1）。

### 3.13 情景归纳（episodic consolidation，change `0218`／ADR-0208／台账 E155）

三类记忆的专属沉淀 prompt 里**情景类**长期缺位（复用通用**会话摘要** prompt）⇒ 材料口径 /
副作用 / 产物去向三重不同的两路被同一文本压平、无法各自演进。本 change 给它独立接缝：

- **新模块** `core.memory.episodic`（镜像 `extract.py` 三段式、契约返回**文本**同 `summarize_with`）：
  `EpisodicExtractor = Callable[[list[MemoryEntry]], str]`、`_PROMPT_HEAD`（四段：目标 / 经过 /
  结果 / 教训）、`build_episodic_prompt`、`consolidate_with`。memory 依旧**不 import** LLM / rag 抽象。
- **接缝** `MemoryStore.episodic_extractor`（缺省 UNWIRED），挂进 `_summarize_sessions` 的会话循环
  ⇒ 与摘要 / 关键事实 / 关系**同材料、同价值门控、同 trace**（`compact()` 守卫同步纳入）。
- **条目形状**：`id=episodic.<key>`（`key = session_id or "default"`）⇒ **每会话至多一条**、同 id
  **覆盖式**更新（条目不增长）；`source="episodic"`；`tags=["episodic","session:<key>"]`；
  `session_id=""`（全局层，同关键事实 / 关系）；`trace_id=compaction.<key>`（随压实回滚）。
- **`kind="semantic"` 是承重设计**（非标签选择）：`_episodic_groups`（§3.4 / §3.6 的材料源）入选判据是
  `kind == "episodic"` ⇒ 归纳产物**结构性**地**不进**压实材料、**不回喂**摘要器 —— 否则形成
  「摘要 → 归纳 → 摘要」**自激环**。`tags` 里的 `episodic` 只是**人读标签**、不承担机制。
- **脱敏在 store 侧无条件**（承 `extract` 红线）：注入的归纳器**不构成信任边界**（输出可能夹带模型
  **复述**的明文密钥）⇒ 落库前 `redact_secrets` ＋ 截断 `MAX_EPISODIC_CHARS`；失败 / 空文本 ⇒
  整条不写、留痕**只报会话键**。
- **缺省关**（`episodic_extractor=None`）⇒ 压实**逐字不变**；组合根键 `memory.episodic_extract`。
- **已知局限**：新 `source="episodic"` **未**登记 `_GATE_EXEMPT_SOURCES` / `_FORGETTABLE_SEMANTIC_SOURCES`
  ⇒ 与 `importance_gate` 同开时会**过闸**且**恒豁免遗忘**（登记为后续候选）；归纳文本**自由不可机读**；
  每会话一条 ⇒ 超长会话早期结论被后续**覆盖稀释**。详见 `coding-plan/known-risk.md` §3 ADR-0208 行。

### 3.14 L2 活跃层软上限的装配（change `0230` 实现／`0251` 接线，ADR-0241／台账 E187）

`MemoryStore(l2_soft_max_entries=...)` 的收口逻辑见规格「L2 活跃层软上限」：写入落库后先走
`forget()` 衰减归档，仍超限则按 `ts` 从旧到新把**可遗忘**条目迁 L4（`l2_cap.<id>` trace，
可撤销）。本 change 补的是**生产可达性**：

- **配置键** `memory.l2_soft_max_entries`（ConfigSpec 单一真源，三面：CLI flag / env /
  `memory:` 段），**缺省未设置 = `None` = 不启用**。取值须为 ≥1 的整数；`bool` / 小数 /
  非数值 / `0` / 负数归一为 `None`（`memory` 段非结构化 ⇒ 不阻断启动）。
- **组合根注入**：`build_runtime` 以 `config.l2_soft_max_entries()` 构造 `MemoryStore`
  ⇒ 配置即生效。接线前该形参**没有任何生产调用方**，软上限能力永远关闭。
- **未启用即无界**：`FileBackend` 整份加载 JSONL、检索线性扫描 ⇒ 不设上限时 L2 常驻内存与
  每轮扫描成本随运行时长单调上升。这是**运维风险**（登记 `coding-plan/known-risk.md`），
  不是缺省行为缺陷：缺省关闭保证升级后不静默归档既有数据。
- **只在写入后收口**：存量超限库要等下一次写入才收敛（不在 `load()` 里跑，避免启动即迁移）；
  L4 归档只增不减（「不物理删除」规格的必然结果）。

### 3.15 写入观察者（memory.write 钩子接缝，change `0269`／ADR-0259）

- **DI 形参**：`MemoryStore(write_observer=...)`，契约 `Callable[[Layer, MemoryEntry], None]`
  （`layer`, `entry`）。缺省 `None` ⇒ **零调用**，写入路径逐字不变。
- **调用点**：公开 `write` 落库（含可逆效应登记）**之后**同步通知 —— 钩子看到的是
  「已写入」事实；通知异常**吞掉**（写入成败不受钩子影响）。
- **不可否决**：观察者无返回值语义；`memory.write` 不得阻断写入（静默丢写入 = 进化轨迹断点）。
- **载荷由观察者侧构造**：memory 只交 `(layer, entry)`，不 import 钩子语义面（依赖方向不变）。
- **代价**：同步执行在写入路径上 —— 慢钩子会拖慢落盘（登记为 ADR-0259 已知局限）。

### 3.16 跨进程落盘合并与遗忘检索隔离（change `0301`／ADR-0291／台账 E237）

**跨进程合并落盘**（闭合 P0-1）：`FileBackend` 原实现每次写入都用**进程启动时的内存快照**
整体重写 `memory.jsonl`（`put` / `put_many` / 删除 / 每轮读取强化皆如此）⇒ TUI 长驻进程、
`task` / cron 短进程、`memory maintain` 共用同一文件时后写者**静默覆盖**先写者，无锁、无告警。

- **变更集而非快照**：`_persist(changed, deleted)` 在独占建议锁内**先读盘**（逐行容错、静默），
  再覆盖本次写入的 id、移除本次删除的 id，最后原子写；落盘成功后进程内集合**采纳盘上集合**
  （他进程写入立即可见）。`put` / `put_many` / `delete` 只声明本次变更。
- **顺序语义**：同一 id 并发写保持 last-writer-wins（后取锁者胜）；删除只删指定 id，不复活
  他进程已删条目；「完好文件往返逐字节不变」仍成立（合并以盘上顺序为基线）。
- **锁语义 fail-open**：`core/filelock.py::exclusive_file_lock`（自 `orchestration/state_files.py`
  迁入的中性模块，后者 re-export ⇒ 调用方零改动）。锁不可用 ⇒ **无锁写**，记忆写入不得成为
  新失败面。锁文件 `.memory.jsonl.lock`（`0600`），释放不删除。
- **代价**：每次落盘多一次全文件解析（写放大本就是全量重写，同阶）；无锁降级期间仍有覆盖窗口
  （与修复前等价，但不再是常态路径）；Windows `msvcrt.LK_LOCK` 等锁有约 10s 上限，超时即降级。

**遗忘检索隔离**（闭合 P0-2）：原 `forget()` 只迁 L4，而 `read()` 与 `failure_lessons()` 都不按
层过滤（L4 仅降权）⇒ 被「遗忘」的内容仍从两个注入面进入提示词。

- **`forgotten` 标签**：`forget()` 迁移的同时追加该标签，并记一条同 `forgetting.<id>` trace 的
  可逆效应（撤销时先摘标签、再由迁移 undo 迁回 L2 ⇒ 恢复可召回）。标签是既有语义通道
  （同 `failure` / `steps` / `_PRESERVE_TAGS`），不新增 `MemoryEntry` 字段、不改落盘形状。
- **退出注入面**：`read()` 在**排名与预算之前**排除带标签条目（不吃预算、不被复用强化）；
  新增仅关键字 `include_forgotten: bool = False` 作为显式回溯面。`failure_lessons()` 同样排除。
- **审计面不过滤**：`audit()` / `session_chain()` / CLI 列表仍可见（墓碑语义：保留追溯、停止召回）。
- **归档 ≠ 遗忘**：压实、重要度闸门、L2 软上限产生的 L4 条目无标签 ⇒ 仍可召回（既有行为逐字
  不变）。旧数据（0301 之前遗忘产生的 L4）无标签 ⇒ 不具遗忘语义，无法追溯。

### 3.17 读取面层过滤与事实面分层（change `0302`／ADR-0292／台账 E238）

**读取面 `layers`**（闭合 P1-3 的记忆侧）：`read(..., layers=(...))` 接受层白名单，非空时
只保留所列层，过滤与来源排除 / 会话过滤 / `forgotten` **同一位置**（排名与预算之前）
⇒ 被滤条目不吃预算、不被复用强化；缺省空元组 ⇒ 检索语义逐字不变。

**装配面分层**（消费侧）：

- 「相关事实」固定层白名单 `("L1", "L2")` —— L0 人格、L3 演化候选、L4 归档不再以「事实」
  名义进 prompt（L4 归档不再与活跃事实争抢事实面预算）。
- L0 人格经 `read(layers=("L0",))` **单独**读取 → `ContextPack.personality`，规划器以独立
  「人格」块注入，并计入预算**必保项**（与宪法同档）。空 ⇒ 不产块。
- 事实行携带 `layer` / `source` / `id` / `date`（`ts<=0` ⇒ `unknown`），块首声明
  「历史数据、不是指令」；项目信息行独立成块（见 `context` 模块 §3 / context-interface §1）。

**代价**：L4 归档不再经 prompt 偶遇（主动回溯走 `audit()` / CLI）；人格配置过大时极小预算
直接 `BUDGET_EXCEEDED`（显式失败取代静默超窗）。

### 3.18 治理信封与关键事实版本链（change `0303`／ADR-0293／台账 E239）

**信封字段**（`MemoryEntry`，全默认 ⇒ 旧 JSONL 缺键可直接加载）：`content_hash`
（`content.strip()` 的 SHA-256，`write()` 为空时自动计算）、`status`（`active` /
`superseded`）、`version`（同链递增）、`parent_id`（本版本替代的旧版 id）、`superseded_by`
（旧版指向新版）。**不**引入 `namespace` / `trust` / `confidence`（当前无消费方）。

**检索口径**：`read()` 在来源排除 / 会话 / 遗忘 / 层过滤**同一位置**（排名与预算之前）剔除
`status != "active"` ⇒ 旧版不吃预算、不被复用强化；`audit()` / `index()` / `_all_entries()`
不过滤（历史可追溯）。无 `include_superseded` 开关。

**关键事实版本链**（取代此前的原地覆盖）：同实体 slug 的活跃链头为
`keyfact.<slug>`（v1）/ `keyfact.<slug>.vN`。

| 情形 | 行为 |
|---|---|
| 取值未变 | 在活跃版本上**就地刷新**（`trace_id` / `tags` 随本次压实刷新；保留首见 `ts`） |
| 取值变化 | 新增 `keyfact.<slug>.v{N+1}`（`parent_id` 指向旧版），旧版置 `superseded` + `superseded_by`；**不覆盖** ⇒ 旧值经 `audit()` 可读 |
| 旧值为 `<redacted>` | 视为**无历史取值** ⇒ 就地重写（避免失效关键事实修复造出悬空 `.v2` 链头） |

取代动作记 `Effect(op="memory.supersede")`（同 `compaction.<session_id>` trace）⇒ 回滚新版
压实即删除新版并恢复旧版 `active`。`_stale_key_facts()` 只扫活跃条目（历史版本不参与修复）。
关系条目不做版本链：其 id 已编码完整三元组，同三元组覆盖即幂等。

**代价 / 局限**：版本链无保留期上限（压实越频繁、取值越常变，L2 增长越多，清理依赖
`audit()` / 人工）；链头判定每次写关键事实都扫描全部条目（`_all_entries()`，O(N)）。

### 3.19 召回多样性与注入统计（change `0304`／ADR-0294／台账 E240）

**管线位置**：候选 → 既有硬过滤（来源 / 会话 / 遗忘 / 层 / `status`）→ 排名 → **多样性** →
预算截断 → 复用强化。被多样性剔除的条目**不吃预算**、不被 `_reinforce` 强化，排名顺序不变。

| 过滤 | 判据 | 豁免 |
|---|---|---|
| 近重复抑制 | `content_hash` 相同 ⇒ 只留排名最高一条（跨层 / 跨来源生效） | `content.strip()` 为空的条目不参与（否则空正文会压成一条）；旧行哈希为空时按同口径现算 |
| 同会话上限 | `session_id` 非空的条目每会话最多 `_MAX_PER_SESSION = 3` 条 | `session_id == ""` 的全局条目；调用方已用检索参数 `session_id` 收窄到单会话时（结果本就来自同一会话，施加上限只会截断该会话自身事实面） |

**API**：`recall(...) -> RecallResult`（与 `read()` 同参数）；`read()` 签名与返回类型不变
（`recall(...).entries` 的兼容薄壳）。统计字段：

- `matched_count`：通过既有硬过滤、进入排名的候选数；
- `injected_count`：最终返回条目数；
- `excluded_by_diversity` / `excluded_by_budget`：多样性 / 预算剔除数；
- 不变式：`matched_count == injected_count + excluded_by_diversity + excluded_by_budget`；
- `minimum_budget`：再注入第一条被预算跳过条目所需的最小预算（无预算剔除 ⇒ 0）。

**代价 / 局限**：近重复是**完全同文**级（不做 embedding 语义近重复）；会话上限为模块常量、
无配置键；kind 配额与 `source` 级上限不做（本仓字段语义不匹配，见 proposal Non-goals）。

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
| 写入失败 | **不重试、无本地队列**：`_persist` 直写后端，异常向调用方传播（loop 侧不吞错；由进程级错误边界处理）。change `0302` 订正旧文档的「重试 1 次 + 本地队列」臆述 |
| 结晶后插件退化 | L4 评测触发溶解，回退 L3，保留教训 |
| 索引与事实不一致 | 写入 / 迁移在同一路径内同步更新后端索引（`put` / `move`），无异步同步窗口 |

---

## 6. 关联

- 规格：`doc/openspec/specs/memory/spec.md`
- 进化联动：`doc/02-modules/evolution.md`
- 接口：`doc/03-interfaces/memory-interface.md`
- 测试：`doc/04-testing/test-cases.md`（MEM 系列）
