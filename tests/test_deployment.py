"""deployment 单元测试（对齐契约红线：连接生命周期状态机 / 升级回滚 / 健康探活恢复）。"""

from __future__ import annotations

import pytest

from core.deployment import (
    ClientConnection,
    CloudAdapter,
    DeploymentError,
    DeploymentErrorCode,
    DeployTarget,
    EnvironmentState,
    HarnessHost,
    HealthStatus,
    LifecycleController,
    ReleaseInfo,
    ReleaseManager,
    RuntimeConfig,
    RuntimeEnvironment,
    ServeStateStore,
)

# ---- Harness Host：连接生命周期状态机 ----


def test_host_accept_disconnect_isolation() -> None:
    host = HarnessHost()
    host.serve()
    first = host.accept(ClientConnection("alice"))
    host.accept(ClientConnection("bob"))
    host.disconnect(first.session_id)
    remaining = host.sessions()
    assert [session.client_id for session in remaining] == ["bob"]


def test_host_reap_timeout() -> None:
    now = [0.0]
    host = HarnessHost(clock=lambda: now[0])
    session = host.accept(ClientConnection("alice"))
    assert host.sessions() == [session]
    now[0] = 100.0
    assert host.reap(timeout=10.0) == [session.session_id]
    assert host.sessions() == []


def test_host_persists_sessions(tmp_path) -> None:
    host = HarnessHost(path=tmp_path / "sessions.jsonl")
    host.serve()
    first = host.accept(ClientConnection("alice"))
    host.accept(ClientConnection("bob"))
    host.disconnect(first.session_id)
    # 新进程（新实例）读同一文件：只见 bob 一个活跃会话
    reloaded = HarnessHost(path=tmp_path / "sessions.jsonl")
    assert [s.client_id for s in reloaded.sessions()] == ["bob"]


def test_serve_state_probe_liveness(tmp_path) -> None:
    live_pid = 42
    dead_pid = 99
    store = ServeStateStore(path=tmp_path / "serve.json", pid_alive=lambda pid: pid == live_pid)
    store.mark_running(pid=live_pid)
    assert store.probe().alive is True
    store.mark_running(pid=dead_pid)  # 死 pid
    assert store.probe().alive is False
    store.mark_stopped()
    assert store.probe().alive is False


# ---- 运行环境状态机 ----


def test_environment_configure_assemble_bootstrap() -> None:
    env = RuntimeEnvironment()
    env.configure(
        RuntimeConfig(kind="self-hosted", target=DeployTarget(host="pc", runtime="process"))
    )
    assert env.state is EnvironmentState.CONFIGURED
    env.assemble()
    env.bootstrap()
    assert env.state is EnvironmentState.BOOTSTRAPPED


def test_environment_bootstrap_before_assemble_not_ready() -> None:
    env = RuntimeEnvironment()
    with pytest.raises(DeploymentError) as exc_info:
        env.bootstrap()
    assert exc_info.value.code is DeploymentErrorCode.NOT_READY


# ---- 发布与升级：升级失败自动回滚 ----


def test_upgrade_failure_auto_rollback() -> None:
    alive = {"v1", "v2"}

    def apply(version: str) -> HealthStatus:
        return HealthStatus(alive=version in alive)

    manager = ReleaseManager(apply=apply)
    manager.publish(ReleaseInfo(version="v1", hash="h1"))
    manager.publish(ReleaseInfo(version="v2", hash="h2"))
    manager.publish(ReleaseInfo(version="v3", hash="h3"))
    manager.upgrade("v2")
    assert manager.current == "v2"
    with pytest.raises(DeploymentError) as exc_info:
        manager.upgrade("v3")
    assert exc_info.value.code is DeploymentErrorCode.UPGRADE_FAILED
    assert manager.current == "v2"  # 已自动回滚


def test_rollback_failure() -> None:
    def apply(version: str) -> HealthStatus:
        return HealthStatus(alive=version == "v2")

    manager = ReleaseManager(apply=apply)
    manager.publish(ReleaseInfo(version="v1", hash="h1"))
    manager.publish(ReleaseInfo(version="v2", hash="h2"))
    manager.upgrade("v2")
    with pytest.raises(DeploymentError) as exc_info:
        manager.rollback()
    assert exc_info.value.code is DeploymentErrorCode.ROLLBACK_FAILED
    assert manager.current == "v2"


def test_rollback_without_previous() -> None:
    with pytest.raises(DeploymentError) as exc_info:
        ReleaseManager().rollback()
    assert exc_info.value.code is DeploymentErrorCode.ROLLBACK_FAILED


def test_release_manager_persists_across_instances(tmp_path) -> None:
    path = tmp_path / "releases.json"
    manager = ReleaseManager(path=path)
    manager.publish(ReleaseInfo(version="v1", hash="h1"))
    manager.publish(ReleaseInfo(version="v2", hash="h2"))
    manager.upgrade("v2")
    # 新进程（新实例）读同一文件：版本登记跨进程可见，可回滚
    reloaded = ReleaseManager(path=path)
    assert reloaded.current == "v2"
    reloaded.rollback()
    assert reloaded.current == "v1"


# ---- 健康探活与恢复 ----


def test_lifecycle_probe_unhealthy_then_recover() -> None:
    healthy = [False]
    controller = LifecycleController(probe_fn=lambda: HealthStatus(alive=healthy[0]))
    controller.start()
    assert controller.probe().alive is False
    with pytest.raises(DeploymentError) as exc_info:
        controller.restart()
    assert exc_info.value.code is DeploymentErrorCode.HEALTH_UNHEALTHY
    healthy[0] = True
    controller.restart()
    assert controller.probe().alive is True


def test_lifecycle_start_twice_not_ready() -> None:
    controller = LifecycleController()
    controller.start()
    with pytest.raises(DeploymentError) as exc_info:
        controller.start()
    assert exc_info.value.code is DeploymentErrorCode.NOT_READY


# ---- 云托管 BYOC 适配 ----


def test_cloud_adapter_adapt_and_parity() -> None:
    adapter = CloudAdapter()
    env = adapter.adapt(DeployTarget(host="cloud", runtime="container"))
    assert env.state is EnvironmentState.CONFIGURED
    local = RuntimeConfig(kind="self-hosted", target=DeployTarget(host="pc", runtime="container"))
    cloud = RuntimeConfig(kind="byoc-cloud", target=DeployTarget(host="cloud", runtime="container"))
    assert adapter.parity_check(local, cloud) is True
    assert (
        adapter.parity_check(
            local, RuntimeConfig(kind="byoc-cloud", target=DeployTarget(host="c", runtime="vm"))
        )
        is False
    )
