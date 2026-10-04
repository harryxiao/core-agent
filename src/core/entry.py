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
import hashlib
import json
import os
import sys
import uuid
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from core.cli_ops import CLICommandDispatcher
from core.configuration import (
    AppConfig,
    ConfigManager,
    ConfigSpec,
    ConfigurationError,
    config_specs,
    resolve,
)
from core.deployment import (
    ClientConnection,
    DeploymentError,
    HarnessHost,
    LifecycleController,
    ReleaseInfo,
    ReleaseManager,
    ServeStateStore,
)
from core.evolution import EvolutionError, GenerationCandidate
from core.loop import LoopPlugin
from core.orchestration import Plan, TaskScheduler, plan_from_dict
from core.permission import (
    ApprovalChannel,
    ApprovalRequest,
    ApprovalTicket,
    ApprovalWorkflow,
)
from core.pet.core import PetManager
from core.pet.library import load_persona, load_personas
from core.plugin_registry import DomainError, PluginInstaller, PluginKind, PluginSource
from core.plugins import InstallDispatcher
from core.runtime import Runtime, build_runtime
from core.skills import SkillLibrary
from core.tools import StubPlugin, ToolProvider
from core.ui import CLIBridge, DesktopBridge, UIAPILayer, UiError, WebBridge
from core.ui.repl import format_action_event, format_task_event

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
    _add_memory_parser(sub)
    _add_evolve_parser(sub)
    _add_run_parser(sub)
    _add_task_parser(sub)
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


def _add_memory_parser(sub: Any) -> None:
    memory = sub.add_parser("memory", help="记忆维护")
    mem_sub = memory.add_subparsers(dest="memory_cmd", metavar="<memory-cmd>")
    mem_sub.add_parser("maintain", help="触发一次记忆维护（压实 + 遗忘归档）")


def _add_evolve_parser(sub: Any) -> None:
    evolve = sub.add_parser("evolve", help="进化冷路径")
    ev_sub = evolve.add_subparsers(dest="evolve_cmd", metavar="<evolve-cmd>")
    ev_sub.add_parser("run", help="强制跑一轮进化冷路径（诊断/提案 dry-run）")
    ev_sub.add_parser("pending", help="列出待人工确认的候选")
    confirm = ev_sub.add_parser("confirm", help="确认候选并发布结晶")
    confirm.add_argument("candidate_id", help="候选身份（见 evolve pending）")
    confirm.add_argument("--approver", default="human", metavar="NAME")
    confirm.add_argument("--note", metavar="TEXT")
    reject = ev_sub.add_parser("reject", help="拒绝候选（不再发布）")
    reject.add_argument("candidate_id", help="候选身份（见 evolve pending）")
    reject.add_argument("--note", metavar="TEXT")


def _add_run_parser(sub: Any) -> None:
    run = sub.add_parser("run", help="运行一轮/一个任务")
    run.add_argument("--prompt", metavar="TEXT")
    run.add_argument("--file", metavar="PATH")
    run.add_argument("--session", metavar="ID", dest="session_id")
    run.add_argument("--max-turns", type=int, metavar="N")


def _add_task_parser(sub: Any) -> None:
    task = sub.add_parser("task", help="多任务编排：拆解 → 波次执行 → 验收")
    task.add_argument("goal", nargs="?", metavar="GOAL", help="任务目标")
    task.add_argument("--task-id", metavar="ID", dest="task_id", help="任务 id（审计/续跑定位）")
    task.add_argument("--resume", metavar="ID", dest="resume_id", help="从该任务最新检查点续跑")


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
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="config.yaml 路径（默认 cwd config.yaml，缺失回落 ~/.core-agent/config.yaml）",
    )
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
        return _repl(args)
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    # mcp：识别但 Phase 12 未落地
    print(f"命令 '{command}' 已识别，尚未接线（对应里程碑未落地）", file=sys.stderr)
    return 0


def _build_ui(args: argparse.Namespace, *, interactive: bool = False) -> UIAPILayer | None:
    """装配真 runtime + UIAPILayer 并注入 LLM 配置（四入口共用）；失败返回 None。

    interactive=True 时创建交互审批通道：confirm 门经终端 y/n 决断；
    非交互入口无通道，高风险 fail-closed 拒绝。
    """
    approval = ApprovalChannel() if interactive else None
    try:
        runtime = build_runtime(
            ConfigManager(yaml_path=args.config, cli=_cli_overrides(args)),
            approver=approval.ask if approval is not None else None,
        )
    except Exception as exc:  # noqa: BLE001 — 配置/装配失败统一转 stderr 退出码
        print(f"装配失败: {exc}", file=sys.stderr)
        return None
    api = UIAPILayer(
        loop=cast(LoopPlugin, runtime.loop),
        memory=runtime.memory,
        tools=runtime.tools,
        config=runtime.config,
        approval=approval,
        orchestrator=runtime.orchestrator,  # /task 命令驱动同一编排器
        pet_activator=runtime.pet_activator,  # WebUI 自然语言宠物激活
    )
    api.set_llm_config(runtime.app.llm)
    return api


def _repl(args: argparse.Namespace) -> int:
    """无子命令进入 Textual 交互会话循环（阻塞，退出后返回）。"""
    api = _build_ui(args, interactive=True)
    if api is None:
        return 1
    CLIBridge(api=api).connect()
    return 0


def _serve(args: argparse.Namespace) -> int:
    api = _build_ui(args)
    if api is None:
        return 1
    host = HarnessHost(path=_state_path("sessions.jsonl"))
    host.serve()
    host.accept(ClientConnection(client_id="serve"))
    store = ServeStateStore(_state_path("serve.json"))
    store.mark_running()
    try:
        WebBridge(api=api).serve(args.host, args.port)
    finally:
        store.mark_stopped()
    return 0


def _app(args: argparse.Namespace) -> int:
    api = _build_ui(args)
    if api is None:
        return 1
    DesktopBridge(api=api).start_sidecar()
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
    mgr = ConfigManager(yaml_path=args.config, cli=_cli_overrides(args))
    if args.config_cmd == "show":
        return _config_show(mgr, args)
    if args.config_cmd == "validate":
        return _config_validate(args)
    if args.config_cmd == "set":
        return _config_set(mgr, args)
    print(f"config {args.config_cmd} 已识别，尚未接线", file=sys.stderr)
    return 0


def _config_show(mgr: ConfigManager, args: argparse.Namespace) -> int:
    """显示有效配置（env > cli > yaml 合并后的 AppConfig）。"""
    try:
        app = mgr.load()
    except ConfigurationError as exc:
        print(f"配置无效: {exc}", file=sys.stderr)
        return 1
    data = _dump_config(app)
    if getattr(args, "format", "yaml") == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(_to_yaml(data))
    return 0


def _config_validate(args: argparse.Namespace) -> int:
    """校验 config.yaml：无效时打印错误并 exit 1。"""
    path = getattr(args, "file", None) or args.config
    try:
        ConfigManager(yaml_path=path).load()
    except ConfigurationError as exc:
        print(f"无效: {exc}", file=sys.stderr)
        return 1
    print("配置有效")
    return 0


def _config_set(mgr: ConfigManager, args: argparse.Namespace) -> int:
    """运行时变更配置：apply_change 校验通过才生效，写回 yaml 并 revalidate。"""
    try:
        patch = _key_to_patch(args.key, args.value)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        mgr.load()
    except ConfigurationError as exc:
        print(f"配置无效，无法变更: {exc}", file=sys.stderr)
        return 1
    try:
        mgr.apply_change(patch)
    except ConfigurationError as exc:
        print(f"变更失败: {exc}", file=sys.stderr)
        return 1
    try:
        mgr.write_patch(patch)
        mgr.load()  # revalidate：从磁盘重读重校验
    except ConfigurationError as exc:
        print(f"写回失败: {exc}", file=sys.stderr)
        return 1
    print(f"已设置 {args.key}={args.value}（已写回 config.yaml）")
    return 0


def _plugin(args: argparse.Namespace) -> int:
    """插件/资产安装生命周期（process 内注册，跨进程持久化未接）。"""
    if args.plugin_cmd == "install":
        return _plugin_install(_build_installer(), args.asset, PluginKind(args.kind or "skill"))
    if args.plugin_cmd == "list":
        return _plugin_list(_build_installer(), args.kind)
    if args.plugin_cmd == "uninstall":
        return _plugin_uninstall(_build_installer(), args.name)
    print(f"plugin {args.plugin_cmd} 已识别，尚未接线", file=sys.stderr)
    return 0


def _skill(args: argparse.Namespace) -> int:
    """技能市场：search 走本地库（市场拉取未接）；install/remove 别名到 plugin。"""
    if args.skill_cmd == "search":
        return _skill_search(SkillLibrary(), args.query)
    if args.skill_cmd == "install":
        return _plugin_install(_build_installer(), args.name, PluginKind.SKILL)
    if args.skill_cmd == "remove":
        return _skill_remove(SkillLibrary(), args.name)
    print(f"skill {args.skill_cmd} 已识别，尚未接线", file=sys.stderr)
    return 0


def _release(args: argparse.Namespace) -> int:
    """发布 / 升级 / 回滚（ReleaseManager，版本登记持久化，真实制品仓库未接）。"""
    manager = ReleaseManager(path=_state_path("releases.json"))
    try:
        if args.release_cmd == "publish":
            version = manager.publish(
                ReleaseInfo(version=args.bundle, hash=_content_hash(args.bundle))
            )
            print(f"已发布版本 {version}")
            return 0
        if args.release_cmd == "upgrade":
            manager.upgrade(args.version)
            print(f"已升级到 {args.version}")
            return 0
        if args.release_cmd == "rollback":
            manager.rollback()
            print(f"已回滚到 {manager.current}")
            return 0
    except DeploymentError as exc:
        print(f"发布失败: {exc}", file=sys.stderr)
        return 1
    print(f"release {args.release_cmd} 已识别，尚未接线", file=sys.stderr)
    return 0


def _probe(args: argparse.Namespace) -> int:
    """健康探针 → HealthStatus：alive 时 exit 0，否则 exit 1。"""
    store = ServeStateStore(_state_path("serve.json"))
    status = LifecycleController(probe_fn=store.probe).probe()
    if getattr(args, "format", "json") == "json":
        print(json.dumps({"alive": status.alive, "detail": status.detail}, ensure_ascii=False))
    else:
        print(f"alive={status.alive}" + (f" detail={status.detail}" if status.detail else ""))
    return 0 if status.alive else 1


def _sessions(args: argparse.Namespace) -> int:
    """枚举 Harness Host 当前活跃会话（读持久化会话文件）。"""
    sessions = HarnessHost(path=_state_path("sessions.jsonl")).sessions()
    if not sessions:
        print("（无活跃会话）")
        return 0
    for session in sessions:
        print(f"{session.session_id} ({session.client_id}, {session.state.value})")
    return 0


# ---- 命令辅助 ----


def _build_installer() -> PluginInstaller:
    """装配轻量插件安装器（无需 LLM/loop，仅本地来源解析）。"""
    skills = SkillLibrary()
    provider = ToolProvider()
    dispatcher = InstallDispatcher(skill_library=skills, tool_provider=provider)
    return PluginInstaller(
        source_resolver=dispatcher.resolve,
        installer=dispatcher.install,
        uninstaller=dispatcher.uninstall,
    )


def _plugin_install(installer: PluginInstaller, asset: str, kind: PluginKind) -> int:
    try:
        item = installer.discover(PluginSource.LOCAL_PATH, asset, kind)
        installer.install(item)
        manifest = item.manifest
        plugin_id = str(
            manifest.get("plugin_id")
            or manifest.get("skill_id")
            or manifest.get("name")
            or f"installed.{kind.value}.{asset}"
        )
        installer.register(item, StubPlugin(plugin_id, manifest))
    except DomainError as exc:
        print(f"安装失败: {exc}", file=sys.stderr)
        return 1
    print(f"已安装 {kind.value} 资产: {asset}")
    return 0


def _plugin_list(installer: PluginInstaller, kind: str | None) -> int:
    assets = installer.installed()
    if kind:
        assets = [a for a in assets if a["kind"] == kind]
    if not assets:
        print("（无已安装资产）")
        return 0
    for item in assets:
        print(f"{item['plugin_id']} ({item['kind']}, {item['source']})")
    return 0


def _plugin_uninstall(installer: PluginInstaller, name: str) -> int:
    try:
        installer.uninstall(name)
    except DomainError as exc:
        print(f"卸载失败: {exc}", file=sys.stderr)
        return 1
    print(f"已卸载 {name}")
    return 0


def _skill_search(library: SkillLibrary, query: str) -> int:
    q = query.lower()
    matches = [
        s for s in library.all_skills() if q in s.skill_id.lower() or q in s.description.lower()
    ]
    if not matches:
        print(f"（未找到匹配技能: {query}）")
        return 0
    for skill in matches:
        print(f"{skill.skill_id}: {skill.description}")
    return 0


def _skill_remove(library: SkillLibrary, name: str) -> int:
    try:
        library.remove(name)
    except KeyError:
        print(f"技能未注册: {name}", file=sys.stderr)
        return 1
    print(f"已卸载技能 {name}")
    return 0


def _dump_config(app: AppConfig) -> dict[str, Any]:
    """AppConfig → dict（仅含 ${VAR} 引用，不含明文密钥）。"""
    data: dict[str, Any] = asdict(app)
    for key in ("im", "pet", "judgment"):
        if data.get(key) is None:
            data.pop(key, None)
    return data


def _to_yaml(data: dict[str, Any], indent: int = 0) -> str:
    """极简嵌套 dict → 缩进 yaml（仅标量 + 映射，够 config show 用）。"""
    lines: list[str] = []
    pad = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{pad}{key}:")
            lines.append(_to_yaml(cast(dict[str, Any], value), indent + 1))
        else:
            lines.append(f"{pad}{key}: {_yaml_scalar(value)}")
    return "\n".join(lines)


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _key_to_patch(key: str, value: str) -> dict[str, Any]:
    """点分键 → apply_change 支持的嵌套 patch（仅 llm./features./im.）。"""
    top, _, rest = key.partition(".")
    if top not in ("llm", "features", "im") or not rest:
        raise ValueError(f"config set 暂不支持键: {key}（仅支持 llm./features./im.）")  # noqa: TRY003
    node: dict[str, Any] = {}
    parts = rest.split(".")
    target = node
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = _coerce(value)
    return {top: node}


def _coerce(value: str) -> Any:
    lowered = value.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _content_hash(version: str) -> str:
    """bundle 内容哈希（CLI 无真实制品内容，退化为版本名哈希）。"""
    return hashlib.sha256(version.encode("utf-8")).hexdigest()[:16]


def _state_path(name: str) -> Path:
    """全局状态文件路径：$CORE_STATE_DIR（缺省 ~/.core/state）/<name>。

    env 覆盖便于测试隔离（对齐 config 的 env 覆盖惯例）；缺省对齐 ~/.core/Core.md
    全局约定。
    """
    base = os.environ.get("CORE_STATE_DIR") or str(Path.home() / ".core" / "state")
    return Path(base) / name


def _session(args: argparse.Namespace) -> int:
    if args.session_cmd != "create":
        print("用法: core-agent session create", file=sys.stderr)
        return 1
    session_id = UIAPILayer().create_session(args.profile or "cli")
    print(session_id)
    return 0


def _memory(args: argparse.Namespace) -> int:
    """`memory maintain`：装配 runtime → 触发一次记忆维护（压实 + 遗忘），打印归档条数。"""
    if args.memory_cmd != "maintain":
        print("用法: core-agent memory maintain", file=sys.stderr)
        return 1
    try:
        runtime = build_runtime(ConfigManager(yaml_path=args.config, cli=_cli_overrides(args)))
    except Exception as exc:  # noqa: BLE001 — 配置/装配失败统一转 stderr 退出码
        print(f"装配失败: {exc}", file=sys.stderr)
        return 1
    memory = runtime.memory
    memory.compact()
    forgotten = memory.forget()
    print(f"记忆维护完成：归档 {len(forgotten)} 条")
    return 0


_EVOLVE_USAGE = "用法: core-agent evolve {run|pending|confirm <id>|reject <id>}"


def _evolve(args: argparse.Namespace) -> int:
    """进化冷路径操作面：跑一轮 / 看待确认 / 确认发布 / 拒绝。"""
    handlers = {
        "run": _evolve_run,
        "pending": _evolve_pending,
        "confirm": _evolve_confirm,
        "reject": _evolve_reject,
    }
    handler = handlers.get(args.evolve_cmd or "")
    if handler is None:
        print(_EVOLVE_USAGE, file=sys.stderr)
        return 1
    return handler(args)


def _evolve_runtime(args: argparse.Namespace) -> Any | None:
    """装配 runtime；失败转 stderr 并返回 ``None``（调用方给退出码 1）。"""
    try:
        return build_runtime(ConfigManager(yaml_path=args.config, cli=_cli_overrides(args)))
    except Exception as exc:  # noqa: BLE001 — 配置/装配失败统一转 stderr 退出码
        print(f"装配失败: {exc}", file=sys.stderr)
        return None


def _evolve_run(args: argparse.Namespace) -> int:
    """`evolve run`：**强制**跑一轮进化冷路径，打印结局。"""
    runtime = _evolve_runtime(args)
    if runtime is None:
        return 1
    evolution = runtime.evolution
    if evolution is None:
        return _module_disabled("evolution")
    outcome = evolution.maybe_run(force=True)
    if outcome is None:
        print("进化冷路径完成：无候选（no_op）")
    else:
        target = f"，目标 {outcome.skill_id}" if outcome.skill_id else ""
        print(f"进化冷路径完成：{outcome.status}{target}")
        if outcome.status == "pending" and outcome.candidate is not None:
            print(f"待确认候选：{outcome.candidate.candidate_id}（core-agent evolve pending）")
    return 0


def _evolve_pending(args: argparse.Namespace) -> int:
    """`evolve pending`：列出待人工确认的候选。"""
    runtime = _evolve_runtime(args)
    if runtime is None:
        return 1
    evolution = runtime.evolution
    if evolution is None:
        return _module_disabled("evolution")
    candidates = evolution.engine.pending()
    if not candidates:
        print("待确认队列为空")
        return 0
    print(f"待确认候选 {len(candidates)} 项：")
    for candidate in candidates:
        print(
            f"  {candidate.candidate_id}  风险={candidate.risk_level}  "
            f"目标={candidate.target_plugin}  {candidate.delta.get('issue', '')}"
        )
    return 0


def _resolve_candidate(args: argparse.Namespace, engine: Any) -> GenerationCandidate | None:
    """定位候选；不存在或已不在待确认态则反馈并非零退出。"""
    candidate = engine.find(args.candidate_id)
    if candidate is None:
        print(f"候选不在待确认队列: {args.candidate_id}", file=sys.stderr)
        return None
    if candidate.status != "pending":
        print(f"候选不处于待确认状态（{candidate.status}）: {args.candidate_id}", file=sys.stderr)
        return None
    return candidate


def _evolve_confirm(args: argparse.Namespace) -> int:
    """`evolve confirm`：确认候选并发布结晶（架构级候选由本操作面签发审批单）。"""
    runtime = _evolve_runtime(args)
    if runtime is None:
        return 1
    evolution = runtime.evolution
    if evolution is None:
        return _module_disabled("evolution")
    engine = evolution.engine
    candidate = _resolve_candidate(args, engine)
    if candidate is None:
        return 1
    approval = _sign_approval(candidate, approver=args.approver, note=args.note)
    try:
        engine.confirm(candidate, approval=approval)
        outcome = engine.crystallize(candidate)
    except EvolutionError as exc:
        print(f"确认失败: {exc}", file=sys.stderr)
        return 1
    print(f"已确认并发布：{outcome.status}（{candidate.target_plugin}）")
    return 0


def _sign_approval(
    candidate: GenerationCandidate, *, approver: str, note: str | None
) -> ApprovalTicket | None:
    """架构级候选的审批单签发：本操作面即「人工」来源（技能库级无需工单）。"""
    if candidate.risk_level != "high":
        return None
    workflow = ApprovalWorkflow()
    ticket = workflow.create(
        ApprovalRequest(
            op="evolution.publish",
            target=candidate.target_plugin,
            impact_summary=str(candidate.delta.get("issue", "")),
            rollback_plan="dissolve 回 L3（技能标 deprecated + 教训写回 L2）",
            trace_id="evolution",
        )
    )
    workflow.approve(ticket, approver=approver, note=note)
    return ticket


def _evolve_reject(args: argparse.Namespace) -> int:
    """`evolve reject`：拒绝候选（不再发布）。"""
    runtime = _evolve_runtime(args)
    if runtime is None:
        return 1
    evolution = runtime.evolution
    if evolution is None:
        return _module_disabled("evolution")
    candidate = _resolve_candidate(args, evolution.engine)
    if candidate is None:
        return 1
    evolution.engine.reject(candidate, reason=args.note)
    print(f"已拒绝：{candidate.target_plugin}（{candidate.candidate_id}）")
    return 0


def _run(args: argparse.Namespace) -> int:
    prompt = _read_prompt(args)
    if prompt is None:
        print("用法: core-agent run [--prompt TEXT | --file PATH]", file=sys.stderr)
        return 1
    api = _build_ui(args)
    if api is None:
        return 1
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
        # 增量 reply_delta（Event 层映射为 dict 载荷的 loop.result）不逐行打印，
        # 完整回复由终态 LoopResult 事件携带
        if event.type == "loop.result" and isinstance(payload, dict):
            continue
        if event.type.startswith("loop.action_"):  # 工具动作行（与 TUI 同构单行）
            line = format_action_event(event.type.removeprefix("loop."), payload)
            if line:
                print(line)
            continue
        print(f"[{event.type}] {payload}")


def _task(args: argparse.Namespace) -> int:  # noqa: PLR0911 — 入口校验天然多早退
    """多任务编排入口：拆解 → 波次执行 → 验收，流式打印进度事件。

    非交互入口：无审批通道，高风险工具动作 fail-closed（与 run/serve 一致）。
    """
    if not args.goal and not args.resume_id:
        print("用法: core-agent task <目标> [--task-id ID | --resume ID]", file=sys.stderr)
        return 1
    try:
        runtime = build_runtime(ConfigManager(yaml_path=args.config, cli=_cli_overrides(args)))
    except Exception as exc:  # noqa: BLE001 — 配置/装配失败统一转 stderr 退出码
        print(f"装配失败: {exc}", file=sys.stderr)
        return 1
    goal = args.goal or ""
    task_id = args.task_id or f"task-{uuid.uuid4().hex[:8]}"
    plan: Plan | None = None
    completed: set[str] | None = None
    results: dict[str, str] | None = None
    if args.resume_id:
        cps = runtime.checkpoints.list_checkpoints(task_id=args.resume_id)
        if not cps:
            print(f"未找到任务 {args.resume_id} 的检查点", file=sys.stderr)
            return 1
        state = runtime.checkpoints.get_snapshot(cps[-1].checkpoint_id).state
        if state.get("done"):
            print(f"[task_finished] 任务 {args.resume_id} 已完成（检查点 done）")
            return 0
        if not isinstance(state.get("plan"), dict):
            print("检查点缺少计划，无法续跑；请直接给定 <目标> 重新拆解", file=sys.stderr)
            return 1
        plan = plan_from_dict(state["plan"])
        completed = {str(o["subtask_id"]) for o in state.get("outcomes", []) if o.get("ok")}
        results = {  # 已完成子任务的回复重建（依赖交接上下文）
            str(o["subtask_id"]): str(o.get("reply", ""))
            for o in state.get("outcomes", [])
            if o.get("ok")
        }
        goal = plan.goal or goal
        task_id = args.resume_id
    if not goal:
        print("缺少任务目标（检查点未携带且未给定 <目标>）", file=sys.stderr)
        return 1
    failed = asyncio.run(
        _stream_task(runtime.orchestrator, task_id, goal, plan, completed, results)
    )
    return 1 if failed else 0


async def _stream_task(  # noqa: PLR0913, PLR0917 — 续跑注入面参数组
    orchestrator: TaskScheduler,
    task_id: str,
    goal: str,
    plan: Plan | None,
    completed: set[str] | None,
    results: dict[str, str] | None,
) -> bool:
    """流式驱动编排器并打印进度事件；返回是否终态失败（task_failed）。"""
    failed = False
    async for event in orchestrator.astream(
        task_id, goal, plan=plan, completed=completed, results=results
    ):
        line = format_task_event(event.type, event.payload)
        if line:
            print(line)
        if event.type == "task_failed":
            failed = True
    return failed


def _read_prompt(args: argparse.Namespace) -> str | None:
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if args.prompt:
        return args.prompt
    return None


def _module_disabled(module: str) -> int:
    """已关闭模块的入口拒绝（`features.<模块>: false`）：说明 + 退出 0。

    对齐既有 `pet.enabled` 未启用形态：请求的功能不可用不是进程错误；文案含模块名与开关名，
    便于脚本判读（见 configuration spec「功能开关（feature flag）」）。
    """
    print(
        f"{module} 模块已关闭（features.{module}=false，移除该项或改为 true 即恢复缺省装配）",
        file=sys.stderr,
    )
    return 0


def _pet(args: argparse.Namespace) -> int:  # noqa: PLR0911 — CLI 分支各自退出码
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

    if verb is None:
        print(
            "用法: core-agent pet <verb> [--name NAME] [...]（gather|info|explore|walk|list|stop）"
        )
        return 0
    try:
        runtime = build_runtime(ConfigManager(yaml_path=args.config, cli=cli))
    except Exception as exc:  # noqa: BLE001 — 配置/装配失败统一转 stderr 退出码
        print(f"装配失败: {exc}", file=sys.stderr)
        return 1
    manager = runtime.pet_manager
    activator = runtime.pet_activator
    if manager is None or activator is None:
        return _module_disabled("pet")
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


def _beast_runtime(args: argparse.Namespace) -> Runtime | None:
    """装配运行时（与 `_pet` 同口径）：配置/装配失败转 stderr 并返回 None。

    0057 前 summon/recall 造裸 `BeastActivator()`——那是空装配（无 loop / 无记忆 / 无神通
    路由），与规格 R4「独立 loop + 共享记忆」不符。
    """
    try:
        return build_runtime(ConfigManager(yaml_path=args.config, cli=_cli_overrides(args)))
    except Exception as exc:  # noqa: BLE001 — 配置/装配失败统一转 stderr 退出码
        print(f"装配失败: {exc}", file=sys.stderr)
        return None


def _summon(args: argparse.Namespace) -> int:
    runtime = _beast_runtime(args)
    if runtime is None:
        return 1
    activator = runtime.beast_activator
    if activator is None:
        return _module_disabled("beast")
    session = asyncio.run(activator.activate_from_cli(args.beast, list(args.task or [])))
    print(f"已召唤神兽 {session.beast.agent_id}（状态 {session.state.value}）")
    return 0


def _recall(args: argparse.Namespace) -> int:
    runtime = _beast_runtime(args)
    if runtime is None:
        return 1
    activator = runtime.beast_activator
    if activator is None:
        return _module_disabled("beast")
    session = activator.recall_from_cli(args.beast)
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
    "memory": _memory,
    "evolve": _evolve,
    "run": _run,
    "task": _task,
    "config": _config,
    "plugin": _plugin,
    "skill": _skill,
    "release": _release,
    "probe": _probe,
    "sessions": _sessions,
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
