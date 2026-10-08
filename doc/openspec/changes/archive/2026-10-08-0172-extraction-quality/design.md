# Design: extraction-quality

> 规格 delta：`specs/memory/spec.md`（MODIFIED「结构化实体抽取（关键事实）」）
> ADR：**ADR-0163** ｜ 台账：**E109** ｜ 规格先行：`doc/openspec/specs/memory/spec.md`

---

## 1. 现状核实（逐条有代码定位）

| # | 缺陷 | 定位 | 后果 | 定性 |
|---|---|---|---|---|
| **D1** | 同批同 slug 不归并 | `store.py:67` `_plan_key_facts` 逐条 append，无 slug 去重；`_write_key_fact`（`store.py:526`）以同一 `id` 覆盖式写 | 同批内同实体（或 slug 撞车，如 `API Key` / `api-key`）只留**末条**、**静默**丢值；且 8 个额度被重复占用（`plan` 计 2、实落 1） | **规格未覆盖**（既有条款只讲跨压实「重复抽取」⇒ 覆盖式，属**新规范**） |
| **D2** | 解析失败静默 | `extract.py:152` `parse_key_facts` 在 `_json_array`（`extract.py:138`）返回 `None` 时返回 `[]`，与「合法 0 条」不可区分；store 仅在**抽取器抛错**时 warn（`store.py:508-515`） | 模型反复回不可解析文本（0166/0170 那类「解释 + 围栏」）⇒ **静默零抽取** | **既有规格未兑现** —— `spec.md:379-381` 已明写「抽取器抛错**或返回不可解析的结果** ⇒ SHALL 降级为不抽取（`warnings.warn` 留痕）」 |
| **D3** | `value` 硬截断有损 | `extract.py:115` `value[:_MAX_FACT_CHARS]` 只留**头部 200** | 长取值**尾部信息全丢**（取值常「头定名、尾定值」） | **规格未覆盖**（既有只规定「长度有界 + 先脱敏后截断」，不说截断形态） |

**被原稿误判为缺陷的项**（本文**不做**，理由记录在案）：

- 「多次压缩不重复累积」—— **规格已保证**（`spec.md:362`「同一实体至多一条 —— 重复抽取得覆盖式更新」）。
- `content[:400]` 硬截断 —— **不存在**：`400` 是 `extract.py:27` `_MAX_ENTRY_CHARS`（**入 prompt 的事件节选**，
  另一旋钮）；事实截断是 `_MAX_FACT_CHARS = 200`；且 `content = f"{entity}: {value}"`（`store.py:536`）
  本就 ≤ ~403 字符 ⇒ 对它做首尾保留近乎空操作。

## 2. 决策

### 决策 1 —— D1 归并在**落库前**（`_plan_key_facts`），只留首条

- **落点**：`store.py:67` `_plan_key_facts`（归一化阶段，与脱敏**同处**）—— 该函数已是「整批归一化 ⇒
  `(plan, dropped)`」的唯一咽喉，归并放这里**不新增调用点**、不触 `_write_key_fact`。
- **保留哪条**：**首条**。理由：`plan` 的顺序即模型输出的顺序，「先到先得」与既有「额度按顺序取满
  即 `break`」的语义**一致**；无证据支持「后者更优」（模型重复枚举同一实体时，先后无稳定优劣）。
- **留痕**：**新增独立 warn**，不复用 `dropped`（后者文案是「secret-shaped value without a usable
  reference」—— 语义不同，复用即**谎报**）。`_plan_key_facts` 返回值由二元组扩为**三元组**
  `(plan, dropped_secret, deduped)`；它是**私有函数**，非契约面。
- **额度语义**：归并后条数计额 ⇒ 8 个额度不再被同一实体重复占用（D1 的第二个后果随之消失）。
- **跨批不动**：同实体跨压实的覆盖式更新是**规格明定的正确行为**（`spec.md:362`），逐字不改。
- **`break` 保留原样**：达额即停 ⇒ 额度之后的重名**不**再扫描（归并只在额度内进行，符合有界取向）。

### 决策 2 —— D2 在 `extract_with` 闭包内补告警，契约零变更

- **落点**：`extract.py:173` `extract_with` 的 `_extract` —— 此处是「模型调用」与「解析」的唯一衔接点，
  判别「有输出但无 JSON 数组」**只能**在此（`parse_key_facts` 只拿到文本、拿不到「模型是否调用成功」）。
- **判别**：`facts == [] and text.strip() and _json_array(text) is None` ⇒ warn。
  - **合法空数组**（`[]`）⇒ `_json_array` 非 `None` ⇒ **不**告警（模型明确表示无可抽，正常结果）。
  - **数组存在但元素全不合规**（`spec.md:156-157` 的跳过口径）⇒ 同样 `_json_array` 非 `None` ⇒ 不告警
    （属 schema 不合，非「不可解析」；记为局限）。
- **契约零变更**：`parse_key_facts` 仍返回 `list[KeyFact]`、不可解析仍 `[]` ⇒ `MemoryStore` 侧、
  `KeyFactExtractor` 契约、既有 24 例测试**皆不动**（`test_parse_returns_empty_on_unparseable:312` 继续为真）。
- **留痕禁区**：消息**不含**模型输出正文（可能含明文密钥，承红线「留痕含实体名、不含取值」），
  只报失败事实与**文本长度**。
- **口径**：`warnings.warn(..., RuntimeWarning, stacklevel=2)` —— 与 `store.py:503-525` 既有降级口径**同形态**。

### 决策 3 —— D3 只改 `value` 的截断形态，**总额度不变**

- **落点**：`extract.py:115`（`scrub_key_fact` 的返回式）→ 抽出 `_truncate_value(value)` 助手（`extract.py` 模块内私有）。
- **形态**：`half = (_MAX_FACT_CHARS - 1) // 2`；`f"{text[:half]}…{text[-half:]}"` ⇒ 总长 `2*half + 1 ≤ _MAX_FACT_CHARS`
  （200 ⇒ half 99 ⇒ 199 ≤ 200）⇒ **规格「长度不超过 `_MAX_FACT_CHARS`」的既有断言仍为真**，
  故既有 Scenario「条数与长度有界（先脱敏后截断）」**逐字不改**，另**新增**一条形态 Scenario。
- **只改 `value`**：`entity` / `ref` 维持头部截断 —— 二者恒短（实体名、`coeffect:<名称>`），尾部无信息。
- **顺序不变**：脱敏（第 3/4 步）**先于**截断 —— 首尾保留不触碰该前提，红线段落**逐字不动**。
- **代价（写进 ADR 局限）**：首尾保留**扩大**了截断后可见面 ⇒ 对**脱敏完备性**的要求更高
  （若明文在 200 字符之后且形态未命中，首尾保留会把尾部带出）。本 change **不改**脱敏启发式 ⇒
  风险与现状同阶但**暴露面略增**；跨出该边界需独立 change（0173，见 §5）。

## 3. 接缝与不变量

| 面 | 变更 |
|---|---|
| `KeyFactExtractor` 契约 | **零变更**（仍是 `Callable[[list[MemoryEntry]], list[KeyFact]]`） |
| `MemoryStore.__init__` / `_extract_key_facts` / `_write_key_fact` | **零变更**（仅 `_extract_key_facts` 增一条 warn 语句消费三元组） |
| `parse_key_facts` / `scrub_key_fact` / `slug_entity` / `KeyFact` | 签名与语义**零变更** |
| 公有导出（`core.memory.__init__`） | **零变更** |
| 缺省路径（未注入 `key_fact_extractor`） | **逐字不变** |
| 脱敏顺序与方向 | **逐字不变**（先脱敏后截断；over-redact） |
| 依赖方向 | 不新增任何 import（`extract.py` 仅新增 stdlib `warnings`） |

**无跨层**：不引入 `core.notes`（`extract.py:77` 的分层约束保持）；不触碰 `loop` / `rag` / `ui`。

## 4. 实现待办

1. `src/core/memory/extract.py`
   - 新增 `import warnings`。
   - 新增 `_truncate_value(text: str) -> str`（首尾保留、总额度不变）。
   - `scrub_key_fact` 返回式：`value=_truncate_value(value)`（`entity` / `ref` 不变）。
   - `extract_with._extract`：取文本 → 解析 → 「有输出但无 JSON 数组」⇒ warn → 返回 facts。
2. `src/core/memory/store.py`
   - `_plan_key_facts` 返回三元组 `(plan, dropped, deduped)`；循环内以 `seen: set[str]` 归并、只留首条。
   - `_extract_key_facts` 解包三元组；`deduped` 非空 ⇒ 追加一条 warn（文案区别于 dropped）。
3. 规格 delta 已就位（`specs/memory/spec.md`）；实现须与之逐条对齐。

## 5. 切出（另立，本文不做）

- **`0173` 密钥脱敏白名单** —— 触碰红线（`spec.md:383-384` over-redact + `extract.py:8-10` 模块文档），
  且 `_looks_secret` **同时**守 `value` 与 `ref`（`extract.py:107-109`）；**URL 形态永不放行**
  （`?token=`/`?sig=`/路径内嵌 base64 正是「长随机串」的常见来源）。**建议不做**。
- **`0174` 主题归并** —— 落点在 **L5 组合根**（在抽取链内 import `notes` 会成环：`notes → core.memory`
  已定，见 `notes/backend.py:23` / `notes/store.py:19` / `notes/promote.py:14`）；且先定「落 memory L2
  还是落 canonical `notes/*.md`」与「聚类靠 LLM 还是靠 slug 分组」。

## 6. 局限（同步写进 ADR §局限 + 台账 §3）

① **首尾保留扩大截断后可见面** ⇒ 对脱敏完备性要求更高（见决策 3 代价）。
② **归并只消同批重复**；跨批同 slug 仍是覆盖式（规格已裁，非缺陷）。
③ **归并丢弃的取值不进任何记忆面**（仅留痕）⇒ **有损**归并；首条未必是"更好"的那条。
④ **解析失败留痕不含模型输出正文** ⇒ 事后无法直接复盘模型到底回了什么（红线所迫）。
⑤ **数组存在但元素全不合规**（全被跳过）**不**告警 —— 与「有输出但无 JSON 数组」不同，本次未覆盖。
⑥ **上界 `MAX_KEY_FACTS_PER_COMPACT` 未放宽**（8 保持）；归并使之不再被重复占用，实质覆盖改善但额度未变。
