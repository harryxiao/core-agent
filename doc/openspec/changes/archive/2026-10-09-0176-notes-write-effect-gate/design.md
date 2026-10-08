# 设计：notes 写回效应闸门（change `0176`）

## 1. 根因定位

闸门判据弱化的根因：`observe_turn` 只看 `steps` 是否为空（0171 的闸门），而 `_action_steps`
对**所有**工具动作一律产出行。导致"调过 `web_fetch`/`file_read`"即满足写回条件——纯读型
工具轮（网页抓取转储、文件排查）整篇进 canonical 知识库，违背「无行动不记忆：只沉淀
**行动与结果**」原则（"行动"应有持久化效应，而非仅"有信息流入"）。

## 2. 关键决策

### 决策 ① 判据：轮内含写效应动作才写回（确定性，零 LLM）

判据定为「本轮行动序列中含至少一个**写效应工具动作**」，而非引入 LLM importance 评分。
理由：
- 与 0171 闸门（`not steps ⇒ None`）**同处**、同口径、可单测，无新依赖注入面
- 确定性（同一输入同一判定），不引入 ADR-0045 依赖方向的例外
- 用户实测中垃圾笔记的来源**全部**是纯读轮，效应判据已足够覆盖

写效应工具集（按工具名匹配，存于常量 `_WRITE_EFFECT_TOOLS`）：
`file_write` / `file_patch` / `code_run` / `gate_run` / `install` / `uninstall`。

### 决策 ② 判据落在存储侧 `observe_turn`（与 0171 同位）

理由与 0171 决策 ③ 相同：与既有守卫同处、可单测、对任意注入方一致生效；
不改 `on_turn`（其仍无条件调用——由被调方自守）。

### 决策 ③ `_action_steps` 不改

写效应判据**不在 loop 侧渲染时过滤**——steps 仍完整产出（SOP 提炼需要完整行动序列），
由 notes 侧闸门单独判定。工具名的匹配从 steps 行**前缀解析**（`_action_steps` 渲染形态
为「工具名（参数摘要）→ …」，工具名为行首至首个 `（` 之前）——不引入 loop↔notes 的
新接口，保持架构红线（loop SHALL NOT import notes，notes 也不 import loop）。

> **落地细节**：行首工具名是**完整 tool_id**（内置工具形如 `tools.file_write`），故解析后再剥
> `tools.` 前缀（`_TOOL_ID_PREFIX`）才与 `_WRITE_EFFECT_TOOLS` 的**裸名**集合对得上。判据为
> 「工具名 ∈ 写效应集**且**行内不含 `错误：`」（失败标记取自 `loop._summarize_result`）。

**备选（已否决）**：loop 侧为 steps 附带结构化元数据（工具名列表）。虽更稳健，但需改
`TurnObserver` 接口签名（影响所有注入方），超出本 change 最小改动面。前缀解析的容错：
行不以已知工具名开头 ⇒ 视为**无写效应**（保守，宁漏写不滥写）。

### 决策 ④ `code_run`/`gate_run` 失败不计写效应

判据为「**成功**的写效应动作」：行内含 `错误：` 前缀（`_summarize_result` 的失败渲染）
或轮整体 `ok=False` ⇒ 不满足。失败轮本已被 `ok` 闸门挡住；行级失败不计写效应与
「只沉淀**验证过的**行动与结果」一致。

## 3. 不变量（规格 Scenario 覆盖）

- 纯读轮（仅 `web_fetch`/`file_read`）⇒ 不落盘
- 含写效应轮 ⇒ 写回（覆盖式，来源守护不变）
- 既有 0171 闸门行为逐字不变（空 steps / ok=False / 空 slug）
