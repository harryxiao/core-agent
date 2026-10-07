# 模块设计：智能体循环（L3 Agent Loop）

> 对应规格：`doc/openspec/specs/loop/spec.md` ｜ 接口：`doc/03-interfaces/loop-interface.md`

---

## 1. 模块定位

L3 是**智能体的心脏**：把 L1 工具、L2 记忆、模型适配器装配成一个可运行的智能体。
关键原则：**loop 本身也是插件**，默认实现 ~100 行，可被不同策略替换（ReAct / Plan-Execute / 自定义）。

---

## 2. 四阶段闭环

```
感知(Perceive) → 推理(Reason) → 行动(Act) → 写记忆(Remember) → (回到 Perceive)
```

| 阶段 | 职责 | 输入 | 输出 |
|---|---|---|---|
| **Perceive** | 收集当前状态：用户输入、记忆检索、工具结果、环境反馈 | 消息流 + MemoryStore | 上下文包（有 token 上界） |
| **Reason** | 调用模型决策下一步（调用哪个工具/输出什么） | 上下文包 + 工具 schema | 动作序列/回复 |
| **Act** | 执行动作：经 L0 EffectTracker 记录可逆效应；不可逆操作先过确认门 | 动作 | 结果 + undo 记录 |
| **Remember** | 把本轮观察/结果/教训写入 L2 记忆（**每轮必做**） | 本轮轨迹 | 记忆写入 |

---

## 3. 关键设计

### 3.1 上下文有上界（Perceive 阶段）

- 注入内容按优先级裁剪：L0 元规则 > 本轮消息 > L1 索引 > L3 相关技能 > L2 相关事实。
- 硬性 token 预算，超出则按相关性分数截断；**绝不允许"把整个记忆塞进上下文"**。
- 调用方会话标识（缺省空串 = 未归属）装入 `LoopContext.session_id`，**推理期**即作检索与
  技能路由的归属维度（不只用于 Remember 写入）⇒ 会话之间对话内容严格隔离
  （change `0114`／ADR-0107）。

### 3.1.1 会话历史回灌（change `0115`／ADR-0108）

- **记忆隔离 ≠ 不失忆**：隔离解决「A 会话的沉淀进 B 的 prompt」；回灌解决「下一轮从一条全新
  user 消息开始 ⇒ 刷新即失忆」。二者互补，缺一不可。
- **载入点**：`perceive` 按**双重上界** `min(history_turns, token_budget // 2)` 从会话转录取既往轮次
  装入 `LoopContext.history`（**新字段**，不前置进 `messages` —— 后者首位被四处 accessor 当本轮任务）；
  记账 `token_used` **覆盖全量装配**（回灌历史 + 本轮消息 + planner 装配的系统提示与工具 schema），
  并以 provider 实报 `usage.prompt_tokens` 为**下界**（change `0152`／ADR-0144）。
  请求组装次序：系统提示 → `history` → 本轮 `messages`。
- **落盘点**：`perceive` 落本轮 user 行；收尾在 `remember` **之前**落 (user, 最终 reply) ——
  且**终止轮不落 reply**（此时 `ctx.reply` 是合成串，落盘即谎报模型原话）。
- **不变量**：`session_id == ""` / 未注入转录 / `history_turns == 0` ⇒ 零写入零回灌（逐字向后兼容）。

### 3.2 行动可回滚（Act 阶段）

- 每个 action 经 `EffectTracker.record` 落 undo 栈。
- 一轮内某 action 失败 → 自动执行该轮 undo 回滚，并把失败原因写入记忆（供 L4 诊断）。
- 不可逆/高风险操作（rm、写系统、杀进程、支付）→ 触发 `ask_user` 确认门。

### 3.3 无行动不记忆（Remember 阶段）

- **每一轮**（即使无事发生）也写入轻量轨迹；有教训/新经验则写 L2 事实 / L3 技能。
- 这是"会记"的硬约束：记忆是循环的必然产物，不是可选动作。

### 3.4 推理输出可解析、失败可见（Reason 阶段，change `0166` / ADR-0156）

- 规划器把模型输出解析为**三形态**：纯 JSON 动作 / 原生 `tool_calls` / 自然语言回复；
  **容错**：正文之后**收在文末**的动作 JSON（含 `tool_id`）仍识别为工具动作 —— 模型「解释在前、
  动作在后」是自然行文次序，旧实现只按首字符判定 ⇒ 整段当答复 ⇒ **静默零执行**。
- **只认尾部**：正文中间夹带的 JSON（如解释协议时引用的示例）**不**命中 —— 宁可漏检不误判。
- **失败可见**：解析失败 / 模型调用失败 ⇒ 终止动作带 `failed=True`（`LLM_PLAN_PARSE_FAILED`），
  本轮记为失败（`LoopResult.failed`、收尾钩子 `ok=False`、`step_completed.failed`）——
  不再与「正常收尾」无从区分。**不改终止语义**：仍以回复收尾，`loop_failed` 只认 `limit_reason`。
- **失败态只属于终止动作**：工具动作失败走既有 ReAct 多轮自愈口径，**不**并入本标记。

### 3.5 收尾与维护在工作线程上执行（change `0167` / ADR-0157）

- 三段收尾/维护工作在**事件循环之外**执行（`asyncio.to_thread`，循环 `await` 其完成）：**轮内压实**
  `_compact`、**收尾钩子** `_notify_turn`、**维护节拍** `_maintain`（含冷路径回调）。
- 理由：这三段**可能含同步模型调用**（组合根注入的 `_llm_text` 接缝 —— 会话摘要 / 关键事实抽取 /
  SOP 提炼 / 技能迭代 / 进化 review），而同步形态 `LLMProvider.completion()` 以 `asyncio.run` 桥接、
  **在事件循环线程上必抛 `RuntimeError`**；且其耗时为模型网络往返（秒级），在循环线程上会阻塞其余任务。
- **只换执行线程**：三个私有方法签名与内部降级链**逐字不动**，四个注入接缝仍是**同步 callable**
  ⇒ 终止语义、事件序、转录追加、遥测事件名零回归。依据：ADR-0064 决策②（同步传输本就在工作线程上跑）。

### 3.6 可观测

- 每轮生成 `trace_id`，贯穿日志/效应/记忆写入，单轮可复现（NFR-OBS2）。

---

## 4. 伪代码（默认实现骨架，~100 行）

```python
class DefaultLoop(Plugin):
    coeffects = ["model:adapter", "memory:store", "tools:provider", "constitution:v1"]

    def run(self, user_input: str) -> LoopResult:
        trace_id = new_trace_id()
        ctx = self.perceive(user_input)          # 检索记忆 + 拼上下文（有上界）
        while not ctx.done():
            action = self.reason(ctx)            # 模型决策
            if action.is_irreversible and not self.gate.confirm(action):
                action = self.decline(action)    # 确认门拒绝
            result = self.act(action, trace_id)  # 经 EffectTracker 记录
            if result.failed:
                self.rollback(trace_id)          # 回滚本轮
            ctx = self.observe(ctx, result)
        self.remember(trace_id, ctx.trajectory)  # 无行动不记忆
        return LoopResult(reply=ctx.reply, trace_id=trace_id)
```

---

## 5. 错误处理与边界

| 场景 | 行为 |
|---|---|
| 模型返回非法动作 | 忽略并回传结构化错误，不中断循环；**本轮记为失败**（`failed=True`，change `0166`） |
| 单轮超时/资源超限 | 回滚该轮，写记忆，进入下一轮（不无限重试） |
| 连续 N 轮失败 | 触发 L4 诊断钩子，暂停并请求人工介入 |
| 确认门被拒绝 | 记录拒绝原因，改写为安全动作或终止 |

---

## 6. 关联

- 规格：`doc/openspec/specs/loop/spec.md`
- 工具：`doc/02-modules/tool-use.md`
- 记忆：`doc/02-modules/memory.md`
- 测试：`doc/04-testing/test-cases.md`（LOOP 系列）
