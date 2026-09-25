"""架构测试基线（Phase -1 工程规范门禁，零第三方依赖）。

用 stdlib 的 ``ast`` / ``importlib`` 对源码做静态结构检查，
与 ruff（lint/style）、pyright（类型）互补，把 12 主题中
「无法被单文件 lint 覆盖」的架构约束固化为可执行测试。

覆盖主题：
- 主题 2  命名约定：公共函数/方法 snake_case
- 主题 4  if/else ≤3：控制流嵌套深度上限
- 主题 5  低耦合高内聚：依赖倒置 Protocol 契约存在性
- 主题 7  异常处理：禁止裸 ``except:``
- 主题 9  模块设计：L0-L5 分层包结构、包可导入性

运行：``pytest tests/test_architecture.py -v``
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import re
from collections.abc import Iterator

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "core"

# 主题 9：L0-L5 分层 + 横切包结构
EXPECTED_PACKAGES = {
    "substrate",  # L0 能力基座
    "tools",  # L1 工具使用
    "memory",  # L2 记忆
    "loop",  # L3 智能体循环
    "evolution",  # L4 进化
    "composition",  # L5 组合分发
    "mcp",  # 横切：MCP 协议
}

_SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_NESTABLE = (ast.If, ast.For, ast.While, ast.Try, ast.With)
_MAX_NESTING = 3  # 主题 4：if/else 最大嵌套 ≤3


def _iter_py_files() -> Iterator[pathlib.Path]:
    yield from SRC.rglob("*.py")


def _parse(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _max_nesting(node: ast.AST, depth: int = 0) -> int:
    if isinstance(node, _NESTABLE):
        depth += 1
    children = list(ast.iter_child_nodes(node))
    if not children:
        return depth
    return max(_max_nesting(child, depth) for child in children)


# ---- 主题 9：模块设计（分层） ----


def test_layered_packages_present() -> None:
    present = {p.name for p in SRC.iterdir() if p.is_dir()}
    missing = EXPECTED_PACKAGES - present
    assert not missing, f"缺失分层包: {sorted(missing)}"


def test_every_package_has_init() -> None:
    missing = [p for p in EXPECTED_PACKAGES if not (SRC / p / "__init__.py").is_file()]
    assert not missing, f"缺少 __init__.py 的包: {missing}"


def test_packages_importable() -> None:
    for pkg in sorted(EXPECTED_PACKAGES):
        importlib.import_module(f"core.{pkg}")


# ---- 主题 2：命名约定 ----


def test_public_function_names_snake_case() -> None:
    offenders: list[str] = []
    for path in _iter_py_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                if name.startswith("__") and name.endswith("__"):
                    continue  # dunder 豁免
                if not _SNAKE_RE.match(name):
                    offenders.append(f"{path.name}:{node.lineno} {name}")
    assert not offenders, f"函数/方法命名非 snake_case: {offenders}"


# ---- 主题 4：if/else 最大嵌套 ----


def test_control_flow_nesting_max_three() -> None:
    offenders: list[str] = []
    for path in _iter_py_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                depth = _max_nesting(node)
                if depth > _MAX_NESTING:
                    offenders.append(f"{path.name}:{node.lineno} {node.name} 嵌套 {depth}")
    assert not offenders, f"控制流嵌套超过 {_MAX_NESTING} 层: {offenders}"


# ---- 主题 5：低耦合高内聚（依赖倒置） ----


def test_protocol_contracts_defined() -> None:
    expected_by_pkg = {
        "loop": {"LoopPlugin"},
        "memory": {"MemoryStore", "Crystallizer", "MemoryBackend"},
    }
    for pkg, expected in expected_by_pkg.items():
        path = SRC / pkg / "protocol.py"
        assert path.is_file(), f"{pkg} 缺少 protocol.py（依赖倒置契约）"
        tree = _parse(path)
        proto_names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and any(isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases)
        }
        missing = expected - proto_names
        assert not missing, f"{pkg}/protocol.py 缺失 Protocol 契约: {sorted(missing)}"


# ---- 主题 7：异常处理 ----


def test_no_bare_except() -> None:
    offenders: list[str] = []
    for path in _iter_py_files():
        tree = _parse(path)
        offenders.extend(
            f"{path.name}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler) and node.type is None
        )
    assert not offenders, f"存在裸 except: {offenders}"
