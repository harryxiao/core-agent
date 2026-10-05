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

        ``session_id`` 为本轮会话归属（缺省空串 = 未归属），随调用传递、不驻留实例，
        由「记忆」步写入 L2 条目的 ``session_id``（供压实/固化/遗忘按会话归组）。
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
            trace_id, [*ctx.trajectory, {"reply": ctx.reply}], session_id=session_id
        )  # 无行动不记忆；末条 reply 供语义检索；条目带 source 命名空间与会话归属
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

@dataclass
class LoopEvent:
    type: str                   # loop_started / action_started / action_completed /
                                # step_completed / reply_delta / loop_finished / loop_failed
                                # 动作事件仅非终止动作产出：started(round/tool_id/args 节选)、
                                # completed(round/tool_id/ok/duration_ms/output 节选，≤400 字符)
    payload: Any                # 事件负载（delta token / step 结果 / 终态原因）

@dataclass
class LoopContext:
    messages: list[Message]     # 本轮消息流
    tools: list[ToolSchema]     # 可调用工具 schema
    trajectory: list[Step]      # 本轮轨迹（供 Remember 写入）
    reply: str = ""

    def done(self) -> bool:
        """推理判定可结束本轮时返回 True。"""

@dataclass
class Action:
    is_irreversible: bool       # True → 触发确认门
```

阶段方法签名（私有，但为策略替换点）：

```python
def perceive(self, user_input: str) -> LoopContext
def reason(self, ctx: LoopContext) -> Action
def act(self, action: Action, trace_id: str) -> ActionResult   # 经 EffectTracker.record
def observe(self, ctx: LoopContext, result: ActionResult) -> LoopContext
def remember(self, trace_id: str, trajectory: list[Step]) -> None
    # 轨迹项 {round, ok, error} 渲染为可读行；末条 {reply} 提供可检索正文
```

---

## 3. 四阶段职责

| 阶段 | 方法 | 职责 | 硬约束 |
|---|---|---|---|
| Perceive | `perceive` | 收集状态，拼上下文包 | token 有硬上界，按优先级裁剪 |
| Reason | `reason` | 调用模型决策下一步动作 | 非法动作回传结构化错误，不中断 |
| Act | `act` | 执行动作，经 EffectTracker 记录 | 可回滚；不可逆操作过确认门 |
| Remember | `remember` | 写本轮轨迹/教训入 L2/L3 | **每轮必做**（无行动不记忆） |

---

## 4. 约束

- 上下文有上界：注入按优先级裁剪（L0 元规则 > 本轮消息 > L1 索引 > L3 技能 > L2 事实），**绝不允许把整个记忆塞进上下文**。
- 行动可回滚：每个 action 经 `EffectTracker.record` 落 undo 栈；失败即回滚并写记忆。
- 不可逆/高风险操作（rm、写系统、杀进程、支付）→ 触发 `ask_user` 确认门，拒绝则改写安全动作或终止。
- 可观测：每轮生成 `trace_id`，单轮可复现（NFR-OBS2）。
- 连续 N 轮失败 → 触发 L4 诊断钩子，暂停并请求人工介入。
- 预算/轮数达阈值 → 触发压实（注入 `context.Compactor` 时）：多轮历史提炼沉淀（`persist`）
  → 记忆固化（`memory.compact`：打分写回 + 价值门控 + 会话摘要归档）→ 遗忘（`memory.forget`：
  低分条目迁 L4 归档）；任一步失败降级不中断本轮（记 `maintenance_failed`），**终止语义不变**
  （仍按既有预算/轮数条件终止，不因压实而续跑）。
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

---

## 5. 关联

- 模块：`02-modules/loop.md`
- 规格：`openspec/specs/loop/spec.md`
- 记忆：`memory-interface.md`
- 进化（L4 只读观测 L3）：`evolution-interface.md`
- 测试：`04-testing/test-cases.md`（LOOP 系列）
