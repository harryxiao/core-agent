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
  长随机串兜底）⇒ **强制** `<redacted>`；② 给出 `ref`（`coeffect:<名称>`）⇒ `value` **一律**
  `<redacted>`；③ **裸密钥无可用引用 ⇒ 整条丢弃** + `warnings.warn` 留痕（含实体名、**不含**取值）。
  ⇒ 方向恒为 **over-redact**（拿不准即多脱敏）。**先脱敏后截断**（截断不得使明文逃逸）。
- **有界**：单次条数 `MAX_KEY_FACTS_PER_COMPACT`(8)；`entity` / `ref` 长度 `_MAX_FACT_CHARS`(200)
  头部截断，`value` 超长时**首尾保留**（头 / 尾各半、中以 `…` 连接，总长仍 ≤ 上限；取值常
  「头定名、尾定值」—— change `0172`）。**同批同 slug 归并**：一批内 `slug_entity` 相同者归并为
  一条、**只留首条**（后至者不挤占额度），被归并者经 `warnings.warn` 留痕（含实体名、不含取值；
  与因密钥丢弃的留痕各自独立）。
  **整批归一化后再落库**（归一化失败 ⇒ 整批不写，不留半批）；抽取器抛错 ⇒ **降级为不抽取**（不牵连
  摘要写回与条目迁移）；返回不可解析 ⇒ 同样不抽取 + 留痕，且 `extract_with` 判据为「**有输出但无
  JSON 数组**」（合法空数组 `[]` 不告警），留痕**不含**模型输出正文（可能含明文密钥 —— change `0172`）。
- 落库走既有唯一写路径 `MemoryStore.write()`（记可撤销效应），不另开第二写路径。

### 3.5 后端可插拔

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
