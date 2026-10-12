"""0228 · 文件工具 `~` 展开（change 乙，承 ADR-0218）。

`Path(path)` **不做** `~` 展开 ⇒ `~/x` 被当作**当前工作目录下字面名为 `~` 的目录**下的文件，
父目录不存在 ⇒ 读/写失败（意图家目录、行为字面 `~`，静默背离）。本文件覆盖：
  * 三个 `file_*` 工具的 `~` 展开（读 / 写 / 精确替换）；
  * **撤销点与写入点一致** —— 存展开后路径 ⇒ `_restore` 恢复家目录文件，**不**误建字面 `~`；
  * 无 `~` 的路径（相对 / 绝对）逐字不变。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.plugin_registry import CoeffectResolver
from core.tools import ToolProvider, file_patch, file_read, file_write
from core.tools.builtin import _expand  # noqa: PLC2701 — helper 恒等性断言


def _provider() -> ToolProvider:
    resolver = CoeffectResolver()
    resolver.register("filesystem:read", True)
    resolver.register("filesystem:write", True)
    return ToolProvider(coeffect_resolver=resolver)


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """把 `$HOME` 指向临时目录 ⇒ `~` 展开落点可控、不碰真实家目录。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


# ── 1. `~` 展开：读 / 写 / 精确替换 ──────────────────────────────────────────


def test_file_read_expands_tilde(home: Path) -> None:
    """`file_read("~/x.txt")` 命中**家目录**文件（而非字面 `./~`）。"""
    (home / "x.txt").write_text("hello", encoding="utf-8")
    provider = _provider()
    provider.register(file_read())

    result = provider.invoke("tools.file_read", {"path": "~/x.txt"}, trace_id="t")

    assert result.ok is True
    assert result.data["content"] == "hello"


def test_file_write_expands_tilde_keeps_input_in_result(home: Path) -> None:
    """`file_write("~/x.txt")` 落到家目录；返回体仍回**原文**路径（contract 不变）。"""
    provider = _provider()
    provider.register(file_write())

    result = provider.invoke("tools.file_write", {"path": "~/x.txt", "content": "hi"}, trace_id="t")

    assert result.ok is True
    assert (home / "x.txt").read_text(encoding="utf-8") == "hi"  # 落到家目录
    assert result.data["path"] == "~/x.txt"  # 回显输入原文，非解析后路径


def test_file_patch_expands_tilde(home: Path) -> None:
    """`file_patch("~/x.txt")` 命中家目录文件并完成替换。"""
    (home / "x.txt").write_text("one two", encoding="utf-8")
    provider = _provider()
    provider.register(file_patch())

    result = provider.invoke(
        "tools.file_patch",
        {"path": "~/x.txt", "old_content": "two", "new_content": "three"},
        trace_id="t",
    )

    assert result.ok is True
    assert (home / "x.txt").read_text(encoding="utf-8") == "one three"


# ── 2. 撤销点与写入点一致（承重：存展开路径）──────────────────────────────────


def test_undo_restores_home_file_not_literal_tilde(home: Path) -> None:
    """写 `~/x.txt` 后撤销 ⇒ 恢复**家目录**文件，且**不**创建字面 `~` 目录/文件。"""
    (home / "x.txt").write_text("orig", encoding="utf-8")
    provider = _provider()
    provider.register(file_write())
    result = provider.invoke(
        "tools.file_write", {"path": "~/x.txt", "content": "changed"}, trace_id="t"
    )
    assert (home / "x.txt").read_text(encoding="utf-8") == "changed"

    provider.rollback("t")

    assert result.effect_id is not None
    assert (home / "x.txt").read_text(encoding="utf-8") == "orig", "恢复的是家目录文件"
    assert not (Path.cwd() / "~").exists(), "撤销 SHALL NOT 触及字面 `~` 路径"


def test_undo_of_new_home_file_deletes_it(home: Path) -> None:
    """写**原本不存在**的 `~/new.txt` 后撤销 ⇒ 该家目录文件被删除。"""
    provider = _provider()
    provider.register(file_write())
    provider.invoke("tools.file_write", {"path": "~/new.txt", "content": "x"}, trace_id="t")
    assert (home / "new.txt").exists()

    provider.rollback("t")

    assert not (home / "new.txt").exists()


# ── 3. 无 `~` 路径逐字不变 ────────────────────────────────────────────────────


def test_relative_and_absolute_paths_unchanged(tmp_path: Path) -> None:
    """无 `~` 的相对 / 绝对路径行为**逐字不变**（`expanduser` 是恒等变换）。"""
    absolute = tmp_path / "a.txt"
    provider = _provider()
    provider.register(file_write())
    provider.register(file_read())

    provider.invoke("tools.file_write", {"path": str(absolute), "content": "A"}, trace_id="t")
    absolute_result = provider.invoke("tools.file_read", {"path": str(absolute)}, trace_id="t")

    assert absolute.read_text(encoding="utf-8") == "A"
    assert absolute_result.data["content"] == "A"


def test_expand_is_identity_without_tilde() -> None:
    """`_expand` 对无 `~` 的路径是纯 `Path`（无解析、无绝对化）。"""
    assert _expand("a/b/c.txt") == Path("a/b/c.txt")


def test_expand_resolves_tilde_to_home(home: Path) -> None:
    """`_expand` 把 `~` 归一到家目录（与 `core_profile.loader` 同口径）。"""
    assert _expand("~/x.txt") == home / "x.txt"
