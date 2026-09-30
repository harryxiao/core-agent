"""产品化入口层（entry）：argparse 全命令面 + 路由到三桥/编排层。

`core-agent` 可安装、可启动的入口：解析 argv，路由到三桥（CLI/Web/Desktop）与
编排层（pet/beast/session），`-h/--help` 输出三级帮助（顶层 → 命令族 → 参数
详情），覆盖 32 动词 + 全局 flag；argparse 只做「解析 + 路由」，具体动作进各
桥/编排层，不内联命令逻辑。

对应接口：doc/03-interfaces/cli-ops-interface.md §2（统一命令入口）
契约：coding-plan/cli-contract-baseline.md（32 动词 + 14 flag）
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from core.beast import BeastActivator
from core.cli_ops import CLICommandDispatcher
from core.configuration import ConfigManager, ConfigSpec, config_specs, resolve
from core.loop import LoopPlugin
from core.pet.core import PetActivator, PetManager
from core.pet.library import load_persona, load_personas
from core.runtime import build_runtime
from core.ui import CLIBridge, DesktopBridge, UIAPILayer, UiError, WebBridge

_VERSION = "0.1.0"


def main(argv: list[str] | None = None) -> int:
    """console_scripts 入口：解析 argv → 路由 → 进程退出码。"""
    args = _build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except Exception as exc:  # noqa: BLE001 — 入口兜底，统一转 stderr 退出码
        print(f"错误: {exc}", file=sys.stderr)
        return 1


# ---- argparse 构建（三级帮助：顶层 → 命令族 → 参数详情） ----


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="core-agent",
        description="CORE-Harness 无特权核心分层插件化智能体框架（可启动产品入口）",
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_VERSION}")
    _add_global_flags(parser)

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # 顶层入口（三模桥接）
    serve_p = sub.add_parser("serve", help="Web 模式：HTTP + SSE 打开单 SPA")
    serve_p.add_argument("--host", default="127.0.0.1", help="监听地址")
    serve_p.add_argument("--port", type=int, default=8000, help="监听端口")
    sub.add_parser("app", help="Desktop 模式：Tauri 壳 + sidecar")

    # 生命周期/运维
    sub.add_parser("start", help="启动实例（profile 经全局 --profile）")
    sub.add_parser("stop", help="停止实例")
    sub.add_parser("restart", help="重启实例")
    probe_p = sub.add_parser("probe", help="健康探针 → HealthStatus")
    probe_p.add_argument("--format", choices=["json"], default="json", help="输出格式")
    sub.add_parser("status", help="运行状态概览")
    sub.add_parser("doctor", help="自检诊断")
    sub.add_parser("sessions", help="枚举托管会话")

    _add_config_parser(sub)
    _add_mcp_parser(sub)
    _add_plugin_parser(sub)
    _add_skill_parser(sub)
    _add_session_parser(sub)
    _add_run_parser(sub)
    _add_release_parser(sub)
    _add_pet_parser(sub)
    _add_beast_parser(sub)

    return parser


def _add_config_parser(sub: Any) -> None:
    config = sub.add_parser("config", help="配置读写校验")
    cfg_sub = config.add_subparsers(dest="config_cmd", metavar="<config-cmd>")
    show = cfg_sub.add_parser("show", help="显示有效配置")
    show.add_argument("--format", choices=["yaml", "json"], default="yaml")
    show.add_argument("--effective", action="store_true")
    validate = cfg_sub.add_parser("validate", help="校验 config.yaml")
    validate.add_argument("--file", metavar="PATH")
    get = cfg_sub.add_parser("get", help="读单键")
    get.add_argument("key")
    setp = cfg_sub.add_parser("set", help="运行时变更（变更即生效/失败回滚）")
    setp.add_argument("key")
    setp.add_argument("value")


def _add_mcp_parser(sub: Any) -> None:
    mcp = sub.add_parser("mcp", help="MCP 端点管理")
    mcp_sub = mcp.add_subparsers(dest="mcp_cmd", metavar="<mcp-cmd>")
    serve = mcp_sub.add_parser("serve", help="启动 MCP server")
    serve.add_argument("--transport", choices=["stdio", "http", "streamable-http"], default="stdio")
    serve.add_argument("--endpoint", metavar="E")
    mcp_sub.add_parser("list", help="列出已注册 MCP 端点")
    add = mcp_sub.add_parser("add", help="运行期添加 MCP 端点")
    add.add_argument("endpoint")
    add.add_argument("--transport", metavar="T")
    add.add_argument("--command", metavar="C")
    add.add_argument("--args", nargs="*", metavar="A")
    remove = mcp_sub.add_parser("remove", help="移除 MCP 端点")
    remove.add_argument("name")


def _add_plugin_parser(sub: Any) -> None:
    plugin = sub.add_parser("plugin", help="插件/资产安装")
    pl_sub = plugin.add_subparsers(dest="plugin_cmd", metavar="<plugin-cmd>")
    install = pl_sub.add_parser("install", help="安装三方资产")
    install.add_argument("asset")
    install.add_argument("--kind", choices=["skill", "mcp", "cli"])
    uninstall = pl_sub.add_parser("uninstall", help="卸载资产")
    uninstall.add_argument("name")
    listp = pl_sub.add_parser("list", help="枚举已装资产")
    listp.add_argument("--kind", metavar="K")


def _add_skill_parser(sub: Any) -> None:
    skill = sub.add_parser("skill", help="技能市场")
    sk_sub = skill.add_subparsers(dest="skill_cmd", metavar="<skill-cmd>")
    search = sk_sub.add_parser("search", help="搜索技能市场")
    search.add_argument("query")
    install = sk_sub.add_parser("install", help="安装技能（= plugin install --kind skill）")
    install.add_argument("name")
    install.add_argument("--source", metavar="S")
    remove = sk_sub.add_parser("remove", help="卸载技能（= plugin uninstall）")
    remove.add_argument("name")


def _add_session_parser(sub: Any) -> None:
    session = sub.add_parser("session", help="会话管理")
    sess_sub = session.add_subparsers(dest="session_cmd", metavar="<session-cmd>")
    sess_sub.add_parser("create", help="新建会话（返回 session_id）")


def _add_run_parser(sub: Any) -> None:
    run = sub.add_parser("run", help="运行一轮/一个任务")
    run.add_argument("--prompt", metavar="TEXT")
    run.add_argument("--file", metavar="PATH")
    run.add_argument("--session", metavar="ID", dest="session_id")
    run.add_argument("--max-turns", type=int, metavar="N")


def _add_release_parser(sub: Any) -> None:
    release = sub.add_parser("release", help="分发")
    rel_sub = release.add_subparsers(dest="release_cmd", metavar="<release-cmd>")
    publish = rel_sub.add_parser("publish", help="发布 bundle")
    publish.add_argument("bundle")
    upgrade = rel_sub.add_parser("upgrade", help="升级")
    upgrade.add_argument("version")
    rel_sub.add_parser("rollback", help="回滚")


def _add_pet_parser(sub: Any) -> None:
    pet = sub.add_parser("pet", help="宠物模式（后台自治会话）")
    pet.add_argument("verb", nargs="?", help="gather|info|explore|walk|list|stop")
    pet.add_argument("rest", nargs=argparse.REMAINDER, help="[--name NAME] 任务描述（自由文本）")


def _add_beast_parser(sub: Any) -> None:
    summon = sub.add_parser("summon", help="召唤神兽执行前台重大任务")
    summon.add_argument("beast")
    summon.add_argument("task", nargs="*")
    recall = sub.add_parser("recall", help="召回神兽")
    recall.add_argument("beast")


def _add_global_flags(parser: argparse.ArgumentParser) -> None:
    # 启动参数（F1-F3）
    parser.add_argument("--profile", metavar="P", help="Bundle 组合清单（独立文件）")
    parser.add_argument("--cwd", metavar="DIR", help="工作目录")
    parser.add_argument("--config", metavar="PATH", help="config.yaml 路径（默认 config.yaml）")
    # feature flag（F5，外推形态：--feature NAME[=BOOL]）
    parser.add_argument(
        "--feature", action="append", metavar="NAME[=BOOL]", help="feature flag 覆盖"
    )
    # 日志（F13）
    parser.add_argument("--verbose", action="store_true", help="verbose 日志")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    parser.add_argument("--log-level", metavar="LEVEL", help="日志级别")
    # ConfigSpec 驱动 flag（F4/F6-F12 + pet.*）：单一真源，不得另起命令解析
    for spec in config_specs():
        _add_config_flag(parser, spec)


def _add_config_flag(parser: argparse.ArgumentParser, spec: ConfigSpec) -> None:
    dest = spec.key.replace(".", "_").replace("-", "_")
    help_text = f"配置 {spec.key}（env {spec.env_var}）"
    if isinstance(spec.default, bool):
        parser.add_argument(
            spec.cli_flag, dest=dest, action="store_true", default=None, help=help_text
        )
    else:
        parser.add_argument(
            spec.cli_flag,
            dest=dest,
            default=None,
            metavar=_metavar(spec.key),
            help=help_text,
        )


def _metavar(key: str) -> str:
    return key.rsplit(".", 1)[-1].replace("-", "_").upper()


# ---- 路由 ----


def _dispatch(args: argparse.Namespace) -> int:
    command: str | None = args.command
    if command is None:
        return _repl()
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    # probe / sessions / mcp / plugin / skill / release：识别但对应里程碑未落地
    print(f"命令 '{command}' 已识别，尚未接线（对应里程碑未落地）", file=sys.stderr)
    return 0


def _repl() -> int:
    """无子命令进入 Textual 交互会话循环（阻塞，退出后返回）。"""
    CLIBridge().connect()
    return 0


def _serve(args: argparse.Namespace) -> int:
    WebBridge().serve(args.host, args.port)
    return 0


def _app(args: argparse.Namespace) -> int:
    DesktopBridge().start_sidecar()
    return 0


def _ops(args: argparse.Namespace) -> int:
    dispatcher = CLICommandDispatcher()
    if args.command in ("status", "doctor"):
        print(dispatcher.status(args.command))
    else:
        dispatcher.dispatch([args.command])
    return 0


def _config(args: argparse.Namespace) -> int:
    if args.config_cmd == "get":
        value = resolve(args.key, cli=_cli_overrides(args), env=os.environ)
        print(value if value not in (None, "") else "(未配置)")
        return 0
    print(f"config {args.config_cmd} 已识别，尚未接线", file=sys.stderr)
    return 0


def _session(args: argparse.Namespace) -> int:
    if args.session_cmd != "create":
        print("用法: core-agent session create", file=sys.stderr)
        return 1
    session_id = UIAPILayer().create_session(args.profile or "cli")
    print(session_id)
    return 0


def _run(args: argparse.Namespace) -> int:
    prompt = _read_prompt(args)
    if prompt is None:
        print("用法: core-agent run [--prompt TEXT | --file PATH]", file=sys.stderr)
        return 1
    try:
        runtime = build_runtime(
            ConfigManager(yaml_path=args.config or "config.yaml", cli=_cli_overrides(args))
        )
    except Exception as exc:  # noqa: BLE001 — 配置/装配失败统一转 stderr 退出码
        print(f"装配失败: {exc}", file=sys.stderr)
        return 1
    api = UIAPILayer(
        loop=cast(LoopPlugin, runtime.loop),
        memory=runtime.memory,
        tools=runtime.tools,
        config=runtime.config,
    )
    api.set_llm_config(runtime.app.llm)
    session_id = args.session_id or api.create_session("cli")
    try:
        asyncio.run(_stream(api, session_id, prompt))
    except UiError as exc:
        print(f"运行失败: {exc}", file=sys.stderr)
        return 1
    return 0


async def _stream(api: UIAPILayer, session_id: str, prompt: str) -> None:
    async for event in api.run_loop(session_id, prompt):
        payload = event.payload if event.payload is not None else ""
        print(f"[{event.type}] {payload}")


def _read_prompt(args: argparse.Namespace) -> str | None:
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if args.prompt:
        return args.prompt
    return None


def _pet(args: argparse.Namespace) -> int:
    cli = _cli_overrides(args)
    if not _as_bool(resolve("pet.enabled", cli=cli, env=os.environ)):
        print(
            "宠物模式未启用（pet.enabled=false，可用 --pet-enabled 或 CORE_PET_ENABLED 开启）",
            file=sys.stderr,
        )
        return 0
    persons_dir = str(resolve("pet.persons_dir", cli=cli, env=os.environ) or "persons")
    verb: str | None = args.verb
    name, rest = _split_pet_name(list(args.rest or []))

    manager = PetManager()
    activator = PetActivator(manager=manager)

    if verb is None:
        print(
            "用法: core-agent pet <verb> [--name NAME] [...]（gather|info|explore|walk|list|stop）"
        )
        return 0
    if verb == "list":
        _print_pets(manager, persons_dir)
        return 0
    if verb == "stop":
        if not rest:
            print("用法: core-agent pet stop <session_id>", file=sys.stderr)
            return 1
        manager.stop(rest[0])
        print(f"已停止宠物会话 {rest[0]}")
        return 0
    session = activator.activate_from_cli(verb, rest, persona=_load_persona(persons_dir, name))
    print(f"已激活宠物会话 {session.session_id}（verb={verb}，状态 {session.state.value}）")
    return 0


def _print_pets(manager: PetManager, persons_dir: str) -> None:
    personas = load_personas(Path(persons_dir))
    if personas:
        print("可用 persona：")
        for name, persona in sorted(personas.items()):
            print(f"  - {name}: {persona.species}")
    else:
        print(f"（目录 {persons_dir} 无 persona，将用默认人格）")
    pets = manager.list()
    if pets:
        print("已激活宠物：")
        for pet in pets:
            print(f"  - {pet.session_id}: {pet.state.value}")
    else:
        print("（当前无激活宠物）")


def _split_pet_name(rest: list[str]) -> tuple[str | None, list[str]]:
    """从 free-text rest 提取 `--name NAME`，其余为任务描述（robust 处理任意顺序）。"""
    name: str | None = None
    task: list[str] = []
    i = 0
    while i < len(rest):
        if rest[i] == "--name" and i + 1 < len(rest):
            name = rest[i + 1]
            i += 2
        else:
            task.append(rest[i])
            i += 1
    return name, task


def _load_persona(persons_dir: str, name: str | None):
    if not name:
        return None
    path = Path(persons_dir) / f"{name}.md"
    if not path.is_file():
        print(f"persona 文件不存在: {path}", file=sys.stderr)
        return None
    return load_persona(path)


def _summon(args: argparse.Namespace) -> int:
    session = asyncio.run(BeastActivator().activate_from_cli(args.beast, list(args.task or [])))
    print(f"已召唤神兽 {session.beast.agent_id}（状态 {session.state.value}）")
    return 0


def _recall(args: argparse.Namespace) -> int:
    session = BeastActivator().recall_from_cli(args.beast)
    print(f"已召回神兽 {session.beast.agent_id}（状态 {session.state.value}）")
    return 0


# ---- 路由表（纯路由，动作进各 handler；不内联命令逻辑） ----


_HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "serve": _serve,
    "app": _app,
    "pet": _pet,
    "summon": _summon,
    "recall": _recall,
    "session": _session,
    "run": _run,
    "config": _config,
    "start": _ops,
    "stop": _ops,
    "restart": _ops,
    "status": _ops,
    "doctor": _ops,
}


# ---- 工具 ----


def _cli_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """从 argparse namespace 收集显式设置的 ConfigSpec flag（key=配置键）。"""
    cli: dict[str, Any] = {}
    for spec in config_specs():
        dest = spec.key.replace(".", "_").replace("-", "_")
        value = getattr(args, dest, None)
        if value is not None:
            cli[spec.key] = value
    return cli


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes", "on")
