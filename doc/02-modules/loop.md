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
  并以 provider 实报 `usage.prompt_tokens` 为**下界**（change `0152`／ADR-0144）；**流式路径同口径**
  （change `0183`／ADR-0174）：末块上报用量时在 `astream` 循环体首行消费并取较大者，未上报则维持估算。
  请求组装次序：系统提示 → `history` → 本轮 `messages`。
- **请求侧输出上限**（change `0183`／ADR-0174）：`LLMPlanner(max_tokens=…)` 由组合根按
  `loop.output_reserve` 注入（四个 loop 的全部 planner 同源同参）⇒ `> 0` 时下发 `max_tokens`，
  预留从**记账假设**变为**端点上界**。
- **落盘点**：`perceive` 落本轮 user 行；收尾在 `remember` **之前**落 (user, 最终 reply) ——
  且**终止轮不落 reply**（此时 `ctx.reply` 是合成串，落盘即谎报模型原话）。
- **不变量**：`session_id == ""` / 未注入转录 / `history_turns == 0` ⇒ 零写入零回灌（逐字向后兼容）。

### 3.1.2 三层会话滑窗：短 / 中 / 长（change `0178`／ADR-0169）

- **动机**：单层「双重上界」切片在超限时**静默丢最旧**、无摘要替换 ⇒ 超 `history_turns` 轮即失忆；
  且会话摘要**从不进 prompt**、日常会话**根本不产摘要**。三层滑窗把「原文 + 摘要」按比例混合。
- **三层语义**：短层 = 最近 `short_turns` 轮**原文逐字**；中层 = 紧随其前的 `mid_turns` 轮 → **模型滚动
  摘要**（`compaction.mid.<session>`）；长层 = **会话整体摘要**（`compaction.summary.<session>`，既有产物）。
- **比例配额**：短 / 中 / 长 = `0.5 / 0.3 / 0.2`（模块常量），历史预算沿用 `token_budget // 2`；
  配额由 `core.context.plan_window`（纯函数、零 I/O）给出，切分由 `TranscriptStore.window()` 执行。
  `loop.history_turns` 仍是**唯一**用户可调旋钮（三层配比随之等比缩放）。
- **注入面**：两层摘要作**独立系统块**（顺序：常驻笔记 → 历史摘要（长期）→ 历史摘要（中期））注入
  `_system_prompt`，**绝不折入** `history` / `messages`；token 计入 `token_used`（非空守卫）。
- **物化点**：`_maintain(trace_id, session_id)` 会话感知，四步各自降级：①会话级记忆压实
  ②中期摘要物化（读转录中带 → 只读桩 → 既有摘要通道）③遗忘 ④冷路径；仍 off-loop（承 ADR-0157）。
- **轮内压实的记忆固化**（change `0192`／ADR-0182）：`_compact` 的记忆固化步骤改传
  `session_id=ctx.session_id`，与维护节拍①**同口径**（仅聚合本轮会话的 L2 episodic 条目，
  SHALL NOT 顺手提炼他会话条目）；此前裸调 `compact()` = **全量聚合**（跨会话串扰）。空会话轮
  `compact(session_id="")` ≡ 裸调（全量），行为**逐字不变**；全量语义保留给显式调用（CLI / 运维）。
- **冷会话逐字兼容**：无任何摘要 ⇒ `tiered=False` ⇒ 短层吃满 `history_turns` 与全部预算、中层零 ⇒
  请求**逐字等于今天**。
- **摘要注入与历史回放解耦**（change `0194`／ADR-0184／账本 E131）：`_load_summaries` 的门控只按
  **本职**判据（空标识 / 未注入转录 / 未注入 memory ⇒ 摘要不读不注入），**不**受 `loop.history_turns`
  连坐 —— `history_turns` 是**原文回灌**的轮数上界，`history_turns=0`（关原文回放）时历史带为空，
  但该会话已有的两层摘要 SHALL 照常注入（此前连坐 ⇒ 摘要被静默丢弃，长任务失忆来源之一）。
  缺省（`history_turns > 0`）⇒ 门控**等价**、行为**逐字不变**。

### 3.2 行动可回滚（Act 阶段）

- 每个 action 经 `EffectTracker.record` 落 undo 栈。
- 一轮内某 action 失败 → 自动执行该轮 undo 回滚，并把失败原因写入记忆（供 L4 诊断）。
- 不可逆/高风险操作（rm、写系统、杀进程、支付）→ 触发 `ask_user` 确认门。
- **执行接缝可包裹**（change `0209` / ADR-0199）：`DefaultLoop` 新可选参
  `act_wrapper: Callable[[ActFn], ActFn] | None`（缺省 `None`）——`__init__` 里
  `self._act = act_wrapper(self.act) if act_wrapper is not None else self.act`，`astream` 经
  `self._act(...)` 调动作。组合根用 `core.loop.fault_adapter.FaultChain` 注入容错重试（详见
  `02-modules/constraints.md` §4）；`None` ⇒ `self._act is self.act` ⇒ 既有路径**逐字不变**。
  适配层落 loop 侧（`fault_adapter` 在 `core/loop/` 内、import `core.constraints`）：`loop → constraints`
  是合法依赖方向，`constraints → loop` 才是红线（`tests/test_architecture.py` 守护）。`ActFn` 协议在
  `core/loop/protocol.py`。

### 3.3 无行动不记忆（Remember 阶段）

- **每一轮**（即使无事发生）也写入轻量轨迹；有教训/新经验则写 L2 事实 / L3 技能。
- 这是"会记"的硬约束：记忆是循环的必然产物，不是可选动作。
- **行动与结果另立一条 L2 条目**（change `0173` / ADR-0164）：`remember` 除轨迹条目
  （`loop.<trace_id>`，内容**逐字不变**）外，把本轮的**行动与结果**序列（工具名 + 有界参数摘要 +
  有界结果节选，复用 `_action_steps` 渲染）写成**另一条** `loop.steps.<trace_id>`。**另立而非合并**：
  抽取器对**每条** L2 条目只取前 400 字符入 prompt，而关键事实的实体历来产自轨迹条目的**散文** ⇒
  合并会把散文顶出窗口。该条目 **有界**（逐行 ≤`_MAX_STEP_LINE`、整体 ≤`_MAX_MEMORY_ENTRY`=2048）、
  写入前**逐行**经 `redact_secrets` 脱敏（判据与关键事实抽取**同源**、方向 over-redact），
  与轨迹条目**同 trace / 同 session**（一并可逆、归组口径一致）。**无工具调用 ⇒ 不写该条目**；
  `remember(steps=…)` 缺省空 ⇒ 行为与变更前逐字一致。
- **轮级失败再另立一条 L2 条目**（change `0179` / ADR-0170）：本轮**失败**时，除上述两条外
  写第三条 `loop.failure.<trace_id>`（`tags=["loop","failure"]`、`kind="episodic"`、与二者并存、
  同 trace / 同 session）。内容＝`failure_digest`＝任务 + 失败原因 + 失败轮次 + 失败动作，
  **逐行** `redact_secrets`、整体 ≤`_MAX_MEMORY_ENTRY`。**范围＝轮级失败** ——
  `failed=bool(limit_reason) or turn_failed`（终止动作失败 / 轮次·token 预算终止 / 推理产出不可解析）；
  轮内自愈的工具失败**不入**（仍在 `loop.steps` 条目里）。**未失败 ⇒ 不写**；三参数缺省 ⇒ 逐字一致。
  该标签使**压实材料排除**它（见 `02-modules/memory.md` §4）⇒ 失败证据不被摘成中性总结、不被迁 L4。
  `raw_output` **不入**本条（ADR-0161 明文禁入面，失败条目不得成为旁路）。

### 3.4 推理输出可解析、失败可见（Reason 阶段，change `0166` / ADR-0156）

- 规划器把模型输出解析为**四形态**：纯 JSON 动作 / 原生 `tool_calls` / 自然语言回复 / **未闭合的动作载荷**（见下）；
  **容错**：正文之后**收在文末**的动作 JSON（含 `tool_id`）仍识别为工具动作 —— 模型「解释在前、
  动作在后」是自然行文次序，旧实现只按首字符判定 ⇒ 整段当答复 ⇒ **静默零执行**。
- **只认尾部**：正文中间夹带的 JSON（如解释协议时引用的示例）**不**命中 —— 宁可漏检不误判。
- **失败可见**：解析失败 / 模型调用失败 ⇒ 终止动作带 `failed=True`（`LLM_PLAN_PARSE_FAILED`），
  本轮记为失败（`LoopResult.failed`、收尾钩子 `ok=False`、`step_completed.failed`）——
  不再与「正常收尾」无从区分。**不改终止语义**：仍以回复收尾，`loop_failed` 只认 `limit_reason`。
- **失败态只属于终止动作**：工具动作失败走既有 ReAct 多轮自愈口径，**不**并入本标记。
- **形态 4：未闭合的动作载荷**（change `0170` / ADR-0161）：外层动作对象被**截断或写坏**时，尾部
  最末一个「可解析且其后无剩余」的对象往往是它的**内层 `args`** ⇒ 承 0166 的兜底会把整段 JSON 当
  正文且记为**成功**。判据（严格）：自**最后一次** `"tool_id"` 回退至其外层 `{`，做**字符串感知**的
  括号深度扫描（`_never_closes`），深度**从未**回到 0 即命中 ⇒ **失败态终止动作**；**闭合**的尾部
  对象一律**不**命中。**原始产出可诊断**：「首字符 `{` 解析失败」与形态 4 两类失败态终止动作另带有界
  原始产出（`Action.raw_output` → `LoopResult.raw_output`，上界 `_RAW_OUTPUT_MAX`），只供呈现层折叠
  与 trace 留痕，**不进**转录 / 记忆 / 笔记、**不并入** `reply`。**成因可辨**：消费 provider 的
  `finish_reason`（`LLMChunk` 亦已携带）—— `length` ⇒ 提示明示**被截断**，否则 ⇒ **未闭合**。
- **行动序列人类可读**（change `0171` / ADR-0162）：收尾观察者交付的 `steps` 由
  「`role: json.dumps(...)`」改为「工具名（有界参数摘要）→ 有界结果节选」——
  **不落** ReAct 消息原文与整篇工具输出（容器型参数只报类型与规模）；纯文字回复轮为空列表
  ⇒ 下游（笔记写回）据此判「有无行动」。

### 3.5 收尾与维护在工作线程上执行（change `0167` / ADR-0157）

- 三段收尾/维护工作在**事件循环之外**执行（`asyncio.to_thread`，循环 `await` 其完成）：**轮内压实**
  `_compact`、**收尾钩子** `_notify_turn`、**维护节拍** `_maintain`（含冷路径回调）。
- 理由：这三段**可能含同步模型调用**（组合根注入的 `_llm_text` 接缝 —— 会话摘要 / 关键事实抽取 /
  SOP 提炼 / 技能迭代 / 进化 review），而同步形态 `LLMProvider.completion()` 以 `asyncio.run` 桥接、
  **在事件循环线程上必抛 `RuntimeError`**；且其耗时为模型网络往返（秒级），在循环线程上会阻塞其余任务。
- **只换执行线程**：三个私有方法签名与内部降级链**逐字不动**，四个注入接缝仍是**同步 callable**
  ⇒ 终止语义、事件序、转录追加、遥测事件名零回归。依据：ADR-0064 决策②（同步传输本就在工作线程上跑）。

### 3.6 轮级检查点（change `0214` / ADR-0204）

- 新可选构造参 `turn_checkpoint: Callable[[str, str, str, bool], None] | None`（`(trace_id, session_id,
  goal, done)`，**闭包注入** —— loop **不** import durability，沿 `turn_observer`／`cold_path` 先例）。
- **两写点**：轮首（`_load_pinned_notes` 后）写 `done=False`、轮末（`remember` 后）写 `done=True`，
  经私有 `_mark_turn`；`astream` 无 `try/finally` ⇒ 轮内异常 / 被杀**天然**留 `done=False`（镜像波次语义）。
- **缺省 `None`** ⇒ `_mark_turn` 首行短路 ⇒ **零写入**、既有路径逐字不变；`goal` 由 `_task_text(ctx)` 取。

### 3.6.1 既往失败教训注入块（change `0217` / ADR-0207 / 台账 E154）

- 新可选构造参 `failure_lessons_consult: Callable[[str], str] | None`（**入参 = 本轮会话标识**）——
  **闭包注入**（loop 不 import memory 语义面，沿 `turn_observer` / `turn_checkpoint` 先例）。
- `astream` 轮首经 `_load_failure_lessons` 写入 `LoopContext.failure_lessons`；**抛错降级**：置空该字段
  ＋ trace `failure_lessons_consult_failed`，**不改变本轮结局**（同 `_consult_notes` / `_load_pinned_notes`）。
- 推理规划器把非空该字段以**独立系统块**（「既往失败教训：」）注入 —— **不折入**「相关事实」（后者按
  预算截断会静默丢弃）或「相关笔记」（语义不同）。
- **缺省 `None`** ⇒ 首行短路 ⇒ 该字段恒空 ⇒ **提示词逐字不变**；**只接主 loop**（子 Agent / 神兽 /
  宠物 loop 不接，同 `transcript` / `turn_checkpoint` 注入面）。

### 3.7 可观测

- 每轮生成 `trace_id`，贯穿日志/效应/记忆写入，单轮可复现（NFR-OBS2）。
- **压实/抽取成本留痕**（change `0253`／ADR-0243）：每实际维护节拍产一条 `maintenance` 事件
  （总耗时 + 分步耗时），每次轮内压实产一条 `compaction` 事件（`trigger` + 总耗时 + 分步耗时）；
  步骤失败记 `maintenance_failed` 并带 `step` 归因，不中断其余步骤。未注入 tracer ⇒ 零事件；
  payload 不含正文、摘要文本或会话标识。

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
