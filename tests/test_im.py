"""im 单元测试（对齐契约红线：平台路由 / 白名单 / 幂等去重 / 高危确认 / 六错误码兜底）。"""

from __future__ import annotations

import pytest

from core.im import ImError, ImErrorCode, IMGateway, Message, Session


class FakeProvider:
    """fake 平台 Provider：identity 透传 user_id，send 记录回推。"""

    platform = "telegram"

    def __init__(self) -> None:
        self.started = False
        self.sent: list[str] = []
        self.fail_send = False

    def start(self, gateway: IMGateway) -> None:
        self.started = True

    def send(self, session: Session, text: str) -> None:
        if self.fail_send:
            raise RuntimeError("socket closed")  # noqa: TRY003
        self.sent.append(text)

    def identity(self, msg: Message) -> str:
        return msg.user_id


def _msg(
    text: str = "hi",
    *,
    user_id: str = "u1",
    platform: str = "telegram",
    message_id: str = "",
) -> Message:
    return Message(platform=platform, user_id=user_id, text=text, message_id=message_id)


def _session() -> Session:
    return Session(session_key="telegram:u1", platform="telegram", user_id="u1")


# ---- 平台路由 / 白名单 ----


def test_unregistered_platform() -> None:
    gateway = IMGateway()
    with pytest.raises(ImError) as exc_info:
        gateway.on_message(_msg(platform="discord"))
    assert exc_info.value.code is ImErrorCode.IM_PLATFORM_UNSUPPORTED


def test_whitelisted_message_runs_session() -> None:
    ran: list[str] = []
    gateway = IMGateway(whitelist={"u1"}, run_session=lambda s, t: ran.append(t))
    gateway.register(FakeProvider())
    gateway.on_message(_msg(text="build"))
    assert ran == ["build"]


def test_non_whitelisted_rejected() -> None:
    gateway = IMGateway(whitelist={"u1"})
    gateway.register(FakeProvider())
    with pytest.raises(ImError) as exc_info:
        gateway.on_message(_msg(user_id="u2"))
    assert exc_info.value.code is ImErrorCode.IM_NOT_WHITELISTED


def test_duplicate_message_id_deduped() -> None:
    ran: list[str] = []
    gateway = IMGateway(whitelist={"u1"}, run_session=lambda s, t: ran.append(t))
    gateway.register(FakeProvider())
    gateway.on_message(_msg(text="a", message_id="m1"))
    gateway.on_message(_msg(text="a", message_id="m1"))
    assert ran == ["a"]


# ---- 高危确认 ----


def test_confirm_denied() -> None:
    gateway = IMGateway(whitelist={"u1"}, confirm=lambda s, p: False)
    with pytest.raises(ImError) as exc_info:
        gateway.approve(_session(), "rm -rf /")
    assert exc_info.value.code is ImErrorCode.IM_CONFIRM_DENIED


def test_confirm_timeout_no_channel() -> None:
    gateway = IMGateway(whitelist={"u1"})
    with pytest.raises(ImError) as exc_info:
        gateway.approve(_session(), "rm -rf /")
    assert exc_info.value.code is ImErrorCode.IM_CONFIRM_TIMEOUT


def test_confirm_approved() -> None:
    gateway = IMGateway(whitelist={"u1"}, confirm=lambda s, p: True)
    assert gateway.approve(_session(), "rm -rf /") is True


# ---- 回推 / 断线 ----


def test_reply_send_failed() -> None:
    provider = FakeProvider()
    provider.fail_send = True
    gateway = IMGateway()
    gateway.register(provider)
    with pytest.raises(ImError) as exc_info:
        gateway.reply(_session(), "hi")
    assert exc_info.value.code is ImErrorCode.IM_SEND_FAILED


def test_disconnected_platform() -> None:
    gateway = IMGateway(whitelist={"u1"})
    gateway.register(FakeProvider())
    gateway.disconnect("telegram")
    with pytest.raises(ImError) as exc_info:
        gateway.on_message(_msg())
    assert exc_info.value.code is ImErrorCode.IM_PLATFORM_DISCONNECTED
