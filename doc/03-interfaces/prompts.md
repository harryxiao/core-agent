# 内置提词总表（Built-in Prompt Catalog）

> **change `0219` / ADR-0209 / 台账 E156**（承 `0215` / ADR-0205 / 台账 E152）。本文件是**全仓内置
> prompt 的现状快照（镜像）**，便于集中查阅与评审。

---

## 0. 本文件的定位（先读）

- **本文件是镜像，不是真源。** prompt 的真源是**各模块常量**（下表「落点」列的 `文件:行`），
  以及 `tests/test_prompt_pinning.py` 里逐字 pin 的**独立副本**。
- **改一条 prompt = 改三处**：① 模块常量 → ② `tests/test_prompt_pinning.py` 的逐字副本 →
  ③ 本表。只改 ① 会让 pin 测试**转红**（这正是 pin 的设计意图：逼改者显式确认）。
  未 pin 的条目（见 §6）改 ① 后同步 ③ 即可。
- **分类口径**：「控制面／数据面／进化面／人格面」是本表的**解释性归类**，**不是**仓内正式术语
  —— 仓内「控制面／数据面」另有既定含义（pet 控制面 `PetControl`、分布式「控制面·执行面分离」、
  进化「数据面·执行面分离」）。此处：**控制面** = 决定「怎么想／怎么动」的推理与编排提词；
  **数据面** = 把素材（会话事件／执行轨迹）变换为产物的提词；**进化面** = 改核心自身的提词；
  **人格面** = 宠物人格。
- **安全口径**：凡涉及密钥的条目，其「绝不输出明文」措辞是**安全承重**，改动须格外审慎
  （见 §2 ⑤⑦、§7）。

---

## 1. 总表

| # | 面 | 提词 | 落点（`src/`） | 输出契约 | pin |
|---|---|---|---|---|---|
| ① | 控制面 | 推理规划器 | `loop/planner.py:50` `_SYSTEM_PROMPT` | 自然语言 **或** 工具 JSON | ✓ `0215` |
| ② | 控制面 | 任务拆解器 | `orchestration/planner.py:19` `_DECOMPOSE_SYSTEM` | JSON `{subtasks:[…]}` | ✓ `0215` |
| ③ | 控制面 | 验收判定器 | `orchestration/planner.py:29` `_VERIFY_SYSTEM` | JSON `{passed,reason}` | ✓ `0215` |
| ④ | 数据面 | 记忆压实器 | `memory/summarize.py:37` `_PROMPT_HEAD` | 文本（更新后摘要） | ✓ `0215` |
| ⑤ | 数据面 | 关键事实抽取器 | `memory/extract.py:178` `_PROMPT_HEAD` | JSON `[{entity,value,ref}]` | ✓ `0215` |
| ⑥ | 数据面 | 实体关系抽取器 | `memory/extract.py:394` `_RELATION_PROMPT_HEAD` | JSON `[{head,predicate,tail}]` | ✓ `0215` |
| ⑦ | 数据面 | 记忆重要度评分器 | `memory/importance.py:27` `_PROMPT_HEAD` | 数值 `0`–`1` | ✓ `0215` |
| ⑧ | 数据面 | 情景归纳器 | `memory/episodic.py:35` `_PROMPT_HEAD` | 文本（四段结论快照） | ✓ `0219` |
| ⑨ | 数据面 | SOP 提炼器 | `skills/sop.py:48` `_PROMPT_HEAD` | 文本（编号步骤清单） | ✓ `0215` |
| ⑩ | 数据面 | 技能迭代器 | `skills/iteration.py:40` `_PROMPT_HEAD` | 文本（编号步骤清单） | ✓ `0215` |
| ⑪ | 进化面 | 源码修补者 | `evolution/author.py:32` `_PROMPT_HEAD` | 文本（完整文件内容） | ✓ `0219` |
| ⑫ | 进化面 | 候选审查者 | `evolution/validator.py:43` `_REVIEW_PROMPT_HEAD` | 文本（首行 `PASS`/`REJECT`） | ✓ `0219` |
| ⑬ | 人格面 | 宠物人格 | `pet/library/persona.py:24` `render_prompt()` | 文本（人格设定） | ✗ 动态拼接 |

---

## 2. 控制面（3 条）—— 推理与编排循环本体

### ① 主推理规划器 · `loop/planner.py:50`
```
你是 CORE-Harness 无特权核心的推理规划器，把用户任务推理为下一步动作。
输出格式二选一：①自然语言回复；②JSON 工具调用 {"tool_id": "...", "args": {...}}。
工具调用 JSON 须**单独成块**：不得与解释文字混写在同一段，不得用代码块围栏包裹。
```
**动态内置内容**：该 `_SYSTEM_PROMPT` 是**基座块**，运行时由 `Planner._system_prompt()`
按序装配**至多 11 个块**（空字段不产块 ⇒ 未触发时提示词逐字不变）。块种类（`0201`/`0217`）：

| 序 | 块标题 | 触发条件 |
|---|---|---|
| 1 | （基座 `_SYSTEM_PROMPT`） | 恒在 |
| 2 | `宪法规则：` | `pack.constitution` 非空 |
| 3 | `常驻笔记（任务级硬约束，逐轮生效，勿违背）：` | `ctx.pinned_notes` 非空 |
| 4 | `历史摘要（长期）：` | `ctx.summary_long` 非空 |
| 5 | `历史摘要（中期）：` | `ctx.summary_mid` 非空 |
| 6 | `相关事实：` | `pack.facts` 非空 |
| 7 | `文档目录（按需取详情，勿请求全文）：` | `pack.pointers` 非空 |
| 8 | `相关笔记：` | `ctx.notes` 非空 |
| 9 | `既往失败教训：` | `ctx.failure_lessons` 非空（`0217` 新增块种类） |
| 10 | `可用技能：` | 技能路由命中 |
| 11 | `可用工具：` | `self._tools is not None` |

> 解析侧旁注：模型把动作写成「解释 ＋ 换行 ＋ JSON」的混写形态时，`_trailing_json_object`
> 从文末 `{` 起 `raw_decode`（change `0166`/ADR-0156）—— 属**解析**逻辑，非提词。

### ② 任务拆解器 · `orchestration/planner.py:19`
```
你是任务拆解器。把目标拆成 2-6 个可执行的子任务 DAG，仅输出 JSON：{"subtasks": [{"id": "1", "goal": "...", "acceptance": "...", "depends_on": [], "priority": 0, "difficulty": "medium"}]}。规则：goal 是给执行智能体的单一明确指令；acceptance 是可判定的验收标准；depends_on 只引用已声明的 id，无依赖则留空数组；无依赖子任务不要伪造依赖；difficulty 是该子任务的难易度，只能取 "easy" / "medium" / "hard" 三档之一，把握不足时取 medium。
```

### ③ 验收判定器 · `orchestration/planner.py:29`
```
你是验收判定器。对照验收标准判定子任务结果是否达标，仅输出 JSON：{"passed": true, "reason": "..."}。结果未提供、与标准无关或未达标准时判 false，并给出一句话理由。
```
> 输入侧：结果正文经 `_MAX_VERIFY_CHARS = 4000` 截断后拼入（有界）。

---

## 3. 数据面（7 条）—— 素材 → 产物

### ④ 记忆压实器 · `memory/summarize.py:37`
```
你是记忆压实器。把新的会话事件合并进既有摘要，保留结论、决策与未决事项；既有摘要为空则据事件首次提炼。只输出更新后的摘要，不要复述过程。
```
**动态内置内容**：`build_prompt(entries)` = 头 ＋（既有摘要节选）＋ `会话事件：` 段 ＋ 逐条
`- {content[:400]}`。既有摘要投喂经 `_elide_summary`（越界时**首尾保留**，三段相加恰为
`MAX_SUMMARY_CHARS = 2000`，change `0193`）。产物落 `compaction.summary.<key>`。

### ⑤ 关键事实抽取器 · `memory/extract.py:178`（`{max}` 注入）
```
你是关键事实抽取器。从下面的会话事件中抽取「实体 → 取值」的关键事实，最多 {max} 条。只输出一个 JSON 数组，元素形如 {"entity": "实体名", "value": "取值", "ref": ""}。**绝不**输出任何密钥 / 凭据 / 口令的明文：凡属此类，value 一律写 "<redacted>" 并在 ref 写 "coeffect:<名称>"；若给不出引用，就不要输出该条。ref **只允许**形如 "coeffect:<名称>" 的引用；给不出这样的引用时 ref 留**空字符串**，**不要**用出处说明（如「第 N 轮」「某结论」「证据链」）充数。不要输出解释或多余文字。
```
> ⚠ **安全承重**：「**绝不**输出明文 ＋ value 写 `<redacted>` ＋ ref 写 `coeffect:`」是密钥不落
> 记忆的**第一道**（模型侧）约束；第二道是 store 侧无条件 `redact_secrets`。改动此措辞前须重评安全面。
> 条数上限 `{max}` 取 `KEY_FACTS_MIN = 8`（抽取出厂值，`KEY_FACTS_MAX = 16` 为自适应上限）。

### ⑥ 实体关系抽取器 · `memory/extract.py:394`（`{max}` / `{predicates}` 注入）
```
你是实体关系抽取器。从下面的会话事件中抽取「头实体 — 谓词 — 尾实体」三元组，最多 {max} 条。只输出一个 JSON 数组，元素形如 {"head": "头实体", "predicate": "谓词", "tail": "尾实体"}。谓词**必须**归入下表之一（可用中英任一变体，落库会归一化）：{predicates}。归不入下表的关系**不要输出**。**绝不**输出任何密钥 / 凭据 / 口令的明文（含作为实体名的情形）。不要输出解释或多余文字。
```
> `{predicates}` 由 `_CANONICAL_PREDICATES` 以「、」连接注入，**闭合白名单 8 谓词**：
> `depends_on` / `part_of` / `uses` / `causes` / `blocks` / `owns` / `implements` / `related_to`。
> 表外谓词由解析侧丢弃（`0203`/ADR-0193）。**安全承重**同 ⑤。

### ⑦ 记忆重要度评分器 · `memory/importance.py:27`
```
你是记忆重要度评分器。判断这条记忆对后续任务的价值，只输出 0 到 1 之间的一个数值（1 = 高度可复用，0 = 无价值），不要解释。
```
> 动态内置内容：`build_score_prompt(entry)` 渲染 `层 / 来源 / 内容[:400]` 三行（`0177`/ADR-0168）。

### ⑧ 情景归纳器 · `memory/episodic.py:35`（`0218`/ADR-0208 新增）
```
你是情景归纳器。把下面这段会话事件归纳为一段**结论快照**，四段结构依次写：目标（这段会话要做什么）、经过（实际怎么做的）、结果（最终达成了什么）、教训（下次同类任务该注意什么）。只输出归纳本身，不要复述过程、不要罗列原始事件。
```
> 动态内置内容：`会话事件：` 段 ＋ 逐条 `- {content[:400]}`。产物落 `episodic.<key>`
> （`kind="semantic"`、`session_id=""` 全局层，每会话至多一条覆盖式；store 侧无条件脱敏＋截断
> `MAX_EPISODIC_CHARS = 2000`）。键 `memory.episodic_extract`（缺省关）。

### ⑨ SOP 提炼器 · `skills/sop.py:48`
```
你是 SOP 提炼器。下面是同一类任务的多次成功执行轨迹（任务 + 行动/结果序列）。请提炼为可复用的标准作业步骤：只输出编号步骤清单，不要复述轨迹、不要解释理由。
```
> 动态内置内容：`任务：` ＋ `成功轨迹：` 段 ＋ 逐条 `- {step[:400]}`（`_MAX_STEP_CHARS = 400`）。

### ⑩ 技能迭代器 · `skills/iteration.py:40`
```
你是技能迭代器。下面是某技能的现行标准作业步骤与最近的实际执行情况。请针对失败给出更稳健的改进版步骤：只输出编号步骤清单，不要复述原文、不要解释理由。
```
> 动态内置内容：`技能 / 适用任务 / 执行情况` ＋ `现行步骤：`。

---

## 4. 进化面（2 条）—— 改核心自身

### ⑪ 源码修补者 · `evolution/author.py:32`
```
你是核心源码修补者。只修这一个模块，保持其现有风格与对外契约不变；只输出修补后的**完整**文件内容，不要解释、不要 diff、不要代码围栏。
```
> 动态内置内容：`目标模块 / 问题 / 当前内容`（原源码**给全**——模型要改的就是它）。输出经
> `strip_fence` 剥围栏后落盘。

### ⑫ 候选审查者 · `evolution/validator.py:43`
```
你是候选变更的审查者。只审这一个候选**自身是否自洽**（候选类型 / 目标模块 / 变更内容三者是否互相说得通、是否是真该由该目标承担的变更）；不评收益、不写实现。第一行以 PASS 起首表示通过，以 REJECT 起首表示不通过，其后可附一句理由。
```
> 动态内置内容：`候选类型 / 目标模块 / 变更内容`。判定词表 `_PASS_WORDS = ("PASS", "通过")`：
> **首行**以通过词起首才算通过，其余（REJECT／空／含糊／调用失败）一律不通过。

---

## 5. 人格面（1 条）—— 宠物

### ⑬ 宠物人格 · `pet/library/persona.py:24` `render_prompt()`
```
你是 {name}，一只{species}。
性格：{traits}。喜好：{likes}。
{persona_text}
```
> **动态拼接**（非模块私有常量）：`name`/`species`/`traits`/`preferences` 来自宠物档案，
> `persona_text` 来自 `pet.md`。因非固定常量，**不纳入**逐字 pin（见 §6）。

---

## 6. pin 覆盖与缺口

- **已 pin（12 条）**：①②③④⑤⑥⑦⑧⑨⑩⑪⑫ —— `tests/test_prompt_pinning.py`（`0215` 立 9 条，
  `0219` 补 ⑧⑪⑫）。覆盖：**逐字头** ＋ **结构不变量**（头恒首位 / 条目 `- ` 前缀 /
  占位符解析 / 谓词白名单集合恒等 / 节选上界字面量 `400`）。
- **未 pin（1 条）**：⑬ 宠物人格 —— 动态拼接，其行数/槽位随档案变化，逐字 pin 无稳定锚；
  如将来需要，宜按「固定槽位结构」而非逐字全文来 pin。

---

## 7. 改动指引（怎么改一条 prompt）

1. 改**模块常量**（§1 落点列）。
2. 若该条**已 pin** ⇒ 同步改 `tests/test_prompt_pinning.py` 的逐字副本（改错一处即转红）。
3. 同步改**本表**（§1 总表行 ＋ 对应小节正文）。
4. 跑四门禁：`.venv/bin/ruff check src tests` ／ `.venv/bin/ruff format --check src tests` ／
   `pyright`（0-0-0）／ `.venv/bin/pytest -q`。
5. **安全承重条目**（⑤⑥）：任何措辞改动须重评「密钥不落记忆」两条防线
   （模型侧 `绝不输出明文` ＋ store 侧 `redact_secrets`），必要时补反证。
