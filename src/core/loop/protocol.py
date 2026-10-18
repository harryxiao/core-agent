"""智能体循环接口协议（L3 Loop）。

把 doc/03-interfaces/loop-interface.md 的接口契约提炼为 typing.Protocol：
LoopPlugin 声明同步 run / 异步 arun / 流式 astream 三入口 + 阶段方法
（perceive / reason / act / observe / remember），DefaultLoop 为默认实现。

对应规格：doc/openspec/specs/loop/spec.md
模块设计：doc/02-modules/loop.md
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Protocol, cast, runtime_checkable

# 当前动作所属会话（change 0247 / ADR-0235）：`DefaultLoop` 在每次 `_act` 调用前后
# set/reset；工具处理器（如 `tools.delegate`）由此把发起会话转交子 Agent。
# 缺省空串 = 未归属（与 `arun(..., session_id="")` 同口径）。
current_session_id: ContextVar[str] = ContextVar("current_session_id", default="")

# 当前轮 trace（change 0269）：`DefaultLoop.astream` 在整轮迭代期间 set/reset，
# 供组合根注入的钩子中间件 / 观察者取 trace_id 落 `kind="hook"` 遥测。
current_trace_id: ContextVar[str] = ContextVar("current_trace_id", default="")


@dataclass
class LoopResult:
    """一轮闭环的最终产物。"""

    reply: str  # 最终回复
    trace_id: str  # 本轮追溯 ID（贯穿日志/效应/记忆）
    failed: bool = False  # 成败信号：目标未达成/异常终止/预算耗尽为 True
    # 推理产出不可解析时的**原始文本**（有界；缺省空）。仅供呈现层折叠查看与 trace 留痕，
    # SHALL NOT 进入转录 / 记忆 / 笔记（见 change 0170 / ADR-0161）。
    raw_output: str = ""


@dataclass
class LoopEvent:
    """执行生命周期事件（loop_started/step_completed/reply_delta/loop_finished/loop_failed）。"""

    type: str
    payload: Any = None


@dataclass
class LoopContext:
    """一轮循环中的上下文包（token 有硬上界）。"""

    messages: list[Any] = field(default_factory=list[Any])
    tools: list[Any] = field(default_factory=list[Any])
    trajectory: list[Any] = field(default_factory=list[Any])
    reply: str = ""
    rounds: int = 0
    token_used: int = 0
    notes: str = ""  # 任务前 Consult 摘要（文档化记忆；缺省空 ⇒ 不注入。见 change 0106）
    # 常驻（pinned）笔记注入块：任务级硬约束锚，**每轮无条件**（不依赖 query 命中；见 0149）。
    # **独立字段**：不得折入 `notes` —— 二者是两条通道（命中面 vs 常驻面），分列成块。
    pinned_notes: str = ""
    session_id: str = ""  # 本轮会话标识（缺省空串 = 未归属）；推理期检索/技能路由的归属维度
    # 本会话最近历史对话（「用户原话 / 最终回复」成对；缺省空 ⇒ 不回灌）。
    # **独立字段**：不得前置进 `messages` —— 后者首条被当「本轮任务」、其后被当动作序列。
    history: list[Any] = field(default_factory=list[Any])
    # 分层历史的**长期摘要**（会话整体摘要；缺省空 ⇒ 不注入）。见 change 0178 / ADR-0169。
    # **独立字段**：不得折入 `history` / `messages` —— 摘要是压缩产物，非原文回灌。
    summary_long: str = ""
    # 分层历史的**中期摘要**（紧邻短带之前的中带滚动摘要；缺省空 ⇒ 不注入）。
    summary_mid: str = ""
    # 该会话的**既往失败教训**块（按会话、`ts` 降序取用；缺省空 ⇒ 不注入）。
    # **独立字段**：不得折入 `notes` / `summary_*` —— 失败教训的语义与命中笔记、压缩摘要均不同，
    # 折入会改既有块的语义（见 change 0217 / ADR-0207）。
    failure_lessons: str = ""
    # 本轮 token 预算（缺省 `0` = **未接线**）。唯一消费者是 planner 的区块配额
    # （`context.plan_blocks`）⇒ 推断期把「记忆」份额传给装配器 `build(budget=…)`。
    # 缺省 `0` ⇒ 不产出配额 ⇒ planner 沿用其既有字面预算（change 0201 / ADR-0191）。
    token_budget: int = 0
    _done: bool = field(default=False, repr=False)

    def done(self) -> bool:
        """推理判定可结束本轮时返回 True。"""
        return self._done

    def finish(self) -> None:
        """标记本轮可结束（供循环实现写入）。"""
        self._done = True


@dataclass(frozen=True)
class Thinking:
    """推理原文增量（change `0145` / ADR-0137 / 账本 E57）。

    planner 流式协议中与 ``str``（回复增量）、``Action``（终态动作）**并存**的第三类
    item：仅在思考回显开启时外发，转 ``loop.reasoning`` 事件供三端折叠呈现 —— **纯呈现层**，
    不进转录 / 记忆 / 日志 / trace，亦不经子任务运行态回流。
    """

    delta: str


@dataclass
class Action:
    """模型决策的下一步动作；tool_id 为空串表示本轮结束（终止动作）。

    ``failed`` **仅对终止动作有意义**：推理产出**不可用**（解析失败 / 模型调用失败）时置位，
    供循环把本轮记为失败。缺此标记时，这类终止动作与正常回复无从区分 ⇒「没执行」会被
    静默记成成功（见 change 0166 / ADR-0156）。非终止动作（工具调用）不用本字段。

    ``raw_output`` 亦**仅对终止动作有意义**：推理产出的**原始文本**（有界，见 change 0170 /
    ADR-0161），供呈现层折叠查看与 trace 留痕；SHALL NOT 并入 ``reply``（后者只放可读提示），
    SHALL NOT 写入转录 / 记忆 / 笔记。
    """

    tool_id: str = ""
    args: dict[str, Any] = field(default_factory=dict[str, Any])
    is_irreversible: bool = False
    failed: bool = False
    raw_output: str = ""

    @property
    def is_terminal(self) -> bool:
        return not self.tool_id


@dataclass
class ActionGroup:
    """一次推理产出的**多个**工具动作（change 0257 / ADR-0248）。

    planner 仅在原生 ``tool_calls`` 多于一个时返回本类型（按 provider ``index`` 升序）；
    单调用仍返回 :class:`Action`，既有协议消费方逐字不变。循环把组内动作**按序串行**
    送入既有单动作执行体（中间件 / 确认门 / 观测 / 事件 / 压实阈值逐动作生效）。
    """

    actions: list[Action] = field(default_factory=list[Action])


@dataclass
class ActionResult:
    """动作执行结果。"""

    failed: bool = False  # True → 回滚本轮
    data: Any = None
    error: str = ""
    # 执行耗时（毫秒；change 0269）：loop 在提交阶段写入，供结果侧观察者（tool.after 钩子）
    # 读取。缺省 0 ⇒ 既有构造逐字不变。
    duration_ms: int = 0


class ActFn(Protocol):
    """动作执行接缝（`DefaultLoop.act` 可被可选 wrapper 包裹；change 0209 / ADR-0199）。"""

    async def __call__(
        self, action: Action, trace_id: str, *, approved: bool = False
    ) -> ActionResult:
        """执行一个动作，返回结构化结果。"""
        ...


class LoopPlugin(Protocol):
    """Loop 插件接口（策略替换点：ReAct / Plan-Execute / 自定义）。

    装配依赖（coeffects）：模型适配器 + 记忆存储 + 工具提供者 + 元规则。
    """

    plugin_id: str = "loop.default"
    coeffects: list[str] = [
        "model:adapter",
        "memory:store",
        "tools:provider",
        "constitution:v1",
    ]

    def run(self, user_input: str, *, session_id: str = "") -> LoopResult:
        """同步执行入口：经事件循环桥接 arun（薄壳），调用方零改动。"""
        ...

    async def arun(self, user_input: str, *, session_id: str = "") -> LoopResult:
        """异步执行入口：与 run 同构，事件循环内非阻塞。"""
        ...

    # 声明为**异步生成器**（stub 形式：`def` 返回 `AsyncIterator`）——与实现（`async def` + `yield`）
    # 的调用形态一致：`astream(...)` 直接产出可 `async for` 的事件流，**不是**待 await 的协程。
    def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        """流式执行入口：按生命周期顺序产出 LoopEvent 事件流。

        ``session_id`` 为本轮的会话归属（缺省空串 = 未归属），随调用传递、不驻留实例。
        """
        ...

    # ---- 阶段方法（私有，但为策略替换点）----

    def perceive(self, user_input: str, *, session_id: str = "") -> LoopContext:
        """收集状态，拼上下文包（token 有硬上界，按优先级裁剪）。

        ``session_id`` 非空时载入该会话最近历史（受轮数与 token 双重上界）进
        `LoopContext.history`，并把历史 token 计入本轮记账。
        """
        ...

    async def reason(self, ctx: LoopContext) -> Action | ActionGroup:
        """调用模型决策下一步动作（非法动作回传结构化错误，不中断）。"""
        ...

    def act(self, action: Action, trace_id: str) -> ActionResult:
        """执行动作，经 EffectTracker 记录（可回滚；不可逆操作过确认门）。"""
        ...

    def observe(self, ctx: LoopContext, result: ActionResult) -> LoopContext:
        """把动作结果写回上下文，推进循环。"""
        ...

    def remember(  # noqa: PLR0913 — 注入面均为可选 keyword-only（缺省 ⇒ 逐字一致）
        self,
        trace_id: str,
        trajectory: list[Any],
        *,
        session_id: str = "",
        steps: Sequence[str] = (),
        failed: bool = False,
        reason: str = "",
        task: str = "",
    ) -> None:
        """写本轮轨迹/教训入 L2/L3（每轮必做，无行动不记忆），条目带会话归属。

        ``steps`` 非空 ⇒ **另立一条**条目承载本轮行动与结果序列（change 0173），
        轨迹条目内容逐字不变；缺省空 ⇒ 行为与变更前逐字一致。

        ``failed`` 为真 ⇒ **再另立一条** ``loop.failure.<trace_id>`` 承载**轮级**失败
        （任务 + ``reason`` + 失败轮次与失败动作；change 0179）；该条目带 ``failure`` 标签，
        压实材料据此**排除**它。三者缺省 ⇒ 行为与变更前逐字一致。
        """
        ...


@runtime_checkable
class LimitsConfigurable(Protocol):
    """可运行期调整预算上限的 loop（change `0099`）。

    能力探测协议：`UIAPILayer` 保存 LLM 配置后按本协议把派生上限推给**运行中**的 loop，
    **不**把 UI 层焊死在 `DefaultLoop`（本仓策略插件可替换）。不支持者静默跳过。
    """

    def set_limits(
        self,
        *,
        max_rounds: int | None = None,
        token_budget: int | None = None,
        history_turns: int | None = None,
    ) -> None:
        """改上限（``None`` = 保持该项）；各值在每轮读取处生效 ⇒ 赋值即下次生效。"""
        ...


async def collect_result(
    stream: AsyncIterator[LoopEvent],
    on_event: Callable[[LoopEvent], None] | None = None,
) -> LoopResult:
    """驱动事件流：逐事件回调（``on_event``，可选），返回**归一化终态** `LoopResult`。

    「三态归一」语义的**唯一实现**（`DefaultLoop.arun` 即其薄壳；编排层消费子 Agent 事件流时
    复用同一实现，避免两处语义漂移）：

    - `loop_finished` 的载荷即终态结果；
    - `loop_failed` 归一为 `failed=True` 且回复取失败原因；
    - 流未给终态（异常实现）⇒ 不抛，返回 `failed=False` 的空回复（保持 `arun` 既有语义）。
    """
    reply = ""
    trace_id = ""
    failed = False
    async for event in stream:
        if on_event is not None:
            on_event(event)
        if event.type == "loop_started":
            trace_id = str(event.payload.get("trace_id", ""))
        elif event.type == "loop_finished":
            return cast(LoopResult, event.payload)
        elif event.type == "loop_failed":
            reply = str(event.payload.get("reason", "LOOP_FAILED"))
            failed = True
    return LoopResult(reply=reply, trace_id=trace_id, failed=failed)
