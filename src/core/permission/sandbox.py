"""沙箱执行与策略门（permission）。

- :class:`SandboxManager`：终端域经 subprocess 真进程隔离执行（内存/CPU 配额经
  rlimit 约束），后端不可用降级 SANDBOX_UNAVAILABLE，超配额 QUOTA_EXCEEDED；
  浏览器 / 文件系统域走 :class:`SandboxPolicy` 策略门（三域隔离）。
- :class:`SandboxPolicy`：网络出站白名单 + 文件系统受控访问（deny-by-default
  策略门）。

对应接口：doc/03-interfaces/permission-interface.md §6
"""

from __future__ import annotations

import subprocess
import threading
import uuid
from collections.abc import Callable
from typing import Any

from .errors import AccessControlError, PermissionErrorCode
from .models import ResourceBudget, SandboxDomain, SandboxHandle, SandboxResult

try:
    import resource as _resource  # POSIX only；Windows 无此模块
except ImportError:  # pragma: no cover — Windows / 无 rlimit 平台
    _resource = None

SandboxBackend = Callable[[list[str], dict[str, str] | None, ResourceBudget], SandboxResult]


class SandboxPolicy:
    """出站网络白名单 + 文件系统受控访问。"""

    def __init__(
        self,
        host_allowlist: list[str] | None = None,
        fs_allowlist: dict[str, str] | None = None,
    ) -> None:
        self._hosts = set(host_allowlist or [])
        self._fs = dict(fs_allowlist or {})

    def check_outbound(self, host: str) -> None:
        if host not in self._hosts:
            raise AccessControlError(
                PermissionErrorCode.PERMISSION_DENIED, f"出站目标不在白名单: {host}"
            )

    def check_fs(self, path: str, mode: str = "r") -> None:
        allowed = self._fs.get(path)
        if allowed is None or (mode == "w" and allowed != "rw"):
            raise AccessControlError(
                PermissionErrorCode.PERMISSION_DENIED, f"文件系统访问受控: {path}"
            )


def _apply_resource_limits(budget: ResourceBudget) -> Callable[[], None] | None:
    """把内存/CPU 配额映射为 POSIX rlimit 的 preexec_fn（无配额 / 非 POSIX 返回 None）。"""

    if _resource is None:
        return None
    if budget.max_memory_bytes is None and budget.max_cpu_seconds is None:
        return None

    def _limits() -> None:
        assert _resource is not None
        if budget.max_memory_bytes is not None:
            _resource.setrlimit(
                _resource.RLIMIT_AS, (budget.max_memory_bytes, budget.max_memory_bytes)
            )
        if budget.max_cpu_seconds is not None:
            soft = max(1, int(budget.max_cpu_seconds))
            _resource.setrlimit(_resource.RLIMIT_CPU, (soft, soft))

    return _limits


def _subprocess_backend(
    cmd: list[str], env: dict[str, str] | None, budget: ResourceBudget
) -> SandboxResult:
    # preexec_fn 仅 POSIX；Windows 传该参数会 NotImplementedError，故有限额才注入。
    run_kwargs: dict[str, Any] = {
        "env": env,
        "capture_output": True,
        "text": True,
        "timeout": budget.timeout_s,
        "check": False,
    }
    preexec = _apply_resource_limits(budget)
    if preexec is not None:
        run_kwargs["preexec_fn"] = preexec
    try:
        proc = subprocess.run(cmd, **run_kwargs)
    except subprocess.TimeoutExpired as exc:
        raise AccessControlError(PermissionErrorCode.QUOTA_EXCEEDED, "沙箱资源配额超限") from exc
    if proc.returncode < 0:  # 被信号终止（内存/CPU 配额触发 SIGKILL/SIGXCPU）
        raise AccessControlError(
            PermissionErrorCode.QUOTA_EXCEEDED, f"进程被资源配额终止 (signal {-proc.returncode})"
        )
    return SandboxResult(proc.returncode, proc.stdout, proc.stderr, destroyed=True)


class SandboxManager:
    """沙箱执行器：subprocess 后端 + 句柄注册表回收。"""

    def __init__(
        self, backend: SandboxBackend | None = None, policy: SandboxPolicy | None = None
    ) -> None:
        self._backend: SandboxBackend = backend if backend is not None else _subprocess_backend
        self._policy = policy if policy is not None else SandboxPolicy()
        self._handles: dict[str, SandboxHandle] = {}
        self._lock = threading.RLock()

    def run(
        self,
        cmd: list[str],
        env: dict[str, str] | None = None,
        budget: ResourceBudget | None = None,
        *,
        domain: SandboxDomain = SandboxDomain.TERMINAL,
    ) -> SandboxResult:
        """按执行域路由：终端走 subprocess 隔离，浏览器/文件系统走策略门。

        - TERMINAL：``cmd`` 为命令行参数，真实子进程隔离执行，受资源配额约束。
        - BROWSER：``cmd`` 为 ``[host]``，出站目标经网络白名单校验后放行。
        - FILESYSTEM：``cmd`` 为 ``[path, mode]``，文件访问经受控清单校验后放行。
        """
        budget = budget if budget is not None else ResourceBudget()
        if domain is SandboxDomain.BROWSER:
            self._policy.check_outbound(self._target(cmd))
            return SandboxResult(0, "浏览器域出站请求已放行", "", destroyed=True)
        if domain is SandboxDomain.FILESYSTEM:
            path = self._target(cmd)
            mode = cmd[1] if len(cmd) > 1 else "r"
            self._policy.check_fs(path, mode)
            return SandboxResult(0, f"文件系统域访问已放行: {path}", "", destroyed=True)
        try:
            return self._backend(cmd, env, budget)
        except AccessControlError:
            raise
        except Exception as exc:  # noqa: BLE001 — 后端故障统一降级 SANDBOX_UNAVAILABLE
            raise AccessControlError(
                PermissionErrorCode.SANDBOX_UNAVAILABLE, f"沙箱不可用: {exc}"
            ) from exc

    def spawn(
        self,
        cmd: list[str],
        env: dict[str, str] | None = None,
        budget: ResourceBudget | None = None,
    ) -> subprocess.Popen[str]:
        """以资源配额拉起**常驻**子进程，返回可交互句柄（长连接消费者用）。

        与 :meth:`run` 的一次性执行互补：``run`` 跑完即返回结果，无法承载需要持续
        stdin/stdout 的长连接（如本地 stdio MCP 服务端）。句柄归调用方持有并负责终止；
        进程受 POSIX rlimit（内存/CPU）约束，拉起失败降级 SANDBOX_UNAVAILABLE。

        .. note:: 仅施加 rlimit；可移植的文件系统 jail 需 OS 设施（namespaces/bwrap），
           与 :meth:`run` 的终端域同款限制。
        """
        budget = budget if budget is not None else ResourceBudget()
        try:
            return subprocess.Popen(
                cmd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
                preexec_fn=_apply_resource_limits(budget),
            )
        except Exception as exc:  # noqa: BLE001 — 后端故障统一降级 SANDBOX_UNAVAILABLE
            raise AccessControlError(
                PermissionErrorCode.SANDBOX_UNAVAILABLE, f"沙箱不可用: {exc}"
            ) from exc

    @staticmethod
    def _target(cmd: list[str]) -> str:
        return cmd[0] if cmd else ""

    def create(self, kind: str = "local-subprocess") -> SandboxHandle:
        handle = SandboxHandle(handle_id=uuid.uuid4().hex, kind=kind)
        with self._lock:
            self._handles[handle.handle_id] = handle
        return handle

    def destroy(self, handle: SandboxHandle) -> None:
        with self._lock:
            self._handles.pop(handle.handle_id, None)

    def active_handles(self) -> list[SandboxHandle]:
        with self._lock:
            return list(self._handles.values())
