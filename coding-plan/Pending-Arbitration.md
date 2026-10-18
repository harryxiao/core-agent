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
> **第二轮来源**：2026-10-11 用户问「**现在的 core-agent 四层记忆光谱 ＋ 四类记忆模式，满足长任务
> 要求了吗**」。两路只读取证（要求侧规范 / 实现侧现状，含数值旋钮表与未接线清单）＋ 主代理对
> **真实运行配置与 state** 的经验核验。结论：**四类记忆的能力位已落地接线；但长任务三条硬要求里
> 两条无对应机制，四项无立项**。本簿收该轮**明确未动**的部分（PA-08~PA-12）。
> 术语先对齐：「四层记忆光谱」**不是本仓措辞** —— 正式口径是 **「记忆即光谱」＋ L0–L4 五层**
> （ADR-0004；`doc/openspec/specs/memory/spec.md:4,9`）；「四维/四类」（会话/语义/程序/情景）
> 只来自外部蓝图 `memory-4-layer-architecture.md:57-60`，**从未立为 Requirement**。
>
> **编号约定**：本簿取 `PA-<n>`（Pending Arbitration），与 `known-risk.md` 的 `E<n>` **不共用**序列。
> 裁决后：① 转实现 ⇒ 按既有纪律走 change/ADR ＋ 四门禁，本行标「已闭（change `0xxx`）」；
> ② 判不做 ⇒ 转 `known-risk.md` §2「有意取舍」（带裁决日期与理由，避免二次翻案）；
> ③ **缓议 / 单独立项** ⇒ 记入 **§4** ＋ `known-risk.md` §3（ADR 局限），**不重开**已闭项。

---

## §0.1 第一轮边界（提词收紧，已闭）

| 项 | 状态 |
|---|---|
| 10 条提词（①规划 / ②拆解 / ③验收 / ④压实 / ⑤事实 / ⑥关系 / ⑨SOP / ⑩迭代 / ⑪修补 / ⑫审查） | **已改**（模块常量 + pin 副本 + `prompts.md` 三处同步） |
| `evolution.validator.parse_review`：`startswith` → **等值** | **已改**（P0 fail-open 的解药） |
| `skills.sop.build_sop_prompt(task, trajectories)`：**按轨迹分组** | **已改**（签名变更；`skills-interface.md` 已同步） |
| loop 解析 / 流式的**代码侧**加固 | **已闭**（形态 5 入 `_parse`：change `0222`／ADR-0212）；**流式泄漏缓议**（§4） |
| ⑩ 迭代器的**失败材料**注入 | **已闭**（`failure_steps`：change `0223`／ADR-0213）；**错误原因面缓议**（§4） |
| ⑭ 文档摘要路径的**脱敏面** | **已闭**（写入侧 `redact_secrets` ＋ 提示侧纵深：change `0224`／ADR-0214） |
| `evolution.author.strip_fence` 的兜底边界 | **已闭**（`_FENCE_ANY` 取末块：change `0220`／ADR-0210）；`ast.parse` 自检缓议（§4） |
| `prompts.md` 镜像一致性**未入门禁** | **已闭**（`tests/test_prompt_mirror.py`：change `0220`）；**行号 / 旁注盲区**由 change `0225` 补 |
| ⑦ 重要度 / ⑧ 情景归纳（未点名，仅评审提及） | **⑧ 已闭**（change `0220`）；**⑦ 缓议**（§4） |
| change / ADR / 台账**登记** | **已闭**（追溯挂账 `1f93b88`：change `0221`／ADR-0211） |

---

## §0.2 第二轮范围（长任务 × 记忆，**开放**）

| 项 | 核验结论 |
|---|---|
| 四类记忆的**能力位**（会话/语义/程序/情景） | **已落地接线**（成文映射见 `coding-plan/phase-38.md:7-8`）——这是「四维是否落地」的官方口径 |
| 「记忆即光谱」**五层**（L0–L4） | 实现层**只有 L2 ＋ L4 是活的**：全仓无一处写 `L1`（`grep '"L1"' src/` 零命中、`MemoryStore.index()` 无消费者）；技能落 `skills.json`，**无一处写 `L3`** ⇒ **PA-09** |
| 会话：三层滑窗 ＋ 长/中摘要 | 主 loop **已接**；**子/神兽/宠物 loop 不注入 transcript** ⇒ 无长期摘要 |
| 语义：`keyfact.` 点 ＋ `relation.` 边 | 点已接（缺省 **True**）；边**缺省关**（`memory.relation_extract` 缺省 `False`）⇒ **PA-09** |
| 程序：SOP 提炼 / 路由 / 灰度 A-B / 退役 | 前三条【产】；**退役缺省关**（`skills.retirement` 缺省 `False`） |
| 情景：轨迹 / 步序 【产】；归纳 / 教训块 | 归纳（`memory.episodic_extract`）与教训块（`loop.failure_lessons`）**均缺省关** |
| 上下文区块配比 20/15/30/15 ＋ 缓冲 20% | 纯函数已落地（change `0201`/ADR-0191），**缺省关**，且**唯一消费者是事实面预算**（其余四块无消费者）⇒ **PA-09** |
| **早期硬约束的自动锚定** | **不存在**：半自动提升产物 `pin=False`（`src/core/runtime.py:570-572` ＋ `src/core/notes/promote.py:30`），只有**显式** `notes promote` 才 `pin=True` ⇒ **PA-08** |
| **循环内检索面** | 只有 `MemoryStore.read()` 的**全库扫描 ＋ 热度加权**（L1 一阶路由未落）；**RAG 对循环不可达**（`grep rag src/core/tools src/core/loop` 零命中）；缺省无 `llm.embedding_model` ⇒ memory 走词法、rag 走 `HashEmbedder` 降级；**无图存储/无遍历 API** ⇒ **PA-09** |
| 产品指标 **M4**「token 次线性」 | `doc/00-product/product-definition.md:83` 有目标值，**零测量面** ⇒ **PA-10** |
| `coding-plan/README.md` 阶段索引 | 只覆盖 `phase-0~34`（自述「36 份」），实测已有 `phase-41` ⇒ **PA-11** |
| `phase-38` 的 G1/G2 与「记忆三面 G1/G2/G3」 | **同名不同义**（两套编号）⇒ **PA-12** |
| **外部蓝图的数值承诺** | **已被裁决弃置**：ADR-0190「蓝图字面 tier 边界 `0-5/6-20/21+` **不采纳**…采其**结构**弃其**数值**」（`coding-plan/known-risk.md:106`）；`known-risk.md:269`「取精华弃糟粕，**不取**其里程碑永久删除／单库无隔离／三方依赖」 |

> **实测（可复现，方法见 §5）**：本机真实配置 `~/.core/config.yaml` **只配了** `llm.*` /
> `permission.mode` / `loop.max_rounds`；`~/.core/.env` 只有两个 GLM 键；**无任何 `CORE_*` 环境变量**
> ⇒ 上表所有「缺省关」项**在实际部署里确实关着**，非纸面推断。

---

## §1.1 第一轮裁决清单（PA-01~PA-07，全闭）

| 编号 | 主题 | 一句话 | 不做的最坏后果 | 建议 |
|---|---|---|---|---|
| **PA-01** | loop 输出协议的第二道防线 | 提示已收紧「JSON 必须首字符」，但**代码侧仍允许两种失守**：闭合 JSON + 尾随正文 ⇒ **静默零执行**；正文 + JSON ⇒ 流式把 JSON **漏给用户** | 模型偶发违反提示时，动作被当答复（记成功、进转录与记忆） | 先做 **B**（把静默变可见）；**C** 单独立项 ✔ **B 已闭 `0222`** |
| **PA-02** | 技能迭代器的失败材料 | 提示要求「针对失败改进」，但 `build_iterate_prompt` 拿到的只有失败**计数** | 迭代闭环只产出空泛重写，A/B 灰度拿不到收益 | 先做 **B**；**C** 单独立项 ✔ **B 已闭 `0223`** |
| **PA-03** | 文档摘要路径的脱敏面 | 文档**全文**进 prompt，产物落 canonical 笔记，而 `notes` 侧**无** `redact_secrets` | 文档含密钥 ⇒ 明文进结论笔记（长期可检索） | **B + C**（与 memory 同构的两道防线） ✔ **已闭 `0224`** |
| **PA-04** | `strip_fence` 的兜底边界 | 正则只匹配「**整体**被围栏包裹」；「说明 + 围栏」不匹配 ⇒ 说明文字被写进 `.py` | 候选补丁语法错误，白耗一轮进化 | **B**（低风险兜底） ✔ **已闭 `0220`** |
| **PA-05** | 镜像一致性是否入门禁 | `prompts.md` 靠人肉同步，pin 测试**不校验镜像** | 改提词忘改镜像 ⇒ 镜像失真，评审依据错误 | **B**（落成测试） ✔ **已闭 `0220`** |
| **PA-06** | 提词可选微调（⑦ / ⑧） | 两条旁及提词的措辞可再收紧（低优先） | 影响有限 | **B**（只改 ⑧） ✔ **已闭 `0220`** |
| **PA-07** | 本轮改动的 change / ADR / 台账登记 | 10 条提词 + 2 处代码已落地，**无 change 号** | 与 `0215` / `0219` 的登记惯例不一致，追溯断点 | **A**（补登记） ✔ **已闭 `0221`** |

---

## §1.2 第二轮裁决清单（PA-08 / PA-09 方案 B、C / PA-10 / PA-11 / PA-12 **已闭**；PA-09 D/E **开放**）

| 编号 | 主题 | 一句话 | 不做的最坏后果 | 建议 |
|---|---|---|---|---|
| **PA-08** | 阶段/里程碑**锚定** | 蓝图要「每阶段高保真报告**永久置顶**、不被压缩覆盖」；仓内对应物只有 L0 宪法 ＋ **手工**常驻笔记，且**半自动提升 `pin=False`** ⇒ **自动锚定链不存在** | 跨月长任务的早期硬约束只能靠人记得去 `notes pin`；忘了就随摘要中略区一起丢 | **B**（复用 pinned 通道做「结构化里程碑报告 ＋ 一键常驻」），**C 自动置顶**须先裁哲学冲突。**已闭**（change `0273` / ADR-0263 / 台账 E209）：方案 B 落地 `notes milestone`，C 维持否决 |
| **PA-09** | 检索质量（**分区 / 图 / 真语义 / 缺省值**） | 无分区权重、无图与遍历、缺省无 embedding（词法/`HashEmbedder` 降级）、配比只生效 1/5、L1 层为空 | 「万条后检索不漂移」无机制支撑；蓝图 ≥92% 那档无从谈起 | **B 先建可测性**（1 万条语料基准 ＋ 延迟），**C 分区加权**次之；图/真语义须独立裁决。**B 已闭**（change `0275` / ADR-0265 / 台账 E211）：10k 基准落地（recall/MRR 1.000），**实测中位 ≈657ms 未达 100ms** ⇒ **检索延迟已修（change `0276` / ADR-0266 / 台账 E212：中位 85.8ms）**；**C 已闭**（change `0277` / ADR-0267 / 台账 E213）：tags 三档加性居零，两基准逐项不变。D/E 仍开放 |
| **PA-10** | **M4 基准 harness** | `product-definition.md:83` 写明「基准任务序列测量」，**该 harness 不存在** | 「token 次线性」既不可证伪也不可证实；长任务成本无法回归 | **B**（最小 harness，离线桩 provider，复用 `last_prompt_tokens()` 探针）。**已闭**（change `0274` / ADR-0264 / 台账 E210）：方案 B 落地，C 阈值门禁未采纳 |
| **PA-11** | `README.md` 阶段索引**漂移** | 自述「36 份（phase-0~34）」，实际已有 `phase-35~41` | **索引缺口直接导致重复劳动**：本轮差点漏掉「Phase 38 已答过同一问题」 | **C**（补 README ＋ 加计数守卫测试）。**已闭**（change `0287` / ADR-0277 / 台账 E223）：README 计数/§1 覆盖按实际文件校正，`test_coding_plan_index.py` 守卫 |
| **PA-12** | `phase-38` 与「记忆三面」**G1/G2 同名不同义** | 两套编号共用 `G1`/`G2`（一为批内缺口、一为路线图） | 检索 `G1` 命中两义；本轮取证已踩到 | **B**（批内缺口改前缀 ＋ 加一行「非同组」注记），**不**全局重编号。**已闭**（change `0287` / ADR-0277 / 台账 E223）：§0 改 `B38-1/2/3` ＋ 注记，守卫钉住 |

---

## §2 逐条

> 各条「现象 / 证据」段引用的是**改动前**的 `file:line` 快照（历史证据，保留不改 —— 否则失去
> 「当时为什么这么判」的可追溯性）。**现状**行号以 `doc/03-interfaces/prompts.md` §1 落点列为准
> （该列现受 `test_prompt_mirror` 行号核对；见 change `0225`）。
> **第二轮（PA-08~PA-12）**的 `file:line` 是 **2026-10-11 取证时的现状**（非历史快照），引用前宜复核；
> 其经验证据的复现方法见 **§5 取证附录**。

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

> **已闭（change `0224` / ADR-0214 / 台账 E161）**：采 **B + C** —— **B（承重）**
> `entry._doc_summary_note` 落盘前**无条件** `redact_secrets(summary.strip())`（信任边界在**写入
> 侧**、不依赖提示自律；复用 `core.memory.redact_secrets` 与 `memory`/loop `failure_digest` **同
> 口径**；**只作用于正文**、不碰 `note_id`/`title` ⇒ 保幂等覆盖）；**C（纵深）**
> `_DOC_SUMMARY_PROMPT` 补「不要输出任何密钥…」，镜像 `prompts.md` ⑭ 同步（去「待裁决」）。
> 规格：`notes` **MODIFIED**「文档摘要笔记（notes.rag）」＋ ADDED 1 Scenario（既有 4 Scenario
> 逐字保留）；`rag` 规格**不动**（不改送模型的材料）。测试 +3（2513 → 2516）；反证 2 组（摘
> `redact_secrets` ⇒ `test_rag_summary -k redact` `2 failed`；改提示未同步镜像 ⇒
> `test_prompt_mirror` `1 failed`；复原 `md5sum` 逐字节相同）。

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

### PA-08 阶段 / 里程碑锚定（长任务的硬约束自动锚）

**现象**：外部蓝图要求「每个里程碑结束时**自动**生成一份高保真结构化报告，仅保留最终结论、核心
决策、不可动摇的硬约束…**永久置顶在 System Prompt 最前端，永远不会被压缩流程覆盖**」
（`Agent-Memory-LongTask.md:15`）。仓内的对应物只有三个，且**都不自动**：

- L0 宪法（`Core.md`）—— 每轮恒注入，但是**全局、非任务级**；
- **常驻（pinned）笔记** —— 具备「整篇纳入 / 逐轮无条件 / 紧随宪法块 / 超限整篇排除 ＋ 可见」
  （`doc/openspec/specs/notes/spec.md:190` 起；change `0149`/`0154`）—— 但**置位靠人**；
- `notes promote` —— **显式 CLI**；半自动路径（摘要首次越界交付一次）产的笔记
  **`pin=False`**（`src/core/runtime.py:570-572` ＋ `src/core/notes/promote.py:30`）。

**证据**：

| 事实 | 出处 |
|---|---|
| 半自动提升**不常驻**（不占 4000 预算、只经 Consult 命中面） | `runtime.py:570-572`；`promote.py:30,39-41` |
| 显式提升**才** `pin=True` | `promote.py:30`；`entry.py:1857-1863`（未传 pin ⇒ 走缺省 True） |
| ADR-0142①：「**显式触发** ⇒ **无人在场的长任务仍不自动落 canonical**」 | `known-risk.md:171` |
| ADR-0208③：情景归纳**每会话仅一条** ⇒ 超长会话早期结论被后续**覆盖稀释** | `known-risk.md:245` |
| ADR-0170③：零复用 ≈19 天仍被**遗忘归档 L4**（压实豁免 ≠ 遗忘豁免） | `known-risk.md:203` |
| `src/` 的「里程碑」只在编排进度事件与 TUI（**记忆侧无阶段维度**） | `orchestration/scheduler.py:496`；`ui/repl.py:1132` |
| 「待办任务能力」已登记为遗留（需新实体 ＋ 工具 ＋ 注入块） | `coding-plan/phase-41.md:142` |

**可选项与代价**

| 选项 | 做法 | 代价 |
|---|---|---|
| **A** | 不做（靠人 `notes pin`） | 硬约束丢失不可观测，且**遗忘路径仍会归档** |
| **B** | **复用 pinned 通道**：新增「里程碑报告」动词（如 `milestone close`）⇒ 生成结构化报告（结论/决策/硬约束）并 `pin=True` ＋ 高 `pin_priority` | 阶段结束仍靠人触发；但**零新注入块**（复用整篇纳入 ＋ 优先级语义），风险最小 |
| **C** | **自动锚定**：半自动提升改 `pin=True` ＋ 从 `loop.steps` / 待办任务推断阶段 | 与 ADR-0142①「notes 是**刻意知识**、非某一轮残留」哲学冲突；未 review 的内容每轮进上下文（ADR-0141① 的密钥红线）；自动「阶段」判定不可靠 |
| **D** | B ＋ 触发面（`phase-41.md:142` 的「待办任务」实体） | 改动面最大（新实体 ＋ 工具 ＋ 注入块） |

**建议**：**B 先行**（把「人工置常驻」升级为「结构化里程碑报告 ＋ 一键常驻」，立刻消除「忘了 pin」）；
**C 的前置裁决是「是否允许自动置常驻」** —— 它与 ADR-0142①/0141① 直接冲突，须显式翻案或否决。

**落地面**：`src/core/notes/`（新动词或新类型）＋ `src/core/entry.py`（CLI）＋
`doc/openspec/specs/notes/spec.md`（MODIFIED/ADDED）＋ `doc/02-modules/notes.md` ＋ 测试 ＋
`coding-plan/known-risk.md` 台账。

**收口（2026-10-18，change `0273` / ADR-0263 / 台账 E209）**：按**方案 B** 落地 ——
`core.notes.close_milestone(...)`（确定性零 LLM；结论 / 关键决策 / 硬约束 / 关键事实固定节次序；
来源 = 显式条目 + 压实摘要 + 该会话 keyfact）＋ CLI `notes milestone`；产出 `pinned=True`、
缺省 `pin_priority=100`，复用既有常驻注入通道（**零新注入块**）。幂等覆盖、来源守护、
`redact_secrets` + 3000 字符头部保留截断同上档。**方案 C（自动置常驻）维持否决** —— 须显式翻案
ADR-0142① / ADR-0141① 方可再议。

---

### PA-09 检索质量：分区 / 图 / 真语义 / 缺省值

**现象**：蓝图的三项机制里，「三区分层向量检索」在本仓**没有对应物**，且检索面还有三处降级：

1. **无分区权重**：蓝图要「里程碑区权重拉满 / 关键决策区 / 过程日志区最低」；本仓是**统一打分**
   `rank = (0.5·sim + 0.2·layer_prio) × recency × (1+log1p(reuse)) × (1+importance)`
   （`src/core/memory/relevance.py:24-28,61-80`）。`layer_prio` 是 **L0–L4 稳定度**轴，
   **不是**「内容重要性」轴 ⇒ 过程日志与关键决策同权。
2. **无图**：`doc/02-modules/memory.md:313-316`「**无图存储 / 无遍历 API**」；
   `0203/proposal.md:29`「**不做知识图谱层**」；ADR-0193④（`known-risk.md:223`）——
   谓词闭合的理由是「谓词开放 ⇒ 图不可遍历」，**但闭合后并没有建图**，只把 `"A --p--> B"` 文本
   塞进「相关事实」块，与关键事实**争同一份额度**。
3. **缺省降级**：无 `llm.embedding_model` ⇒ memory 走 **0039 词法路径**、rag 走
   `HashEmbedder(dim=128, ngram=3)`（`runtime.py:539-553,606-610`）；`relation_extract` 缺省关
   ⇒ 边**惰性**；配比 `block_plan` 缺省关且**只生效 1/5**（唯一消费者 `memory_tokens`）。
4. **循环内查不到向量库**：`RagService` 只被 CLI 消费，`grep rag src/core/tools src/core/loop`
   **零命中** ⇒ 模型在循环内只能用 `MemoryStore.read()` 的**全库扫描 ＋ 热度加权**（L1 一阶路由
   未落，`known-risk.md:153`）。

**证据**（含**实测**）：

| 事实 | 出处 |
|---|---|
| L1 层为空：无一处写 `"L1"`；`MemoryStore.index()` 无消费者 | `grep '"L1"' src/` 零命中；`store.py:475-476`；`known-risk.md:153` |
| `importance` 维**空转**（写入闸门缺省关 ⇒ 恒 0.0） | `configuration/manager.py:767-772`；`runtime.py:591` |
| 唯一量化目标是**延迟**、无准确率判据 | `doc/00-product/requirements.md:331` CORE-NFR-PERF2「<100ms（1 万条事实规模）」 |
| **实测**：213 条记忆中 `relation.*` **0 条**（`keyfact.*` 24 条） | §5 附录（`~/.core/state/memory.jsonl`） |

**可选项与代价**

| 选项 | 做法 | 代价 |
|---|---|---|
| **A** | 现状 | 「是否漂移」永远无法判定 |
| **B** | **先建可测性**：1 万条合成事实语料 ＋ 召回准确率/延迟基准（离线，零网络） | 无产品行为改动；但**是 C/D/E 的前置** —— 没它无法证明任何优化有效 |
| **C** | B ＋ **分区加权**：按 `tags`/来源给 `relevance` 加一维权重（里程碑/决策/日志三档） | 需定义「三档」的判定（新 `tags` 约定）；与既有 `layer_prio` **正交**，须裁口径。**已闭**（change `0277` / ADR-0267 / 台账 E213） |
| **D** | C ＋ **图**：邻接表 ＋ 遍历 API（新 `MemoryBackend` 方法） | **显式翻案** 0203 的「不做知识图谱层」；触及后端协议与所有实现 |
| **E** | 真语义：必配 `embedding_model` 或引本地 embedder | 与「零三方运行时依赖」红线冲突（`known-risk.md:150` 已裁「不引本地语义模型」）；须翻案 |

**建议**：**B 先行**（把「记忆外置是否生效」变成可判定），**C 次之**（低成本、直接对应蓝图三区、
零新存储）；**D / E 是能力级翻案**，须各自独立裁决（E 还要与零三方依赖红线对账）。

**落地面**：`tests/`（基准）＋ `src/core/memory/relevance.py` / `store.py`（若取 C）＋
`doc/openspec/specs/memory/spec.md` ＋ `doc/openspec/specs/context/spec.md` ＋ `known-risk.md` 台账。

**收口·方案 B（2026-10-18，change `0275` / ADR-0265 / 台账 E211）**：按**方案 B** 落地 ——
`tests/test_memory_scale_benchmark.py`：固定 10 000 条合成事实（L2/L3/L4、唯一锚点 `zqNNNNN`）×
20 条带 gold 查询，纯内存、零网络，度量 recall@5 / MRR@5 / 逐查询延迟。门禁：recall ≥ 0.9、
MRR ≥ 0.7（实测均 **1.000**）；延迟**只报告**（仅设 p95 `< 5000ms` 宽松回归护栏），语料确定性
由两次生成逐条一致钉住。**关键发现**：本机实测中位 **≈657ms** / p95 772ms / max 796ms ——
**未达 CORE-NFR-PERF2「<100ms / 1 万条」**；cProfile 显示约 78% 时间在 `_truncate` 对全部候选
逐条 `estimate_tokens`。本 change 零产品行为改动，**未修**该缺口。
**后续顺序（更新）**：检索延迟修复已落地（change `0276` / ADR-0266 / 台账 E212 —— `estimate_tokens` 正则化 ＋ 按内容校验的有界词元缓存；参考机中位 **85.8ms**，recall/MRR 1.000 不变）⇒ **可直接进 C（分区加权）**，收益可对照本基线评估。**D（图）/ E（真语义）仍须各自独立裁决**（E 与零三方依赖红线冲突，见 `known-risk.md:150`）。

**收口·方案 C（2026-10-18，change `0277` / ADR-0267 / 台账 E213）**：按用户裁决的 **tags 约定**
落地 —— `milestone`/`decision` ⇒ 高档（`tier = +1`）、`log`/`transcript` ⇒ 低档（`−1`）、其余
（含未知 / 无标签）⇒ 默认档（`0`），系数 `0.15` 加性；精确小写、冲突高档优先、只看 `tags`；
默认开启、无配置开关。**关键反证**：初版默认档取 `+0.075` 常量偏移，1 万条基准 recall@5 由
`1.000` 降至 **0.45** —— `rank` 的乘性复用调制放大了常量偏移，高复用填充项反超 gold；改为
`{+1, 0, −1}` 居零后，`0261`（26 条）与 `0275`（1 万条）基准 recall/MRR **逐项不变**（1.000），
10k 中位 85.8–108.3ms。测试 +4（3026 → 3030），反证 3/3。**D（图）/ E（真语义）仍须各自独立裁决**。

---

### PA-10 M4 基准 harness（token 次线性）

**现象**：`doc/00-product/product-definition.md:83` 的 M4 写着「长任务 token 增长随任务数呈
**次线性**（记忆外置生效）｜衡量方式：**基准任务序列测量**」——**该基准任务序列在本仓不存在**，
全仓无任何测量该指标的文件。于是 M4 既不可证伪也不可证实。

**证据**：

| 事实 | 出处 |
|---|---|
| M4 目标值 ＋ 衡量方式「基准任务序列测量」 | `doc/00-product/product-definition.md:83` |
| 自认「工程落地滞后」 | `doc/00-product/design-completeness-eval.md:116` |
| 已知**线性**膨胀点：工具说明**全量注入**、无按需筛选 | `known-risk.md:37`（E91，仍开） |
| 记账口径已修对（可直接喂 harness） | `0152`/ADR-0144：`last_prompt_tokens()` 探针 ＋ 系统提示/工具 schema 计入 |
| 素材已在手（每次运行的 trace/检查点） | `~/.core/state/traces.jsonl` 409KB；`checkpoints.jsonl` 36KB（§5） |

**可选项与代价**

| 选项 | 做法 | 代价 |
|---|---|---|
| **A** | 现状（有目标无测量） | 长任务成本无法回归；「记忆外置生效」这句话不可审计 |
| **B** | **最小 harness**：固定任务序列 × N 轮，记录每轮 `prompt_tokens` 曲线 ⇒ 输出斜率/是否次线性；**离线桩 provider**、零网络 | 需定义「任务序列」样本（可用既有 e2e 桩）；不入门禁时仍可能腐坏 |
| **C** | B ＋ CI 门（超阈转红） | 需定阈值；长序列跑时较长（或标 `slow`） |
| **D** | C ＋ 真模型长跑基线 | 成本/时间不可控，不宜入门禁 |

**建议**：**B**（`last_prompt_tokens()` 探针已存在、记账口径已修对，harness 成本低）；
阈值与是否入门禁（C）另行裁决。

**落地面**：`tests/`（新基准文件）＋ `doc/04-testing/test-cases.md`（新节）＋
`doc/00-product/product-definition.md`（M4 行补「衡量落地」）＋ `known-risk.md` 台账。

**收口（2026-10-18，change `0274` / ADR-0264 / 台账 E210）**：按**方案 B** 落地 ——
`tests/test_m4_token_growth.py`（离线确定性 harness：固定 24 轮等长任务 × 真实 `DefaultLoop`
＋ 桩 provider ＋ 有界摘要器；步进时钟确定性触发维护节拍），逐轮采集
`LLMPlanner.last_prompt_tokens()` 曲线并与「关闭摘要器/维护节拍 + 全量原文回灌」线性基线对比。
判据为机制性相对量（远期逐轮恒定、整体斜率低于基线、末轮占用更小、两次重放一致）；
**不设绝对阈值门禁**（方案 C 未采纳，阈值另行裁决）。M4 行已补「衡量落地」。**已知局限**见
`known-risk.md` §3 ADR-0264 行。

---

### PA-11 `coding-plan/README.md` 阶段索引漂移

**现象**：`coding-plan/README.md:3` 自述「本目录 `coding-plan/` 承载 **36 份** Phase 文档
（本 README 总索引 + `phase-0.md` ~ `phase-34.md`）」，而实测已有 **`phase-35.md` ~ `phase-41.md`**；
`:26` 亦自认「`coding-plan/README.md` §2（标 ✅ 与事实不符，属**已知**）」。

**证据**：`coding-plan/README.md:3`（计数与范围）、`:25-66`（索引表）、`:74-113`（总览表）；
`ls coding-plan/phase-*.md` ⇒ 最大 `phase-41.md`；`known-risk.md:26`（自认已知）。

**后果（本轮实证）**：索引缺口**直接导致重复劳动** —— 本次回答用户「长任务满足了吗」时，若只按
README 索引找，会**漏掉 `phase-36`（长任务硬化）与 `phase-38`（对照四维记忆蓝图查漏补缺）**
两册最相关的账，从而把「已裁决过的事项」重报为「缺口」。

**可选项与代价**

| 选项 | 做法 | 代价 |
|---|---|---|
| **A** | 现状 | 下一次走查继续漏 |
| **B** | 补 README：索引表 ＋7 行、总览表 ＋7 行、计数 36 → 43 | 纯文档；但**会再漂**（无守卫） |
| **C** | B ＋ **守卫测试**：断言 README 声明的份数/范围与实际 `phase-*.md` 一致 | 一条断言；把「漂移」变成转红 |

**建议**：**C**（本轮实测已证明这个缺口会**实际造成返工**，值得一条断言兜住）。

**落地面**：`coding-plan/README.md` ＋ `tests/`（守卫）＋ `known-risk.md`（销 `:26` 的已知项）。

**收口（2026-10-18，change `0287` / ADR-0277 / 台账 E223）**：按**方案 C** 落地 ——
`coding-plan/README.md` 计数改为可机读事实（`phase-*.md` 共 **48** 份：主文档 44 ＋
配套记录 4，最大 `phase-41.md`）；§1 索引补齐 `phase-32.md` 与 `phase-35.md`~`phase-41.md`
共 8 行、§2 总览补 7 行；新增 `tests/test_coding_plan_index.py` 三条断言（计数/最大编号、
§1 行覆盖、PA-12 前缀注记），新增 Phase 未补索引即转红。**已知局限**见
`known-risk.md` §3 ADR-0277 行。

---

### PA-12 `phase-38` 与「记忆三面路线图」G1/G2 同名不同义

**现象**：两套**独立**编号共用 `G1` / `G2`：

- **记忆三面职责重划路线图**：`G1` = notes 常驻预算（`0154`）、`G2` = notes 写入安全（`0151`）、
  `G3` = 半自动提升（`0153`）、`G4` = 结构化抽取（`0155`）、`G5` = rag 定位成文（`0156`）
  —— 见 `known-risk.md:44-48`；收官声明见 `phase-38.md:118`「**记忆三面路线图 G1~G5：全闭**」。
- **`phase-38` 自己的 §0 批内缺口**：`G1` 接线（`0203`）、`G1` 谓词面（`0203`）、`G2` 因果（`0202`）
  —— 见 `coding-plan/phase-38.md:24-27`。

**证据**：`coding-plan/phase-38.md:24-27` vs `coding-plan/known-risk.md:44-48` ＋ `phase-38.md:118`。

**后果**：按 `G1` 检索会同时命中两套语义；本轮取证（要求侧子代理）**专门标注过这一歧义**，
说明它已在实践中造成误读成本。

**可选项与代价**

| 选项 | 做法 | 代价 |
|---|---|---|
| **A** | 现状 | 继续误读 |
| **B** | 给 `phase-38` 的批内缺口改前缀（如 `B38-1..3`）＋ 在 §0 加一行「**与记忆三面 G1/G2/G3 非同组**」注记 | 只动一处文档 ＋ 一行注记；**不改写历史裁决内容** |
| **C** | 全局重编号（含历史 ADR/台账） | 历史成本极高，**不建议** |

**建议**：**B**（最小改动消除歧义；否定 C）。

**落地面**：`coding-plan/phase-38.md` §0 ＋（可选）`known-risk.md` 交叉注 ＋ `coding-plan/README.md`
（若取 PA-11 一并补约定）。

**收口（2026-10-18，change `0287` / ADR-0277 / 台账 E223）**：按**方案 B** 落地 ——
`phase-38.md` §0 批内缺口改 `B38-1 因果` / `B38-2 接线` / `B38-3 谓词面`，表下加
「与记忆三面路线图 G1~G5 **非同组**」注记；§118 路线图收官声明逐字保留；全局重编号
（方案 C）维持否决。守卫见
`tests/test_coding_plan_index.py::test_phase38_batch_gaps_do_not_reuse_roadmap_labels`。

---

## §3 第一轮已落地（对照，**不属**本簿）

- **10 条提词**（`src/core/loop/planner.py:50`、`src/core/orchestration/planner.py:19/29`、
  `src/core/memory/summarize.py:37`、`src/core/memory/extract.py:178/394`、
  `src/core/skills/sop.py:48`、`src/core/skills/iteration.py:46`、
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

---

## §4 已转出 / 缓议（不在本簿裁决队列，但有账可查）

本簿**开放项为 0**（PA-01~PA-07 全闭）。以下子项在闭项时被明确**缓议 / 单独立项**，登记落在
`known-risk.md`（§1 账目 / §3 ADR 局限）—— 此处只做**索引**，避免「从本簿入口看不见」。

| 来源 | 子项 | 登记位置 |
|---|---|---|
| PA-01 C | **流式泄漏**：`astream` 以首个非空 chunk 首字符定形态 ⇒ 尾随 JSON 漏到屏幕（根治须放弃边出边流的全缓冲，**产品级取舍**） | `known-risk.md` §3 ADR-0212 局限② |
| PA-02 C | 扩 `on_turn` 带 `trace_id` ⇒ 取 `loop.failure.<trace>`（材料比 `steps` 更贴近「为什么失败」；触及 loop 钩子协议） | `known-risk.md` §3 ADR-0213 局限① ＋ PA-02 闭项正文 |
| PA-02 旁 | `sop.py::observe` 把**未脱敏** `steps` 喂 `build_sop_prompt`（**既有**暴露面，非该 change 引入） | `known-risk.md` §3 ADR-0213 局限② |
| PA-04 C | 落盘前 `ast.parse` 语法自检（裁决为**验证门职责**，未采） | `known-risk.md` §1 E157 行 ＋ §3 ADR-0210 行 |
| PA-05 C | 镜像**反向生成**（人不再手改；须先解决旁注另存的结构重排） | 本簿 PA-05 闭项正文 ＋ `known-risk.md` §3 ADR-0210 局限② |
| PA-06 B′ | ⑦ 重要度提词收紧（牵动 `W_IMPORTANCE` 乘性权重与写入闸门，**待真实分布证据**） | `known-risk.md` §3 ADR-0210 局限③ |
| change `0225` | 镜像旁注的**新增加固点**须手工登记锚（`_NOTE_ANCHORS`）—— 旁注无真源可核 | `known-risk.md` §3 ADR-0215 局限② |

---

## §5 取证附录（第二轮：要求侧 / 实现侧 / 实测三层）

> 本附录只记**方法与结论**，不搬原始报告；每条结论的 `file:line` 已入 PA-08~PA-12。

### 5.1 要求侧（规范面）

- **正式口径**：「**记忆即光谱**」＋ **L0–L4 五层**（ADR-0004；`doc/openspec/specs/memory/spec.md:4,9`）。
  「四层记忆光谱」**不是本仓措辞**；「四维/四类」只来自外部蓝图（未跟踪文件
  `memory-4-layer-architecture.md:57-60`），**从未立为 Requirement**。
- **长任务不是任何 Requirement**：`doc/00-product/requirements.md:32-35` 的 CORE-MEM-R1~R4 无
  「跨月 / 上千轮」措辞；长任务只在 spec 散见（`orchestration/spec.md:99` 断点续跑、
  `context/spec.md:4` 长任务信息过载）＋ 指标 M4（`product-definition.md:83`）。
- **外部材料效力**：`Agent-Memory.md` / `Agent-Memory-LongTask.md` / `memory-4-layer-architecture.md`
  三者均为**未跟踪文件**，前两份末尾自标「百度AI生成，内容仅供参考」；台账定位为「外部参考审查…
  取精华弃糟粕」，并**明写不取**其「里程碑永久删除 / 单库无隔离 / 三方依赖」（`known-risk.md:269`）。
- **数值承诺已弃**：ADR-0190「**采其结构弃其数值**」（`known-risk.md:106`）。

### 5.2 实现侧（三态：规格 / 代码 / 生产接线）

- 四类记忆 × 载体/写入/读取/上限/可达性 的完整表 ＝ 本轮实现侧取证产物；要点已提炼进
  §0.2 与 PA-09。
- **未接线/降级清单**（20 条）要点：`relation_extract` / `episodic_extract` / `importance_gate` /
  语义遗忘面 / `block_plan` / `failure_lessons` / `skills.retirement` **七项缺省关**；
  `MemoryStore.index()`（L1）无消费者；`MemoryStore` 未实现自己 Protocol 声明的
  `crystallize`/`dissolve`；`Crystallizer.dissolve()` 无调用；**RAG 对循环不可达**；
  压实 `from:<id>` 出处面**死面**；`Compactor.compact` 只吃本轮消息。

### 5.3 实测（本机真实配置 ＋ 真实 state）

**配置层**（判「缺省关」是否等于「实际关」）：

```bash
cat ~/.core/config.yaml          # 仅 llm.* / permission.mode / loop.max_rounds: 20
grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' ~/.core/.env   # 仅 GLM_BASE_URL / GLM_API_KEY（**不读值**）
env | grep -oE '^CORE_[A-Za-z0-9_]*'               # 空 ⇒ 无 CORE_* 功能键
```

⇒ 三项配置源均无功能键 ⇒ §0.2 的「缺省关」项**在本机确实关闭**。

**state 层**（判「四类记忆实际产出过什么」）—— 只统计**结构**，不回显正文/取值（守
`CORE-NFR-SEC1`）：

```bash
python3 - <<'PY'
import collections, json, pathlib
mem = [json.loads(l) for l in (pathlib.Path.home()/".core/state/memory.jsonl")
       .read_text(encoding="utf-8").splitlines() if l.strip()]
print(len(mem))
print(collections.Counter(r["id"].split(".")[0] for r in mem if r.get("id")))
print(collections.Counter(r.get("layer") for r in mem))
PY
```

实测结果（2026-10-11，213 条）：

| 维度 | 应有产物 | 实测 |
|---|---|---|
| 会话 | 长期 / 中期摘要 | `compaction.summary.*` 3 ／ `compaction.mid.*` **0** |
| 语义 | `keyfact.` 点 ／ `relation.` 边 | 24 ／ **0** |
| 程序 | skills ／ SOP 样本 ／ 反馈 | `skills.*` 75（多为 miss 计数）／`sop-samples.json` 456KB／`skill-feedback.json` **78 B** |
| 情景 | 轨迹 ／ 步序 ／ 失败 ／ 归纳 | `loop.*` 88（轨迹 81 / 步序 7）／`loop.failure.*` **0**／`episodic.*` **0** |

层分布 `L2=201 / L4=12`（归档在动）；`notes/` 19 篇 canonical 笔记。

> **口径限定**：本机 213 条的样本，用户用法未必是「跨月长任务」跑法 ⇒ 属**证据**不是**证明**。
> 它的价值在于把「缺省关」从**代码事实**升级为**运行事实**，并给出下次复核的**可重跑命令**。
