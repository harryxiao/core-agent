"""IM 网关（im）：统一接入 + 消息驱动会话。

IMGateway 是 Plugin：register 注册平台 Provider，on_message 入站消息
映射为内核会话（identity → 白名单 → 幂等去重 → loop → 高危 approve →
reply）。高危确认复用 permission.ApprovalWorkflow。

对应接口：doc/03-interfaces/im-interface.md §1/§4/§5
"""

from __future__ import annotations

from collections.abc import Callable

from core.permission import ApprovalRequest, ApprovalResult, ApprovalWorkflow

from .errors import ImError, ImErrorCode
from .models import Message, Session
from .provider import IMProvider


class IMGateway:
    """IM 统一网关：多平台注册 + 消息驱动会话 + 白名单 + 高危确认。"""

    plugin_id = "im.gateway"
    generation = 1
    schema: dict[str, object] = {"type": "object"}
    coeffects: list[str] = []

    def __init__(  # noqa: PLR0913 — 注入面均为可选依赖注入
        self,
        *,
        whitelist: set[str] | None = None,
        run_session: Callable[[Session, str], str] | None = None,
        confirm: Callable[[Session, str], bool] | None = None,
        workflow: ApprovalWorkflow | None = None,
    ) -> None:
        self._providers: dict[str, IMProvider] = {}
        self._whitelist: set[str] = whitelist if whitelist is not None else set()
        self._run_session = run_session
        self._confirm = confirm
        self._workflow = workflow if workflow is not None else ApprovalWorkflow()
        self._sessions: dict[str, Session] = {}
        self._seen: set[str] = set()
        self._disconnected: set[str] = set()

    # ---- Plugin 生命周期 ----

    def load(self) -> None:
        return None

    def unload(self) -> None:
        return None

    def check(self) -> bool:
        return True

    # ---- 平台注册 / 生命周期 ----

    def register(self, provider: IMProvider) -> None:
        """注册平台 Provider，新增平台零侵入。"""
        self._providers[provider.platform] = provider

    def start(self) -> None:
        """拉起所有已注册 Provider。"""
        for provider in self._providers.values():
            provider.start(self)

    def disconnect(self, platform: str) -> None:
        """标记平台断线，触发熔断隔离；后续该平台入站消息抛 IM_PLATFORM_DISCONNECTED。"""
        self._disconnected.add(platform)

    # ---- 消息驱动会话 ----

    def on_message(self, msg: Message) -> None:
        """入站消息 → 会话事件 → 内核 loop 执行（消息驱动会话）。"""
        if msg.platform in self._disconnected:
            raise ImError(
                ImErrorCode.IM_PLATFORM_DISCONNECTED,
                f"平台 {msg.platform} 连接断开（熔断隔离）",
            )
        provider = self._providers.get(msg.platform)
        if provider is None:
            raise ImError(
                ImErrorCode.IM_PLATFORM_UNSUPPORTED,
                f"平台 {msg.platform} 无对应 Provider 适配器",
            )
        user_id = provider.identity(msg)
        if user_id not in self._whitelist:
            raise ImError(ImErrorCode.IM_NOT_WHITELISTED, f"非白名单用户 {user_id}，拒绝执行")
        if msg.message_id and msg.message_id in self._seen:
            return  # 重复消息幂等去重
        if msg.message_id:
            self._seen.add(msg.message_id)
        session = self._session_for(msg, user_id)
        if self._run_session is not None:
            self._run_session(session, msg.text)

    def reply(self, session: Session, text: str) -> None:
        """执行结果经 Provider 编码回推到来源会话。"""
        provider = self._providers.get(session.platform)
        if provider is None:
            raise ImError(
                ImErrorCode.IM_PLATFORM_UNSUPPORTED,
                f"平台 {session.platform} 无对应 Provider 适配器",
            )
        try:
            provider.send(session, text)
        except ImError:
            raise
        except Exception as exc:  # noqa: BLE001 — 平台回推异常归一到领域错误码
            raise ImError(ImErrorCode.IM_SEND_FAILED, f"回推失败: {exc}") from exc

    # ---- 高危确认 ----

    def approve(self, session: Session, prompt: str) -> bool:
        """高危操作 IM 内二次确认：拒绝 → IM_CONFIRM_DENIED；无确认通道 → IM_CONFIRM_TIMEOUT。"""
        if self._confirm is None:
            raise ImError(
                ImErrorCode.IM_CONFIRM_TIMEOUT,
                "高危操作确认超时（无人工确认通道，fail-closed）",
            )
        request = ApprovalRequest(
            op="im.confirm",
            target=session.session_key,
            impact_summary=prompt,
            rollback_plan="",
            trace_id=session.session_key,
        )
        ticket = self._workflow.create(request)
        if not self._confirm(session, prompt):
            self._workflow.archive(ticket)
            raise ImError(ImErrorCode.IM_CONFIRM_DENIED, "高危操作确认被拒绝")
        self._workflow.ask(ticket, approver=lambda _t: ApprovalResult(approved=True))
        return True

    # ---- 内部辅助 ----

    def _session_for(self, msg: Message, user_id: str) -> Session:
        key = msg.session_key or f"{msg.platform}:{user_id}"
        session = self._sessions.get(key)
        if session is None:
            session = Session(session_key=key, platform=msg.platform, user_id=user_id)
            self._sessions[key] = session
        session.history.append(msg.text)
        return session
