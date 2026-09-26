"""沙箱执行与策略门（permission）。

- :class:`SandboxManager`：终端域经 subprocess 真进程隔离执行，后端可注入；
  后端不可用降级 SANDBOX_UNAVAILABLE，超配额 QUOTA_EXCEEDED。
- :class:`SandboxPolicy`：网络出站白名单 + 文件系统受控访问（deny-by-default
  策略门，浏览器 / 文件系统域不做事容器级隔离，M2 范围外）。

对应接口：doc/03-interfaces/permission-interface.md §6
"""

from __future__ import annotations

import subprocess
import threading
import uuid
from collections.abc import Callable

from .errors import AccessControlError, PermissionErrorCode
from .models import ResourceBudget, SandboxHandle, SandboxResult

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
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AccessControlError(PermissionErrorCode.QUOTA_EXCEEDED, "沙箱资源配额超限") from exc
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
    ) -> SandboxResult:
        budget = budget if budget is not None else ResourceBudget()
        try:
            return self._backend(cmd, env, budget)
        except AccessControlError:
            raise
        except Exception as exc:  # noqa: BLE001 — 后端故障统一降级 SANDBOX_UNAVAILABLE
            raise AccessControlError(
                PermissionErrorCode.SANDBOX_UNAVAILABLE, f"沙箱不可用: {exc}"
            ) from exc

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
