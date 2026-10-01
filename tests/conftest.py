"""pytest 会话级隔离：把全局状态目录重定向到每测试独立的临时目录。

``entry`` 层的 serve/probe/sessions/release 会读写 ``~/.core/state/``（经
``CORE_STATE_DIR`` 覆盖）；本夹具 autouse 保证测试互不污染、不碰真实 home。
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_state_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
