# 设计：notes 写回质量（change `0171` / ADR-0162）

## 1. 根因与定位

逐轮写回的输入端是 loop 收尾钩子的 `steps`（`_action_steps(ctx)`），其**唯一**生产点是
`loop/default.py:108-112`：把首条 user 消息之后的每条上下文消息线性渲染为 `f"{role}: {content}"`。
而 `content` 由 `_record_observation`（`default.py:537-553`）写死为 `json.dumps(...)`：

| 消息 | role | content |
|---|---|---|
| 助手动作 | `assistant` | `json.dumps({"tool_id": …, "args": …})` |
| 工具观察 | `tool` | `json.dumps({"data": …})` 或 `json.dumps({"error": …})` |

⇒ 笔记正文 = ReAct 消息原文（JSON 转储 + 整篇工具输出）。**根因是渲染形态**，不是写回逻辑。

闸门缺失的根因：`observe_turn` 只挡 `ok=False` 与空 slug，**不挡「无行动」**；而纯文字回复轮
按 `_record_observation` 的 `is_terminal` 早退，`ctx.messages[1:]` 本就为空 ⇒ 闸门判据天然可判。

## 2. 关键决策

### 决策 ① 可读渲染落在 `_action_steps` 全局（而非 notes 专属投影）

`steps` 有两个消费者：`sop_extractor.observe`（经 LLM 提炼）与 `note_store.observe_turn`。
若只在 notes 路径二次投影，则渲染逻辑**两份**、且 SOP 仍吃 JSON dump。改为**全局**渲染 ⇒
单一实现；SOP 提炼输入随之一并变干净（LLM 提示更好，且**不改变** SOP 的任何接口/阈值）。

**代价**：SOP 的行为随输入变化。风险评估 —— SOP 提炼器对 `steps` 只做「拼进 prompt」，
其阈值门 / 分组键 / 入库逻辑均以 `task` 为键、与 step 文本形态无关；测试面无对 step 形态的断言
（除空列表情形）。⇒ 可接受。

### 决策 ② 渲染契约（人类可读 + 有界）

```
<工具名>（<参数摘要>） → <结果节选>
```

- **工具名**：取 `tool_id` **原样**（不发明命名策略 —— 友好名映射是展示层政策，loop 不复制）。
- **参数摘要**：`k: v` 逗号连接，`key` 升序（确定性）；`v` 的取值：
  - `str` ⇒ 值本身，超 `_MAX_STEP_VALUE`(80) 截断加 `…`；
  - `int/float/bool/None` ⇒ `str(v)`；
  - `dict/list/tuple/set` ⇒ `<type len=N>`（**只报类型与规模，绝不 dump 正文**）；
  - 其余 ⇒ `<type>`。
- **结果节选**：复用既有 `_output_excerpt`（`_MAX_ACTION_EXCERPT`=400）；`{"error": …}` ⇒ 前缀 `错误：`。
- **整行有界**：`line[:_MAX_STEP_LINE]`(300) 兜底（多参数叠加不失控）。
- **健壮**：`content` 非 `{"tool_id": str}` 形态 ⇒ 该消息**不产行**（终止动作本无动作消息；
  畸形输入静默跳过，绝不因渲染失败而崩 —— 收尾钩子降级链仍在）。

### 决策 ③ 有意义闸门落在 `observe_turn`（存储侧自守）

判据：`if not ok or not steps: return None`。放存储侧（而非 `on_turn`）的理由：与既有
`ok=False` / 空 slug 的守卫**同处**、同口径、可单测；且对**任意**注入方（含神兽/子代理各自的
`turn_observer`）一致生效。**不改** `on_turn`（其仍无条件调用 —— 由被调方自守）。

### 决策 ④ 派生增殖不改

`_derived_turn_topic` 与来源守护**逐字不变**。闸门 ② 已消除「纯聊天轮成篇」这一主要噪音源；
真实任务轮每篇即一份沉淀，派生链同主题复用（不漏、不无谓增长）。

## 3. 不变量（规格 Scenario 覆盖）

- 纯文字回复轮 ⇒ 零写盘、既有文件逐字不变。
- 含工具动作轮 ⇒ 正文可读、无 `{"tool_id"` / `{"data"` dump、长度有界。
- `ok=False` ⇒ 不写（既有）。
- 来源守护、覆盖式写回、`tags`/`pinned` 保留 ⇒ 逐字不变。
- `TurnObserver` 签名 / 调用点 / 降级链 ⇒ 逐字不变。

## 4. 局限（写入 ADR-0162 §3 与 known-risk）

① 参数摘要对**结构简单**的工具（`path`/`url`/`script`）可读性好，但对深层嵌套参数只报类型与规模 ⇒
可能「看不出改了什么」。根治需按工具的语义字段白名单（与 TUI `_TARGET_FIELDS` 同源）—— 属展示层
政策，**不**下沉 loop；记入台账另议。
② 工具名保留 `tools.` / `mcp.` 命名空间前缀（未美化）。
③ 结果节选仍是 `str()` 形态（dict 结果呈现为 Python repr 而非 JSON）—— 有界可读，非结构化。
④ 闸门以「有无工具动作」为判据，**不**判「有无新结论」⇒ 无信息量的工具轮仍会写回（接受：
  覆盖式写回同主题、不增长）。
