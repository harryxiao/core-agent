# Design 0203 — 实体关系抽取（relations）

## D1 独立类型 `Relation`，不给 `KeyFact` 加字段

`KeyFact` 是**已发布契约**（`KeyFactExtractor = Callable[..., list[KeyFact]]`）；加宽它会动摇
`parse_key_facts` / `scrub_key_fact` / `_plan_key_facts` 与 `tests/test_memory_key_facts.py` 的
全部既有用例。独立 frozen dataclass 是**纯加法**，且三个字段（`head` / `predicate` / `tail`）
无 `value` / `ref` —— 「关系不携带取值」由**类型**表达，不靠约定。

## D2 谓词：中英双语闭合白名单 + 归一化（用户裁决）

`RELATION_PREDICATES` = 变体串 → 规范英文谓词的映射，规范集合为 8 个：
`depends_on / part_of / uses / causes / blocks / owns / implements / related_to`。

归一化：`strip()` → 去包裹引号 → 小写 → 内部空白折叠为单空格 → 查表。中文无大小写，故小写化
对中文变体无害。**落库存规范英文谓词**（`id` / `tags` / `predicate:` 标注一并用规范值）。

**为什么闭合**：（a）开放谓词使「图」不可遍历、不可靠查询；（b）成为**第四个无界自由文本字段**
（head / tail 已是两个）—— 新的密钥携带面；（c）不可有界 ⇒ 同三元组幂等去重的基数失控。
**为什么双语**：纯中文会话的 drop 率显著下降；代价是词表维护面翻倍、归一化规则更重（登记为局限）。

## D3 脱敏：判据一处定义、`scrub_relation` 单一入口

复用 `extract.looks_like_secret` / `redact_secrets` / `slug_entity`（沿 `loop/default.py` 复用
先例 —— 判据只有一处定义、多处消费）。

`scrub_relation(relation) -> tuple[Relation | None, str]`，第二项为**丢弃原因码**：
`""`（可用）/ `"empty"` / `"predicate"` / `"secret"`。**检查顺序**（顺序即安全）：
1. **先**对 `head` / `tail` / **原始** `predicate` 做密钥形态判定 ⇒ 命中即 `"secret"`。
   —— 必须**先于**谓词归一化：否则密钥形状的原始谓词会走「未知谓词」分支，被**原样回显**进留痕。
2. `head` / `tail` 去空白后为空 ⇒ `"empty"`。
3. 谓词归一化；不在白名单 ⇒ `"predicate"`（留痕报**原始**谓词）。
4. 截断：`head` / `tail` 头截断于 `_MAX_FACT_CHARS`。

**留痕中的实体名 / 谓词名一律先 `redact_secrets`**（over-redact）—— head 本身可能就是密钥，
直接回显即泄漏。这是本 change 相对 `_plan_key_facts` 的一处**加固**（keyfact 的实体名不可能是
被丢弃的原因，关系的实体名**正是**丢弃原因）。

**`:ref` 逃生口的有意缺失**：keyfact 可在「无引用 ⇒ 丢弃」与「有引用 ⇒ 抹值」间选择；关系
**没有取值可抹** ⇒ 任一侧密钥形状**只能**整条丢弃。该不对称写入 ADR。

## D4 有界：`relation_cap` 别名到 `key_fact_cap`

`relation_cap = key_fact_cap`（赋值别名，**不**复制常量）。全仓**一把调参旋钮**：同一 `RATIO /
MIN / MAX` 形状；同批去重按**完整三元组** `id`、keep-first（同 `_plan_key_facts`）。

## D5 存储：复用 `_write_key_fact` 的形状（不开新写入路径）

| 维度 | keyfact | relation |
|---|---|---|
| `id` | `keyfact.<slug(entity)>` | `relation.<slug(h)>--<pred>--<slug(t)>` |
| `content` | `<entity>: <value>` | `<h> --<pred>--> <t>` |
| `source` | `extraction` | `relation` |
| `kind` | `semantic` | `semantic` |
| `session_id` | `""`（全局层） | `""`（全局层） |
| `trace_id` | `compaction.<key>` | `compaction.<key>` |
| `tags` | `key_fact` + `entity:` + `ref:`? + `session:`? | `relation` + `entity:`×2 + `predicate:` + `session:`? |

**收益全部是免费的**：同 `id` 幂等覆盖、`_GATE_EXEMPT_SOURCES` 豁免（补 `"relation"`）、
`Effect(op="memory.write", trace_id="compaction.<key>", undo=…)` ⇒ **回滚 `compaction.<key>`
连带撤销关系**。`kind="semantic"` 是**承重**的：`_episodic_groups` 只收
`kind=="episodic" and layer=="L2"` ⇒ 关系**不回喂**压实材料（**必须断言**）。

**长 `id` sanity**：3 × `slug(48)` ≈ 105–150 字符。`FileBackend` 把 `id` 作为 **JSONL 的字段**
（`json.dumps(asdict(entry))`）—— **非**文件名 ⇒ 无路径长度约束。但仍**断言**（长 id 经
`FileBackend` 往返 `put` → 重载 `get` 成功），不靠假设。

## D6 注入面：复用既有「相关事实」块，不加第 11 个提示词块

`DynamicAssembler._gather_facts` 以 `exclude_fact_sources=("compaction",)` 读 L2，而关系
`source="relation"` ⇒ 自动被检索并经 `planner.py` 既有的「相关事实：」块渲染 —— 零管线改动、
零新块序契约、与 `0201` 的区块工作零冲突。

**代价（登记）**：关系与关键事实**争同一份额度**（`0201` 的 `memory_tokens`），提示词中除
`-->` 渲染外不可区分。要分开就是**另一个 change**（新块 = 提示词契约变更，且须在 `0201` 之后）。

## D7 DI 接缝 + 配置（缺省关、显式开启 —— 用户裁决）

- `MemoryStore(relation_extractor=None)` 缺省 ⇒ `_extract_relations` 立即返回 ⇒ 压实**逐字不变**。
- 配置 `memory.relation_extract` 缺省 **`False`**；组合根
  `relation_extractor=extract_relations_with(_llm_text) if config.relation_extract() else None`。
- ADR **明写**：这**刻意偏离** `0155`（keyfact 抽取器在 `runtime.py` **无条件**接线），
  代价是开箱即用时该能力**惰性**；换来的是「无配置 ⇒ 既有路径逐字不变」。
- 与 `key_fact_extractor` **刻意分离**（合并会改关键事实 prompt 字节、打掉 `0155` 的提示词用例）。

## D8 架构门禁（既有，自动覆盖 —— 不需新测试）

`tests/test_architecture.py::test_memory_notes_api_excludes_document_corpus_dimension` 对
`src/core/memory/` 的**公开面**（函数 / 方法名 + 形参名 + 类名，AST 走查）做词元比对，新增公开
标识符（`Relation` / `RelationExtractor` / `RELATION_PREDICATES` / `build_relation_prompt` /
`parse_relations` / `scrub_relation` / `extract_relations_with` / `relation_cap`）**不**含
`document/chunk/corpus/ingest/pdf/retrieve/rag` 任一词元 ⇒ 自动全绿，**无需**另立门禁用例。
（该门禁刻意不含 `vector` / `embed` —— memory 语义记忆面合法用嵌入。）

## 已知局限（登记）

① 每次压实**多一次模型调用**（2× 抽取延迟；压实是冷路径 ⇒ 接受）；② 事实预算现由
关键事实 / 关系 / 摘要**三分**（`cap` 为 16 ⇒ 有界，但这也是未来可能需要独立块的原因）；
③ 双语白名单上线初期仍在长尾表达上 drop（**这正是预期的可观测信号**）；④ 无图遍历 / 查询 API
（**有意**：零消费者 + 后端接口变更 + 迁移成本 ⇒ 关系以「普通 L2 条目 + 标签约定」承载）。
