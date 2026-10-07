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
    "context",  # L2.5 上下文工程
    "tools",  # L1 工具使用
    "memory",  # L2 记忆
    "notes",  # L2 文档化真相层（canonical Markdown）
    "rag",  # L3 检索底座
    "loop",  # L3 智能体循环
    "skills",  # L3 技能封装
    "skillhub",  # L3 技能市场
    "orchestration",  # L3.5 任务编排
    "evolution",  # L4 进化
    "composition",  # L5 组合分发
    "distributed",  # 分布层（横切）
    "deployment",  # 托管层（横切）
    "constraints",  # 横切：约束/熔断/压缩
    "durability",  # 横切：检查点/恢复
    "permission",  # 横切：权限/审批/沙箱
    "mcp",  # 横切：MCP 协议
    "cli_ops",  # 横切：CLI 运维命令面
    "diagnostics",  # 横切：只读诊断源（doctor / status，change 0162）
    "ci_cd",  # 交付：CI/CD 流水线
    "ui",  # 接入：三模统一入口
    "im",  # 接入：IM 网关
    "git",  # 工具横切：版本控制
    "pet",  # 宠物模式子系统（core/library/explore/safety/notify/microtask）
    "beast",  # 神兽召唤层（前台重大任务，pet-mode 对偶）
    "judgment",  # 横切：决策模型（System One 决策小模型 + 主 LLM 回退）
}

# 主题 9（Phase 0 补充）：底座模块只依赖彼此 + stdlib，不反向依赖能力层
BASE_MODULES = {"plugin_registry", "configuration", "observability", "core_profile"}
CAPABILITY_MODULES = {
    "context",
    "tools",
    "memory",
    "notes",
    "rag",
    "loop",
    "skills",
    "skillhub",
    "orchestration",
    "evolution",
    "composition",
    "distributed",
    "deployment",
    "constraints",
    "durability",
    "permission",
    "mcp",
    "cli_ops",
    "diagnostics",
    "ci_cd",
    "ui",
    "im",
    "git",
    "pet",
    "beast",
    "judgment",
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


def _core_subpackages(path: pathlib.Path) -> set[str]:
    """返回文件中 import 的 core 一级子包名（相对导入 / 非 core 导入忽略）。"""
    tree = _parse(path)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            dotted = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            dotted = [node.module]
        else:
            continue
        for name in dotted:
            parts = name.split(".")
            if len(parts) > 1 and parts[0] == "core":
                found.add(parts[1])
    return found


def _pet_subpackages(path: pathlib.Path) -> set[str]:
    """返回文件中 import 的 pet 子模块名（core/library/explore/safety/notify/microtask）。"""
    tree = _parse(path)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            dotted = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            dotted = [node.module]
        else:
            continue
        for name in dotted:
            parts = name.split(".")
            if len(parts) >= 3 and parts[0] == "core" and parts[1] == "pet":  # noqa: PLR2004
                found.add(parts[2])
    return found


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
                if name.startswith("_"):
                    continue  # dunder + 私有成员豁免（主题 2：私有成员用单下划线前缀）
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


# ---- 主题 9（Phase 0 补充）：底座模块依赖边界 ----


def test_phase0_modules_no_reverse_dependency() -> None:
    offenders: list[str] = []
    for base in sorted(BASE_MODULES):
        for path in (SRC / base).rglob("*.py"):
            offenders.extend(
                f"{base}/{path.name} -> core.{sub}"
                for sub in sorted(_core_subpackages(path))
                if sub in CAPABILITY_MODULES
            )
    assert not offenders, f"底座模块反向依赖能力层: {offenders}"


# ---- 主题 9（Phase 1 补充）：能力模块单向依赖（拓扑序 llm-provider → tool-use → memory） ----


def test_phase1_capability_no_reverse_dependency() -> None:
    """Phase 1 能力模块禁止反向 import，保持 §0 拓扑序单向依赖。"""
    forbidden: dict[str, set[str]] = {
        "llm_provider": {"tools", "memory"},
        "tools": {"memory", "llm_provider"},
        "memory": {"tools", "llm_provider"},
    }
    offenders: list[str] = []
    for pkg, banned in forbidden.items():
        for path in (SRC / pkg).rglob("*.py"):
            offenders.extend(
                f"{pkg}/{path.name} -> core.{sub}"
                for sub in sorted(_core_subpackages(path) & banned)
            )
    assert not offenders, f"Phase1 能力模块反向依赖: {offenders}"


# ---- 主题 9（Phase 2 补充）：横切中间件不反向依赖上层（loop/skills/orchestration） ----


def test_phase2_middleware_no_reverse_dependency() -> None:
    """横切中间件禁止反向 import loop/skills/orchestration，保持 L3 以下。"""
    middleware = {"constraints", "durability", "permission", "mcp"}
    upper_layers = {"loop", "skills", "orchestration"}
    offenders: list[str] = []
    for pkg in sorted(middleware):
        for path in (SRC / pkg).rglob("*.py"):
            offenders.extend(
                f"{pkg}/{path.name} -> core.{sub}"
                for sub in sorted(_core_subpackages(path) & upper_layers)
            )
    assert not offenders, f"横切中间件反向依赖上层: {offenders}"


# ---- 主题 9（Phase 3 补充）：引擎主轴不反向依赖上层 ----


def test_phase3_loop_no_reverse_dependency() -> None:
    """loop 不得反向依赖 skills/skillhub/notes；context 不得反向依赖 loop。"""
    forbidden: dict[str, set[str]] = {
        "loop": {"skills", "skillhub", "notes"},
        "context": {"loop"},
    }
    offenders: list[str] = []
    for pkg, banned in forbidden.items():
        for path in (SRC / pkg).rglob("*.py"):
            offenders.extend(
                f"{pkg}/{path.name} -> core.{sub}"
                for sub in sorted(_core_subpackages(path) & banned)
            )
    assert not offenders, f"引擎主轴反向依赖上层: {offenders}"


# ---- 主题 9（Phase 4 补充）：编排与检索底座不反向依赖上层 ----


def test_phase4_orchestration_rag_no_reverse_dependency() -> None:
    """orchestration 不得反向依赖 evolution/composition；rag 不得反向依赖 orchestration 及以上。"""
    forbidden: dict[str, set[str]] = {
        "orchestration": {"evolution", "composition"},
        "rag": {"orchestration", "evolution", "composition"},
    }
    offenders: list[str] = []
    for pkg, banned in forbidden.items():
        for path in (SRC / pkg).rglob("*.py"):
            offenders.extend(
                f"{pkg}/{path.name} -> core.{sub}"
                for sub in sorted(_core_subpackages(path) & banned)
            )
    assert not offenders, f"Phase4 编排/检索底座反向依赖上层: {offenders}"


# ---- 主题 9（G5 补充）：RAG 定位 —— 辅助本地知识库，不注入主链路（ADR-0097 ⑥ / ADR-0148） ----


def test_rag_not_imported_by_reference_chain() -> None:
    """RAG 是辅助本地知识库，经 CLI 一次性驱动，**不**注入 loop 主链路。

    守护 ADR-0097 ⑥ / ADR-0148：主链路与三面兄弟（``loop`` / ``context`` / ``memory`` /
    ``notes``）SHALL NOT import ``core.rag`` —— 把「定位」由文档散文固化为**可执行不变量**
    （要令 RAG 参与 loop 上下文，须**先改 ADR-0097 ⑥**、再经组合根 ``runtime`` 注入，而非让
    主链路直接 import rag）。``runtime``（组合根）与 ``entry``（CLI）是仅有的例外。
    """
    chain = {"loop", "context", "memory", "notes"}
    offenders: list[str] = []
    for pkg in sorted(chain):
        for path in (SRC / pkg).rglob("*.py"):
            offenders.extend(
                f"{pkg}/{path.name} -> core.rag"
                for sub in sorted(_core_subpackages(path))
                if sub == "rag"
            )
    assert not offenders, f"主链路 / 三面兄弟反向 import core.rag（ADR-0097 ⑥）: {offenders}"


def test_phase5_evolution_no_reverse_dependency() -> None:
    """evolution 不得反向依赖 composition（L5 组合层）。"""
    forbidden: dict[str, set[str]] = {
        "evolution": {"composition"},
    }
    offenders: list[str] = []
    for pkg, banned in forbidden.items():
        for path in (SRC / pkg).rglob("*.py"):
            offenders.extend(
                f"{pkg}/{path.name} -> core.{sub}"
                for sub in sorted(_core_subpackages(path) & banned)
            )
    assert not offenders, f"Phase5 进化层反向依赖 composition: {offenders}"


def test_phase6_composition_distributed_deployment_no_reverse_dependency() -> None:
    """composition 不依赖 distributed/deployment/evolution；distributed 不依赖 deployment。"""
    forbidden: dict[str, set[str]] = {
        "composition": {"distributed", "deployment", "evolution"},
        "distributed": {"deployment"},
    }
    offenders: list[str] = []
    for pkg, banned in forbidden.items():
        for path in (SRC / pkg).rglob("*.py"):
            offenders.extend(
                f"{pkg}/{path.name} -> core.{sub}"
                for sub in sorted(_core_subpackages(path) & banned)
            )
    assert not offenders, f"Phase6 组合/分布层反向依赖上层: {offenders}"


def test_phase7_ci_cd_ui_im_git_no_reverse_dependency() -> None:
    """ci-cd/ui/im/git 四模块两两互不依赖（均为交付/接入/工具横切端顶点）。"""
    forbidden: dict[str, set[str]] = {
        "ci_cd": {"ui", "im", "git"},
        "ui": {"ci_cd", "im", "git"},
        "im": {"ci_cd", "ui", "git"},
        "git": {"ci_cd", "ui", "im"},
    }
    offenders: list[str] = []
    for pkg, banned in forbidden.items():
        for path in (SRC / pkg).rglob("*.py"):
            offenders.extend(
                f"{pkg}/{path.name} -> core.{sub}"
                for sub in sorted(_core_subpackages(path) & banned)
            )
    assert not offenders, f"Phase7 交付/接入层两两互不依赖: {offenders}"


def test_phase8_pet_modules_no_reverse_dependency() -> None:
    """pet 六子模块单向依赖：core 基座；leaf 仅依赖 core。

    microtask 额外可依赖 safety。
    """

    forbidden: dict[str, set[str]] = {
        "core": {"library", "explore", "safety", "notify", "microtask"},
        "library": {"explore", "safety", "notify", "microtask"},
        "explore": {"library", "safety", "notify", "microtask"},
        "safety": {"library", "explore", "notify", "microtask"},
        "notify": {"library", "explore", "safety", "microtask"},
        "microtask": {"library", "explore", "notify"},
    }
    offenders: list[str] = []
    for sub, banned in forbidden.items():
        for path in (SRC / "pet" / sub).rglob("*.py"):
            offenders.extend(
                f"pet/{sub}/{path.name} -> pet.{dep}"
                for dep in sorted(_pet_subpackages(path) & banned)
            )
    assert not offenders, f"Phase8 宠物模式子模块反向依赖: {offenders}"


def test_phase10_beast_not_imported_by_dependencies() -> None:
    """beast 是编排层扩展叶子：loop/skills/orchestration 不得反向 import beast。"""

    lower_layers = {"loop", "skills", "orchestration"}
    offenders: list[str] = []
    for pkg in sorted(lower_layers):
        for path in (SRC / pkg).rglob("*.py"):
            offenders.extend(
                f"{pkg}/{path.name} -> core.beast"
                for sub in sorted(_core_subpackages(path))
                if sub == "beast"
            )
    assert not offenders, f"Phase10 神兽召唤层被底层反向依赖: {offenders}"


def test_phase11_judgment_no_reverse_dependency() -> None:
    """judgment 低层横切叶子：只依赖 llm_provider/observability 底座。

    不得反向依赖其消费方上层（loop/memory/permission 等）。
    """

    upper_layers = {
        "loop",
        "memory",
        "permission",
        "context",
        "rag",
        "skills",
        "skillhub",
        "orchestration",
        "evolution",
        "composition",
    }
    offenders: list[str] = []
    for path in (SRC / "judgment").rglob("*.py"):
        offenders.extend(
            f"judgment/{path.name} -> core.{sub}"
            for sub in sorted(_core_subpackages(path) & upper_layers)
        )
    assert not offenders, f"Phase11 决策层反向依赖上层: {offenders}"


def test_runtime_is_sole_composition_root() -> None:
    """runtime 是唯一被允许 import 全部模块的组合根。

    其余模块（除 entry 入口）不得反向依赖 runtime，否则与组合根形成循环。
    """
    required = {
        "configuration",
        "context",
        "durability",
        "evolution",
        "judgment",
        "llm_provider",
        "loop",
        "memory",
        "observability",
        "orchestration",
        "permission",
        "skills",
        "tools",
    }
    imported = _core_subpackages(SRC / "runtime.py")
    missing = required - imported
    assert not missing, f"runtime 组合根未装配这些模块: {sorted(missing)}"

    offenders: list[str] = []
    for path in _iter_py_files():
        if path.name in ("runtime.py", "entry.py"):
            continue
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                dotted = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                dotted = [node.module]
            else:
                continue
            offenders.extend(
                f"{path.relative_to(SRC)} -> core.runtime"
                for name in dotted
                if name == "core.runtime" or name.startswith("core.runtime.")
            )
    assert not offenders, f"非组合根模块反向依赖 runtime: {offenders}"
