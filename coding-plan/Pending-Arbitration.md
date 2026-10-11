# Pending-Arbitration.md · 待裁决登记簿

> **定位**：登记**需要人裁决才能推进**的开放项。与 `known-risk.md`（已知风险 / 有意取舍 / 已修项）
> **互补**：本簿只收「**裁决动作本身就是下一步**」的项 —— 未裁决之前既不该动代码，也不该当缺陷去修；
> `known-risk.md` 收「已定性的长期未闭项」。每条**必须**带 `file:line` 证据、**可选项与代价**、
> **裁决后的落地面**。本簿**只登记与转引**，不改各源文档。
>
> **来源**：2026-10-11 内置提词收紧一轮（10 条提词 + 2 处配套代码）。
> 该轮四门禁在冻结树上全绿：`ruff check` ✓ ／ `ruff format --check` ✓（402 文件）／
> `pyright` 0-0-0 ／ `pytest -q` **2487 passed**。本簿收**该轮明确未动**的部分。
> **该轮已提交**：`1f93b88`（15 文件，+213/−76；`src` 11 处 + `doc` 5 处 + `tests` 2 处）——
> 故下文「未提交 / 可 checkout 撤销」的表述**已作废**，改动回收一律走新 commit。
>
> **编号约定**：本簿取 `PA-<n>`（Pending Arbitration），与 `known-risk.md` 的 `E<n>` **不共用**序列。
> 裁决后：① 转实现 ⇒ 按既有纪律走 change/ADR ＋ 四门禁，本行标「已闭（change `0xxx`）」；
> ② 判不做 ⇒ 转 `known-risk.md` §2「有意取舍」（带裁决日期与理由，避免二次翻案）。

---

## §0 本轮边界（已改 / 未改）

| 项 | 状态 |
|---|---|
| 10 条提词（①规划 / ②拆解 / ③验收 / ④压实 / ⑤事实 / ⑥关系 / ⑨SOP / ⑩迭代 / ⑪修补 / ⑫审查） | **已改**（模块常量 + pin 副本 + `prompts.md` 三处同步） |
| `evolution.validator.parse_review`：`startswith` → **等值** | **已改**（P0 fail-open 的解药） |
| `skills.sop.build_sop_prompt(task, trajectories)`：**按轨迹分组** | **已改**（签名变更；`skills-interface.md` 已同步） |
| loop 解析 / 流式的**代码侧**加固 | **未改** ⇒ **PA-01** |
| ⑩ 迭代器的**失败材料**注入 | **未改** ⇒ **PA-02**（改提示做不到的那半） |
| ⑭ 文档摘要路径的**脱敏面** | **未改** ⇒ **PA-03** |
| `evolution.author.strip_fence` 的兜底边界 | **未改** ⇒ **PA-04** |
| `prompts.md` 镜像一致性**未入门禁** | **未改** ⇒ **PA-05** |
| ⑦ 重要度 / ⑧ 情景归纳（未点名，仅评审提及） | **未改** ⇒ **PA-06** |
| change / ADR / 台账**登记** | **未登记** ⇒ **PA-07** |

---

## §1 裁决清单

| 编号 | 主题 | 一句话 | 不做的最坏后果 | 建议 |
|---|---|---|---|---|
| **PA-01** | loop 输出协议的第二道防线 | 提示已收紧「JSON 必须首字符」，但**代码侧仍允许两种失守**：闭合 JSON + 尾随正文 ⇒ **静默零执行**；正文 + JSON ⇒ 流式把 JSON **漏给用户** | 模型偶发违反提示时，动作被当答复（记成功、进转录与记忆） | 先做 **B**（把静默变可见）；**C** 单独立项 ✔ **B 已闭 `0222`** |
| **PA-02** | 技能迭代器的失败材料 | 提示要求「针对失败改进」，但 `build_iterate_prompt` 拿到的只有失败**计数** | 迭代闭环只产出空泛重写，A/B 灰度拿不到收益 | 先做 **B**；**C** 单独立项 ✔ **B 已闭 `0223`** |
| **PA-03** | 文档摘要路径的脱敏面 | 文档**全文**进 prompt，产物落 canonical 笔记，而 `notes` 侧**无** `redact_secrets` | 文档含密钥 ⇒ 明文进结论笔记（长期可检索） | **B + C**（与 memory 同构的两道防线） |
| **PA-04** | `strip_fence` 的兜底边界 | 正则只匹配「**整体**被围栏包裹」；「说明 + 围栏」不匹配 ⇒ 说明文字被写进 `.py` | 候选补丁语法错误，白耗一轮进化 | **B**（低风险兜底） ✔ **已闭 `0220`** |
| **PA-05** | 镜像一致性是否入门禁 | `prompts.md` 靠人肉同步，pin 测试**不校验镜像** | 改提词忘改镜像 ⇒ 镜像失真，评审依据错误 | **B**（落成测试） ✔ **已闭 `0220`** |
| **PA-06** | 提词可选微调（⑦ / ⑧） | 两条旁及提词的措辞可再收紧（低优先） | 影响有限 | **B**（只改 ⑧） ✔ **已闭 `0220`** |
| **PA-07** | 本轮改动的 change / ADR / 台账登记 | 10 条提词 + 2 处代码已落地，**无 change 号** | 与 `0215` / `0219` 的登记惯例不一致，追溯断点 | **A**（补登记） ✔ **已闭 `0221`** |

---

## §2 逐条

### PA-01 loop 输出协议的第二道防线

> **已闭（change `0222` / ADR-0212 / 台账 E159）**：采 **B**（现象①）—— `_parse` 增**形态 5**「已闭合 + 非空 `tool_id` + 其后仍有正文 ⇒ 可见失败」，**取代** ADR-0156「正文中间夹带一律按回复」（旧测试 `test_action_json_mid_text_stays_reply` 语义由新 ADR 承接、已改写为失败断言）。**C（流式泄漏，现象②）单独立项**（须放弃边出边流的全缓冲，属产品级取舍）。

**现象（两条独立故障，同一根因：形态判定依赖模型守规矩）**

1. **静默零执行**：模型输出「闭合的动作 JSON ＋ 尾随正文」（如 JSON 后紧跟一句「我读一下这个文件」）。
   `_parse` 不以 `{` 开头 ⇒ 走 `_trailing_json_object` ⇒ 该对象**不收在文末**（尾部还有正文）⇒ 返回 `None`
   ⇒ `_unclosed_action_payload` 判「已闭合」⇒ 落到 `planner.py:461` `return Action(args={"reply": text})`。
   **整段 JSON 被当成最终答复，记为成功，且进转录与记忆** —— 这正是 change `0166` 要消灭的形态，
   当年只堵住了「正文 + 尾部 JSON」，未堵反向。
2. **流式泄漏**：`planner.py:248` 用**首个非空 chunk 的首字符**判定形态
   （`reply_stream = not chunk.content.lstrip().startswith("{")`）；一旦判为回复，其后**所有** chunk
   原样外发（`planner.py:250`）⇒ 尾随的 JSON 出现在用户屏幕上（动作其实执行成功）。

本轮已改：`loop/planner.py` `_SYSTEM_PROMPT` 收紧为「JSON 必须是整条回复的**第一个字符**，
其后**不得**再有任何字符」——覆盖了模型守规矩的情形，但**不构成防线**（模型可违反）。

**为什么本轮没动**

- 收紧 `_parse` 与**既有有意语义**冲突：`tests/test_loop_output_protocol.py:93`
  `test_action_json_mid_text_stays_reply` 明确要求「正文中间夹带的 JSON 当答复」（change `0166`／ADR-0156
  的「只认尾部、**宁漏勿误**」——避免把「解释协议时引用的 JSON 示例」误当执行）。
- 流式泄漏要根治得**放弃边出边流**，属产品取舍，不是 bug 修复。

**可选项与代价**

| 选项 | 做法 | 代价 |
|---|---|---|
| **A** | 只保留提示收紧（本轮现状） | 模型违规时静默零执行 / 泄漏仍在 |
| **B** | `_parse` 增判据：尾部存在**闭合**对象且含非空 `tool_id`、但**不在文末** ⇒ `LLM_PLAN_PARSE_FAILED`（与 `_unclosed_action_payload` 同型的**可见失败**） | 与 `test_action_json_mid_text_stays_reply` 的既有语义冲突 ⇒ 须同步该测试 + 由**新 ADR** 承接（ADR-0156 是历史记录，不得改写）；须确认不误伤「合法回复里引用 JSON 示例」 |
| **C** | 本轮**有可用工具**时改全缓冲（形态判定在完整文本上做，不边流边出） | 牺牲首字延迟与流式体验；须裁决「有工具时是否放弃流式」 |
| **D** | B + C | 两者代价叠加 |

**建议**：先做 **B**（把静默失败变**可见**失败，不动流式体验，改动局限在 `_parse` 与一条测试）；
**C** 作为产品级取舍单独立项（它改变的是交互体感，不是正确性）。

**裁决后落地面**：`src/core/loop/planner.py::_parse` ＋ `tests/test_loop_output_protocol.py`
（改 1 条 + 补 1 条反证）＋ 接口文档 `doc/03-interfaces/loop-interface.md` ＋ 新 ADR。

---

### PA-02 技能迭代器的失败材料

> **已闭（change `0223` / ADR-0213 / 台账 E160）**：采 **B** —— `consider` / `build_iterate_prompt`
> 各增**可选** `failure_steps`，非空 ⇒ 插一节「最近一次失败的实际执行步骤：」；组合根 `on_turn`
> 失败轮把本轮 `steps` 一并传入（同 `sop_extractor.observe` 先例）。注入前在**迭代器内**做
> **有界 + 行内脱敏**（`redact_secrets` 先行 → 再截断：末尾至多 5 步 × 单步 200 字）。**不改**
> `_PROMPT_HEAD` 一字（pin/镜像逐字锚）。**规格中性**（`skip_specs: true`；spec 未约束 prompt
> 输入材料）。测试 +6（2507 → 2513）；反证 2 组（摘组合根透传 ⇒ `test_phase13` `1 failed`；摘
> prompt 块 ⇒ `test_skills` `4 failed, 1 passed`；复原 `md5sum` 逐字节相同）。
> **C（错误原因面）单独立项**：扩 `on_turn` 带 `trace_id` ⇒ 组合根经 `runtime.py:384` 同型接缝取
> `loop.failure.<trace>` 有界正文（材料比 `steps` 更贴近「为什么失败」，但触及 `loop` 钩子协议，
> 须与 `skills`→`memory` 材料桥接方向一并裁决）。**另**：SOP 路径（`sop.py::observe`）把同一批
> **未脱敏** `steps` 喂给 `build_sop_prompt`，系既有行为，统一脱敏**亦登记为遗留**（非本次范围）。

**现象**

提示（`src/core/skills/iteration.py:40` `_PROMPT_HEAD`）要求「请**针对失败**给出更稳健的改进版步骤」，
但 `build_iterate_prompt`（`iteration.py:48`）给模型的全部输入是：

```
技能：<id>（<描述>）／适用任务：<task_types>／执行情况：<N> 次，失败 <M> 次（失败率 X%）／现行步骤：…
```

**没有任何一次失败的具体信息** —— 哪一步失败、什么错误、在什么输入下失败，全都没有。
模型只能凭一个百分比空泛重写。本轮改提示只能做到「最小必要修改 / 不缩窄适用面」，
**做到「针对失败」必须补材料**。

**为什么本轮没动**：属实现改动，且材料口径（取哪条、留多久、怎么脱敏）需要裁决，非纯文字。

**可行性线索（已核实，非推测）**

- 失败轮的**步序已在手**：组合根钩子 `runtime.py:741` `on_turn(task, steps, ok)` 的 `steps` 就是本轮
  行动序列（同一份材料已喂给 `sop_extractor.observe`），只是没传给 `skill_iterator.consider(skill)`
  （`runtime.py:746`）。
- **失败原因已沉淀**：轮级失败另立 `loop.failure.<trace_id>` 条目（`loop/default.py:923`），
  只读查询接缝在 `runtime.py:384-396`；`MemoryStore.failure_lessons(session_id, limit=5)`
  （`memory/store.py:536`）已服务「既往失败教训」块。
- **缺口**：`on_turn` 签名**没有** `trace_id` / `session_id`（对比 `hints(task, session_id)` 有），
  故当前拿不到「本轮那条失败摘要」。
- **脱敏**：`loop.*` 条目落库时已过 `redact_secrets`，回读相对安全；但注入前**仍须有界**
  （与「既往失败教训」块同口径）。

**可选项与代价**

| 选项 | 做法 | 代价 |
|---|---|---|
| **A** | 现状（只有计数） | 迭代收益接近零 |
| **B** | 用**已有** `steps`：失败轮的步序作为「执行情况」注入 | 零新数据源、零签名变更；但只有步骤、无错误原因 |
| **C** | 扩 `on_turn` 带 `trace_id` ⇒ 组合根经 `runtime.py:384` 同型接缝取 `loop.failure.<trace>` 有界正文注入 | 动 loop 钩子签名（跨模块面）＋ 有界/脱敏口径要定 |
| **D** | B + C | 材料最全，改动面最大 |

**建议**：**B 先落地**（`SkillFeedback` 只存计数的现状不变，改由 `consider` 接收一份有界材料），
把 C 的签名扩展单独立项 —— 它触及 `loop` 钩子协议与 `skills`→`memory` 的材料桥接方向。

**裁决后落地面**：`src/core/skills/iteration.py`（`consider` / `build_iterate_prompt` 形参）＋
`src/core/skills/feedback.py`（若选 C：记录 trace 绑定）＋ `src/core/runtime.py`（钩子接线）＋
`tests/test_skills*.py` ＋ `doc/03-interfaces/skills-interface.md` §4 ＋ pin 副本与镜像。

---

### PA-03 文档摘要路径的脱敏面（⑭）

**现象**

`src/core/entry.py:1679` `_DOC_SUMMARY_PROMPT` 把**摄取文档全文**灌进 prompt
（`entry.py:1718` `_write_doc_summary_note`），产物经 `notes` 公开面落 canonical 结论笔记
（`entry.py:1688` `_doc_summary_note` → `NoteStore.update`，`doc-<slug>`，`pinned=False`）。

**两道防线都不在**：

- **模型侧**：该提示**不含任何**脱敏要求（对比 `memory/extract.py` 的「**绝不**输出明文 ＋ `<redacted>`」）。
- **store 侧**：`src/core/notes/` 内 grep 不到 `redact` / `looks_like_secret`（无脱敏），
  而 `memory` 侧对每一条落库结果**无条件** `redact_secrets`（`core.memory.__init__:39/95` 公开导出）。

⇒ 文档含密钥时，摘要可能把明文带进**长期可检索**的结论笔记。

**为什么本轮没动**：属既有路径的暴露面，改动涉及「哪个面负责脱敏」的边界裁决
（`notes` 公开面不得承载外部语料维度，桥搭在 `entry` 侧 —— 见 `entry.py:1691-1694` 的边界说明）。

**可选项与代价**

| 选项 | 做法 | 代价 |
|---|---|---|
| **A** | 只在提示里加脱敏要求 | 只有模型侧，不可审计（与「靠 prompt 让模型别写密钥」被否的先例冲突） |
| **B** | `_doc_summary_note` 写盘前对 `summary` 无条件 `redact_secrets`（**复用** `core.memory` 的公开函数；`entry.py:67` 已 import `core.memory`） | 需裁决：`entry` 作为 rag 例外面**是否可**代 `notes` 执行脱敏（方向与 `0162`/`0173` 的桥接先例一致，但要点明） |
| **C** | 提示侧同步加脱敏措辞（两道防线，与 `memory/extract.py` 同构） | 无实质代价 |

**建议**：**B + C**。B 是唯一可审计的那道；C 降低 B 的触发频率（over-redact 方向与既有纪律一致）。

**裁决后落地面**：`src/core/entry.py`（`_doc_summary_note` / `_DOC_SUMMARY_PROMPT`）＋
`tests/test_entry.py`（rag 摘要路径脱敏反证）＋ `doc/03-interfaces/prompts.md` §3⑭ ＋
`doc/02-modules/rag.md` / `notes.md`（若裁决 B 涉及面归属）＋ change/ADR。

---

### PA-04 `strip_fence` 的兜底边界

> **已闭（change `0220` / ADR-0210 / 台账 E157）**：采 **B** —— `strip_fence` 加兜底 `_FENCE_ANY`，整体匹配失败时取**最后一个**围栏块（同 `_trailing_json_object`「只认尾部」）；C（落盘前 `ast.parse`）**未采**，属验证门职责。`tests/test_evolution_author.py` ＋4 用例（23 passed）。

**现象**

`src/core/evolution/author.py:42` `_FENCE = re.compile(r"^```[^\n]*\n(?P<body>.*?)\n?```\s*$", re.DOTALL)`
要求**行首即**围栏。模型若输出「先一句说明，再一个 ```python 块」，正则**不匹配** ⇒
`author.py:61` `strip_fence` 原样返回 ⇒ **说明文字连同代码一起被写进 `.py`** ⇒ 语法错误，
候选必然过不了门禁（白耗一轮进化）。

本轮已改：提示侧要求「回复的第一个字符就是文件内容，最后一个字符也是」——又一处「只靠模型守规矩」。

**为什么本轮没动**：属代码行为改动（解析兜底），非提词；且现有提示加固已降低触发频率。

**可选项与代价**

| 选项 | 做法 | 代价 |
|---|---|---|
| **A** | 现状（只剥「整体被包裹」） | 违规形态污染源码 |
| **B** | `strip_fence` 增兜底：无整体匹配时，取**最后一个**围栏块作为内容（与 `loop/planner.py:62` `_trailing_json_object` 的「只认尾部」同型思路） | 须裁决：若模型输出**两个**围栏块时取末块是否可能取错（倾向 false-positive 风险低） |
| **C** | B + 落盘前做一次语法自检（`ast.parse`），失败即判该候选不可用 | 增加一次解析开销；须裁决是否属 verification 门职责 |

**建议**：**B**（低风险，与既有「只认尾部」纪律一致）。C 交由验证门裁决，不在本项内。

**裁决后落地面**：`src/core/evolution/author.py::strip_fence` ＋ `tests/test_evolution_author.py`
（补「说明 + 围栏」反证）＋ `doc/03-interfaces/prompts.md` §4⑪（该注已写明当前边界）。

---

### PA-05 镜像一致性是否纳入门禁

> **已闭（change `0220` / ADR-0210 / 台账 E157）**：采 **B** —— 新 `tests/test_prompt_mirror.py`（13 常量逐行核对 ＋ ⑬⑭ 登记断言，14 用例）；C（反向生成）**未采**（镜像含解释性旁注，生成器须结构重排）。

**现象**

`doc/03-interfaces/prompts.md` 自称「全仓内置 prompt 的**现状快照（镜像）**」，其 §7 定的纪律是
**改三处**（模块常量 → `tests/test_prompt_pinning.py` 逐字副本 → 本表）。
但 `tests/test_prompt_pinning.py` **只校验源码常量之间的一致性，不读 `prompts.md`** ⇒
第三处（镜像）**无任何自动校验**，全靠人肉；一旦漏改，镜像失真、评审依据错误。

本轮以**一次性脚本**核对过：11 条提词（含新补录的 ⑭）逐行命中镜像 ⇒ 0 不一致。但脚本未入库、未入门禁。

**可选项与代价**

| 选项 | 做法 | 代价 |
|---|---|---|
| **A** | 现状（人肉同步） | 漂移无声累积 |
| **B** | 把核对落成 `tests/test_prompt_mirror.py`：逐条取模块常量（⑤⑥ 用 `{max}`/`{predicates}` 模板形态），断言其**每一非空行**都出现在 `prompts.md` | 须裁决「`doc/` 是否参与门禁」的边界（`coding-plan/debug-gaps.md:3` 曾声明该文件不参与门禁，那是**针对自身**，不等于 doc 一律不入门禁） |
| **C** | 反向生成：`prompts.md` 由脚本从常量生成，人不再手改 | 最强的单一真源；但镜像里的**解释性旁注**（现状、安全承重说明、动态内置内容）须另存，结构要重排 |

**建议**：**B**（最小代价拿到「漏改即红」）。C 作为长期方向，须先裁决 `prompts.md` 是否允许保留手写旁注。

**裁决后落地面**：新增 `tests/test_prompt_mirror.py`（或并入 `test_prompt_pinning.py`）＋
`doc/03-interfaces/prompts.md` §7 纪律条目 ＋ `coding-plan/README.md` 门禁计数。

---

### PA-06 提词可选微调（⑦ 重要度 / ⑧ 情景归纳）

> **已闭（change `0220` / ADR-0210 / 台账 E157）**：采 **B** —— 只改 ⑧ 教训段加「须写成可复用的判据」（模块常量 ＋ pin 副本 ＋ 镜像三处同改）；**⑦ 未动**（牵动 `W_IMPORTANCE` 分布，待观测，保留为遗留）。

**现象**：本轮评审顺带指出、但**未点名**故未改的两处：

- ⑦ `src/core/memory/importance.py:27`：`0`–`1` 连续值下模型倾向给 `0.5` 这类无信息中间值，
  可加「除非确实无价值，不要给 0.5 这类中间值」。**风险**：可能把分布推向两端，
  影响 `W_IMPORTANCE` 乘性权重与写入闸门 —— 应先在真实样本上看分布再动。
- ⑧ `src/core/memory/episodic.py:35`：四段结构清晰，但「教训」段易写成「下次小心」这类空话；
  该段会被 `planner.py:374-375` 的「既往失败教训」块直接注入规划器 ⇒ 可加「教训须写成可复用的判据」。

**为什么本轮没动**：非点名项；⑦ 牵动权重分布，改措辞前应先有分布观测。

**可选项**：A 不动（登记即可）；B 只改 ⑧（低风险）；C ⑦⑧ 都改，⑦ 先补分布观测。

**建议**：**B**（随手可做）；⑦ 待有分布证据再议。

**裁决后落地面**：对应模块常量 ＋ pin 副本 ＋ `prompts.md` ＋ 四门禁（同本轮流程）。

---

### PA-07 本轮改动的 change / ADR / 台账登记

> **已闭（change `0221` / ADR-0211 / 台账 E158）**：采 **A** —— 追溯挂账 `1f93b88`。**三处行为变更并为一个 change**（同一提交/动机/验证轮）；唯一改语义的 `parse_review` **不另立 change**，以 ADR-0211 **D2 独立小节**承接（取证判为**规格符合性缺陷修复**：`evolution/spec.md:144-145` 已 SHALL fail-closed ⇒ 无 spec delta）；**不改写历史**（新提交挂账，`prompts.md` 头部「待补」→ change `0221`）。

**现象**：本轮 10 条提词 + 2 处配套代码已**提交**（`1f93b88`），但**未登记 change / ADR / 台账**。
`prompts.md` §7 的改动纪律只要求「常量 → pin 副本 → 本表 → 四门禁」（已照办），
但惯例上 `0215`（立 9 条 pin）与 `0219`（补 3 条 + 建总表）都配了 change 号与 ADR。

**未决点**

- 编号：按序似为 `0220`，但**台账 / ADR 占用情况本簿无从核实**，由人定。
- 归属：本轮含**三处行为变更**（`parse_review` 等值、`build_sop_prompt` 签名、提词措辞），
  是否**并为一个 change** 还是拆开（提词措辞 / 解析收紧 / 渲染分组）需裁决。
- 规格面：`parse_review` 的等值判定**改的是 fail-closed 语义**，是否须有 spec/Scenario 承接
  （对照 `0120` 的 `build_review_prompt` / `parse_review` 条）需裁决。

**可选项**：A 补登记（推荐，并在 `prompts.md` 头部把「待补」改成 change 号）；
B 判为本轮「无规格影响的措辞收紧」不登记 —— 但 `parse_review` 的语义变更**不属于**纯措辞，此路至少须拆出它。

**建议**：**A**，且至少把「`parse_review` 等值判定」单列（它改变了门禁的判定语义）。

**裁决后落地面**：`doc/openspec/changes/<新号>-*/`（proposal / design / tasks）＋ `doc/01-architecture/adr.md`
＋ `coding-plan/README.md` / `known-risk.md` 台账行 ＋ `doc/03-interfaces/prompts.md` 头部来源行。

---

## §3 附：本轮已落地（对照，**不属**本簿）

- **10 条提词**（`src/core/loop/planner.py:50`、`src/core/orchestration/planner.py:19/29`、
  `src/core/memory/summarize.py:37`、`src/core/memory/extract.py:178/394`、
  `src/core/skills/sop.py:48`、`src/core/skills/iteration.py:40`、
  `src/core/evolution/author.py:32`、`src/core/evolution/validator.py:43`）——
  与 `tests/test_prompt_pinning.py` 副本、`doc/03-interfaces/prompts.md` **三处同步**。
- **`parse_review` 改等值**（`validator.py:71`）：消除「通过不了」「PASS 但存在问题」「PASSING」被读成通过。
- **`build_sop_prompt` 按轨迹分组**（`sop.py:57`，签名 `Sequence[Sequence[str]]`）。
- **新增反证**：`test_sop_prompt_groups_trajectories`；验收判定参数化 +3 条；
  pin **变异反证**（塞 `MUTANT` ⇒ 转红，还原 ⇒ `17 passed`，逐字一致）。
- **文档同步**：`prompts.md`（含**补录 ⑭**、落点列补 `core/` 前缀）、`evolution-interface.md`、
  `02-modules/evolution.md`、`skills-interface.md`、`test-cases.md`（8 处对齐 + 新增 TC-PROMPTPIN-13）。

> **落盘状态**：本轮已提交为 `1f93b88`（**非**未提交）—— 回退须 `git revert 1f93b88` 或走新 commit，
> 不能再 `git checkout`。
