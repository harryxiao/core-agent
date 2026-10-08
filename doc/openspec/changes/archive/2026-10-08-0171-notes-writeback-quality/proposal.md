# 变更提案：notes 写回质量 —— 可读解决过程 + 有意义闸门（change `0171` / ADR-0162 / 台账 E108）

> 规格：`doc/openspec/specs/notes/spec.md`「Consult → Build → Update 循环纪律」（**MODIFIED**）

## 为什么

用户实测（2026-10-08）：文档化记忆（notes）的**逐轮写回**把 canonical 知识库里塞进了
**不可读的原文转储**，且**琐碎轮次也入库**。逐条取证（读代码，非猜测）：

1. **JSON 转储进笔记** —— 逐轮写回正文的来源是 `loop/default.py::_action_steps`：
   ```python
   return [f"{m.get('role', '')}: {m.get('content', '')}" for m in ctx.messages[1:]]
   ```
   而 `ctx.messages` 里的助手动作 / 工具观察消息的 `content` **正是** `json.dumps(...)`
   （`default.py::_record_observation`：`{"tool_id":…, "args":…}` / `{"data":…}`）。
   ⇒ canonical 文件的 `## 解决过程` 逐字如：
   ```
   - assistant: {"tool_id": "file_read", "args": {"path": "…"}}
   - tool: {"data": {"content": "…整篇文件…", "bytes": 4096}}
   ```
   既是**最不可读**的形态（违背「文档化真相层」的立意），又**无界**（整篇工具输出 verbatim 落盘）。

2. **琐碎轮次入库** —— `runtime.py::on_turn` 在**每个成功轮**无条件调
   `note_store.observe_turn(task, steps, ok=True)`，**无有意义判据**。一句「你好 / 谢谢」的纯文字
   回复（零工具动作）也会创建 / 覆写一篇 canonical 笔记。

3. **派生 `topic-N` 增殖** —— 写回以 `slug_topic(首条 user 消息)` 为主题键；每句不同措辞各成一篇，
   撞外来源时再派生 `<topic>-2`、`-3`…（`store.py::_derived_turn_topic`，change 0151 来源守护）。

## 改什么

**只动两处实现 + 一处规格**：

- **① 人类可读的解决过程**（`loop/default.py::_action_steps` **全局改造**，用户裁决）：
  loop 交付给收尾观察者的 `steps` 由「`role: json.dumps(...)`」改为
  「工具名（有界参数摘要）→ 有界结果节选」的人类可读行；容器型参数只报类型与规模（不 dump 正文）。
  **同源**供 SOP 提炼（`sop_extractor.observe`）与笔记写回消费 —— 单一实现、SOP 输入质量一并受益。
- **② 有意义闸门**（`notes/store.py::observe_turn`，用户裁决「有工具行动才写」）：
  行动序列**为空**（纯文字回复轮）⇒ **不落盘**（返回 `None`），与 `ok=False` / 空 slug 的既有跳过
  口径一致。零新增可调参数、确定性。
- **③ 派生增殖**（用户裁决「靠闸门减量，保留每任务一篇 + 派生」）：**不做结构性改动**；琐碎轮被 ② 挡掉
  后残留多为真实任务，派生链本已复用（同主题覆盖、不无谓增长）。

## 影响面

- **loop 侧零接口变更**：`TurnObserver` / `turn_observer(task, steps, ok)` 签名与调用点**逐字不变**，
  只改 `steps` 的**内容渲染**。终止语义、事件序、转录追加、遥测零回归。
- **notes 侧零接口变更**：`observe_turn` 签名不变，仅增内部闸门。
- **spec**：`notes` spec「Consult → Build → Update 循环纪律」**MODIFIED**（既有 6 Scenario 逐字保留
  + 2 新 Scenario）；`loop` / `cli-ops` / `observability` 规格**零改动**。
- **不接 `EffectTracker`**：承 canonical 文档层既有取舍（`observe_turn` 本就不入效应栈）。
- **密钥红线不变**：正文为工具名 + 有界参数/结果摘要；**不新增**任何读取密钥的路径；脱敏口径不动。
