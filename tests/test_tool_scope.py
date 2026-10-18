"""工具参数按需注入（change 0272 / ADR-0262 / 账本 E208）。

覆盖四层：

* **配置**：`loop.tool_scope` 三面齐备、缺省 `auto`、取值归一、非法值阻断启动。
* **规划器**：`auto` 只注入核心集 + 已加载 + `schema_read`；小工具面 / 未注册
  `schema_read` 回落全量；`all` 与构造缺省保持全量；目录不随开关收窄。
* **循环**：`schema_read` 成功后吸收 id，下一轮请求可见；新回合重置。
* **工具面**：`schema_read` 列表 / 按 id / 未知 id；权限判只读。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.llm_provider import LLMResponse, TokenUsage
from core.loop import DefaultLoop, LLMPlanner, LoopContext
from core.permission import PolicyEngine, RiskLevel
from core.plugin_registry import CoeffectResolver
from core.runtime import build_runtime
from core.tools import Tool, ToolDef, ToolProvider, schema_read

_CORE = (
    "tools.file_read",
    "tools.file_write",
    "tools.file_patch",
    "tools.code_run",
    "tools.web_fetch",
    "tools.context_read",
    "tools.delegate",
)
_ON_DEMAND = ("tools.gate_run", "tools.process")
_SCHEMA_READ = "tools.schema_read"

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _config(tmp_path: Path, extra: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    return str(cfg)


def _manager(
    tmp_path: Path,
    extra: str = "",
    *,
    environ: dict[str, str] | None = None,
    cli: dict[str, object] | None = None,
) -> ConfigManager:
    manager = ConfigManager(
        yaml_path=_config(tmp_path, extra),
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
        cli=cli,
    )
    manager.load()
    return manager


def _tool(tool_id: str) -> Tool:
    return Tool(
        definition=ToolDef(
            tool_id=tool_id,
            description=f"{tool_id} 描述",
            schema={"type": "object", "properties": {}},
            coeffects=[],
            reversible=True,
        ),
        handler=lambda **_: {"ok": True},
    )


def _provider(
    tool_ids: tuple[str, ...] = (*_CORE, *_ON_DEMAND),
    *,
    with_schema_read: bool = True,
) -> ToolProvider:
    resolver = CoeffectResolver()
    resolver.register("schema:read", True)
    provider = ToolProvider(coeffect_resolver=resolver)
    for tool_id in tool_ids:
        provider.register(_tool(tool_id))
    if with_schema_read:
        provider.register(schema_read(catalog=provider.active_tools))
    return provider


class _CapturingLLM:
    """记录每次请求；按序出内容，末项重复。"""

    def __init__(self, *contents: str) -> None:
        self.requests: list[Any] = []
        self._contents = list(contents)

    async def acompletion(self, request: Any) -> LLMResponse:
        self.requests.append(request)
        content = self._contents.pop(0) if len(self._contents) > 1 else self._contents[0]
        return LLMResponse(
            content=content,
            usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
            finish_reason="stop",
            provider="fake",
            model="test-model",
        )


def _context(**overrides: Any) -> LoopContext:
    ctx = LoopContext(messages=[{"role": "user", "content": "任务"}])
    for key, value in overrides.items():
        setattr(ctx, key, value)
    return ctx


def _names(request: Any) -> set[str]:
    return {item["function"]["name"] for item in request.tools}


def _planner(
    provider: ToolProvider, *, scope: str
) -> tuple[LLMPlanner, _CapturingLLM, LoopContext]:
    llm = _CapturingLLM("完成")
    planner = LLMPlanner(llm, tools=provider, tool_scope=scope)
    return planner, llm, _context()


def _request(planner: LLMPlanner, ctx: LoopContext) -> None:
    asyncio.run(planner(ctx))


# ---- 配置面 ----


def test_spec_declares_tool_scope() -> None:
    """`loop.tool_scope` 经 ConfigSpec 单一真源三面齐备。"""
    spec = {item.key: item for item in config_specs()}["loop.tool_scope"]
    assert (spec.cli_flag, spec.env_var, spec.map_to) == (
        "--loop.tool-scope",
        "CORE_LOOP_TOOL_SCOPE",
        "loop.tool_scope",
    )
    assert spec.default == "auto"


def test_default_scope_is_auto(tmp_path: Path) -> None:
    assert _manager(tmp_path).tool_scope() == "auto"


@pytest.mark.parametrize(
    ("extra", "environ", "cli"),
    [
        ("loop:\n  tool_scope: all\n", None, None),
        ("", {"CORE_LOOP_TOOL_SCOPE": "all"}, None),
        (
            "loop:\n  tool_scope: auto\n",
            {"CORE_LOOP_TOOL_SCOPE": "auto"},
            {"loop.tool_scope": "all"},
        ),
    ],
)
def test_scope_three_faces(
    tmp_path: Path,
    extra: str,
    environ: dict[str, str] | None,
    cli: dict[str, object] | None,
) -> None:
    """yaml / env / CLI 三面可达，且 CLI > env > yaml。"""
    assert _manager(tmp_path, extra, environ=environ, cli=cli).tool_scope() == "all"


def test_scope_is_normalized(tmp_path: Path) -> None:
    """取值大小写不敏感、忽略首尾空白。"""
    assert _manager(tmp_path, "loop:\n  tool_scope: '  AUTO '\n").tool_scope() == "auto"


@pytest.mark.parametrize("value", ["maybe", '""', "true"])
def test_invalid_scope_blocks_startup(tmp_path: Path, value: str) -> None:
    """非法取值校验期阻断启动（不静默回落缺省）。"""
    with pytest.raises(ConfigurationError, match="非法工具注入范围"):
        _manager(tmp_path, f"loop:\n  tool_scope: {value}\n")


# ---- 规划器过滤 ----


def test_auto_narrows_main_surface() -> None:
    """auto：只注入核心集 + 已加载 + schema_read。"""
    planner, llm, ctx = _planner(_provider(), scope="auto")
    _request(planner, ctx)
    names = _names(llm.requests[0])
    assert names == {*_CORE, _SCHEMA_READ}
    assert not names & set(_ON_DEMAND)


def test_all_injects_every_tool() -> None:
    planner, llm, ctx = _planner(_provider(), scope="all")
    _request(planner, ctx)
    assert _names(llm.requests[0]) == {*_CORE, *_ON_DEMAND, _SCHEMA_READ}


def test_constructor_default_keeps_all() -> None:
    """直接构造 planner 不给 scope ⇒ 全量（既有调用零变化）。"""
    llm = _CapturingLLM("完成")
    planner = LLMPlanner(llm, tools=_provider())
    asyncio.run(planner(_context()))
    assert _names(llm.requests[0]) == {*_CORE, *_ON_DEMAND, _SCHEMA_READ}


def test_small_surface_injects_all_under_auto() -> None:
    """≤8 件工具 ⇒ auto 免加载（子 Agent / 宠物的天然形态）。"""
    small = ("tools.file_read", "tools.file_write", "tools.code_run")
    planner, llm, ctx = _planner(_provider(small), scope="auto")
    _request(planner, ctx)
    assert _names(llm.requests[0]) == {*small, _SCHEMA_READ}


def test_auto_without_schema_read_falls_back_to_all() -> None:
    """未注册 schema_read ⇒ 回落全量（不得造出不可达工具面）。"""
    provider = _provider(
        (*_CORE, *_ON_DEMAND, "tools.tasks", "tools.install"), with_schema_read=False
    )
    planner, llm, ctx = _planner(provider, scope="auto")
    _request(planner, ctx)
    assert _names(llm.requests[0]) == {*_CORE, *_ON_DEMAND, "tools.tasks", "tools.install"}


def test_loaded_tool_is_injected() -> None:
    planner, llm, ctx = _planner(_provider(), scope="auto")
    ctx.loaded_tools = {"tools.process"}
    _request(planner, ctx)
    assert "tools.process" in _names(llm.requests[0])


def test_catalog_not_narrowed_and_hint_only_in_auto() -> None:
    """目录恒全量；按需加载说明行只在 auto 生效时出现。"""
    auto_planner, _, ctx = _planner(_provider(), scope="auto")
    prompt = auto_planner._system_prompt(ctx)  # noqa: SLF001 — 块装配判据
    assert "- tools.gate_run:" in prompt
    assert "tools.schema_read" in prompt
    assert "参数 schema" in prompt

    all_planner, _, ctx = _planner(_provider(), scope="all")
    prompt_all = all_planner._system_prompt(ctx)  # noqa: SLF001 — 块装配判据
    assert "- tools.gate_run:" in prompt_all
    assert "参数 schema 未注入" not in prompt_all


# ---- 循环吸收与回合生命周期 ----


def test_schema_read_visible_next_round_and_reset_next_turn() -> None:
    """加载后下一轮可见；新回合重新只含核心集。"""
    provider = _provider()
    llm = _CapturingLLM(
        '{"tool_id": "tools.schema_read", "args": {"tool_ids": ["tools.gate_run"]}}',
        "完成",
    )
    loop = DefaultLoop(
        planner=LLMPlanner(llm, tools=provider, tool_scope="auto"),
        tools=provider,
        max_rounds=3,
    )
    first = loop.run("第一轮")
    assert first.failed is False
    assert "tools.gate_run" not in _names(llm.requests[0])
    assert "tools.gate_run" in _names(llm.requests[1])

    second = loop.run("第二轮")
    assert second.failed is False
    assert "tools.gate_run" not in _names(llm.requests[2])


def test_unknown_schema_read_id_is_not_absorbed() -> None:
    """未知 id 吸收不进来（下一轮仍不可见），但本轮不失败。"""
    provider = _provider()
    llm = _CapturingLLM(
        '{"tool_id": "tools.schema_read", "args": {"tool_ids": ["tools.nope"]}}',
        "完成",
    )
    loop = DefaultLoop(
        planner=LLMPlanner(llm, tools=provider, tool_scope="auto"),
        tools=provider,
        max_rounds=3,
    )
    result = loop.run("任务")
    assert result.failed is False
    assert "tools.nope" not in _names(llm.requests[1])


# ---- tools.schema_read 工具面 ----


def test_schema_read_lists_all_tools() -> None:
    provider = _provider()
    result = asyncio.run(provider.ainvoke(_SCHEMA_READ, {}, trace_id="t"))
    assert result.ok
    ids = {item["tool_id"] for item in result.data["tools"]}
    assert _SCHEMA_READ in ids
    assert "tools.process" in ids


def test_schema_read_returns_parameters_by_id() -> None:
    provider = _provider()
    result = asyncio.run(
        provider.ainvoke(_SCHEMA_READ, {"tool_ids": ["tools.process", "tools.nope"]}, trace_id="t")
    )
    assert result.ok
    assert result.data["unknown"] == ["tools.nope"]
    (schema,) = result.data["schemas"]
    assert schema["tool_id"] == "tools.process"
    assert schema["parameters"] == {"type": "object", "properties": {}}


def test_schema_read_is_read_only() -> None:
    assert PolicyEngine().classify(_SCHEMA_READ, "", ["schema:read"]) == RiskLevel.READ


# ---- 组合根接线 ----


def test_runtime_wires_auto_and_registers_schema_read(tmp_path: Path) -> None:
    runtime = build_runtime(
        ConfigManager(yaml_path=_config(tmp_path), environ={"OPENAI_API_KEY": "sk-test"})
    )
    loop = cast(DefaultLoop, runtime.loop)  # type: ignore[attr-defined]
    assert loop._planner._tool_scope == "auto"  # noqa: SLF001 — 接线断言
    assert _SCHEMA_READ in {tool.tool_id for tool in loop._tools.active_tools()}  # noqa: SLF001


def test_runtime_honours_all_scope(tmp_path: Path) -> None:
    runtime = build_runtime(
        ConfigManager(
            yaml_path=_config(tmp_path, "loop:\n  tool_scope: all\n"),
            environ={"OPENAI_API_KEY": "sk-test"},
        )
    )
    loop = cast(DefaultLoop, runtime.loop)  # type: ignore[attr-defined]
    assert loop._planner._tool_scope == "all"  # noqa: SLF001 — 接线断言
