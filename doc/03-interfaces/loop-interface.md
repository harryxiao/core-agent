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

    def run(self, user_input: str) -> LoopResult:
        """执行一轮完整闭环：感知 → 推理 → 行动 → 记忆。"""

    async def arun(self, user_input: str) -> LoopResult:
        """异步执行入口：与 run 同构，事件循环内非阻塞，可并发驱动多个循环。"""

    def astream(self, user_input: str) -> AsyncIterator[LoopEvent]:
        """流式执行入口：按生命周期顺序产出 LoopEvent 事件流。"""
```

默认实现 `DefaultLoop`（骨架见 `02-modules/loop.md` 第 4 章）：

```python
class DefaultLoop(Plugin):
    coeffects = ["model:adapter", "memory:store", "tools:provider", "constitution:v1"]

    def run(self, user_input: str) -> LoopResult:
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
        self.remember(trace_id, [*ctx.trajectory, {"reply": ctx.reply}])  # 无行动不记忆；末条 reply 供语义检索
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
  → 记忆会话摘要归档（`memory.compact`）；压实失败降级不中断本轮，**终止语义不变**
  （仍按既有预算/轮数条件终止，不因压实而续跑）。

---

## 5. 关联

- 模块：`02-modules/loop.md`
- 规格：`openspec/specs/loop/spec.md`
- 记忆：`memory-interface.md`
- 进化（L4 只读观测 L3）：`evolution-interface.md`
- 测试：`04-testing/test-cases.md`（LOOP 系列）
