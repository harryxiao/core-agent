"""工具提供者（tool-use 核心）。

统一调用入口（invoke / ainvoke 同构）：schema 参数校验（口径委托
:class:`~core.constraints.Validator`，单一真源）→ coeffect 解析（缺失拒绝）→
确认门（不可逆/高风险阻止）→ 执行（超时保护）→ 写类工具效应记录（可逆撤销）；
回滚委托 :class:`EffectTracker` 按 trace 逆序撤销。

对应接口：doc/03-interfaces/tool-use-interface.md §2
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, cast

from core.constraints import Validator
from core.plugin_registry import (
    CoeffectMissing,
    CoeffectResolver,
    Effect,
    EffectTracker,
    RollbackReport,
)

from .errors import ToolErrorCode, ToolUseError
from .models import ToolDef, ToolError, ToolResult
from .safety_gate import SafetyGate
from .tool import Tool

# 审批回调：确认门判 confirm 时询问人工（tool_id, args, reason）→ 是否放行。
Approver = Callable[[str, dict[str, Any], str], Awaitable[bool]]


class ToolProvider:
    """工具注册与统一调用入口。"""

    def __init__(
        self,
        coeffect_resolver: CoeffectResolver | None = None,
        effect_tracker: EffectTracker | None = None,
        gate: SafetyGate | None = None,
        approver: Approver | None = None,
    ) -> None:
        self._resolver = coeffect_resolver if coeffect_resolver is not None else CoeffectResolver()
        self._tracker = effect_tracker if effect_tracker is not None else EffectTracker()
        self._gate = gate if gate is not None else SafetyGate()
        self._approver = approver
        self._tools: dict[str, Tool] = {}
        self._warnings: list[str] = []

    def register(self, tool: Tool) -> None:
        """注册工具：schema 非法拒绝；声明/行为不符记录告警。"""
        schema = cast(Any, tool.definition.schema)
        if not isinstance(schema, dict):
            raise ToolUseError(
                ToolErrorCode.INVALID_TOOL_SCHEMA,
                f"工具 {tool.definition.tool_id} schema 非法（须为 dict）",
            )
        if tool.undo is not None and not any("write" in c for c in tool.definition.coeffects):
            self._warnings.append(
                f"工具 {tool.definition.tool_id} 有撤销闭包却未声明写类 coeffect，待复核"
            )
        self._tools[tool.definition.tool_id] = tool

    def unregister(self, tool_id: str) -> None:
        """卸载工具：对称于 register；不存在静默忽略（卸载幂等）。"""
        self._tools.pop(tool_id, None)

    @property
    def warnings(self) -> list[str]:
        """声明/行为不符告警列表（遥测观测到偏差后待复核）。"""
        return list(self._warnings)

    def active_tools(self) -> list[ToolDef]:
        """返回当前已注册工具的定义列表（供 loop 注入）。"""
        return [tool.definition for tool in self._tools.values()]

    def subset(self, tool_ids: Iterable[str]) -> ToolProvider:
        """返回共享依赖的受限视图：只暴露 ``tool_ids`` 内工具（change 0313）。

        schema 面（``active_tools``）与执行面（``ainvoke``）同时受限：视图外工具按
        「未知工具」fail-closed。解析器 / 效应追踪 / 安全门 / 审批通道与本体共享，
        故审批与回滚语义不变；注册表本体不受视图影响。
        """
        allowed = frozenset(tool_ids)
        view = ToolProvider(
            coeffect_resolver=self._resolver,
            effect_tracker=self._tracker,
            gate=self._gate,
            approver=self._approver,
        )
        view._tools = {tool_id: tool for tool_id, tool in self._tools.items() if tool_id in allowed}
        view._warnings = list(self._warnings)
        return view

    def invoke(
        self, tool_id: str, args: dict[str, Any], *, trace_id: str, approved: bool = False
    ) -> ToolResult:
        """同步统一调用入口：经事件循环桥接 ainvoke。"""
        return asyncio.run(self.ainvoke(tool_id, args, trace_id=trace_id, approved=approved))

    async def ainvoke(  # noqa: PLR0911 — 调用管道天然多早退分支
        self, tool_id: str, args: dict[str, Any], *, trace_id: str, approved: bool = False
    ) -> ToolResult:
        """异步统一调用入口（非阻塞，支持真并发）。"""
        tool = self._tools.get(tool_id)
        if tool is None:
            return ToolResult(
                ok=False,
                error=ToolError(ToolErrorCode.INVALID_ARGS, f"未知工具: {tool_id}"),
            )

        err = self._validate_args(tool, args)
        if err is not None:
            return ToolResult(ok=False, error=err)

        coeffects = tool.definition.coeffects
        try:
            self._resolver.resolve(coeffects)
        except CoeffectMissing as exc:
            return ToolResult(ok=False, error=ToolError(ToolErrorCode.COEFFECT_MISSING, str(exc)))

        decision = self._gate.confirm(tool_id, args, coeffects, tool.definition.reversible)
        if decision.action == "deny":
            return ToolResult(ok=False, error=ToolError(ToolErrorCode.GATE_DENIED, decision.reason))
        if decision.action == "confirm" and not approved:
            # 上层未批准：经审批通道询问人工；无通道或被拒即 fail-closed
            human_approved = self._approver is not None and await self._approver(
                tool_id, args, decision.reason
            )
            if not human_approved:
                return ToolResult(
                    ok=False,
                    error=ToolError(ToolErrorCode.IRREVERSIBLE_BLOCKED, decision.reason),
                )

        try:
            result = await asyncio.wait_for(
                self._call(tool, args), timeout=tool.definition.timeout_s
            )
        except TimeoutError:
            return ToolResult(
                ok=False, error=ToolError(ToolErrorCode.TIMEOUT, f"工具 {tool_id} 执行超时")
            )
        except Exception as exc:  # noqa: BLE001 — handler 异常统一归一结构化错误
            return ToolResult(
                ok=False,
                error=ToolError(ToolErrorCode.EXECUTION_FAILED, f"工具 {tool_id} 执行失败: {exc}"),
            )

        effect_id: str | None = None
        if tool.undo is not None:
            effect_id = self._tracker.record(
                Effect(
                    op=tool_id,
                    target=str(args.get("path") or tool_id),
                    undo=tool.undo(),  # 按次取闭包：绑定**本次**调用写入前的快照（change 0129）
                    reversible=tool.definition.reversible,
                    coeffect=coeffects,
                    trace_id=trace_id,
                    ts=time.time(),
                )
            )
        return ToolResult(ok=True, data=result, effect_id=effect_id)

    def rollback(self, trace_id: str | None = None) -> RollbackReport:
        """回滚：按 trace 逆序撤销该轮效应（None 则全局回滚）。"""
        return self._tracker.rollback(trace_id)

    # ---- 内部辅助 ----

    def _validate_args(self, tool: Tool, args: dict[str, Any]) -> ToolError | None:
        """调用前 schema 校验：口径委托 constraints.Validator（单一真源，本层不另实现副本）。"""
        errors = Validator().validate_input(tool.definition.tool_id, args, tool.definition.schema)
        if errors:
            return ToolError(ToolErrorCode.INVALID_ARGS, errors[0])
        return None

    async def _call(self, tool: Tool, args: dict[str, Any]) -> Any:
        """执行 handler：协程在事件循环上 await，同步 handler 卸载到工作线程。

        同步 handler 直接调用会阻塞事件循环，使多个独立 `ainvoke` 无法真并发
        （change 0265）。`asyncio.to_thread` 不可取消：外层超时只停止等待。
        """
        if inspect.iscoroutinefunction(tool.handler):
            return await tool.handler(**args)
        result = await asyncio.to_thread(tool.handler, **args)
        if inspect.isawaitable(result):
            result = await result
        return result
