# 设计：三面边界另一侧门禁（change 0189 / ADR-0148 附）

## D1 门禁**落点**：为什么是「公开面词汇」而非「import 图」

ADR-0148 局限② 的原始措辞是「`memory` / `notes` 是否越界『兼做知识文档检索』」。import 图这一侧
**已被覆盖**（`_REFERENCE_CHAIN` 内四个面皆不得 `import core.rag`，change `0156`）。因此「另一侧」
不可能是又一条 import 断言 —— 它必须是**能力面**断言：**知识文档检索的面（外部文档 / 分块 /
语料）落在 `rag`**（ADR-0148 决策①），故 `memory` / `notes` 的**公开 API 不得出现该维度**。

选**公开面标识符**作为断言面，理由三条：

1. **可自动判定**：若某面真要兼做知识文档检索，**第一步必然是**出现该维度的公开签名
   （`NoteStore.ingest_document(path)` / `MemoryStore.read(..., chunks=…)`）—— 公开面是必经之路。
2. **误报可控**：精确**词元**匹配（非子串），且只扫**公开**（非 `_` 前缀）名 ⇒ 不误伤
   `memory` 既有的 `_vectors`（语义嵌入缓存，见 D3）。
3. **触发即提问**：门禁变红 = 「你要动三面边界了」⇒ 指向 ADR-0148 决策③（先改 ADR、再开规格变更）。
   这正是局限③「门槛靠人守」所能获得的最小机器化。

## D2 为什么不重复既有两条守护（**诚实记录**）

| 侧 | 守护 | 状态 |
|---|---|---|
| `rag` 侧（主链路不得 import rag） | `test_rag_not_imported_by_reference_chain` | **已存在**（change `0156`）⇒ 本 change 只把 `chain` 抽为常量 `_REFERENCE_CHAIN`，断言**逐字不变** |
| 会话维度侧（`NoteStore` 公开面无 `session` 形参） | `test_session_isolation.py::test_notes_api_has_no_session_dimension` | **已存在**（change `0148` 期）⇒ **不重复**；本 change 补的是**语料维度**这一侧 |
| 语料维度侧（memory / notes 不兼做知识文档检索） | **本 change 新增** | 缺口所在（ADR-0148 局限②） |

计划初稿把②写成「断言 `NoteStore` 公开面无 session 维度参数」= **重复既有守护**；据实改为
「**同一 `inspect`/AST 参数不变量模式**，落到**语料维度**、覆盖 `memory` + `notes` **两面**」。

## D3 词表与切分（**误报边界**）

- 词表 `_CORPUS_DIMENSION_TOKENS`：`document` `documents` `doc` `docs` `chunk` `chunks` `corpus`
  `ingest` `pdf` `retrieve` `rag`。
- 切分：标识符按 `_` 与 `camelCase` 边界切词、小写化后**精确**比对词元 ⇒ `fragment`（→`fragment`）
  不命中 `rag`，`documentation`（→`documentation`）不命中 `document`。
- **刻意不收录 `vector` / `embed`**：`memory` 的**语义记忆**面合法使用嵌入（`_vectors` 缓存 /
  `HashEmbedder` / `LLMEmbedder`，`relevance.py`），它们**不是**「外部文档语料」维度 —— 收进去会
  把既有合法面判红（门禁自伤）。**知识文档**的嵌入归 `rag`（ADR-0097、ADR-0148 决策①）；两者
  同名不同面，本门禁**只钉文档语料词汇**，不入嵌入词汇。
- 白名单式豁免**不设**：命中的**唯一**正确出路是按 ADR-0148 决策③改 ADR / 开规格变更；若确为
  误报（词表需演进），**改词表 + 记录于此**，而不是就地豁免。

## D4 守护非空（防空过）

AST 走查型门禁的典型失效是**静默空过**（路径写错 / 包改名 ⇒ 走查零条 ⇒ 恒绿）。故守护②内断言
走查收集到的公开面条目数 `> 0`（`assert seen, …`）；`_CORPUS_FREE_FACES` 与 `_REFERENCE_CHAIN`
的**成员关系**另由守护①钉住。

## D5 红态如何确认（规格中性下的「测试先行」）

规格中性 ⇒ 现状应**绿**（沿 change `0156` tasks 2.2 先例）：**临时植入**一条违规
（在 `src/core/notes/store.py` 加一个公开方法形参 `chunks: list[str]`）⇒ 守护②**必须变红且指名
`notes/store.py:<行> chunks -> ['chunk']`**；`git checkout` 撤销后回绿。**只确认、不保留**：
`src/` 最终零改动。

## D6 边界（刻意的「不做」）

- 间接路径（共享工具转发 / 动态 `importlib`）**不察** —— 沿 ADR-0148 局限① 的既有裁决（抓最常见
  的直连退化，非形式化隔离）。
- 本门禁**不**守护「三面职责的实质正确性」（例如 `memory` 存的条目质量），只管**边界词汇**；
  实质面仍由各自规格 + 测试守护。
