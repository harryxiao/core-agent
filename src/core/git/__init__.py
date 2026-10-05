"""Git 版本控制（git）：核心操作 + 安全与可靠性。"""

from .backend import GitBackend, build_backend
from .client import GitClient
from .errors import GitError, GitErrorCode
from .models import CommitLog, GitStatus, MergeResult
from .subprocess_backend import SubprocessGitBackend

__all__ = [
    "CommitLog",
    "GitBackend",
    "GitClient",
    "GitError",
    "GitErrorCode",
    "GitStatus",
    "MergeResult",
    "SubprocessGitBackend",
    "build_backend",
]
