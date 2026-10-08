# Proposal: extraction-quality（关键事实抽取端质量）

> **本文取代** 同目录下原 `proposal.md`（原文保留在 `proposal.superseded.md`）。
> 重写理由：原稿 6 条里 **3 条对代码现状的事实陈述有误**（照写会改错旋钮 / 做无用功）、
> **1 条触碰密钥红线**、**1 条跨分层成环**、且自称 `风险：低` 与其中两条自相矛盾。
> 现按「**真实缺陷 + 可独立实施 + 不越红线**」重划范围，并把切出去的两条另立成 change 清单（见 §5）。

---

## 1. Why —— 核实过的现状

规格：`doc/openspec/specs/memory/spec.md`「结构化实体抽取（关键事实）」（change 0155 / ADR-0147 / 台账 E108 后的 G4）。
代码：`src/core/memory/extract.py`（抽取器侧）、`src/core/memory/store.py`（落库侧）。

抽取端**已经**具备（**原稿误判为缺失**）：

- **同实体幂等覆盖**：规格 `spec.md:362` 明文「`id = f"keyfact.{实体 slug}"`（**同一实体至多一条** ——
  重复抽取得**覆盖式更新**，条目不增长）」，`store.py:526` 的 `_write_key_fact` 即按此落库 ⇒
  **「多次压缩不重复累积」已被规格保证**，不存在。
- **值长度有界 + 先脱敏后截断**：`extract.py:33` `_MAX_FACT_CHARS = 200`，`extract.py:114-116`
  逐字段截断；规格 `spec.md:385` 与 Scenario「条数与长度有界（先脱敏后截断）」明写。
  注：原稿所称的 `content[:400]` 不存在 —— `400` 是 `extract.py:27` `_MAX_ENTRY_CHARS`
  （**入 prompt 的事件节选**，另一个旋钮），且 `content = f"{entity}: {value}"`（`store.py:536`）
  本就 ≤ ~403 字符，对它做首尾保留是**空操作**。

抽取端**确实存在**的缺陷（逐条有代码定位）：

| # | 缺陷 | 定位 | 后果 |
|---|---|---|---|
| **D1** | **同批同 slug 不归并** | `store.py:67` `_plan_key_facts` 逐条 append，无按 `slug_entity` 去重；`_write_key_fact` 以同一 `id` 覆盖式写 | 同批内同实体（或两个不同实体 slug 撞车，如 `API Key` / `api-key`）只留**最后一条**，**静默丢事实**；且额度被重复占用（`plan` 计 2、实落 1） |
| **D2** | **解析失败静默** | `extract.py:152` `parse_key_facts` 在 `_json_array`（`extract.py:138`）返回 `None` 时**返回 `[]`**，与「模型确实抽了 0 条」不可区分；store 侧仅在**抽取器抛错**时 warn（`store.py:508-515`） | 模型反复回不可解析文本（如 0166/0170 那类「解释文字 + 围栏」形态）⇒ **静默零抽取**，与正常空结果无从分辨 |
| **D3** | **`value` 硬截断有损** | `extract.py:115` `value[:_MAX_FACT_CHARS]` 只留**头部 200** | 长取值**尾部信息全丢**；实体/取值语义常「头定名、尾定值」 |

> **不成立的项**（原稿第 2、4、5、6 条按原措辞）：见上表与 §4 逐条对照。

## 2. What Changes

1. **同批同 slug 归并（D1）** —— `_plan_key_facts` 落库前按 `slug_entity(entity)` 归并；同批内同 slug
   **只留一条**，额度语义变为「**归并后**条数」。归并**不改**跨批量覆盖语义（那是规格已裁的正确行为，
   `spec.md:362` **逐字不改**）。
   *归并保留哪一条*是本 change 的**唯一待裁项**（见 §3）。
2. **解析失败可观测（D2 —— 兑现既有规格）** —— `spec.md:379-381` **早已**规定「抽取器抛错**或返回
   不可解析的结果** ⇒ SHALL 降级为不抽取（`warnings.warn` 留痕）」，而实现只对**抛错**告警、
   「返回不可解析」一路**静默** ⇒ 本项是**补上既有规格未兑现的一半**，非新增行为。
   在 `extract_with`（`extract.py:173`）闭包内判别「**有输出但无 JSON 数组**」⇒ warn
   （**含文本长度、不含模型输出正文** —— 正文可能含明文密钥，承 0155 红线）。
   **`parse_key_facts` 契约逐字不变**（仍返回 `list[KeyFact]`、不可解析仍 `[]`）⇒ `MemoryStore` 侧
   **零改动**；合法但 0 条**不**告警（那是正常结果，避免刷屏）。
3. **`value` 截断改首尾保留（D3）** —— `value` 超长时改 `head + "…" + tail`（head/tail 平分
   `_MAX_FACT_CHARS`）。**总额度 `_MAX_FACT_CHARS` 不变** ⇒ 规格「长度有界」的既有 Scenario 仍为真，
   仅**追加**一句截断形态说明（`entity` / `ref` 保持头部截断 —— 二者恒短，尾部无信息）。

## 3. 待裁（已定 —— 用户 2026-10-08 采纳推荐）

- **待裁 1 —— 同批同 slug 归并保留哪条？** ⇒ **保留首条**，其余**独立 warn 留痕**。
  *不*复用 `dropped` 通道：后者文案是「secret-shaped value without a usable reference」，复用即**谎报**；
  故 `_plan_key_facts` 返回值由二元组扩为三元组（**私有函数**，非契约面）。
  「先到先得」与 `_plan_key_facts` 固有的顺序语义一致；无证据支持「后者更优」。
- **待裁 2 —— 是否顺带放宽 `MAX_KEY_FACTS_PER_COMPACT`？** ⇒ **不放宽**（8 保持），本 change 剔除该项。
  该上界在 `memory-interface.md:230`、`doc/02-modules/memory.md:122`、规格 `spec.md:385` **三处文档化**，
  抬升属独立取舍（记忆体积 vs 抽取覆盖）。归并使之不再被同一实体重复占用 ⇒ 覆盖实质改善而额度不变。

## 4. 与原稿逐条对照

| 原稿 | 核实结论 | 处置 |
|---|---|---|
| ① 主题聚类层（复用 notes `slug_topic`） | 依赖方向为 `notes → core.memory`（`notes/backend.py:23`、`notes/store.py:19`、`notes/promote.py:14`）；`extract.py:77` 因此**刻意**独立实现 `slug_entity` 并注明「**不得**跨层 import notes」⇒ 在抽取链里 import notes **成环**。且「归并到**主题笔记**下」落 memory 还是落 canonical notes 未定（写路径/source 守护/pinned 预算三者不同） | **切出** ⇒ `0174`，落 **L5 组合根** |
| ② 同实体/同 slug 去重合并 | 跨批覆盖**已由规格保证**（`spec.md:362`）；真缺陷是**同批内**不归并（D1） | **收窄**为 `_plan_key_facts` 同批归并 |
| ③ `_SECRET_PATTERNS` 长随机串加白名单（URL / commit hash 放行） | **松密钥红线**。规格 + `extract.py:8-10` 明写「方向恒为 over-redact（拿不准即多脱敏）」；且 `_looks_secret` 同时守 `value` 与 `ref`（`extract.py:107-109`）。**URL 形态不能放行**——`?token=`/`?sig=`/路径内嵌 base64 正是「长随机串」的常见来源 | **切出** ⇒ `0173`，建议**不做** |
| ④ `content[:400]` 改首尾保留 | 旋钮认错（400 是 prompt 入参节选；事实截断是 200）且对 `content` 做首尾保留近乎空操作 | **改述**为对 `value` 做首尾保留、**总额度不变** |
| ⑤ 「抽取条数为 0 但输入非空」记 warn | 判据会误报（多数正常轮就是 0 条），且与既有脱敏丢弃 warn 重复；「（observability）」伸过头（`core.memory` 不在事件链上） | **改述**为「**模型有输出但无 JSON 数组** ⇒ warn」，走既有 `warnings.warn` 口径 |
| ⑥ `MAX_KEY_FACTS_PER_COMPACT` 8 → 适当放宽 | 无依据 + 三处文档联动 | **剔除**（见 §3 待裁 2） |
| — 风险：低 | 原稿含 ①③ 时不成立 | 本范围下**成立**（见 §6） |

## 5. 切分（另立，本文不做）

- **`0173` 密钥脱敏白名单** —— 触碰红线，需独立 ADR + 对抗性测试（红态须证明「放行后密钥仍不落库」）
  + fail-closed 论证。**建议不做**；若做，白名单须极窄（仅 `[0-9a-f]{7,40}` commit-hash 形态、
  且未被 `token|key|secret|sig` 前缀修饰），URL 形态**永不**放行。
- **`0174` 主题归并** —— 落点先定（memory L2 `keyfact.<slug>` vs canonical `notes/*.md`）、
  「聚类」先定（LLM 一步 ⇒ 改 prompt/解析契约 + 成本；或纯 slug 分组 ⇒ 其实不叫聚类）。落 **L5 组合根**。

## 6. Impact

- **Spec delta**：`doc/openspec/specs/memory/spec.md` —— MODIFIED「结构化实体抽取（关键事实）」。
  该 Requirement 含 **8 条既有 Scenario**，delta **须逐字复现**整条 Requirement 与全部既有 Scenario，
  仅追加：① 归并（新增 Scenario「同批同 slug 归并」）② 解析失败可观测（新增 Scenario）
  ③ 截断形态（在既有「条数与长度有界（先脱敏后截断）」Scenario **上追加**形态说明，
  **不**改其「长度不超过 `_MAX_FACT_CHARS`」断言）。**红线段落逐字不动**。
- **代码**：`src/core/memory/store.py`（`_plan_key_facts`）、`src/core/memory/extract.py`
  （`extract_with`、`value` 截断助手）。**接口零变更**：`KeyFactExtractor` / `parse_key_facts` /
  `scrub_key_fact` / `MemoryStore` 构造形参与 `_extract_key_facts` 签名**皆不动**。
- **测试**：扩 `tests/test_memory_key_facts.py`（既有 **24** 例须**全绿不改**，尤其
  `test_same_entity_is_idempotent_overwrite:137`、`test_parse_returns_empty_on_unparseable:312`）。
- **文档**：`doc/01-architecture/adr.md` **ADR-0163** + 追踪行；`doc/03-interfaces/memory-interface.md`
  §3（归并 + 截断形态 + 解析失败留痕）；`doc/02-modules/memory.md`（同上）；
  `doc/04-testing/test-cases.md` 新节；`coding-plan/known-risk.md` §1 **E109** + §3 ADR-0163 局限行。
- **风险：低** —— 不触碰密钥红线（**脱敏顺序与方向逐字不变**，仍 over-redact）；
  无跨层 import；`MemoryStore` 公有面零变更；缺省路径（未注入抽取器）**逐字不变**。
- **门禁**：`.venv/bin/ruff check src tests` / `ruff format --check src tests` /
  `/home/harry/.praisonai/venv/bin/pyright`（**0/0/0**）/ `.venv/bin/pytest -q`（基线 **1973**，记增量）/
  `openspec validate --all`（预期 **31/0** —— MODIFIED ⇒ capability 数不变）。

## 7. 已知局限（写进 ADR §局限）

① **首尾保留扩大截断后可见面** ⇒ 对**脱敏完备性**的要求**更高**（若密钥在 200 字符之后且形态未命中，
  首尾保留会把尾部也带出）。本 change **不改**脱敏启发式，故该风险与现状同阶但**暴露面略增** ——
  这是选择保真度的显式代价（跨出该边界需 0173）。
② 归并**只消同批重复**；跨批同 slug 仍为覆盖式（规格已裁，非缺陷）。
③ 归并丢弃的取值**不进**任何记忆面（仅留痕），是**有损**归并。
④ 解析失败留痕**不含模型输出正文** ⇒ 事后无法直接复盘模型到底回了什么（红线所迫，取舍记录在案）。
