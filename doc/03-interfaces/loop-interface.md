# 接口设计：智能体循环接口（Loop Interface）

> 层：L3 ｜ 对应规格 `loop/spec.md` ｜ 模块 `02-modules/loop.md`

---

## 1. 插件接口

Loop 本身也是插件，默认实现约 100 行，可被不同策略替换（ReAct / Plan-Execute / 自定义）。

```python
class LoopPlugin(Plugin):
    plugin_id = "loop.default"

    # 装配依赖（coeffects）：模型适配器 + 记忆存储 + 工具提供者 + 元规则
    coeffects = ["model:adapter", "memory:store", "tools:provider", "constitution:v1"]

    def run(self, user_input: str, *, session_id: str = "") -> LoopResult:
        """执行一轮完整闭环：感知 → 推理 → 行动 → 记忆。"""

    async def arun(self, user_input: str, *, session_id: str = "") -> LoopResult:
        """异步执行入口：与 run 同构，事件循环内非阻塞，可并发驱动多个循环。"""

    def astream(
        self, user_input: str, *, session_id: str = ""
    ) -> AsyncIterator[LoopEvent]:
        """流式执行入口：按生命周期顺序产出 LoopEvent 事件流。

        ``session_id`` 为本轮会话归属（缺省空串 = 未归属），随调用传递、不驻留实例；
        装入 :class:`LoopContext` 后**同时**作为：①「记忆」步写入 L2 条目的 ``session_id``
        （供压实/固化/遗忘按会话归组）；②**推理期检索与技能路由**的归属维度（装配器召回、
        路由未命中记录）——SHALL NOT 只用于写入（change 0114 / ADR-0107）。
        """
```

默认实现 `DefaultLoop`（骨架见 `02-modules/loop.md` 第 4 章）：

```python
class DefaultLoop(Plugin):
    coeffects = ["model:adapter", "memory:store", "tools:provider", "constitution:v1"]
    # 构造面（节拍相关）：maintenance_interval=900.0s（<=0 关闭）、clock=time.monotonic（可注入，便于测试）
    # 注入面（可选）：cold_path: Callable[[], None]（收尾节拍的进化冷路径机会；缺省未注入则不做，
    #   loop 不 import evolution——只拿回调，组合根注入闭包，见 evolution-interface §4.1）
    # 注入面（可选）：trace_observer: Callable[[str], None]（收尾回调：本轮遥测已齐后按**轮**提交
    #   trace_id 登记一条已完成 trace；**不随维护节拍节流**，异常降级留痕 trace_observer_failed；
    #   缺省未注入则不做；loop 不 import evolution——组合根注入 EvolutionWorker.on_trace_complete）
    # 注入面（可选）：middlewares: list[Callable[[LoopContext, Action], Action | None]]（动作前链，
    #   返回 None 即拒绝短路、返回 Action 则放行/改写）；action_observers:
    #   list[Callable[[LoopContext, Action, ActionResult], None]]（结果侧观察者，仅通知、异常降级留痕；
    #   loop 不 import constraints——生产侧由组合根注入适配层，见 constraints-interface §7 / ADR-0055）
    # 注入面（可选）：source: str = "loop"（落记忆的**命名空间**：本轮轨迹写入 L2 条目的 ``source``；
    #   神兽 loop 由组合根注入 "beast.<agent_id>" ⇒ 与主 Agent "loop" 隔离，见 beast-mode-interface §4/§10）
    # 注入面（可选）：transcript: TranscriptStore | None = None（会话转录；缺省未注入 ⇒ 零回灌零写入）；
    #   history_turns: int = 20（回灌最近 N 轮，0 = 关闭；与 token 切片取**双重上界**，见 change 0115/ADR-0108）

    def run(self, user_input: str, *, session_id: str = "") -> LoopResult:
        trace_id = new_trace_id()
        ctx = self.perceive(user_input)          # 拼上下文（有上界）；记忆检索由 ContextEngine.assemble 承担
        while not ctx.done():
            action = self.reason(ctx)            # 模型决策
            if action.is_irreversible and not await self.approve(action):
                action = self.decline(action)    # 确认门拒绝（有审批通道则询问，无则 fail-closed）
            result = self.act(action, trace_id)  # 经 EffectTracker 记录
            if result.failed:
                self.rollback(trace_id)          # 回滚本轮
            ctx = self.observe(ctx, result)
        self.remember(
            trace_id, [*ctx.trajectory, {"reply": ctx.reply}], session_id=session_id,
            steps=_action_steps(ctx),
            failed=bool(limit_reason) or turn_failed, reason=limit_reason, task=_task_text(ctx),
        )  # 无行动不记忆；末条 reply 供语义检索；条目带 source 命名空间与会话归属；
           # 行动序列另立一条（0173/ADR-0164）；轮级失败再另立一条（0179/ADR-0170）
        # 收尾维护节拍：距上次维护达 maintenance_interval 才触发一次——①记忆遗忘 ②冷路径机会（各自失败降级）
        return LoopResult(reply=ctx.reply, trace_id=trace_id)
```

---

## 2. 核心数据结构

以下为伪代码最小契约，字段实现可扩展：

```python
@dataclass
class LoopResult:
    reply: str                  # 最终回复
    trace_id: str               # 本轮追溯 ID（贯穿日志/效应/记忆）
    failed: bool = False        # 成败信号（目标未达成/异常终止/预算耗尽/推理产出不可用）
    raw_output: str = ""        # 推理产出不可解析时的**原始文本**（有界；缺省空）。仅供呈现层
                                # 折叠查看与 trace 留痕，SHALL NOT 进转录/记忆/笔记（change 0170 / ADR-0161）

@dataclass
class LoopEvent:
    type: str                   # loop_started / action_started / action_completed /
                                # step_completed / reply_delta / loop_finished / loop_failed /
                                # loop.reasoning（推理原文增量，见 §2.1）
                                # 动作事件仅非终止动作产出：started(round/tool_id/args 节选)、
                                # completed(round/tool_id/ok/duration_ms/output 节选，≤400 字符)
    payload: Any                # 事件负载（delta token / step 结果 / 终态原因 / {"text": 思考增量}）

@dataclass
class LoopContext:
    messages: list[Message]     # 本轮消息流
    tools: list[ToolSchema]     # 可调用工具 schema
    trajectory: list[Step]      # 本轮轨迹（供 Remember 写入）
    reply: str = ""
    notes: str = ""             # 任务前 Consult 摘要（文档化记忆；缺省空 ⇒ 不注入）
    pinned_notes: str = ""      # 常驻（pinned）笔记注入块：任务级硬约束锚，**每轮无条件**
                                # （与 query 命中无关；独立字段、与 ``notes`` 分列成块；change 0149）
    session_id: str = ""        # 本轮会话标识（缺省空串 = 未归属）；推理期检索/技能路由的归属维度
    history: list[Message] = field(default_factory=list)
                                # 本会话**既往**轮次的 (user, assistant) 对（转录回灌；缺省空 ⇒ 不回灌）
                                # **独立字段**：SHALL NOT 前置进 ``messages``——后者首位被四处 accessor
                                # 当「本轮任务」（change 0115 / ADR-0108 决策③）
    summary_long: str = ""      # 分层历史的**长期**摘要（会话整体摘要；缺省空 ⇒ 不注入）
                                # **独立字段**：SHALL NOT 折入 ``messages`` / ``history``（change 0178 / ADR-0169）
                                # 门控**不**受 ``loop.history_turns`` 连坐：``history_turns=0``（关原文回放）
                                # 时历史带为空，但已有摘要照常注入（change 0194 / ADR-0184 / 账本 E131）
    summary_mid: str = ""       # 分层历史的**中期**摘要（中带滚动摘要；缺省空 ⇒ 不注入）
                                # 注入次序：常驻笔记 → 历史摘要（长期）→ 历史摘要（中期）→ 相关事实…

    def done(self) -> bool:
        """推理判定可结束本轮时返回 True。"""

@dataclass
class Action:
    is_irreversible: bool       # True → 触发确认门
    failed: bool = False        # **仅对终止动作有意义**：推理产出不可用（解析失败/模型调用失败）
                                # ⇒ 本轮记为失败，不再与「正常收尾」无从区分（change 0166 / ADR-0156）
                                # 非终止动作（工具调用）**不用**本字段：工具失败属 ReAct 自愈面
    raw_output: str = ""        # **仅对终止动作有意义**：原始产出的**有界**留存（change 0170 / ADR-0161）
                                # SHALL NOT 并入 ``reply``（后者只放可读提示）/ 写入转录 / 记忆 / 笔记
```

### 2.1 思考回显通道（`Thinking` / `loop.reasoning`，change `0145` / ADR-0137 / 账本 E57~E58）

规划器 `astream` 的产出 item 除既有的 `str`（回复增量）与 `Action`（终态动作）外，**新增**第三类：

```python
@dataclass(frozen=True)
class Thinking:
    delta: str                  # 推理原文增量（provider 归一化后的 ``thinking``）
```

**为何新增类型而非「带标记的 str」**：`astream` 既有两类 item 承载**互斥语义**（回复增量 vs 终态
动作）；若用带标记的字符串表达思考，会污染既有判据（`content.startswith("{")` 的工具调用嗅探、
`reply_stream` 判定）。新增 frozen dataclass 使 `isinstance` 分流**显式无歧义**，且 `default.py`
的 `str` / `Action` 分支逐字不动。

事件面：`DefaultLoop._reason_events` 把 `Thinking(delta)` 转 `LoopEvent("loop.reasoning",
{"text": delta})`。语义约定（红线）：

- **开关驱动**：仅当 `LLMPlanner(show_thinking=True)` 时产出 —— 缺省关（`False`）时事件面与既有
  缺省**逐字一致**（零 `loop.reasoning`）。
- **非流式路径一并支持**：provider 无 `astream` 走降级分支时，终态思考以**一次性全文**先行外发
  （先 `Thinking` 后 `Action`）。
- **不吞终态补发**：`astream` 的 `streamed` 判据**只认** `reply_delta`，思考事件**不**参与
  「是否已流式」判定 —— 否则终态全文补发会被吞掉（用户只看到半句）。
- **不进持久面**：思考原文 **SHALL NOT** 进转录 / 记忆 / 日志 / 事件持久化（守 change `0115`
  边界）；**SHALL NOT** 进 `scheduler._PROGRESS_FIELDS` 白名单、**不外发**子任务回流通道
  —— 由「**只**主 planner 注入 `show_thinking`」天然保证。

阶段方法签名（私有，但为策略替换点）：

```python
def perceive(self, user_input: str, *, session_id: str = "") -> LoopContext
def reason(self, ctx: LoopContext) -> Action
def act(self, action: Action, trace_id: str) -> ActionResult   # 经 EffectTracker.record
def observe(self, ctx: LoopContext, result: ActionResult) -> LoopContext
def remember(self, trace_id: str, trajectory: list[Step], *, session_id: str = "",
             steps: Sequence[str] = (), failed: bool = False,
             reason: str = "", task: str = "") -> None
    # 轨迹项 {round, ok, error} 渲染为可读行；末条 {reply} 提供可检索正文
    # steps 非空 ⇒ 另立 `loop.steps.<trace_id>`（change 0173 / ADR-0164）
    # failed 为真 ⇒ 再另立 `loop.failure.<trace_id>`（change 0179 / ADR-0170，见 §3.2）
```

---

## 3. 四阶段职责

| 阶段 | 方法 | 职责 | 硬约束 |
|---|---|---|---|
| Perceive | `perceive` | 收集状态，拼上下文包 | token 有硬上界，按优先级裁剪 |
| Reason | `reason` | 调用模型决策下一步动作 | 非法动作回传结构化错误，不中断 |
| Act | `act` | 执行动作，经 EffectTracker 记录 | 可回滚；不可逆操作过确认门 |
| Remember | `remember` | 写本轮轨迹/教训入 L2/L3 | **每轮必做**（无行动不记忆） |

### 3.1 推理输出的四形态与失败可见（planner，change `0166` / `0170` / ADR-0156 / ADR-0161）

`LLMPlanner` 把模型输出解析为 `Action`，**形态五选**（判据一律只到「含非空 `tool_id`」，
参数校验的单一真源仍在工具调用链，解析层不写第二份）：

| 输入形态 | 解析结果 | 失败态 |
|---|---|---|
| 纯 JSON 对象（首字符 `{`） | `_from_dict` ⇒ 动作 / 回复 | 解析失败 ⇒ `failed=True` |
| 原生 `tool_calls` | `_from_tool_calls`（**优先于** content 协议） | 缺 `function.name` / 参数非对象 ⇒ `failed=True` |
| 自然语言回复（**含尾部动作 JSON**） | 正文 + **收在文末**的 JSON 对象（其后仅剩空白与 Markdown 围栏符）且含非空 `tool_id` ⇒ 转动作；否则整段为回复 | 解析失败 ⇒ `failed=True` |
| **未闭合的动作载荷**（尾部有**到内容结束仍未闭合**的 `"tool_id"` 结构，change `0170`） | **失败态终止动作** ⇒ `reply` 为可读提示，SHALL NOT 把原文当回复 | 命中即 `failed=True` |
| **夹带的动作 JSON**（**非尾部**处有**已闭合**的含非空 `tool_id` 对象、其后仍有正文，change `0222`） | **失败态终止动作** ⇒ `reply` 为可读提示，SHALL NOT 执行、SHALL NOT 当回复 | 命中即 `failed=True` |

- **尾部优先、夹带失败（change `0222` / ADR-0212）**：**收在文末**的动作 JSON ⇒ 工具动作（形态 3）；
  **非尾部**、**已闭合**且含非空 `tool_id` 的动作 JSON ⇒ **可见失败**（形态 5）—— **取代** ADR-0156
  「正文中间夹带一律按回复」的语义（旧语义把完整动作协议 + 尾随正文整段当答复 ⇒ **静默零执行**）。
  正文中夹带**无** `tool_id` 的示例 / 配置 JSON ⇒ 仍按回复（不误伤解释）。
- **形态 4 判据（严格）**：自**最后一次**出现的 `"tool_id"` 回退至其外层 `{`，做**字符串感知**的
  括号深度扫描（见 `_never_closes`）；深度**从未**回到 0 即命中。**闭合**的尾部对象 —— 不论其后是否
  仍有正文、是否含 `tool_id` —— 一律**不**命中。（动机：外层动作被截断时，尾部最末一个「可解析且其后
  无剩余」的对象往往是它的**内层 `args`** ⇒ 承 0166 的兜底会把整段 JSON 当回复且记为**成功**。）
- **失败可见**：`_parse` 各 `LLM_PLAN_PARSE_FAILED` 分支与两处 `LLM 调用失败: {exc}` 均置
  `Action.failed=True` ⇒ `act()` 终止分支透出 ⇒ `trajectory.ok` / `step_completed.failed` /
  `_notify_turn(ok=…)` / `LoopResult.failed` 四处同口径。
- **原始产出可诊断（change `0170` / `0222`）**：「首字符 `{` 解析失败」、「形态 4」与**形态 5** 三类失败态终止动作 SHALL
  另带**有界**原始产出（`Action.raw_output` → `LoopResult.raw_output`；上界 `_RAW_OUTPUT_MAX`，超出即
  截断）。该产出 SHALL NOT 写入转录 / 记忆 / 笔记，SHALL NOT 并入 `reply`（`reply` 为可读提示）；
  TUI 折叠呈现（见 `ui-interface.md` §2）。**成因措辞**（形态 4）：provider 报 `finish_reason="length"`
  ⇒ 提示明示**被截断**；信号不可用 ⇒ **未闭合（疑似截断或写坏）**；二者**失败语义相同**。
- **不改终止语义**：解析失败**照旧以回复收尾**（`loop_failed` 仍**只**由 `limit_reason` 触发），
  变的只是**成败核算**；合成文案仍进转录（既有口径），转录追加逻辑零改动。
- **同族但不动**：审批拒绝 `decline()` 与 `pet/safety` 阻断属**审批**语义，不置 `failed`
  （不是「推理产出不可用」）。

### 3.2 记忆条目的三态：轨迹 / 行动序列 / 失败（change `0173` / `0179` / ADR-0164 / ADR-0170）

`remember` 一轮**至多**写三条 L2 条目，同 `trace_id`、同 `session_id`、同 `source`（一并可逆、归组一致）：

| 条目 | 触发 | `tags` | 内容 |
|---|---|---|---|
| `loop.<trace_id>` | 每轮（有轨迹行） | `["loop","trajectory"]` | 轨迹项渲染的散文（**含** `round N failed <error>` 行） |
| `loop.steps.<trace_id>` | `steps` 非空（本轮有工具动作） | `["loop","steps"]` | 行动与结果序列（每工具一行） |
| `loop.failure.<trace_id>` | `failed=True` | `["loop","failure"]` | 任务 + 原因 + 失败轮次 + 失败动作（`failure_digest`） |

- **轮级失败的判据**：`failed=bool(limit_reason) or turn_failed` —— 终止动作失败（`Action.failed`，
  见 §2 与 change 0166 / ADR-0156）、轮次或 token 预算终止（`limit_reason`）、推理产出不可解析。
  **轮内**自愈的工具失败**不**入（仍在 `loop.steps` 条目里）；**未失败 ⇒ 不写该条**（成功轮零扰动）。
- **内容纪律**：`failure_digest` 逐行 `redact_secrets`、整体 ≤`_MAX_MEMORY_ENTRY`(2048)，
  首行 `任务：` 有界 `_MAX_STEP_LINE`；`reason` 空 ⇒ 恒定兜底文案。
  **`LoopResult.raw_output` 不入**本条（ADR-0161 明文禁入面，失败条目不得成为旁路）。
- **下游语义**：`failure` 标签使**压实材料排除**该条（见 `memory-interface.md`）⇒ 不被摘成中性总结、
  不被迁 L4；但**遗忘不豁免**（仍按自然衰减归档，有界）。注入面**零改动**：失败条目靠既有按相关度检索命中。

---

## 4. 约束

- 上下文有上界：注入按优先级裁剪（L0 元规则 > 本轮消息 > L1 索引 > L3 技能 > L2 事实），**绝不允许把整个记忆塞进上下文**。
- 行动可回滚：每个 action 经 `EffectTracker.record` 落 undo 栈；失败即回滚并写记忆。
- 不可逆/高风险操作（rm、写系统、杀进程、支付）→ 触发 `ask_user` 确认门，拒绝则改写安全动作或终止。
- 可观测：每轮生成 `trace_id`，单轮可复现（NFR-OBS2）。
- 连续 N 轮失败 → 触发 L4 诊断钩子，暂停并请求人工介入。
- 预算/**工具步数**达阈值 → 触发压实（注入 `context.Compactor` 时）：多轮历史提炼沉淀（`persist`）
  → 记忆固化（`memory.compact`：打分写回 + 价值门控 + 会话摘要归档）→ 遗忘（`memory.forget`：
  低分条目迁 L4 归档）；任一步失败降级不中断本轮（记 `maintenance_failed`），**终止语义不变**
  （仍按既有预算/轮数条件终止，不因压实而续跑）。压实触发口径（change 0182 / ADR-0173）：
  第一维度是**本轮工具步数**（`ctx.rounds`，每用户轮自 `0` 起算，**非**对话轮数）达
  `loop.compact_steps`（缺省 `6`），第二维度是 token 达预算；**每轮至多压实一次**（本轮标记）。
- 收尾/维护的执行线程（change 0167 / ADR-0157）：**轮内压实**、**收尾钩子**（`turn_observer`）、
  **维护节拍**（含 `cold_path`）三段工作 SHALL 在**事件循环之外**执行（循环以 `asyncio.to_thread`
  卸载并 `await` 其完成），SHALL NOT 在事件循环线程上同步执行 —— 这三段可能含**同步模型调用**
  （组合根注入的 `_llm_text` 接缝；同步形态 `LLMProvider.completion()` 以 `asyncio.run` 桥接、
  在运行中循环上必抛 `RuntimeError`），且其耗时为模型网络往返（秒级，会阻塞其余任务）。
  卸载 SHALL NOT 改变：三段各自的失败降级语义、触发条件、产物与终态、各注入接缝的**同步契约**
  （`turn_observer` / `cold_path` / `summarizer` / `key_fact_extractor` 仍为同步 callable）——
  换的是执行线程，不变的是接口与语义。
- 技能注入：`LLMPlanner` 每轮推理前调注入的 `skill_router(task) -> list[SkillHint]`，把命中技能
  渲染进 system prompt 的技能块——`- <skill_id>（<版本>）：<instructions 节选>`（步骤为空只留
  `id（版本）`）。`SkillHint` 是**纯 dict**（`skill_id` / `version` / `instructions`），loop 不
  import skills（架构红线）；未注入或未命中时 prompt 不含技能块。
- 横切中间件双接缝：①**动作前链** `middlewares`（`(LoopContext, Action) -> Action | None`）——按注册序执行，
  返回 `None` 即拒绝短路（记入已拒绝回复、本轮终止），返回 Action 则放行/改写；
  ②**结果侧观察者** `action_observers`（`(LoopContext, Action, ActionResult) -> None`）——每个**非终止**
  动作完成后按注册序回调，**仅通知**：单个观察者抛出降级留痕（记 `action_observer_failed`），
  **不改变本轮结局与终止语义**；终止动作（空 `tool_id`）不触发。二者缺省为空 = 零行为变化；
  生产接线（按 `tool_id` 隔离熔断）见 `constraints-interface.md` §7 与 ADR-0055。
- 收尾钩子：每轮收尾调注入的 `turn_observer(task, steps, ok)`——**成功与失败都提交**（`ok=False`
  即超限终止轮，失败信号供技能迭代判据），由组合根分发到技能反馈与 SOP 提炼
  （`SopExtractor.observe` 仍只吸收成功，见 `skills-interface.md §6`）；钩子抛错降级留痕
  （记 `turn_observer_failed`），不改变本轮结果与终止语义；未注入钩子时行为完全不变。
  `steps` 为**人类可读**的行动/结果序列（change 0171 / ADR-0162）：每个工具动作一行
  「工具名（有界参数摘要）→ 有界结果节选」，**不落** ReAct 消息原文（`{"tool_id":…}` / `{"data":…}`
  JSON 转储）与整篇工具输出；**纯文字回复轮为空列表**（终止动作不产生行动消息）——下游写回侧据此
  判「有无行动」。签名 / 调用点 / 降级链**逐字不变**，仅 `steps` 内容渲染改变。
- trace 完成回调：本轮**全部遥测记录完毕之后**按轮调 `trace_observer(trace_id)`（**不随维护节拍节流**，
  与 `cold_path` 是两个独立节律：前者按轮、后者按 `maintenance_interval`）；回调抛错降级留痕
  （记 `trace_observer_failed`），不改变本轮结果与终止语义；未注入时行为完全不变。
  生产接线为 `EvolutionWorker.on_trace_complete`（在**封口前**取事件快照自持，见下条）。
- trace 生命周期：循环**驱动** trace 生命周期——**开轮**调注入 tracer 的 `start_trace` 取回贯穿全链路的
  `trace_id`（未注入 tracer 时回退本地 uuid，行为一致）；**收尾**在 trace 完成回调**之后**调
  `end_trace(trace_id)` **封口**（交付导出器 + 释放内存）。收尾顺序 SHALL 为
  「记录本轮全部遥测 → trace 完成回调 → `end_trace` 封口」，**反序**会让回调回放空链路（静默失效）。
  见 ADR-0096。
- 模块归因：循环**自身失败**（轮数/token 预算耗尽）时其 `loop_finished` 遥测事件带
  `module_id="loop.default"`；正常收尾缺省为空（不产虚假缺陷证据）。见 ADR-0094。
- 会话历史回灌与转录（change 0115 / ADR-0108，`session_id` 非空时）：`perceive` 先按**双重上界**
  `min(history_turns, token_budget // 2)` 从会话转录取既往轮次装入 `ctx.history`（记账口径见下条），
  **再**落本轮 user 行；请求组装次序 SHALL 为
  「系统提示 → `history` → 本轮 `messages`」；收尾在 `remember` **之前**追加本轮
  (user 原话, 最终回复)——**终止轮（`limit_reason` 非空）不落 reply**（此时 `ctx.reply` 是合成串，
  落盘即谎报模型原话）。转录读写各自 `try/except` 降级（`warnings.warn`），不阻断主流程。
  `session_id == ""`、未注入转录、`history_turns == 0` ⇒ 零写入零回灌（逐字向后兼容）。
- token 记账口径（change 0152 / ADR-0144）：`token_used` SHALL **覆盖装配进本轮提示词的全部内容**
  —— 回灌历史 + 本轮消息（含动作 / 观察回灌）+ planner 装配的系统提示与工具 schema（后者经
  `LLMPlanner.last_prompt_tokens()` 探针以 **duck-typing** 消费，与 `astream` 同型；planner 未暴露
  该探针 / 探针异常 ⇒ 退化为纯估算，不阻断本轮）；记账值 SHALL NOT 低于 provider 实报的
  `usage.prompt_tokens`（实测权威作**下界**；不可用 —— 如流式响应不携带用量 —— 时按装配全量估算）。
  口径 SHALL NOT 改变阈值语义（预算终止与压实同取 `token_budget`）与窗口派生规则，且不引入
  第三方 tokenizer。见 ADR-0144。
  **流式路径同口径**（change 0183 / ADR-0174）：provider 在流式**末块**上报用量时，`astream`
  在循环体首行消费（早于 `content` 空判 —— 用量块 `content` 为空）并取**较大者**抬升下界；若端点
  未上报（`LLMChunk.usage is None`）则维持估算。`completion_tokens` 经 `last_completion_tokens()`
  同型探针暴露，**仅观测**、不参与任何判定。
- 请求侧输出上限（change 0183 / ADR-0174）：`LLMPlanner(max_tokens=…)` 为构造期注入点，由组合根按
  `loop.output_reserve` 注入；`> 0` ⇒ 每次请求携带 `LLMRequest.max_tokens`（provider 下发
  `max_tokens`），`None` / `≤ 0` ⇒ 不下发（请求形状逐字不变）。

---

## 5. 关联

- 模块：`02-modules/loop.md`
- 规格：`openspec/specs/loop/spec.md`
- 记忆：`memory-interface.md`
- 进化（L4 只读观测 L3）：`evolution-interface.md`
- 测试：`04-testing/test-cases.md`（LOOP 系列）
