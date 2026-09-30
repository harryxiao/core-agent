"""沙箱执行与策略门（permission）。

- :class:`SandboxManager`：终端域经 subprocess 真进程隔离执行（内存/CPU 配额经
  rlimit 约束），后端不可用降级 SANDBOX_UNAVAILABLE，超配额 QUOTA_EXCEEDED；
  浏览器 / 文件系统域走 :class:`SandboxPolicy` 策略门（三域隔离）。
- :class:`SandboxPolicy`：网络出站白名单 + 文件系统受控访问（deny-by-default
  策略门）。

对应接口：doc/03-interfaces/permission-interface.md §6
"""

from __future__ import annotations

import resource
import subprocess
import threading
import uuid
from collections.abc import Callable

from .errors import AccessControlError, PermissionErrorCode
from .models import ResourceBudget, SandboxDomain, SandboxHandle, SandboxResult

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
    """把内存/CPU 配额映射为 POSIX rlimit 的 preexec_fn（无配额返回 None）。"""

    if budget.max_memory_bytes is None and budget.max_cpu_seconds is None:
        return None

    def _limits() -> None:
        if budget.max_memory_bytes is not None:
            resource.setrlimit(
                resource.RLIMIT_AS, (budget.max_memory_bytes, budget.max_memory_bytes)
            )
        if budget.max_cpu_seconds is not None:
            soft = max(1, int(budget.max_cpu_seconds))
            resource.setrlimit(resource.RLIMIT_CPU, (soft, soft))

    return _limits


def _subprocess_backend(
    cmd: list[str], env: dict[str, str] | None, budget: ResourceBudget
) -> SandboxResult:
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=budget.timeout_s,
            preexec_fn=_apply_resource_limits(budget),
            check=False,
        )
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
