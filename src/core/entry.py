"""产品化入口层（entry）：argparse 全命令面 + 路由到三桥/编排层。

`core-agent` 可安装、可启动的入口：解析 argv，路由到三桥（CLI/Web/Desktop）与
编排层（pet/beast/session），`-h/--help` 输出三级帮助（顶层 → 命令族 → 参数
详情），覆盖 33 动词 + 全局 flag；argparse 只做「解析 + 路由」，具体动作进各
桥/编排层，不内联命令逻辑。

对应接口：doc/03-interfaces/cli-ops-interface.md §2（统一命令入口）
契约：coding-plan/cli-contract-baseline.md（33 动词 + 14 flag）
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import difflib
import json
import os
import sys
import time
import uuid
import warnings
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from core.cli_ops import CLICommandDispatcher
from core.composition import BundlePackager, CompositionError
from core.configuration import (
    AppConfig,
    ConfigManager,
    ConfigSpec,
    ConfigurationError,
    config_specs,
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
from core.diagnostics import (
    ChainHandle,
    Deps,
    collect_doctor,
    collect_status,
    render,
)
from core.durability import DurabilityError
from core.evolution import Benchmark, BenchmarkRegistry, EvolutionError, GenerationCandidate
from core.evolution.executor import COMMIT_TRACE, IMPLEMENT_OP
from core.llm_provider import LLMRequest, Message
from core.loop import LoopPlugin
from core.mcp import (
    EndpointRecord,
    MCPClient,
    MCPEndpoint,
    MCPEndpointRegistry,
    MCPError,
    MCPServer,
    default_endpoint_name,
    mcp_endpoints_path,
)
from core.memory import FileBackend, MemoryEntry, MemoryStore, TranscriptStore, redact_secrets
from core.notes import (
    NoteEntry,
    NoteError,
    NoteStore,
    promote_session_summary,
    render_note,
    slug_topic,
)
from core.orchestration import Plan, TaskScheduler, plan_from_dict
from core.permission import (
    ApprovalChannel,
    ApprovalRequest,
    ApprovalTicket,
    ApprovalWorkflow,
    SandboxManager,
    SandboxPolicy,
)
from core.pet.core import (
    FAILED,
    WOKEN,
    PetControl,
    PetError,
    PetManager,
    PetWakeDriver,
    WakeOutcome,
)
from core.pet.library import load_persona, load_personas
from core.plugin_registry import DomainError, PluginInstaller, PluginKind, PluginSource
from core.plugins import InstallDispatcher, default_install_store
from core.rag import RAGError
from core.runtime import KNOWN_FEATURE_MODULES, Runtime, build_runtime
from core.skillhub import (
    MarketIndex,
    SkillHubClient,
    SkillHubError,
    SkillPublisher,
    TrustVerifier,
)
from core.skills import Skill, SkillLibrary, VersionManager
from core.tools import StubPlugin, ToolProvider, builtin_tools
from core.ui import CLIBridge, DesktopBridge, SessionRegistry, UIAPILayer, UiError, WebBridge
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
    app_p = sub.add_parser("app", help="Desktop 模式：Tauri 壳 + sidecar")
    app_p.add_argument("--port", type=int, default=8000, help="sidecar 后端监听端口")

    # 生命周期/运维
    sub.add_parser("start", help="启动实例（profile 经全局 --profile）")
    sub.add_parser("stop", help="停止实例")
    sub.add_parser("restart", help="重启实例")
    probe_p = sub.add_parser("probe", help="健康探针 → HealthStatus")
    probe_p.add_argument("--format", choices=["json"], default="json", help="输出格式")
    sub.add_parser("status", help="运行状态概览")
    sub.add_parser("doctor", help="自检诊断")
    sub.add_parser("sessions", help="枚举 Harness Host 连接记录（≠ 对话会话，见 session list）")

    _add_config_parser(sub)
    _add_mcp_parser(sub)
    _add_plugin_parser(sub)
    _add_skill_parser(sub)
    _add_session_parser(sub)
    _add_memory_parser(sub)
    _add_rag_parser(sub)
    _add_notes_parser(sub)
    _add_evolve_parser(sub)
    _add_run_parser(sub)
    _add_task_parser(sub)
    _add_release_parser(sub)
    _add_time_travel_parser(sub)
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
    serve.add_argument(
        "--whitelist", metavar="TOOLS", default="", help="显式开放的工具（逗号分隔）"
    )
    mcp_sub.add_parser("list", help="列出已注册 MCP 端点")
    add = mcp_sub.add_parser("add", help="运行期添加 MCP 端点")
    add.add_argument("endpoint")
    add.add_argument(
        "--name", metavar="N", help="端点名（缺省派生：URL → 主机名 / 命令行 → 命令基名）"
    )
    add.add_argument("--transport", metavar="T")
    add.add_argument("--command", dest="mcp_command", metavar="C")
    add.add_argument("--args", dest="mcp_args", nargs="*", metavar="A")
    remove = mcp_sub.add_parser("remove", help="移除 MCP 端点")
    remove.add_argument("name")


def _add_plugin_parser(sub: Any) -> None:
    plugin = sub.add_parser("plugin", help="插件/资产安装")
    pl_sub = plugin.add_subparsers(dest="plugin_cmd", metavar="<plugin-cmd>")
    install = pl_sub.add_parser("install", help="安装三方资产")
    install.add_argument("asset")
    install.add_argument("--kind", choices=["skill", "mcp", "cli"])
    install.add_argument(
        "--source",
        choices=[source.value for source in PluginSource],
        default=PluginSource.LOCAL_PATH.value,
        metavar="S",
        help="来源类型（缺省 local-path）",
    )
    uninstall = pl_sub.add_parser("uninstall", help="卸载资产")
    uninstall.add_argument("name")
    listp = pl_sub.add_parser("list", help="枚举已装资产")
    listp.add_argument("--kind", metavar="K")


def _add_skill_parser(sub: Any) -> None:
    skill = sub.add_parser("skill", help="技能市场")
    sk_sub = skill.add_subparsers(dest="skill_cmd", metavar="<skill-cmd>")
    search = sk_sub.add_parser("search", help="搜索技能市场")
    search.add_argument("query")
    search.add_argument("--source", metavar="S")
    install = sk_sub.add_parser("install", help="从技能市场安装（签名校验后注册为 draft）")
    install.add_argument("name")
    install.add_argument("--source", metavar="S")
    remove = sk_sub.add_parser("remove", help="卸载技能（= plugin uninstall）")
    remove.add_argument("name")
    activate = sk_sub.add_parser("activate", help="显式启用 draft 技能（draft → active，方可路由）")
    activate.add_argument("name")
    publish = sk_sub.add_parser("publish", help="发布本地技能到市场（进入 pending 审核）")
    publish.add_argument("name")
    publish.add_argument("--source", metavar="S")
    review = sk_sub.add_parser("review", help="审核市场技能（approved | rejected）")
    review.add_argument("name")
    review.add_argument("decision", choices=["approved", "rejected"])


def _add_session_parser(sub: Any) -> None:
    session = sub.add_parser("session", help="会话管理")
    sess_sub = session.add_subparsers(dest="session_cmd", metavar="<session-cmd>")
    sess_sub.add_parser("create", help="新建会话（返回 session_id）")
    sess_sub.add_parser("list", help="枚举对话会话（跨入口共享）")
    show = sess_sub.add_parser("show", help="打印该会话的对话转录")
    show.add_argument("session_id", metavar="<session-id>")


def _non_negative_int(value: str) -> int:
    """`--limit` 取值：≥0 的整数（`0` = 全部）；负数 / 非整数由 argparse 拒绝。"""
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"须为整数: {value!r}") from exc  # noqa: TRY003
    if number < 0:
        raise argparse.ArgumentTypeError(f"须为 ≥0 的整数: {value!r}")  # noqa: TRY003
    return number


def _add_memory_parser(sub: Any) -> None:
    memory = sub.add_parser("memory", help="记忆维护")
    mem_sub = memory.add_subparsers(dest="memory_cmd", metavar="<memory-cmd>")
    mem_sub.add_parser("maintain", help="触发一次记忆维护（压实 + 遗忘归档）")
    listp = mem_sub.add_parser("list", help="列出记忆条目（id / 层 / 来源 / 摘要）")
    listp.add_argument(
        "--limit", type=_non_negative_int, default=50, metavar="N", help="展示条数（0 = 全部）"
    )
    getp = mem_sub.add_parser("get", help="打印单条记忆全文（内容脱敏）")
    getp.add_argument("entry_id", metavar="<id>")
    deletep = mem_sub.add_parser("delete", help="删除单条记忆（删除前写持久备份）")
    deletep.add_argument("entry_id", metavar="<id>")
    repair = mem_sub.add_parser("repair-keyfacts", help="修复失效关键事实（重抽 + 清理旧条目）")
    repair.add_argument("--dry-run", action="store_true", help="只报告将修复的内容，不删不写")


def _add_rag_parser(sub: Any) -> None:
    rag = sub.add_parser("rag", help="知识检索（摄取 / 检索 / 生成）")
    rag_sub = rag.add_subparsers(dest="rag_cmd", metavar="<rag-cmd>")
    ingest = rag_sub.add_parser("ingest", help="摄取知识文档建索引（一次性）")
    ingest.add_argument("path", help="知识文档文件路径")
    ingest.add_argument("--doc-id", required=True, metavar="ID", help="文档唯一 id")
    ingest.add_argument(
        "--summarize",
        action="store_true",
        help="摄取后把全文交模型总结，落 canonical 结论笔记（notes.rag；缺省不落）",
    )
    search = rag_sub.add_parser("search", help="语义检索 top-k 片段（不调用生成）")
    search.add_argument("query", help="查询语句")
    search.add_argument("--top-k", type=int, default=5, metavar="N", help="返回片段数")
    ask = rag_sub.add_parser("ask", help="检索增强生成（片段注入 → llm-provider）")
    ask.add_argument("query", help="查询语句")
    ask.add_argument("--top-k", type=int, default=5, metavar="N", help="注入片段数")


def _add_notes_parser(sub: Any) -> None:
    notes = sub.add_parser("notes", help="文档化记忆（canonical Markdown 真相层）")
    notes_sub = notes.add_subparsers(dest="notes_cmd", metavar="<notes-cmd>")
    notes_sub.add_parser("list", help="列出 canonical 笔记清单")
    show = notes_sub.add_parser("show", help="打印一篇 canonical 笔记")
    show.add_argument("note_id", help="笔记（主题）id")
    search = notes_sub.add_parser("search", help="词法检索（标题 / tags / Search Queries）")
    search.add_argument("query", help="查询语句")
    search.add_argument("--top-k", type=int, default=5, metavar="N", help="返回条数")
    pin = notes_sub.add_parser("pin", help="置常驻标记（正文每轮无条件注入推理上下文）")
    pin.add_argument("note_id", help="笔记（主题）id")
    pin.add_argument(
        "--priority", type=int, default=0, metavar="N", help="常驻优先级（高者优先在场；缺省 0）"
    )
    unpin = notes_sub.add_parser("unpin", help="清常驻标记（正文不再无条件注入；优先级一并归零）")
    unpin.add_argument("note_id", help="笔记（主题）id")
    notes_sub.add_parser("pinned", help="列出常驻笔记及其是否进场（超预算篇目报为未进场）")
    promote = notes_sub.add_parser("promote", help="把会话摘要提升为 canonical 常驻笔记")
    promote.add_argument("session_id", metavar="<session-id>", help="会话 id（派生 note_id）")
    promote.add_argument("--as", dest="as_note_id", metavar="NOTE_ID", help="显式覆盖 note_id")
    promote.add_argument("--title", default="", metavar="TITLE", help="笔记标题")


def _add_evolve_parser(sub: Any) -> None:
    evolve = sub.add_parser("evolve", help="进化冷路径")
    ev_sub = evolve.add_subparsers(dest="evolve_cmd", metavar="<evolve-cmd>")
    run = ev_sub.add_parser("run", help="强制跑一轮进化冷路径（诊断/提案 dry-run）")
    run.add_argument("--goal", metavar="PLUGIN_ID", help="显式指定本轮迭代目标（插件 id）")
    ev_sub.add_parser("pending", help="列出待人工确认的候选与待复核的实施制品")
    confirm = ev_sub.add_parser("confirm", help="确认候选并发布结晶")
    confirm.add_argument("candidate_id", help="候选身份（见 evolve pending）")
    confirm.add_argument("--approver", default="human", metavar="NAME")
    confirm.add_argument("--note", metavar="TEXT")
    implement = ev_sub.add_parser(
        "implement", help="原生实施架构级候选：筹备（--dry-run）→ 人工复核 → 落地"
    )
    implement.add_argument("candidate_id", help="候选身份（见 evolve pending）")
    implement.add_argument(
        "--dry-run", action="store_true", help="只筹备（跑门禁 → 回退），打印待复核差异、不落地"
    )
    implement.add_argument("--approver", default="human", metavar="NAME")
    implement.add_argument("--note", metavar="TEXT")
    reject = ev_sub.add_parser("reject", help="拒绝候选（不再发布）")
    reject.add_argument("candidate_id", help="候选身份（见 evolve pending）")
    reject.add_argument("--note", metavar="TEXT")
    benchmark = ev_sub.add_parser(
        "benchmark", help="基准集操作面（数据面：只写落盘、不装配运行时）"
    )
    bench_sub = benchmark.add_subparsers(dest="benchmark_cmd", metavar="<benchmark-cmd>")
    bench_sub.add_parser("list", help="列出已注册基准与基线分")
    register = bench_sub.add_parser("register", help="注册一个评测基准（绑定目标插件）")
    register.add_argument("benchmark_id", help="基准身份")
    register.add_argument(
        "--plugin-id", required=True, metavar="ID", help="绑定到该归因目标（候选 target_plugin）"
    )
    register.add_argument(
        "--task-type",
        required=True,
        choices=["module_health", "tool_use"],
        help="样本执行器按此键选取（worker 生产产出的两类）",
    )
    register.add_argument(
        "--samples",
        required=True,
        metavar="PATH",
        help='JSON 文件：[{"input": ..., "expected": ...}]；expected 须与期望回复**逐字相等**'
        "（缺省只评完成度）",
    )
    baseline = bench_sub.add_parser("set-baseline", help="为某归因目标设置基线分（退化绝对阈值）")
    baseline.add_argument("plugin_id", help="归因目标（候选 target_plugin）")
    baseline.add_argument("score", type=float, help="基线分（留出分低于它即判退化）")


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
    publish = rel_sub.add_parser("publish", help="发布 bundle（哈希由制品内容派生）")
    publish.add_argument(
        "bundle",
        metavar="<bundle-manifest>",
        help="bundle 制品清单（JSON：plugin_refs / 可选 name）",
    )
    upgrade = rel_sub.add_parser("upgrade", help="升级")
    upgrade.add_argument("version")
    rel_sub.add_parser("rollback", help="回滚")


def _add_time_travel_parser(sub: Any) -> None:
    travel = sub.add_parser("time-travel", help="时间旅行：回滚执行态到历史检查点")
    travel.add_argument("checkpoint_id", metavar="<checkpoint-id>", help="目标检查点 id")


def _add_pet_parser(sub: Any) -> None:
    pet = sub.add_parser("pet", help="宠物模式（后台自治会话）")
    pet.add_argument(
        "verb",
        nargs="?",
        help="gather|info|explore|walk|list|run|status|result|sleep|wake|assign|stop",
    )
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
    parser.add_argument(
        "--session",
        metavar="ID",
        dest="session_id",
        help="交互入口续聊既有会话（缺省新建；同 run --session 语义）",
    )
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


def _surface_incomplete(runtime: Runtime) -> None:
    """启动扫描未完成任务：只呈现不重执行（P2：副作用不自动重放；change 0191）。

    `runtime.recover()` 无 replay 回调 ⇒ 纯扫描、零副作用。有未完成任务时告警 +
    提示续跑命令；**只报 task id**（不回显任务正文 / 记忆 / 密钥）。

    会话轮级检查点（change 0214 / ADR-0204）**独立一段**呈现：被中断的会话轮只报**数量与
    所属会话**（task id / 轮目标均不回显），且**不给** `task --resume` 提示 —— **续聊即恢复**，
    与编排任务的续跑语义不同；两面**不混列**。
    """
    handles = runtime.recover()
    turns = runtime.recover_turns()
    if not handles and not turns:
        return
    if handles:
        tasks = sorted({h.task_id for h in handles})
        warnings.warn(f"启动扫描发现 {len(tasks)} 个未完成任务", stacklevel=2)
        prompt = "、".join(f"`task --resume {t}`" for t in tasks)
        print(f"⚠ {len(tasks)} 个未完成任务：{prompt} 可续跑", file=sys.stderr)
    if turns:
        sessions = sorted({session for _, session in turns})
        warnings.warn(f"启动扫描发现 {len(turns)} 个中断的会话轮", stacklevel=2)
        print(
            f"⚠ 上次有 {len(turns)} 个中断的会话轮（会话 {'、'.join(sessions)}）：续聊即恢复",
            file=sys.stderr,
        )


def _build_ui(
    args: argparse.Namespace, *, interactive: bool = False, surface_recovery: bool = False
) -> UIAPILayer | None:
    """装配真 runtime + UIAPILayer 并注入 LLM 配置（四入口共用）；失败返回 None。

    interactive=True 时创建交互审批通道：confirm 门经终端 y/n 决断；
    非交互入口无通道，高风险 fail-closed 拒绝。
    surface_recovery=True 时启动扫描并呈现未完成任务（仅 serve 传入；change 0191）。
    """
    approval = ApprovalChannel() if interactive else None
    try:
        runtime = build_runtime(
            _config_manager(args),
            approver=approval.ask if approval is not None else None,
        )
    except Exception as exc:  # noqa: BLE001 — 配置/装配失败统一转 stderr 退出码
        print(f"装配失败: {exc}", file=sys.stderr)
        return None
    # 词法检索提示（change 0252 / ADR-0242）：未配置 embedding 模型时记忆检索只能走词法，
    # 语义召回不可用。与 `_rag` 的既有权重提示同口径，每次启动只输出一次。
    llm = getattr(getattr(runtime, "app", None), "llm", None)
    if llm is not None and not getattr(llm, "embedding_model", ""):
        print(
            "未配置 llm.embedding_model：记忆检索使用词法匹配（语义检索未启用，召回质量受限）",
            file=sys.stderr,
        )
    if surface_recovery:
        _surface_incomplete(runtime)
    api = UIAPILayer(
        loop=cast(LoopPlugin, runtime.loop),
        memory=runtime.memory,
        tools=runtime.tools,
        config=runtime.config,
        approval=approval,
        orchestrator=runtime.orchestrator,  # /task 命令驱动同一编排器
        pet_activator=runtime.pet_activator,  # WebUI 自然语言宠物激活
        beast_activator=runtime.beast_activator,  # 神兽三入口（/summon·/recall + NL，change 0137）
        pet_control=(
            PetControl(runtime.pet_manager)  # 前台 `/pet [cmd]` 控制面
            if runtime.pet_manager is not None
            else None
        ),
        # 四入口（repl/serve/app/run）共享同一落盘会话注册表 ⇒ CLI ↔ serve 互认会话
        registry=SessionRegistry(path=_state_path("conversations.json")),
        # 转录与主 loop **同源同文件**（`$CORE_STATE_DIR/messages.jsonl`）⇒ 读取面与回灌一致
        transcript=runtime.transcript,
        # 只读诊断源（change 0163）：与 CLI `doctor`/`status` **同一**源；句柄复用已装配的
        # `runtime`（不重复装配），故 TUI 的工具面计数为**全量**（见 ADR-0154 决策④）
        diagnostics=_diag_deps(args, tools=runtime.tools, config=runtime.config),
        # 运行环境事实（change 0240）：活动标题未显式 type 时按有效平台缺省命名
        env_snapshot=runtime.env_snapshot,
    )
    api.set_llm_config(runtime.app.llm)
    return api


def _repl(args: argparse.Namespace) -> int:
    """无子命令进入 Textual 交互会话循环（阻塞，退出后返回）；`--session` 续聊既有会话。"""
    api = _build_ui(args, interactive=True, surface_recovery=True)
    if api is None:
        return 1
    CLIBridge(api=api, session_id=args.session_id or "").connect()
    return 0


def _serve(args: argparse.Namespace) -> int:
    api = _build_ui(args, surface_recovery=True)  # 启动扫描未完成任务并呈现（change 0191）
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
    api = _build_ui(args, surface_recovery=True)
    if api is None:
        return 1
    DesktopBridge(api=api, port=args.port).start_sidecar()
    return 0


def _ops(args: argparse.Namespace) -> int:
    """生命周期动词（start / stop / restart）：进程守护，非只读面。

    `status` / `doctor` 自 change `0162` 起改由**只读诊断源**承载（见 `_status` / `_doctor`）——
    此处不再分派它们（`cli_ops/dispatcher.status` 的 `"ok"` 分支自此不经 CLI 触达，见 ADR-0153 ⑥）。
    """
    CLICommandDispatcher().dispatch([args.command])
    return 0


def _diag_deps(
    args: argparse.Namespace,
    *,
    tools: ToolProvider | None = None,
    config: ConfigManager | None = None,
) -> Deps:
    """构造只读诊断句柄集：经**既有**路径助手取裸 store（不建连接、**不装配 runtime**）。

    不装配 runtime 是刻意的：装配需要**有效**配置，而「配置坏了」恰是最该跑诊断的场景
    （见 ADR-0153 决策①）。工具面因此只装**零注入**的内置五件（`builtin_tools`），
    会话枚举走会话注册表的只读口（不带转录 ⇒ 无标题列）。

    `tools` / `config` 可选覆盖（change 0163）：TUI 侧由 `_build_ui` 传入**已在手**的
    `runtime.tools` / `runtime.config`（不重复装配），故 TUI 的「内置工具数」按**真实**工具面计数
    —— 与 CLI 的 builtin-only 面**有意不同**（见 ADR-0154 决策④）。
    """
    if tools is None:
        tools = ToolProvider()
        for tool in builtin_tools():
            tools.register(tool)
    return Deps(
        config=config if config is not None else _config_manager(args),
        tools=tools,
        sessions=SessionRegistry(path=_state_path("conversations.json")).list,
        chain=_memory_chain(),
        notes=_notes_store(),
        mcp=MCPEndpointRegistry(mcp_endpoints_path()),
        library=_build_skill_library(),
        market=_build_market_index(),
        installer=_build_installer(),
        state_dir=_state_dir(),
    )


def _doctor(args: argparse.Namespace) -> int:
    """`doctor`：逐项自检并逐条呈现；**存在 `fail` 项 ⇒ 退出码 1**（诊断的价值在判据）。"""
    report = collect_doctor(_diag_deps(args))
    print("\n".join(render(report)))
    return 0 if report.ok else 1


def _status(args: argparse.Namespace) -> int:
    """`status`：打印运行概览并**恒以 0 结束**（概览是信息面，不是判据）。"""
    print("\n".join(render(collect_status(_diag_deps(args)))))
    return 0


def _config_manager(
    args: argparse.Namespace, *, yaml_path: Path | str | None = None
) -> ConfigManager:
    """构造配置管理器：**单点注入**组合根维护的已知模块名（`features` 段子键校验，账本 E20①）。

    10 处 `ConfigManager(...)` 构造点收口于此 —— 漏传一处即该入口静默丢失告警；集中在此消除该风险。
    注入的是**两名单之并**（`KNOWN_FEATURE_MODULES`）：缺省关的模块名同样不得被告警成「未知开关」
    （否则开启 `evolution_executor` 的正确写法会被建议「订正」）。
    `yaml_path` 缺省取 `args.config`（覆盖 `config validate --file` 的自定义路径）。
    """
    return ConfigManager(
        yaml_path=yaml_path if yaml_path is not None else args.config,
        cli=_cli_overrides(args),
        known_modules=KNOWN_FEATURE_MODULES,
    )


def _config(args: argparse.Namespace) -> int:
    mgr = _config_manager(args)
    if args.config_cmd == "get":
        # 与配置链同口径：CLI > env > config.yaml > 缺省（账本 E22）
        value = mgr.config_value(args.key)
        print(value if value not in (None, "") else "(未配置)")
        return 0
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
        _config_manager(args, yaml_path=path).load()
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


def _mcp(args: argparse.Namespace) -> int:
    """MCP 端点管理：serve 对外提供工具；add / list / remove 管理已安装端点。"""
    if args.mcp_cmd == "serve":
        return _mcp_serve(args)
    if args.mcp_cmd == "add":
        return _mcp_add(args)
    if args.mcp_cmd == "list":
        return _mcp_list()
    if args.mcp_cmd == "remove":
        return _mcp_remove(args)
    print("用法: core-agent mcp {serve|add|list|remove} ...", file=sys.stderr)
    return 0


def _mcp_add(args: argparse.Namespace) -> int:
    """`mcp add <endpoint>`：**先连通验证再落盘** —— 连不上的端点不持久化。"""
    name = args.name or default_endpoint_name(args.endpoint, args.mcp_command)
    if not name:
        print("无法从来源推断端点名，请用 --name 指定", file=sys.stderr)
        return 1
    registry = MCPEndpointRegistry(mcp_endpoints_path())
    if registry.get(name) is not None:
        print(f"端点名已存在: {name}（先 mcp remove，或用 --name 换名）", file=sys.stderr)
        return 1
    try:
        manager = _config_manager(args)
        manager.load()
    except Exception as exc:  # noqa: BLE001 — 配置失败统一转 stderr 退出码
        print(f"配置错误: {exc}", file=sys.stderr)
        return 1
    record = EndpointRecord(
        name=name,
        source=args.endpoint,
        transport=args.transport,
        command=args.mcp_command,
        args=cast("list[str]", args.mcp_args or []),
    )
    tools = ToolProvider()
    try:
        _mcp_dispatcher(manager, tools).install(record.asset())  # 连接 + 适配 + 注册
        registry.add(record)  # 连接成功才落盘
    except (DomainError, MCPError) as exc:
        print(f"安装失败: {exc}", file=sys.stderr)
        return 1
    print(f"已安装 MCP 端点: {name}（{_describe_endpoint(record)}）")
    for tool in tools.active_tools():
        print(f"  - {tool.tool_id}")
    return 0


def _mcp_list() -> int:
    """列出已安装端点（读注册表，**不建连接** —— 列表是配置面事实）。"""
    print("已安装 MCP 端点:")
    for record in MCPEndpointRegistry(mcp_endpoints_path()).list():
        print(f"  {record.name}\t{_describe_endpoint(record)}")
    return 0


def _mcp_remove(args: argparse.Namespace) -> int:
    """摘除已安装端点，并走完卸载生命周期（本进程若持有连接则就地释放）。"""
    registry = MCPEndpointRegistry(mcp_endpoints_path())
    record = registry.get(args.name)
    if record is None:
        print(f"端点未安装: {args.name}", file=sys.stderr)
        return 1
    try:
        # 一次性 CLI 进程内本无连接可放（连接随持有它的进程退出释放），此处走完整生命周期
        # 以保持与安装对称；长驻进程（如 `mcp serve`）内的连接需重启进程才真正断开。
        InstallDispatcher(skill_library=SkillLibrary(), tool_provider=ToolProvider()).uninstall(
            record.asset()
        )
    except (DomainError, MCPError) as exc:
        print(f"卸载失败: {exc}", file=sys.stderr)
        return 1
    registry.remove(record.name)
    print(f"已移除 MCP 端点: {record.name}")
    return 0


def _describe_endpoint(record: EndpointRecord) -> str:
    """端点一行描述：传输 + 目标（命令行或 URL）。"""
    return f"{record.transport or '自动'} {record.command or record.source}"


def _mcp_dispatcher(manager: ConfigManager, tools: ToolProvider) -> InstallDispatcher:
    """CLI 面的安装执行器：出站策略与**装配期同口径**（白名单缺省空 = fail-closed 全拒）。"""
    policy = SandboxPolicy(host_allowlist=manager.sandbox_host_allowlist())
    client = MCPClient(sandbox=SandboxManager(policy=policy), policy=policy)
    return InstallDispatcher(skill_library=SkillLibrary(), tool_provider=tools, mcp_client=client)


def _mcp_serve(args: argparse.Namespace) -> int:
    """`mcp serve`：装配 runtime → 以 stdio 承载 MCP server 事件循环（阻塞至 EOF）。"""
    if args.transport != "stdio":
        print(f"mcp serve：{args.transport} 传输会话待接入（Mcp-Session-Id 复用）", file=sys.stderr)
        return 1
    try:
        runtime = build_runtime(_config_manager(args))
    except Exception as exc:  # noqa: BLE001 — 配置/装配失败统一转 stderr 退出码
        print(f"装配失败: {exc}", file=sys.stderr)
        return 1
    _surface_incomplete(runtime)  # 启动扫描未完成任务并呈现（只走 stderr；change 0207）
    server = MCPServer(tool_provider=runtime.tools, whitelist=_mcp_whitelist(args.whitelist))
    print("MCP server 已就绪（stdio）", file=sys.stderr)
    server.serve_stdio(MCPEndpoint(transport="stdio", session_id=args.endpoint))
    return 0


def _mcp_whitelist(raw: str) -> list[str]:
    """逗号分隔工具名 → 列表（空白项丢弃；`core.` 前缀由 server 侧归一）。"""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _plugin(args: argparse.Namespace) -> int:
    """插件/资产安装生命周期（process 内注册，跨进程持久化未接）。"""
    if args.plugin_cmd == "install":
        return _plugin_install(
            _build_installer(),
            args.asset,
            PluginKind(args.kind or "skill"),
            PluginSource(args.source),
        )
    if args.plugin_cmd == "list":
        return _plugin_list(_build_installer(), args.kind)
    if args.plugin_cmd == "uninstall":
        return _plugin_uninstall(_build_installer(), args.name)
    print(f"plugin {args.plugin_cmd} 已识别，尚未接线", file=sys.stderr)
    return 0


def _skill(args: argparse.Namespace) -> int:  # noqa: PLR0911 — CLI 分支各自退出码
    """技能市场：search/install 走 SkillHubClient、publish/review 走 SkillPublisher。

    市场目录与制品库均落盘于 `$CORE_STATE_DIR`（发布 / 审核 / 搜索 / 安装跨进程可见）；
    远端市场拉取仍为凭证半，未接入时如实报错。
    """
    library = _build_skill_library()
    source = getattr(args, "source", None) or "official"  # remove/review 分支无 --source
    if args.skill_cmd == "search":
        return _skill_search(_build_skillhub_client(library), args.query, source=source)
    if args.skill_cmd == "install":
        return _skill_install(_build_skillhub_client(library), args.name, source=source)
    if args.skill_cmd == "remove":
        return _skill_remove(library, args.name)
    if args.skill_cmd == "activate":
        return _skill_activate(library, args.name)
    if args.skill_cmd == "publish":
        return _skill_publish(_build_publisher(), library, args.name, source=source)
    if args.skill_cmd == "review":
        return _skill_review(_build_publisher(), args.name, args.decision)
    print(f"skill {args.skill_cmd} 已识别，尚未接线", file=sys.stderr)
    return 0


def _release(args: argparse.Namespace) -> int:
    """发布 / 升级 / 回滚（ReleaseManager，版本登记持久化，真实制品仓库未接）。"""
    manager = ReleaseManager(path=_state_path("releases.json"))
    try:
        if args.release_cmd == "publish":
            bundle = BundlePackager().load_manifest(args.bundle)  # 真口径：哈希由制品内容派生
            version = manager.publish(ReleaseInfo(version=bundle.name, hash=bundle.hash))
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
    except (CompositionError, DeploymentError) as exc:
        print(f"发布失败: {exc}", file=sys.stderr)
        return 1
    print(f"release {args.release_cmd} 已识别，尚未接线", file=sys.stderr)
    return 0


def _time_travel(args: argparse.Namespace) -> int:
    """时间旅行回滚：恢复执行态到历史检查点，并撤销该点撤销集内的写类副作用（账本 E73）。

    取**生产真源** `build_runtime(...).time_travel` —— 与 `task` / `run` 同一组合根、
    同一 `$CORE_STATE_DIR/checkpoints.jsonl`、同一共享 `EffectTracker`（tool-use 的
    EffectId undo 栈，不新建撤销机制）。撤销集来自快照 `state["trace_ids"]`；undo 闭包
    不可持久化 ⇒ 跨进程调用时撤销循环为空转，快照恢复与失败语义仍生效（ADR-0136）。
    """
    try:
        runtime = build_runtime(_config_manager(args))
        snapshot = runtime.time_travel.rollback(args.checkpoint_id)
    except DurabilityError as exc:
        print(f"回滚失败: {exc}", file=sys.stderr)
        return 1
    trace_ids = cast(list[str], snapshot.state.get("trace_ids") or [])
    print(
        f"已回滚到检查点 {snapshot.checkpoint_id}："
        f"恢复状态键 {len(snapshot.state)} 个，撤销 trace {len(trace_ids)} 条"
    )
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
    """装配轻量插件安装器（无需 LLM/loop；来源解析经 `InstallDispatcher` 四源分派）。

    技能库与组合根**同源**（`$CORE_STATE_DIR/skills.json`，见 `_build_skill_library`）——否则
    `plugin install --kind skill` 装进一次性空库，「已安装」是谎报、跨进程不可见。

    安装账本同理（change 0109 / 账本 E36）：注入 `PluginInstallStore` 后 `register` 落盘、
    构造期水合既有记录 ⇒ 新进程 `plugin list` / `plugin uninstall` 才认得上一次安装。
    """
    skills = _build_skill_library()
    provider = ToolProvider()
    dispatcher = InstallDispatcher(skill_library=skills, tool_provider=provider)
    return PluginInstaller(
        source_resolver=dispatcher.resolve,
        installer=dispatcher.install,
        uninstaller=dispatcher.uninstall,
        store=default_install_store(),
    )


def _plugin_install(
    installer: PluginInstaller, asset: str, kind: PluginKind, source: PluginSource
) -> int:
    """`plugin install <asset> --kind K --source S`：来源经 `InstallDispatcher` 解析成 manifest。

    走完整生命周期（change 0108 / 账本 E35）：discover → verify → install → register → activate；
    与 `tools.install` 同链（`installable` 声明 / plugin-registry spec「插件来源与安装」）。
    """
    try:
        item = installer.discover(source, asset, kind)
        installer.verify(item, str(item.manifest.get("signature", "")))
        installer.install(item)
        manifest = item.manifest
        plugin_id = str(
            manifest.get("plugin_id")
            or manifest.get("skill_id")
            or manifest.get("name")
            or f"installed.{kind.value}.{asset}"
        )
        installer.register(item, StubPlugin(plugin_id, manifest))
        installer.activate(plugin_id)
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


def _build_skill_library() -> SkillLibrary:
    """技能库：与组合根**同源**（`$CORE_STATE_DIR/skills.json`，见 `runtime._skill_state_path`）。

    不带路径的 `SkillLibrary()` 是进程内一次性库 —— 下载的技能会随进程消失（「已安装」成谎报）、
    `skill remove` 也永远删不掉运行时真正注册的技能。
    """
    return SkillLibrary(path=_state_path("skills.json"))


def _build_market_index() -> MarketIndex:
    """市场目录：落盘于 `$CORE_STATE_DIR/skillhub-index.json`。

    目录是市场真源（发布 / 审核写入、搜索 / 安装读取），落盘后跨进程可见；不带路径的
    `MarketIndex()` 是进程内一次性目录 —— 上个进程发布的技能下个进程就查不到。
    """
    return MarketIndex(path=_state_path("skillhub-index.json"))


def _build_market_artifacts() -> SkillLibrary:
    """本地市场制品库：发布时入库的技能体（消费侧拉取来源，离线、零凭据）。"""
    return SkillLibrary(path=_state_path("skillhub-artifacts.json"))


def _build_publisher() -> SkillPublisher:
    """发布 / 审核缺省装配：落盘目录 + 本地市场制品库 + 落盘版本管理。"""
    return SkillPublisher(
        index=_build_market_index(),
        artifacts=_build_market_artifacts(),
        version_manager=VersionManager(path=_state_path("skill-versions.json")),
    )


def _market_fetcher(skill_id: str, _source: str) -> Skill | None:
    """消费侧拉取：本地市场制品库（无该技能返回 None ⇒ 客户端如实报错）。"""
    try:
        return _build_market_artifacts().lookup(skill_id)
    except KeyError:
        return None


def _build_skillhub_client(library: SkillLibrary) -> SkillHubClient:
    """技能市场客户端缺省装配：落盘目录 + 签名校验器 + 本地市场制品拉取。"""
    return SkillHubClient(
        library,
        index=_build_market_index(),
        verifier=TrustVerifier(),
        fetcher=_market_fetcher,
    )


def _skill_search(client: SkillHubClient, query: str, *, source: str = "official") -> int:
    try:
        matches = client.search(query, source=source)
    except SkillHubError as exc:
        print(f"搜索失败: {exc}", file=sys.stderr)
        return 1
    if not matches:
        print(f"（未找到匹配技能: {query}）")
        return 0
    for market in matches:
        print(f"{market.skill_id} ({market.version}): {market.description}")
    return 0


def _skill_install(client: SkillHubClient, skill_id: str, *, source: str = "official") -> int:
    try:
        skill = client.download(skill_id, source=source)
    except SkillHubError as exc:
        print(f"安装失败: {exc}", file=sys.stderr)
        return 1
    print(f"已安装技能 {skill.skill_id}（draft，需本地显式激活后可用）")
    return 0


def _skill_remove(library: SkillLibrary, name: str) -> int:
    try:
        library.remove(name)
    except KeyError:
        print(f"技能未注册: {name}", file=sys.stderr)
        return 1
    print(f"已卸载技能 {name}")
    return 0


def _skill_activate(library: SkillLibrary, name: str) -> int:
    """显式启用 draft 技能（E72 死胡同的出口）：落 active 后即进路由；未注册退出码非零。"""
    try:
        skill = library.activate(name)
    except KeyError:
        print(f"技能未注册: {name}", file=sys.stderr)
        return 1
    print(f"已启用技能 {skill.skill_id}（active，可参与路由）")
    return 0


def _skill_publish(
    publisher: SkillPublisher, library: SkillLibrary, skill_id: str, *, source: str = "official"
) -> int:
    try:
        skill = library.lookup(skill_id)
    except KeyError:
        print(f"技能未注册: {skill_id}", file=sys.stderr)
        return 1
    try:
        publisher.publish(skill, source=source)
    except SkillHubError as exc:
        print(f"发布失败: {exc}", file=sys.stderr)
        return 1
    print(f"已发布技能 {skill_id}（pending，待审核）")
    return 0


def _skill_review(publisher: SkillPublisher, skill_id: str, decision: str) -> int:
    try:
        publisher.review(skill_id, decision)
    except SkillHubError as exc:
        print(f"审核失败: {exc}", file=sys.stderr)
        return 1
    print(f"已审核技能 {skill_id}: {decision}")
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
    """点分键 → apply_change 支持的嵌套 patch（llm./features./im./loop./orchestration.）。"""
    top, _, rest = key.partition(".")
    if top not in ("llm", "features", "im", "loop", "orchestration") or not rest:
        raise ValueError(  # noqa: TRY003
            f"config set 暂不支持键: {key}（仅支持 llm./features./im./loop./orchestration.）"
        )
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


def _state_dir() -> Path:
    """全局状态目录：$CORE_STATE_DIR（缺省 ~/.core/state）。

    env 覆盖便于测试隔离（对齐 config 的 env 覆盖惯例）；缺省对齐 ~/.core/Core.md
    全局约定。
    """
    return Path(os.environ.get("CORE_STATE_DIR") or str(Path.home() / ".core" / "state"))


def _state_path(name: str) -> Path:
    """全局状态文件路径：全局状态目录（见 `_state_dir`）/<name>。"""
    return _state_dir() / name


def _session(args: argparse.Namespace) -> int:
    registry = SessionRegistry(path=_state_path("conversations.json"))
    if args.session_cmd == "create":
        print(registry.create(args.profile or "cli"))
        return 0
    if args.session_cmd == "list":
        entries = registry.list()
        if not entries:
            print("无对话会话")
            return 0
        for entry in entries:
            print(f"{entry['session_id']} ({entry['mode']})")
        return 0
    if args.session_cmd == "show":
        return _session_show(registry, args.session_id)
    print("用法: core-agent session create | list | show <session-id>", file=sys.stderr)
    return 1


def _session_show(registry: SessionRegistry, session_id: str) -> int:
    """打印该会话的对话转录（与内核回灌**同一** `TranscriptStore`，不另建副本）。

    未登记标识 fail-closed 拒绝（不放宽会话校验）；无转录 ⇒ 明示、退出码 0（不伪造内容）。
    """
    if not registry.exists(session_id):
        print(f"会话不存在: {session_id}", file=sys.stderr)
        return 1
    entries = TranscriptStore(path=_state_path("messages.jsonl")).read(session_id)
    if not entries:
        print("（无对话记录）")
        return 0
    for entry in entries:
        print(f"{entry['role']}: {entry['content']}")
    return 0


def _memory_maintain(memory: Any, _args: argparse.Namespace) -> int:
    """`memory maintain`：触发一次记忆维护（压实 + 遗忘），打印归档条数。"""
    memory.compact()
    forgotten = memory.forget()
    print(f"记忆维护完成：归档 {len(forgotten)} 条")
    return 0


def _memory_repair_keyfacts(memory: Any, args: argparse.Namespace) -> int:
    """`memory repair-keyfacts`：修复失效关键事实，打印报表（口径见 design §D5）。"""
    dry_run = bool(args.dry_run)
    report = memory.repair_stale_key_facts(dry_run=dry_run)
    head = "失效关键事实修复（预演，未动作）" if dry_run else "失效关键事实修复完成"
    print(f"{head}：识别 {len(report.identified)} 条失效条目 / {len(report.sessions)} 个会话")
    for session_id in report.sessions:
        print(f"  - 会话 {session_id}")
    if dry_run:
        print(f"  将删除 {len(report.identified)} 条（预演，未动作）")
    else:
        print(f"  已删除 {len(report.deleted)} 条；重抽落库 {len(report.written)} 条")
        if report.backup_path:
            print(f"  备份文件：{report.backup_path}")
    for reason, targets in sorted(report.skipped.items()):
        print(f"  跳过（{reason}）：{len(targets)} 项 {'/'.join(targets)}")
    return 0


_SUMMARY_CHARS = 120


def _format_ts(ts: float) -> str:
    """条目时间戳 → 本地 `YYYY-MM-DDTHH:MM:SS`；`ts<=0`（未落时间）显示 `-`。"""
    if ts <= 0:
        return "-"
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))


def _one_line_summary(text: str) -> str:
    """正文 → 单行摘要（先脱敏再截断，避免明文跨越截断边界）。"""
    single = " ".join(redact_secrets(text).split())
    return single if len(single) <= _SUMMARY_CHARS else single[: _SUMMARY_CHARS - 1] + "…"


def _memory_find(entries: list[MemoryEntry], entry_id: str) -> MemoryEntry | None:
    """按 id 精确匹配取首条（口径同 `MemoryStore._entry_by_id` 的「同 id 即覆盖」）。"""
    return next((entry for entry in entries if entry.id == entry_id), None)


def _backup_memory_entry(entry: MemoryEntry) -> Path:
    """把待删条目**追加**到 `$CORE_STATE_DIR/memory-deleted.jsonl`（0600）。

    单次 `os.write` 整行（对齐转录落盘的并发追加口径）；追加日志天然可累积、可人工重放。
    写入失败抛 `OSError`，由调用方 fail-closed（不删除）。
    """
    path = _state_path("memory-deleted.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(asdict(entry), ensure_ascii=False) + "\n"
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    with contextlib.suppress(OSError):  # 追加到既有宽权限文件时一并收紧
        os.chmod(path, 0o600)
    return path


def _memory_list(memory: Any, args: argparse.Namespace) -> int:
    """`memory list`：全量 `audit()` 后只截断**展示**（`--limit 0` = 全部）。"""
    entries = memory.audit(None)
    limit = int(args.limit)
    shown = entries if limit == 0 else entries[:limit]
    for entry in shown:
        print(
            f"{entry.id}\t{entry.layer}\t{entry.kind}\t{entry.source}\t"
            f"{entry.session_id or '-'}\t{entry.importance:.2f}\t"
            f"{_format_ts(entry.ts)}\t{_one_line_summary(entry.content)}"
        )
    if limit and len(entries) > limit:
        print(f"（共 {len(entries)} 条，显示前 {limit} 条；--limit 0 显示全部）")
    return 0


def _memory_get(memory: Any, args: argparse.Namespace) -> int:
    """`memory get <id>`：打印元数据与全文（`redact_secrets` 脱敏后回显）。"""
    entry = _memory_find(memory.audit(None), args.entry_id)
    if entry is None:
        print(f"未找到条目: {args.entry_id}", file=sys.stderr)
        return 1
    print(f"id: {entry.id}")
    print(f"layer: {entry.layer}")
    print(f"kind: {entry.kind}")
    print(f"source: {entry.source}")
    print(f"session: {entry.session_id or '-'}")
    print(f"importance: {entry.importance:.2f}")
    print(f"ts: {_format_ts(entry.ts)}")
    print(f"trace_id: {entry.trace_id}")
    print()
    print(redact_secrets(entry.content))
    return 0


def _memory_delete(memory: Any, args: argparse.Namespace) -> int:
    """`memory delete <id>`：先备份后删除；备份失败 fail-closed。"""
    entry = _memory_find(memory.audit(None), args.entry_id)
    if entry is None:
        print(f"未找到条目: {args.entry_id}", file=sys.stderr)
        return 1
    try:
        backup = _backup_memory_entry(entry)
    except OSError as exc:
        print(f"备份失败，未删除任何条目: {exc}", file=sys.stderr)
        return 1
    if not memory.discard(entry.id):
        print(f"删除失败（条目已不存在）: {entry.id}", file=sys.stderr)
        return 1
    print(f"已删除 {entry.id}；备份文件：{backup}")
    return 0


_MEMORY_COMMANDS: dict[str, Callable[[Any, argparse.Namespace], int]] = {
    "maintain": _memory_maintain,
    "list": _memory_list,
    "get": _memory_get,
    "delete": _memory_delete,
    "repair-keyfacts": _memory_repair_keyfacts,
}


def _memory(args: argparse.Namespace) -> int:
    """`memory <sub>`：装配 runtime → 分派到对应记忆运维动作。"""
    action = _MEMORY_COMMANDS.get(args.memory_cmd or "")
    if action is None:
        print(
            "用法: core-agent memory {maintain|list [--limit N]|get <id>|delete <id>"
            "|repair-keyfacts [--dry-run]}",
            file=sys.stderr,
        )
        return 1
    try:
        runtime = build_runtime(_config_manager(args))
    except Exception as exc:  # noqa: BLE001 — 配置/装配失败统一转 stderr 退出码
        print(f"装配失败: {exc}", file=sys.stderr)
        return 1
    return action(runtime.memory, args)


_EVOLVE_USAGE = (
    "用法: core-agent evolve {run [--goal ID]|pending|confirm <id>|"
    "implement <id> [--dry-run]|reject <id>|"
    "benchmark {register <id> --plugin-id ID --task-type T --samples PATH|"
    "set-baseline ID SCORE|list}}"
)


def _evolve(args: argparse.Namespace) -> int:
    """进化冷路径操作面：跑一轮 / 看待确认 / 确认发布 / 原生实施 / 拒绝 / 基准注册。"""
    handlers = {
        "run": _evolve_run,
        "pending": _evolve_pending,
        "confirm": _evolve_confirm,
        "implement": _evolve_implement,
        "reject": _evolve_reject,
        "benchmark": _evolve_benchmark,
    }
    handler = handlers.get(args.evolve_cmd or "")
    if handler is None:
        print(_EVOLVE_USAGE, file=sys.stderr)
        return 1
    return handler(args)


def _evolve_runtime(args: argparse.Namespace) -> Any | None:
    """装配 runtime；失败转 stderr 并返回 ``None``（调用方给退出码 1）。"""
    try:
        return build_runtime(_config_manager(args))
    except Exception as exc:  # noqa: BLE001 — 配置/装配失败统一转 stderr 退出码
        print(f"装配失败: {exc}", file=sys.stderr)
        return None


def _evolve_run(args: argparse.Namespace) -> int:
    """`evolve run [--goal PLUGIN_ID]`：**强制**跑一轮冷路径，打印结局。

    `--goal` 是**显式目标入口**：人直接指定本轮迭代谁（不参与归因竞争），仍走完整
    四阶段与验证门；缺省则用课程议程（自动开课）作诊断先验。
    """
    runtime = _evolve_runtime(args)
    if runtime is None:
        return 1
    evolution = runtime.evolution
    if evolution is None:
        return _module_disabled("evolution")
    goal = args.goal
    if goal:
        print(f"本轮目标：{goal}（显式指定）")
    outcome = evolution.maybe_run(force=True, goal=goal)
    if outcome is None:
        print("进化冷路径完成：无候选（no_op）")
    else:
        target = f"，目标 {outcome.skill_id}" if outcome.skill_id else ""
        print(f"进化冷路径完成：{outcome.status}{target}")
        if outcome.status == "pending" and outcome.candidate is not None:
            print(f"待确认候选：{outcome.candidate.candidate_id}（core-agent evolve pending）")
    return 0


def _evolve_pending(args: argparse.Namespace) -> int:
    """`evolve pending`：列出待人工确认的候选与待复核的实施制品（含门禁报告）。"""
    runtime = _evolve_runtime(args)
    if runtime is None:
        return 1
    evolution = runtime.evolution
    if evolution is None:
        return _module_disabled("evolution")
    candidates = evolution.engine.pending()
    executor = runtime.evolution_executor
    staged = executor.staged_all() if executor is not None else None
    if not candidates and not staged:
        print("待确认队列为空")
        return 0
    if candidates:
        print(f"待确认候选 {len(candidates)} 项：")
        for candidate in candidates:
            print(
                f"  {candidate.candidate_id}  风险={candidate.risk_level}  "
                f"目标={candidate.target_plugin}  {candidate.delta.get('issue', '')}"
            )
    if staged:
        # 复核材料就地呈现：人不必去翻台账 JSON（差异用 `evolve implement <id> --dry-run` 重看）
        print(f"待复核（原生实施）{len(staged)} 项：")
        for record in staged:
            passed = sum(1 for entry in record.gate.values() if entry.get("passed"))
            print(f"  {record.candidate_id}  {record.path}  门禁 {passed}/{len(record.gate)} 通过")
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
    if outcome.status == "accepted":
        # 架构级候选：批准已登记，但无产物落地（待人工实施）
        print(f"已批准（待人工实施）：{candidate.target_plugin}")
    else:
        print(f"已确认并发布：{outcome.status}（{candidate.target_plugin}）")
    return 0


def _sign_approval(
    candidate: GenerationCandidate,
    *,
    approver: str,
    note: str | None,
    op: str = "evolution.publish",
) -> ApprovalTicket | None:
    """架构级候选的审批单签发：本操作面即「人工」来源（技能库级无需工单）。

    `op` 区分**两道不同的关**：`confirm` 批「做什么」（`evolution.publish`）、原生实施落地批
    「改得对不对」（`IMPLEMENT_OP`）—— 同一张单不得跨关复用（见 executor 的复核关）。
    """
    if candidate.risk_level != "high":
        return None
    implement = op == IMPLEMENT_OP
    workflow = ApprovalWorkflow()
    ticket = workflow.create(
        ApprovalRequest(
            op=op,
            target=candidate.target_plugin,
            impact_summary=str(candidate.delta.get("issue", "")),
            rollback_plan=(
                f"按 EffectTracker 的 undo 还原目标文件"
                f"（trace={COMMIT_TRACE}.{candidate.candidate_id}）"
                if implement
                else "dissolve 回 L3（技能标 deprecated + 教训写回 L2）"
            ),
            trace_id="evolution",
        )
    )
    workflow.approve(ticket, approver=approver, note=note)
    return ticket


#: 执行器未装配（`features.evolution_executor` 缺省关）时的入口说明。
#: 不复用 `_module_disabled`：那句文案是「缺省装配」极性（「移除该项即恢复缺省装配」），
#: 对**缺省关**的能力说反了 —— 移除 `features.evolution_executor` 恰恰是「保持关闭」。
_EXECUTOR_DISABLED = (
    "evolution_executor 已关闭（features.evolution_executor 未开启；显式置 true 才装配原生执行器）"
)


def _unified_diff(before: str, content: str, path: str) -> str:
    """待复核差异：没有它，「复核」只是签个字（人得看得见改了什么）。"""
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
        )
    )


def _evolve_implement(args: argparse.Namespace) -> int:
    """`evolve implement`：筹备（`--dry-run`）→ 人工复核 → 落地（可选的原生执行器）。

    两阶段是本操作面的**唯一**形态：`--dry-run` 只筹备（跑完冻结门即回退工作树）并把制品落
    台账，落地要**另跑一次**并携带实施复核单 —— 复核之前工作树上没有任何改动残留。
    """
    runtime = _evolve_runtime(args)
    if runtime is None:
        return 1
    evolution = runtime.evolution
    if evolution is None:
        return _module_disabled("evolution")
    executor = runtime.evolution_executor
    if executor is None:
        print(_EXECUTOR_DISABLED, file=sys.stderr)
        return 0
    candidate = evolution.engine.find(args.candidate_id)
    if candidate is None:
        print(f"候选不存在: {args.candidate_id}", file=sys.stderr)
        return 1
    try:
        if args.dry_run:
            record = executor.prepare(candidate)
            print(f"待复核：{record.path}")
            print(_unified_diff(record.before, record.content, record.path), end="")
            print(
                f"复核通过后落地：core-agent evolve implement "
                f"{candidate.candidate_id} --approver NAME"
            )
        else:
            approval = _sign_approval(
                candidate, approver=args.approver, note=args.note, op=IMPLEMENT_OP
            )
            outcome = executor.commit(candidate, approval=approval)
            print(f"已实施：{candidate.target_plugin}（{outcome.status}）")
    except EvolutionError as exc:
        print(f"实施失败: {exc}", file=sys.stderr)
        return 1
    return 0


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


def _benchmark_registry() -> BenchmarkRegistry:
    """基准集注册表：与组合根**同源**（`runtime._skill_state_path("evolution-benchmarks.json")`）。

    操作面只写**数据面**、**不装配运行时** —— 注册基准不需要模型、不需要凭据（先例
    `_notes_store` / `_build_skill_library`），装配反而让「配置坏了就注册不了基准」的脆弱性进来
    （同 `_diag_deps` 的免 runtime 取向）。
    """
    return BenchmarkRegistry(path=_state_path("evolution-benchmarks.json"))


def _evolve_benchmark(args: argparse.Namespace) -> int:
    """`evolve benchmark {register|set-baseline|list}`：基准集的人工注册面（数据面）。"""
    handlers = {
        "register": _benchmark_register,
        "set-baseline": _benchmark_set_baseline,
        "list": _benchmark_list,
    }
    handler = handlers.get(args.benchmark_cmd or "")
    if handler is None:
        print(_EVOLVE_USAGE, file=sys.stderr)
        return 1
    return handler(args)


def _benchmark_register(args: argparse.Namespace) -> int:
    """`evolve benchmark register <id> --plugin-id ID --task-type T --samples PATH`。"""
    try:
        raw: Any = json.loads(Path(args.samples).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"样本文件不可用: {exc}", file=sys.stderr)
        return 1
    if not isinstance(raw, list):
        print('样本文件须是 JSON 数组：[{"input": ..., "expected": ...}]', file=sys.stderr)
        return 1
    samples = [cast("dict[str, Any]", s) for s in cast("list[Any]", raw) if isinstance(s, dict)]
    registry = _benchmark_registry()
    registry.register(
        Benchmark(
            benchmark_id=args.benchmark_id,
            task_type=args.task_type,
            samples=samples,
            plugin_id=args.plugin_id,
        )
    )
    print(f"已注册基准：{args.benchmark_id}（绑定 {args.plugin_id}，{len(samples)} 样本）")
    return 0


def _benchmark_set_baseline(args: argparse.Namespace) -> int:
    """`evolve benchmark set-baseline <plugin_id> <score>`：设退化判定的绝对阈值。"""
    _benchmark_registry().set_baseline(args.plugin_id, args.score)
    print(f"已设基线：{args.plugin_id} = {args.score}")
    return 0


def _benchmark_list(args: argparse.Namespace) -> int:
    """`evolve benchmark list`：列出已注册基准与基线分（落盘缺失 ⇒ 空清单）。"""
    registry = _benchmark_registry()
    benchmarks = registry.list()
    if not benchmarks:
        print("基准集为空")
        return 0
    for benchmark in benchmarks:
        baseline = registry.baseline_of(benchmark.plugin_id or "")
        shown = "未设" if baseline is None else str(baseline)
        print(
            f"  {benchmark.benchmark_id}  目标={benchmark.plugin_id or '（未绑定）'}  "
            f"类型={benchmark.task_type}  样本={len(benchmark.samples)}  基线={shown}"
        )
    return 0


_RAG_USAGE = (
    "用法: core-agent rag {ingest <path> --doc-id ID [--summarize]|search <query>|ask <query>}"
)


def _rag_runtime(args: argparse.Namespace) -> Any | None:
    """装配 runtime；失败转 stderr 并返回 ``None``（调用方给退出码 1）。"""
    try:
        return build_runtime(_config_manager(args))
    except Exception as exc:  # noqa: BLE001 — 配置/装配失败统一转 stderr 退出码
        print(f"装配失败: {exc}", file=sys.stderr)
        return None


def _rag(args: argparse.Namespace) -> int:
    """知识检索操作面：摄取建索引 / 语义检索 / 检索增强生成（均一次性，不改运行态）。"""
    handlers = {"ingest": _rag_ingest, "search": _rag_search, "ask": _rag_ask}
    handler = handlers.get(args.rag_cmd or "")
    if handler is None:
        print(_RAG_USAGE, file=sys.stderr)
        return 1
    runtime = _rag_runtime(args)
    if runtime is None:
        return 1
    app = getattr(runtime, "app", None)
    if app is not None and not app.llm.embedding_model:
        # 降级提示落 stderr（不污染 stdout 机读输出）：索引维度与后端绑定，换后端须重建索引
        print(
            "未配置 llm.embedding_model：检索走离线 HashEmbedder 降级基线"
            "（检索质量受限，索引维度与 embedding 后端绑定）",
            file=sys.stderr,
        )
    try:
        return handler(runtime, args)
    except RAGError as exc:
        print(f"RAG 错误 [{exc.code.value}]: {exc.message}", file=sys.stderr)
        return 1


def _rag_ingest(runtime: Any, args: argparse.Namespace) -> int:
    """`rag ingest <path> --doc-id ID [--summarize]`：摄取知识文档（分块 → embedding → 落盘索引）。

    带 `--summarize` 时，摄取成功后把**全文**交一次模型调用产出摘要、落 canonical 结论笔记
    （`notes.rag`）。摘要失败**不**回退摄取、**不**改退出码（摄取已是既成事实），只告警落 stderr
    且**只报 `doc_id`**（绝不回显正文）。
    """
    path = Path(args.path)
    if not path.is_file():
        print(f"知识文档不存在: {path}", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8")
    written = runtime.rag.ingest(args.doc_id, text)
    if written:
        print(f"已摄取 {args.doc_id}：{written} 块")
    else:
        print(f"已摄取 {args.doc_id}：无变更（跳过重建）")
    if args.summarize:
        _write_doc_summary_note(runtime, doc_id=args.doc_id, text=text)
    return 0


#: 文档摘要提示词（single-shot：全文 → 结论摘要；入口侧接缝，非会话压实形状）。
_DOC_SUMMARY_PROMPT = (
    "请用简洁的中文总结下面这份文档的核心结论与关键要点，"
    "直接输出摘要正文，不要前言与客套。"
    "不要输出任何密钥、口令、令牌等敏感值（如遇敏感信息，略过或写成「已省略」）：\n\n{text}"
)

#: 文档摘要笔记的来源标记（canonical 真相层第三条写路径；与 `notes.promote` / `notes.turn` 并列）。
_SUMMARY_NOTE_SOURCE = "notes.rag"


def _doc_summary_note(store: NoteStore, *, doc_id: str, summary: str) -> NoteEntry | None:
    """一份文档摘要 → canonical 结论笔记（幂等覆盖），或 ``None``（无可派生笔记名 ⇒ 不写盘）。

    **桥搭在入口侧**：`notes` 包的**公开面**不得承载「外部文档语料」维度（`doc` / `rag` …）
    —— ADR-0148 三面边界由 `tests/test_architecture.py:426` 的结构门禁钉死 ⇒ 本函数落在
    `entry`（`test_rag_not_imported_by_reference_chain` 明列的两个 rag 例外之一），直接复用
    `NoteStore.update`（**唯一**写路径，与 `promote.py` 同纪律）。`pinned=False` 不占常驻预算。

    摘要正文 SHALL 落盘前**无条件** `redact_secrets`（change 0224）：文档全文经模型产出的摘要可能
    夹带密钥形态子串，而本笔记**长期可检索** ⇒ 信任边界在**写入侧**，不依赖提示词自律。脱敏**只
    作用于正文**，不碰 `note_id` / `title`（派生键 ⇒ 保幂等覆盖）。
    """
    derived = slug_topic(doc_id)
    if not derived:
        return None
    note_id = f"doc-{derived}"
    try:
        existing: NoteEntry | None = store.get(note_id)
    except NoteError:
        existing = None
    body = f"## 文档摘要（{doc_id}）\n\n{redact_secrets(summary.strip())}"
    title = (existing.title if existing is not None else "") or f"文档摘要 {doc_id}"
    return store.update(
        NoteEntry(
            note_id=note_id,
            title=title,
            content=body,
            tags=["rag", f"doc:{doc_id}", "summary"],
            source=_SUMMARY_NOTE_SOURCE,
            pinned=False,
        )
    )


def _write_doc_summary_note(runtime: Any, *, doc_id: str, text: str) -> None:
    """`--summarize` 副作用：一次模型调用产摘要 → `_doc_summary_note` 落结论笔记。

    失败（模型调用 / 落盘）**不**冒泡（摄取已成败局已定），只告警落 stderr 且**只报 `doc_id`**。
    """
    try:
        response = runtime.llm.completion(
            LLMRequest(
                messages=[Message(role="user", content=_DOC_SUMMARY_PROMPT.format(text=text))],
                model=runtime.app.llm.model,
            )
        )
        note = _doc_summary_note(_notes_store(), doc_id=doc_id, summary=response.content)
    except Exception as exc:  # noqa: BLE001 — 摘要失败不阻断摄取的既有成败局
        print(f"文档摘要失败（doc_id={doc_id}）: {type(exc).__name__}", file=sys.stderr)
        return
    if note is None:
        print(f"文档摘要未落（doc_id={doc_id}：无可派生笔记名）", file=sys.stderr)


def _rag_search(runtime: Any, args: argparse.Namespace) -> int:
    """`rag search <query> --top-k N`：打印按相似度降序的 top-k 片段（不调用生成）。"""
    hits = runtime.rag.search(args.query, top_k=args.top_k)
    if not hits:
        print("无命中")
        return 0
    for index, hit in enumerate(hits, start=1):
        text = hit.chunk.text.replace("\n", " ")
        print(
            f"{index}. {hit.score:.4f}  {hit.chunk.chunk_id}  来源 {hit.chunk.doc_id}  {text[:60]}"
        )
    return 0


def _rag_ask(runtime: Any, args: argparse.Namespace) -> int:
    """`rag ask <query> --top-k N`：检索片段注入生成链路并打印答案。"""
    print(runtime.rag.ask(args.query, top_k=args.top_k))
    return 0


_NOTES_USAGE = (
    "用法: core-agent notes {list|show <note_id>|search <query>|"
    "pin <note_id> [--priority N]|unpin <note_id>|pinned|"
    "promote <session-id> [--as ID] [--title T]}"
)


def _notes_store() -> NoteStore:
    """canonical 真相层门面：与组合根同源的 canonical 目录（`notes` 走文件、零凭据）。"""
    return NoteStore(path=_state_path("notes"))


def _notes(args: argparse.Namespace) -> int:
    """文档化记忆操作面：列清单 / 打印一篇 / 词法检索（读）+ 常驻标记（写回 canonical 文档层）。"""
    handlers = {
        "list": _notes_list,
        "show": _notes_show,
        "search": _notes_search,
        "pin": _notes_pin,
        "unpin": _notes_unpin,
        "pinned": _notes_pinned,
        "promote": _notes_promote,
    }
    handler = handlers.get(args.notes_cmd or "")
    if handler is None:
        print(_NOTES_USAGE, file=sys.stderr)
        return 1
    try:
        return handler(_notes_store(), args)
    except NoteError as exc:
        print(f"notes 错误 [{exc.code.value}]: {exc.message}", file=sys.stderr)
        return 1


def _notes_list(store: NoteStore, _args: argparse.Namespace) -> int:
    """`notes list`：列出 canonical 笔记清单（id / 标题 / 更新时间）。"""
    notes = store.list()
    if not notes:
        print("（无笔记）")
        return 0
    for note in notes:
        marker = "\t[pinned]" if note.pinned else ""  # 非常驻行输出逐字不变
        print(f"{note.note_id}\t{note.title or note.note_id}\t{int(note.updated_at)}{marker}")
    return 0


def _notes_pin(store: NoteStore, args: argparse.Namespace) -> int:
    """`notes pin <note_id> [--priority N]`：置常驻并设优先级（**幂等**，同值不写盘）。"""
    store.set_pinned(args.note_id, pinned=True, priority=args.priority)
    print(f"已常驻: {args.note_id}\t优先级 {args.priority}")
    return 0


def _notes_unpin(store: NoteStore, args: argparse.Namespace) -> int:
    """`notes unpin <note_id>`：清常驻标记并归零优先级（缺失 ⇒ ``NOTE_NOT_FOUND`` 非零退出）。"""
    store.set_pinned(args.note_id, pinned=False)
    print(f"已取消常驻: {args.note_id}")
    return 0


def _notes_pinned(store: NoteStore, _args: argparse.Namespace) -> int:
    """`notes pinned`：列出常驻笔记 + 优先级 + **是否进场**（超预算篇目报未进场，change 0154）。"""
    notes = store.pinned()
    if not notes:
        print("（无常驻笔记）")
        return 0
    excluded = set(store.pinned_overflow())
    for note in notes:
        status = "[未进场]" if note.note_id in excluded else "[在场]"
        print(f"{note.note_id}\t{note.title or note.note_id}\t优先 {note.pin_priority}\t{status}")
    return 0


def _memory_chain() -> ChainHandle:
    """情景链取数句柄（**零效应只读**裸实例：`session_chain` 走 `_all_entries()` 而非 `read()`
    ⇒ 不强化 `reuse_count`、不记任何效应），与 `_memory_summary` **同源同构**。
    """
    return MemoryStore(backend=FileBackend(_state_path("memory.jsonl"))).session_chain


def _memory_summary(session_id: str) -> MemoryEntry | None:
    """按会话取回既有压实摘要（**只读**裸实例：全参可选 ⇒ 零凭据、零 LLM、不触发压实）。

    与组合根同源：`_state_path("memory.jsonl")` 即 `Runtime._memory_path()`。
    """
    return MemoryStore(backend=FileBackend(_state_path("memory.jsonl"))).summary_for(session_id)


def _notes_promote(store: NoteStore, args: argparse.Namespace) -> int:
    """`notes promote <session-id>`：会话摘要 → canonical 常驻笔记（**显式**触发，change 0150）。"""
    summary = _memory_summary(args.session_id)
    if summary is None:
        print(f"notes 错误: 会话无摘要: {args.session_id}", file=sys.stderr)
        return 1
    note = promote_session_summary(
        store,
        summary,
        session_id=args.session_id,
        as_note_id=args.as_note_id,
        title=args.title,
    )
    if note is None:
        # 来源守护（change 0151）：撞非 promotion 来源且未给 --as ⇒ 拒绝；或派生 id 为空。
        print(
            f"notes 错误: 无法提升（无摘要派生 id，或目标主题来源冲突；如系有意覆写请用 --as）: "
            f"{args.session_id}",
            file=sys.stderr,
        )
        return 1
    print(f"已提升: {note.note_id}\t[pinned]")
    return 0


def _notes_show(store: NoteStore, args: argparse.Namespace) -> int:
    """`notes show <note_id>`：打印一篇 canonical 笔记（不存在 ⇒ 退出码非零）。"""
    print(render_note(store.get(args.note_id)))
    return 0


def _notes_search(store: NoteStore, args: argparse.Namespace) -> int:
    """`notes search <query>`：词法检索并按命中顺序打印摘要。"""
    hits = store.search(args.query, top_k=args.top_k)
    if not hits:
        print("无命中")
        return 0
    for index, note in enumerate(hits, start=1):
        text = " ".join(note.content.split())
        print(f"{index}. {note.title or note.note_id}  [{note.note_id}]  {text[:60]}")
    return 0


def _run(args: argparse.Namespace) -> int:
    prompt = _read_prompt(args)
    if prompt is None:
        print("用法: core-agent run [--prompt TEXT | --file PATH]", file=sys.stderr)
        return 1
    api = _build_ui(args, surface_recovery=True)
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
        # 增量帧（Event 层映射为专类型 loop.delta，change `0132` / ADR-0125）不逐行打印，
        # 完整回复由终态 LoopResult 事件（loop.result）携带；思考回显（loop.reasoning，
        # change 0145 / ADR-0137）同判据 —— 非交互入口无折叠块可承载，逐段打印只会刷屏
        if event.type in ("loop.delta", "loop.reasoning"):
            continue
        if event.type.startswith("loop.action_"):  # 工具动作行（与 TUI 同构单行）
            line = format_action_event(
                event.type.removeprefix("loop."), payload, default_shell=api.default_shell
            )
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
        runtime = build_runtime(_config_manager(args))
    except Exception as exc:  # noqa: BLE001 — 配置/装配失败统一转 stderr 退出码
        print(f"装配失败: {exc}", file=sys.stderr)
        return 1
    goal = args.goal or ""
    task_id = args.task_id or f"task-{uuid.uuid4().hex[:8]}"
    plan: Plan | None = None
    completed: set[str] | None = None
    results: dict[str, str] | None = None
    # 会话归因（change 0190）：fresh 经共享注册表铸会话；resume 复用检查点的发起会话
    # （旧占位值 "default" / 空视作未归属，与既往行为逐字一致，不迁移旧数据）。
    session_id = ""
    if args.resume_id:
        cps = runtime.checkpoints.list_checkpoints(task_id=args.resume_id)
        if not cps:
            print(f"未找到任务 {args.resume_id} 的检查点", file=sys.stderr)
            return 1
        latest = max(cps, key=lambda cp: cp.ts)  # ts 序取最新（与 restore 同口径；change 0191）
        state = runtime.checkpoints.get_snapshot(latest.checkpoint_id).state
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
        checkpoint_session = str(getattr(latest, "session_id", "") or "")
        if checkpoint_session and checkpoint_session != "default":
            session_id = checkpoint_session  # 复用发起会话（同一任务跨续跑不分裂）
        else:
            print("检查点未携带会话标识（旧版检查点），子任务轨迹归全局层", file=sys.stderr)
    else:
        # fresh：与 run CLI 同注册表同 mode 铸会话（session list 可见；不建 UI 装配）
        session_id = SessionRegistry(path=_state_path("conversations.json")).create("cli")
        _surface_incomplete(runtime)  # 起新任务时呈现未完成任务（只呈现不重执行；change 0191）
    if not goal:
        print("缺少任务目标（检查点未携带且未给定 <目标>）", file=sys.stderr)
        return 1
    failed = asyncio.run(
        _stream_task(runtime.orchestrator, task_id, goal, plan, completed, results, session_id)
    )
    return 1 if failed else 0


async def _stream_task(  # noqa: PLR0913, PLR0917 — 续跑注入面参数组
    orchestrator: TaskScheduler,
    task_id: str,
    goal: str,
    plan: Plan | None,
    completed: set[str] | None,
    results: dict[str, str] | None,
    session_id: str = "",
) -> bool:
    """流式驱动编排器并打印进度事件；返回是否终态失败（task_failed）。"""
    failed = False
    async for event in orchestrator.astream(
        task_id, goal, plan=plan, completed=completed, results=results, session_id=session_id
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
    mgr = _config_manager(args)
    # 前置判定同样走 ConfigSpec 单一真源三层链（CLI > env > config.yaml > 缺省）：
    # 只读单键、不校验整份配置，故无配置文件时按 env/CLI/缺省解析（配置层 E21）。
    if not _as_bool(mgr.config_value("pet.enabled")):
        print(
            "宠物模式未启用（pet.enabled=false，可用 --pet-enabled 或 CORE_PET_ENABLED 开启）",
            file=sys.stderr,
        )
        return 0
    persons_dir = str(mgr.config_value("pet.persons_dir") or "persons")
    verb: str | None = args.verb
    name, rest = _split_pet_name(list(args.rest or []))

    if verb is None:
        print(
            "用法: core-agent pet <verb> [--name NAME] [--session ID] [...]"
            "（gather|info|explore|walk|list|run|status|result|sleep|wake|assign|stop）"
        )
        return 0
    try:
        runtime = build_runtime(mgr)
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
    if verb == "run":
        return _pet_run(manager, rest)
    if verb in ("status", "result", "sleep", "wake", "assign", "stop"):
        return _pet_control(verb, rest, manager)
    session = activator.activate_from_cli(verb, rest, persona=_load_persona(persons_dir, name))
    print(f"已激活宠物会话 {session.session_id}（verb={verb}，状态 {session.state.value}）")
    return 0


def _pet_control(verb: str, rest: list[str], manager: PetManager) -> int:
    """控制面 CLI（change `0088` / 用户诉求①）：`status|sleep|wake|assign|stop` → `PetControl`。

    与 `UIAPILayer.pet_command` 复用**同一** `PetControl`（单一口径）；未知会话 / 多宠物
    未指定 ⇒ 结构化拒绝 + 退出 1。
    """
    session_id, task = _split_pet_session(rest)
    control = PetControl(manager)
    target = session_id or (task[0] if task else None)
    try:
        if verb == "status":
            _print_pet_status(control.status(target))
            return 0
        if verb == "result":
            _print_pet_result(control.result(target))
            return 0
        if verb == "assign":
            print(control.assign(" ".join(task), session_id=session_id))
            return 0
        # 其余三动词签名一致（`session_id=None -> str`），按 verb 取绑定方法
        ops = {"sleep": control.sleep, "wake": control.wake, "stop": control.stop}
        print(ops[verb](target))
    except PetError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _print_pet_status(status: dict[str, Any]) -> None:
    """控制面状态呈现（结构化字段 → 一行；不含偏好与任务正文）。"""
    sleeping = "是" if status["sleeping"] else "否"
    print(
        f"宠物 {status['session_id']}：状态 {status['state']}，休眠 {sleeping}，"
        f"待办 {status['pending']}，唤醒计数 {status['wake_count']}，故障 {status['fault'] or '-'}"
    )


def _print_pet_result(result: dict[str, Any]) -> None:
    """结果查询面呈现（change 0113 / E46）：无结果时**明确报无**，不编造正文。"""
    if not result["has_result"]:
        print(f"宠物 {result['session_id']}：无最近任务结果")
        return
    outcome = "失败" if result["failed"] else "成功"
    print(f"宠物 {result['session_id']}：最近任务结果（{outcome}）：{result['reply']}")


def _split_pet_session(rest: list[str]) -> tuple[str | None, list[str]]:
    """从 free-text rest 提取 `--session ID`，其余原样返回。

    与 `_split_pet_name` 同款：robust 处理任意顺序。
    """
    session_id: str | None = None
    task: list[str] = []
    i = 0
    while i < len(rest):
        if rest[i] == "--session" and i + 1 < len(rest):
            session_id = rest[i + 1]
            i += 2
        else:
            task.append(rest[i])
            i += 1
    return session_id, task


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


def _pet_run(manager: PetManager, rest: list[str]) -> int:
    """`pet run [--interval 秒]`：常驻驱动已注册宠物（尾随文本忽略，Ctrl-C 停止）。

    驱动者 = **用户显式启动的宿主进程**（`0065` 裁决「内核不自建 daemon」的宿主侧落地）；
    无已注册会话时只提示激活入口，**不自动造宠物**（激活归三入口，避免第二真源）。
    """
    interval, _ = _split_pet_interval(rest)
    if interval is None:
        print("用法: core-agent pet run [--interval 秒]（间隔须为正数）", file=sys.stderr)
        return 1
    pets = manager.list()
    if not pets:
        print(
            "当前无激活宠物（先用 gather|info|explore|walk 激活，或在 ui 入口激活）",
            file=sys.stderr,
        )
        return 0
    print(f"已开始驱动 {len(pets)} 只宠物会话（间隔 {interval:g}s，Ctrl-C 停止）")

    def _on_tick(outcomes: list[WakeOutcome]) -> None:
        manager.persist()  # 唤醒消费任务 / 计数递增等驱动侧变更先落盘再呈现
        _report_wake_tick(outcomes)

    try:
        PetWakeDriver(manager.list).run(interval, on_tick=_on_tick)
    except KeyboardInterrupt:
        print("已停止驱动")
    return 0


def _split_pet_interval(rest: list[str]) -> tuple[float | None, list[str]]:
    """从 free-text rest 提取 `--interval 秒`，其余原样返回（缺省 60s）。

    `pet` 子命令用 `REMAINDER` 收自由文本，故旗标与任务词同处 `rest`（同 `_split_pet_name`）。
    非法 / 缺失 / 非正值 → `(None, [])`，调用方报用法并退出 1。
    """
    interval = 60.0
    task: list[str] = []
    i = 0
    while i < len(rest):
        if rest[i] == "--interval":
            if i + 1 >= len(rest):
                return None, []
            try:
                value = float(rest[i + 1])
            except ValueError:
                return None, []
            if value <= 0:
                return None, []
            interval = value
            i += 2
        else:
            task.append(rest[i])
            i += 1
    return interval, task


def _report_wake_tick(outcomes: list[WakeOutcome]) -> None:
    """一轮唤醒的呈现：唤醒数到 stdout，意外失败到 stderr（预期态静默 —— 让行是常态）。"""
    woken = sum(1 for outcome in outcomes if outcome.status == WOKEN)
    if woken:
        print(f"已驱动 {woken} 只宠物")
    for outcome in outcomes:
        if outcome.status == FAILED:
            print(f"宠物 {outcome.session_id} 唤醒失败：{outcome.reason}", file=sys.stderr)


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
        return build_runtime(_config_manager(args))
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
    _print_beast_result(session.result_summary())
    return 0


def _print_beast_result(summary: dict[str, Any]) -> None:
    """呈现神兽任务结果（change 0113 / E46）：有结果才打印，**不**编造正文。"""
    if not summary["has_result"]:
        return
    outcome = "失败" if summary["failed"] else "成功"
    print(f"结果（{outcome}）：{summary['reply']}")


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
    "rag": _rag,
    "notes": _notes,
    "evolve": _evolve,
    "run": _run,
    "task": _task,
    "time-travel": _time_travel,
    "config": _config,
    "mcp": _mcp,
    "plugin": _plugin,
    "skill": _skill,
    "release": _release,
    "probe": _probe,
    "sessions": _sessions,
    "start": _ops,
    "stop": _ops,
    "restart": _ops,
    "status": _status,
    "doctor": _doctor,
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
    for item in cast("list[str]", getattr(args, "feature", None) or []):
        name, value = _parse_feature_flag(item)
        cli[f"features.{name}"] = value
    return cli


def _parse_feature_flag(item: str) -> tuple[str, str]:
    """`--feature NAME[=BOOL]` → ``(模块名, 取值原文)``；裸名视为开（metavar 语义）。

    **模块名是开放集合**（门控名单归组合根 `runtime.GATABLE_MODULES`，配置层不认识模块名，
    ADR-0065）⇒ 该 flag 不入 `ConfigSpec`，在此单独收集。语法非法（缺名 / 缺值）当场拒绝；
    取值本身的合法性与三面归一由配置层统一负责（`_normalize_features`，单一真源）。
    """
    name, sep, value = item.partition("=")
    name = name.strip()
    if not name or (sep and not value.strip()):
        raise ValueError(f"非法 --feature 取值: {item!r}（须为 NAME 或 NAME=BOOL）")  # noqa: TRY003
    return name, (value.strip() if sep else "true")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes", "on")


if __name__ == "__main__":  # sidecar 的调用面：`python -m core.entry serve …`（change 0100）
    raise SystemExit(main())
