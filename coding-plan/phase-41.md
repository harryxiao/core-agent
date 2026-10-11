# Phase 41：记忆注入面补全（批次 `0215`~`0218`，4 change）

> **状态**：✅ **全闭**（2026-10-11；4 条 change 逐条独立收口：各自 change 目录 / ADR / 规格 delta /
> 四门禁 / 手工归档 / 单次提交）。
> **来源**：2026-10-11 用户问「记忆层面完善了吗 / 控制面与数据面的提词是否完成」。四路代码审计 ＋
> 规格面手核结论：**四类记忆的「沉淀 → 存储 → 消费」链路基本齐**，但有**两处真缺口 ＋ 一处强度不对称
> ＋ 一条无防护面**：
> ① **失败经验无专属注入面** —— 成功经验有「可用技能」「相关笔记」专块，失败（`loop.failure.*`）只能靠
> 通用「相关事实」碰运气（`Diagnoser` 只进诊断报告、不回灌推理 prompt）；
> ② **情景类无专属沉淀 prompt** —— 程序类有 `build_sop_prompt`、语义类有 `build_extract_prompt` /
> `build_relation_prompt`，情景类复用通用会话摘要 prompt；
> ③ **关键事实抽取无门控** —— 同族的 `relation_extract` / `importance_gate` 都有键，唯它无条件常开；
> ④ **全仓无任何 prompt 文本 pin 测试** ⇒ 措辞漂移静默改模型行为。
>
> **为什么是一批而非一条**：四条缺口分属**不同 capability**（`memory`／`loop`／`configuration`／
> 测试面），且 ③ 与 ④ 是**不同性质**的收口（一个是 kill-switch、一个是回归护栏）⇒ 沿 Phase 34~40
> 先例：**一个批次、多条 change**，每条仍各自 change / ADR / delta / 四门禁 / 单提交。
> **执行顺序 = 编号顺序**（先立护栏，再动行为）。
>
> **红线（全批次）**：新行为缺省关 ⇒ 既有路径**逐字不变**（**唯一例外 `0216`** —— 该门是既在用能力的
> **kill-switch**，缺省取 `True` ⇒ 实际**零行为改变**，ADR-0206 明写理由）；主方向封存
> `exclude_source_prefixes=("beast.","pet")`（`src/core/runtime.py` **逐字不动**，phase-26）；密钥经
> `CoeffectResolver` 注入、**只引用不读取**、**绝不**进日志/记忆（留痕**只报条目 id / 会话键 / 计数**，
> **绝不回显正文或取值**）；所有写效应经 `EffectTracker` 可回滚；宠物 / 子 / 神兽 loop 不接注入面
> （沿 transcript / turn_checkpoint 隔离注记）；零三方依赖；`config*.yaml` / `.claude/settings*.json` /
> `uv.lock` **不提交**；四门禁**直连二进制**（`.venv/bin/ruff check` ／ `.venv/bin/ruff format --check` ／
> `/home/harry/.praisonai/venv/bin/pyright` **0-0-0** ／ `.venv/bin/pytest -q`）。

---

## §0 用户裁决的四个设计岔口（AskUserQuestion，2026-10-11）

| # | 岔口 | 裁决 |
|---|---|---|
| 1 | **收口范围** | **三项** —— 失败教训注入块 ＋ 提词门控 ＋ 文本 pin ＋ 情景类专属沉淀 prompt；**待办任务能力未选**（无实现、需新实体 ＋ 工具 ＋ 注入块）⇒ 登记为遗留 |
| 2 | **情景提词形态** | **新增独立「情景归纳器」**（与 SOP 提炼 / 事实抽取并列；**不**改造现有会话摘要 prompt） |
| 3 | **门控范围** | **只补关键事实抽取**（memory 摘要 / SOP / 编排 / RAG 的无门控 prompt **不动**） |
| 4 | **关键事实门控缺省** | **缺省 `True`**（保留既有行为，只加可关能力） |

---

## §1 批次总览（执行顺序 = 编号顺序）

| # | change（归档目录） | capability | 一句话 | ADR | 台账 | 测试基线 |
|---|---|---|---|---|---|---|
| 1 | `0215-prompt-text-pinning` | **（规格中性）** | 9 条核心 prompt 头逐字钉死 ＋ 结构不变量（**零 `src/` 改动**） | ADR-0205 | E152 | 2421 → 2433（+12） |
| 2 | `0216-key-fact-extract-gate` | `memory`／`configuration` | `memory.key_fact_extract` 门控（**缺省 `True` = 保留行为**，kill-switch 非 opt-in） | ADR-0206 | E153 | 2433 → 2441（+8） |
| 3 | `0217-failure-lessons-block` | `memory`＋`loop` | 「既往失败教训」专块（**零效应读面** ＋ 闭包注入，**缺省关**） | ADR-0207 | E154 | 2441 → 2460（**+19**；计划估 +16） |
| 4 | `0218-episodic-consolidator` | `memory` | 「情景归纳器」新 prompt ＋ 新 L2 `semantic` 条目（**缺省关**，`kind` 承重阻断自激环） | ADR-0208 | E155 | 2460 → 2479（**+19**；计划估 +18） |

**账目**：change `0215`~`0218` ／ ADR-0205~0208 ／ 台账 E152~E155 ／ 测试节 §128~§131 ／
测试基线 **2421 → 2479**（**+58**）。
**规格**：memory **16 → 17** req（MODIFIED×2[`0216`/`0217`] / ADDED×1[`0218`]）、scenario
**119 → 128**（+9）；loop **6 → 6** req（MODIFIED×1[`0217`]）、scenario **79 → 81**（+2）。
`openspec validate --all`：批次期 31＋1=32 passed → 归档后 **31 passed**。

---

## §2 逐 change 要点

### `0215` 提示词文本 pin（**规格中性** / ADR-0205 / 台账 E152）
- **根因**：prompt 头是模块私有常量（实现细节），**零测试 pin** ⇒ 措辞一改模型行为静默变、无测试拦截。
- **实现**：新 `tests/test_prompt_pinning.py`，**零 `src/` 改动**。9 条：`extract._PROMPT_HEAD` /
  `_RELATION_PROMPT_HEAD` / `summarize._PROMPT_HEAD` / `importance._PROMPT_HEAD` / `sop._PROMPT_HEAD` /
  `iteration._PROMPT_HEAD` / `planner._SYSTEM_PROMPT` / `_DECOMPOSE_SYSTEM` / `_VERIFY_SYSTEM`。
  **逐字头 ＋ 结构不变量**（段槽、`- ` 前缀、节选上界、`.format()` 占位符、谓词白名单）。
- **规格中性判据**：钉的是**实现细节**、是既有行为的回归护栏（非新行为）；升进规格即**过约束**
  （先例 `0195` / `0199` 同为 test-only 零 `src/`、标「规格中性」）。
- **反证**：任改一字符 ⇒ 对应 test 红；复原 ⇒ `diff -q` 逐字节同。

### `0216` 关键事实抽取门控（`memory`／`configuration` / ADR-0206 / 台账 E153）
- **根因**：`runtime.py` 的 `key_fact_extractor=extract_with(_llm_text)` **无条件**；同族
  `relation_extract` / `importance_gate` 皆门控 ⇒ 关键事实抽取**每次压实跑一次模型**却无法关闭。
- **实现**：`manager.py` memory 块加 `memory.key_fact_extract`（`default=True` / `ADVANCED`）＋ 访问器
  `key_fact_extract()`（**唯一差异 = 缺省 True ＋ 未知取值回落 True**）；`runtime.py` 改条件接线。
- **缺省 `True` 论证**：门是 **kill-switch** 非 opt-in 新能力 —— 翻缺省 `False` = **静默删除在用能力**
  （非缺陷修复），方向与全批「缺省关 ⇒ 逐字不变」纪律**初衷相反**；缺省 `True` ⇒ 恒走原分支 ⇒ 与引入
  本键前**逐字等价**。**非法取值回落 `True`**（与同段其余键**相反**）⇒ 拼写错误不得静默停用能力。
- **规格**：memory **MODIFIED**「结构化实体抽取（关键事实）」末句扩写「未注入抽取器**或配置关闭**」＋
  **ADD Scenario ×2**（既有 15 Scenario 逐字保留）。
- **反证（两组）**：摘组合根门 ⇒ `1 failed, 7 passed`；缺省翻 `False` ⇒ `3 failed, 5 passed`。

### `0217` 「既往失败教训」注入块（`memory`＋`loop` / ADR-0207 / 台账 E154）
- **根因**：失败条目（`loop.failure.<trace_id>`，`0179`/ADR-0170 起已沉淀）**已有沉淀无专块**；只靠通用
  「相关事实」碰运气（且 `_PRESERVE_TAGS` 只豁免压实、不建注入面）。
- **实现**：① `store.py` **零效应只读** `failure_lessons(session_id, *, limit=5)`（走 `_all_entries()`，
  **层无关**，`ts` 降序有界）—— **绝不**走 `read()`（`_reinforce` 会 +1 `reuse_count` 并落盘效应）；
  ② `protocol.py` `LoopContext.failure_lessons` 独立字段；`planner.py` 插独立块「既往失败教训：」；
  ③ `default.py` 新钩子 `failure_lessons_consult: (会话标识) → str` ＋ `_load_failure_lessons`（异常降级
  留痕），**只注主 loop**；④ `runtime.py` `exclude_fact_tags` **条件化**（启用 ⇒ 追加 `failure`；
  关 ⇒ **逐字**为既有 `frozenset({"steps"})` —— **本 change 最高风险点**，有专门逐字锚测试）；
  键 `loop.failure_lessons`（结构化段 ⇒ `_loop_errors` 加校验）。
- **规格**：memory **MODIFIED**「情景链」（首段「两件事」→「三件事」、(e) 条件化、新 **(h)** 只读读面；
  既有 7 Scenario 逐字保留 ＋ **ADD ×3**）；loop **MODIFIED**「执行循环」（块句，既有 41 Scenario
  逐字保留 ＋ **ADD ×2**）。
- **反证（三组）**：摘 planner 块 ⇒ `2 failed, 17 passed`；读面改回 `read()` ⇒ `1 failed, 18 passed`；
  摘 `"failure"` 条件项 ⇒ `1 failed, 18 passed`。

### `0218` 「情景归纳器」（`memory` / ADR-0208 / 台账 E155）
- **根因**：情景类复用通用摘要 prompt ⇒ **两路语义被同一文本压平**（材料口径 / 副作用 / 产物去向三重
  不同），任何措辞调整同时改两路 ⇒ 无法为情景类单独演进（违 P3）。
- **实现**：① **新** `src/core/memory/episodic.py`（镜像 `extract.py` 三段式、契约返回**文本**：
  `EpisodicExtractor` / `_PROMPT_HEAD`（四段：目标 / 经过 / 结果 / 教训）/ `build_episodic_prompt` /
  `consolidate_with`）；② `store.py` 新接缝 `episodic_extractor` ＋ `_consolidate_episodic` 挂进
  `_summarize_sessions`；`compact()` 守卫加一项；③ **条目形状**：`id=episodic.<key>`（每会话至多一条、
  覆盖式）、`source="episodic"`、`tags=["episodic","session:<key>"]`、`session_id=""`（全局层）、
  `trace_id=compaction.<key>`、**`kind="semantic"`**（★ **承重**：`_episodic_groups` 只收
  `kind=="episodic"` ⇒ 归纳产物**结构性**地不回喂摘要器，避免自激环）；④ store 侧**无条件**
  `redact_secrets` ＋ 截断 `MAX_EPISODIC_CHARS`；⑤ `runtime.py` 接线，键 `memory.episodic_extract`
  （bool 缺省 `False`）。
- **规格**：memory **ADDED**「情景归纳（episodic consolidation）」＋ **Scenario ×6**（既有 16
  Requirement 逐字保留）。
- **反证（三组）**：摘归纳调用 ⇒ `6 failed, 13 passed`；`kind` 改 `"episodic"` ⇒ `2 failed, 17 passed`
  （承重锚 ＋ 形状锚）；摘 `redact_secrets` ⇒ `1 failed, 18 passed`。
- **两条反证教训**（ADR-0208 已记）：① 承重锚**必须走全量压实**且**逐组全查** —— 归纳条目
  `session_id=""`，会话收窄路径本就按 `session_id` 过滤 ⇒ 用 `compact(session_id="s1")` 测「不回喂」
  **恒绿**；`seen[-1]` 只覆盖最后一组、归纳产物若入选自成 `""` 组而漏检。② **批量替换须锚定唯一子串**
  —— `kind="semantic",` 在 `store.py` 出现 **3 次**，按「首次出现」替换会**静默改错对象**（反证 B
  首跑 19 绿即此故）。

---

## §3 红线与不变量的逐条兑现

- **「缺省关 ⇒ 逐字不变」**：`0217`（`loop.failure_lessons` 缺省 `False`：`exclude_fact_tags` 缺省逐字为
  `{"steps"}`、钩子 `None`、`failure_lessons` 字段恒空 ⇒ 提示词不变）／`0218`（`memory.episodic_extract`
  缺省 `False` ⇒ `episodic_extractor=None`、`compact()` 守卫不变路径）。**唯一例外 `0216`** 反向取值
  （缺省 `True`）但**实际零行为改变**（恒走原分支）。
- **`exclude_source_prefixes=("beast.","pet")` 逐字不动**（phase-26）：本批四条均未触碰。
- **密钥红线**：`0217` 读面**不引入**新脱敏判据（教训正文写入时已脱敏）；`0218` 归纳产物落库前
  store 侧**无条件** `redact_secrets`（注入的归纳器**不构成信任边界**）。两处留痕**均只报会话键**。
- **注入面隔离**：`failure_lessons_consult` **只接主 loop**（宠物 / 子 / 神兽不接，沿 transcript /
  turn_checkpoint 注记）；`0218` 是 memory 侧沉淀、不经 loop 注入面。
- **零三方依赖**：新增仅 stdlib。
- **四门禁直连二进制**：四条 change 各自全绿（`ruff check` ／ `ruff format --check` ／ `pyright` **0-0-0**
  ／ `pytest -q`）；批次末全量 **2479 passed**。

---

## §4 显式不做（登记为遗留 / 后续候选）

- **不做待办任务能力**（用户未选）—— 需新实体 ＋ 工具 ＋ 注入块，已登记为遗留。
- 不补会话摘要 / SOP 提炼 / 编排 / RAG 的**门控键**（用户裁决「只补关键事实抽取」）。
- **不**改造现有会话摘要 prompt（用户裁决「新增独立情景归纳器」）。
- 不做输入 → 规划路由提词、不做运行期 ReAct vs Plan&Execute 模式决策（架构裁决级）。
- **不**把新 `source="episodic"` 登记进 `_GATE_EXEMPT_SOURCES` / `_FORGETTABLE_SEMANTIC_SOURCES`
  —— 与 `importance_gate` 同开时该条目会**过闸**、且**恒豁免遗忘**（ADR-0208 局限 ①，登记为后续候选，
  本轮保最小爆炸半径）。
- `0217` 读面无单独条数上限**配置键**（`limit` 缺省 5 为 `_FAILURE_LESSON_LIMIT` 实现常量）。

---

## §5 收口清单

- [x] 四条 change 各自：spec delta → ADR → test-first（红 → 绿）→ 四门禁 → `openspec validate --all`
      → 手工归档（`python3 /tmp/openspec_archive.py <change-NAME>`，断言 0 Requirement-header /
      0 Scenario-title 丢失）→ 台账回填 → **单次提交**。
- [x] 本册 `coding-plan/phase-41.md`。
- [x] `coding-plan/known-risk.md` §1（E152~E155）／§3（ADR-0205~0208）。
- [x] `doc/04-testing/test-cases.md` §128~§131。
- [x] `doc/02-modules/memory.md`（§3.12 失败教训只读读面 / §3.13 情景归纳）、`doc/02-modules/loop.md`
      （§3.6.1 既往失败教训注入块）。
- [x] `doc/01-architecture/adr.md` ADR-0205~0208 ＋ 变更追踪表。
