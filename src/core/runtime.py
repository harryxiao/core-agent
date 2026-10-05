"""组合根（runtime）：唯一被允许 import 全模块、专职装配的地方。

把 Phase 0–11 的 DI 友好构造串成可运行系统：ConfigManager.load → resolve_secret
→ StdlibLLMProvider → MemoryStore / ToolProvider / Tracer → judgment（DecisionRouter /
Compactor / Guardrail）→ LLMPlanner → PermissionGuard → DefaultLoop，供 entry 三入口复用。

架构约束：全仓库除本文件外，任何模块不得 import core.runtime（test_architecture 断言）。
"""

from __future__ import annotations

import os
import sys
import warnings
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from core.beast import BeastActivator, BeastManager, BeastRegistry, register_innate_skills
from core.beast.models import Beast
from core.configuration import ConfigManager
from core.configuration.models import AppConfig
from core.context import Compactor as ContextCompactor
from core.context import DynamicAssembler
from core.core_profile import CoreProfileEngine
from core.durability import (
    CheckpointManager,
    CheckpointStore,
    CrashRecovery,
    DurabilityError,
    RestoreHandle,
    TimeTravel,
)
from core.evolution import (
    Diagnoser,
    Evaluator,
    EvolutionEngine,
    EvolutionTrigger,
    EvolutionWorker,
    ObservationRegistry,
    PendingQueue,
    Proposer,
    Validator,
)
from core.judgment import Compactor, DecisionRouter, Guardrail, JEVProvider, SkillMatcher
from core.llm_provider import LLMProvider, LLMRequest, Message, StdlibLLMProvider
from core.loop import Approver, DefaultLoop, LoopPlugin, TurnObserver
from core.loop.constraints_adapter import build_constraints_chain
from core.loop.planner import LLMPlanner, SkillHint
from core.mcp import MCPClient, MCPEndpointRegistry, mcp_endpoints_path
from core.memory import (
    Crystallizer,
    FileBackend,
    MemoryBackend,
    MemoryEntry,
    MemoryStore,
    batch_embed,
    summarize_with,
)
from core.notes import NoteStore
from core.observability import BufferedExporter, JSONLExporter, Tracer
from core.orchestration import (
    AgentProfile,
    LLMSubtaskPlanner,
    LLMVerifier,
    MultiAgentRouter,
    OrchestrationError,
    Plan,
    StateMachine,
    SubtaskDecomposer,
    SubtaskOutcome,
    TaskScheduler,
    plan_to_dict,
)
from core.permission import PermissionGuard, SandboxManager, SandboxPolicy
from core.pet.core import PetActivator, PetManager, PetSession
from core.pet.explore import Explorer
from core.pet.microtask import MicrotaskRunner
from core.pet.notify import AsyncNotifier
from core.pet.safety import SafetyBounds, build_safety_middleware
from core.plugin_registry import CoeffectResolver, EffectTracker, PluginInstaller
from core.plugins import (
    InstallDispatcher,
    PluginInstallRegistry,
    default_install_store,
    plugin_installs_path,
)
from core.rag import HashEmbedder, LLMEmbedder, RagGenerator, RagService, SqliteVectorStore
from core.skills import (
    Skill,
    SkillFeedback,
    SkillIterator,
    SkillLibrary,
    SkillRouter,
    SopExtractor,
    VersionManager,
    skill_hint,
    sop_writer_with,
)
from core.tools import (
    Tool,
    ToolDef,
    ToolProvider,
    code_run,
    file_patch,
    file_read,
    file_write,
    install_tool,
    list_tool,
    uninstall_tool,
    web_fetch,
)

# 门控名单（change 0067 / 账本 E10）：组合根装配的**可选**模块 —— 本元组是单一真源，
# configuration 层不认识模块名。名单内模块缺省装配（未声明即开，兼容既有行为），仅显式
# `features.<模块>: false` 才完全**不装配**（不构造实例、不产生装配期副作用、入口拒绝）；
# 名单外的名字不触发任何裁剪。见 configuration spec「功能开关（feature flag）」。
GATABLE_MODULES: tuple[str, ...] = ("pet", "beast", "evolution")


@dataclass
class Runtime:
    """组合根产物：已装配运行系统。

    除 `GATABLE_MODULES` 三项对应的字段（见各字段旁注，关闭时为空）外，所有依赖非空。
    """

    app: AppConfig
    config: ConfigManager
    llm: LLMProvider
    memory: MemoryStore
    tools: ToolProvider
    tracer: Tracer
    router: DecisionRouter
    rag: RagService
    loop: DefaultLoop
    skill_router: SkillRouter
    skill_feedback: SkillFeedback
    skill_iterator: SkillIterator
    skill_extractor: SopExtractor
    installer: PluginInstaller
    mcp_client: MCPClient
    evolution: EvolutionWorker | None  # 空 = features.evolution: false（未装配）
    orchestrator: TaskScheduler
    checkpoints: CheckpointManager
    time_travel: TimeTravel
    crash_recovery: CrashRecovery
    pet_manager: PetManager | None  # 空 = features.pet: false（未装配）
    pet_activator: PetActivator | None
    beast_manager: BeastManager | None  # 空 = features.beast: false（未装配）
    beast_activator: BeastActivator | None

    def recover(self) -> list[RestoreHandle]:
        """启动时扫描检查点，恢复无 done 标记的任务（返回续跑句柄）。"""
        return _recover_incomplete(self.checkpoints, self.crash_recovery)


def _checkpoint_path() -> Path:
    """检查点落盘路径：$CORE_STATE_DIR（缺省 ~/.core/state）/checkpoints.jsonl。

    与 entry 的全局状态目录约定一致；env 覆盖便于测试隔离。
    """
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / "checkpoints.jsonl"


def _memory_path() -> Path:
    """记忆落盘路径：$CORE_STATE_DIR（缺省 ~/.core/state）/memory.jsonl。

    与检查点共用全局状态目录约定；env 覆盖便于测试隔离。
    """
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / "memory.jsonl"


def _trace_path() -> Path:
    """遥测落盘路径：$CORE_STATE_DIR（缺省 ~/.core/state）/traces.jsonl。

    同检查点 / 记忆的状态目录约定；组合根缺省导出器把 trace 事件追加于此（change 0089）。
    """
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / "traces.jsonl"


def _rag_index_path() -> Path:
    """rag 落盘索引路径：$CORE_STATE_DIR（缺省 ~/.core/state）/rag-index.db。

    同检查点 / 记忆的状态目录约定；索引是落盘真源 ⇒ 一次 `rag ingest` 的成果在后续
    进程的检索中可见（见 rag spec「索引跨进程复用」）。
    """
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / "rag-index.db"


def _skill_state_path(name: str) -> Path:
    """技能态落盘路径：$CORE_STATE_DIR（缺省 ~/.core/state）/<name>。

    同检查点 / 记忆的状态目录约定；技能态是可变快照，故用单文件 JSON（见 skills.persist）。
    """
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / name


def _notes_path() -> Path:
    """文档化记忆 canonical 目录：$CORE_STATE_DIR（缺省 ~/.core/state）/notes。

    同检查点 / 记忆的状态目录约定；canonical Markdown 文件是**落盘真源** ⇒ 一次写回在后续
    进程（`notes list/show/search`）可见（见 notes spec「canonical 真相层」）。
    """
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / "notes"


def _notes_workflow_skill() -> Skill:
    """内置循环技能：Consult→Build→Update 纪律载体（由组合根构造，不下沉 notes 包）。

    `notes` 是 L2 文档化真相层，**不向上依赖 L3 skills** ⇒ 技能装配与注入归 L3 组合根。
    `instructions` 同时承载「先 Consult、后 Update」两段纪律，经既有技能路由注入推理上下文。
    """
    return Skill(
        skill_id="skills.notes.consult_build_update",
        description="文档化记忆循环：先 Consult 相关笔记、再 Build、再 Update 写回 canonical 文档",
        task_types=["notes", "documentation", "remember", "决策记录", "研究笔记", "解决过程"],
        preconditions=[],
        param_schema={},
        instructions=(
            "1) Consult：任务前先读相关 canonical 笔记（NoteStore.consult）与笔记清单；"
            "2) Build：在既有结论之上执行任务；"
            "3) Update：任务后把新结论/决策/解决过程覆盖式写回对应主题的 canonical Markdown 文件"
            "（去重、精炼、保持权威）。"
        ),
        version="v1",
        status="active",
    )


def _pet_state_path() -> Path:
    """宠物注册表落盘路径：$CORE_STATE_DIR（缺省 ~/.core/state）/pets.json。

    同检查点 / 技能态的状态目录约定；注册表是可变快照，故用单文件 JSON（见 pet.core.manager）。
    """
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / "pets.json"


def _pet_notification_sink(message: str) -> None:
    """宠物通知缺省投递：写 stderr（主人可见的观测面，不污染 stdout 机读输出）。

    真实通道（IM 网关等）由宿主注入替换；缺省 sink 保证规格「异步投递」在无宿主时亦可达
    （账本 E16）。
    """
    print(f"[pet] {message}", file=sys.stderr)


# 子 Agent 委托运行完整子循环（多次 LLM 往返 + 工具轮），远超 ToolDef 默认 30s
_DELEGATE_TIMEOUT_S = 600.0

# 委托深度护栏：子 Agent 工具面已不含 delegate，此处为纵深防御
_DELEGATE_DEPTH: ContextVar[int] = ContextVar("delegate_depth", default=0)


def build_runtime(  # noqa: PLR0915, PLR0913, PLR0912, C901
    config: ConfigManager,
    *,
    assembler: DynamicAssembler | None = None,
    tracer: Tracer | None = None,
    memory_backend: MemoryBackend | None = None,
    approver: Approver | None = None,
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
) -> Runtime:
    """装配全量依赖：ConfigManager.load → resolve_secret → 各层组件 → DefaultLoop。

    密钥仅经 resolve_secret 取明文供 provider 构造，随后登记到 tracer 脱敏，
    绝不落日志 / 记忆 / 轨迹。LLM 配置缺失或非法时 load() 抛 ConfigurationError，
    结构化拒绝启动。
    """
    app = config.load()
    api_key = config.resolve_secret(app.llm.api_key_ref)
    llm = StdlibLLMProvider(
        api_key=api_key,
        base_url=app.llm.endpoint or None,
        model=app.llm.model,
    )
    # 缺省导出面（change 0089）：JSONL 落 $CORE_STATE_DIR，经缓冲/退避重试包装 ——
    # 导出失败降级为内存缓冲，绝不抛进主循环（规格「遥测故障不阻塞主循环」）；注入者优先。
    tracer = (
        tracer
        if tracer is not None
        else Tracer(exporter=BufferedExporter(JSONLExporter(_trace_path())))
    )
    tracer.register_secret(api_key)

    jev: JEVProvider | None = None
    threshold = 0.7
    judgment = app.judgment
    if judgment is not None and judgment.provider:
        jev = JEVProvider(
            api_key=config.resolve_secret(judgment.api_key_ref),
            base_url=judgment.base_url,
            model=judgment.model,
        )
        threshold = judgment.confidence_threshold
    router = DecisionRouter(
        provider=jev, fallback=llm, confidence_threshold=threshold, tracer=tracer
    )

    guard = PermissionGuard(
        mode=config.permission_mode(),
        guardrail=Guardrail(router) if jev is not None else None,
    )
    backend = memory_backend if memory_backend is not None else FileBackend(_memory_path())
    effect_tracker = EffectTracker()
    # 语义 embedding 来源（0040 / 0104 共用）：llm.embedding_model 非空时以该模型**另构造**
    # provider（聊天模型名打 /embeddings 通常 404），memory 通路经 rag LLMEmbedder →
    # batch_embed 适配为批量契约、rag 通路直接消费 LLMEmbedder；密钥复用 api_key（已登记脱敏）。
    # 未设置则不构造 → memory 走 0039 词法路径、rag 走离线 HashEmbedder 降级基线，
    # 远端不可达由调用期降级兜底，均不阻断启动。
    embed_provider = (
        StdlibLLMProvider(
            api_key=api_key,
            base_url=app.llm.endpoint or None,
            model=app.llm.embedding_model,
        )
        if app.llm.embedding_model
        else None
    )
    if embedder is None and embed_provider is not None:
        embedder = batch_embed(LLMEmbedder(embed_provider).embed)

    # 记忆摘要接缝（0041）：LLM 提炼经 summarize_with 适配为 memory 的摘要契约
    # （与 embedding 同一依赖方向：memory 不 import LLM 抽象，组合根注入模型调用）。
    def _llm_text(prompt: str) -> str:
        """prompt → 文本：摘要（memory）与提炼（skills）两条 DI 接缝共用的模型调用外壳。"""
        response = llm.completion(
            LLMRequest(messages=[Message(role="user", content=prompt)], model=app.llm.model)
        )
        return response.content

    summarizer = summarize_with(_llm_text)
    memory = MemoryStore(
        backend=backend,
        effect_tracker=effect_tracker,
        compactor=Compactor(router) if jev is not None else None,
        embedder=embedder,
        summarizer=summarizer,
    )
    # 上下文压实接线（0041）：多轮历史 → persist 落 L2；此前 context.Compactor 与
    # memory.compact 都无生产调用方（死路径），现由 loop 的轮数/预算阈值触发。
    context_compactor = ContextCompactor(memory=memory)
    # rag 主链路装配（0104）：落盘索引 + 语义优先 / 离线降级的 embedding + 生成融合，
    # 由 RagService 门面收口（CLI / 宿主只调用门面，不各自拼四个对象）。
    rag = RagService(
        LLMEmbedder(embed_provider) if embed_provider is not None else HashEmbedder(),
        SqliteVectorStore(_rag_index_path()),
        generator=RagGenerator(llm, model=app.llm.model),
    )
    resolver = CoeffectResolver()
    resolver.register("filesystem:read", True)
    resolver.register("filesystem:write", True)
    resolver.register("process:spawn", True)
    resolver.register("network:outbound", True)
    resolver.register("agent:delegate", True)  # 委托能力：显式声明供默认暴露面识别（B7）
    tools = ToolProvider(
        coeffect_resolver=resolver, effect_tracker=effect_tracker, gate=guard, approver=approver
    )
    builtin_tools = (file_read(), file_write(), file_patch(), code_run(), web_fetch())
    for tool in builtin_tools:
        tools.register(tool)

    # 技能态落盘（0050）：四类运行态注入 $CORE_STATE_DIR 下状态文件 → 重启恢复；
    # 此前技能库/反馈/样本/灰度全活进程内，结晶链路每进程从零开始（账本 A3）。
    skill_library = SkillLibrary(path=_skill_state_path("skills.json"))
    # 技能反馈（0045）先于路由构造：既是路由排序的历史成功率来源（0058），
    # 也是迭代器/版本指标的数据源——同一实例，避免「迭代看一套数、路由看另一套数」。
    skill_feedback = SkillFeedback(path=_skill_state_path("skill-feedback.json"))
    # 语义兜底（0044）：仅 JEV 配置时注入打分器；否则纯词法（词法命中零模型调用）
    skill_router = SkillRouter(
        skill_library,
        memory=memory,
        scorer=SkillMatcher(router).score if jev is not None else None,
        feedback=skill_feedback,
    )
    # SOP 提炼接线（0043）：成功任务收尾的轨迹经提炼器归组、达阈值提炼为技能入库——
    # 此前技能库只有注册/路由/版本三段，无任何产生技能的入口（生产恒为空）。
    sop_extractor = SopExtractor(
        skill_library,
        writer=sop_writer_with(_llm_text),
        effect_tracker=effect_tracker,
        path=_skill_state_path("sop-samples.json"),
    )
    # 技能迭代接线（0045）：命中注入 + 执行反馈 + 迭代闭环。反馈落盘见上（0050 注入路径，
    # 0058 起同时供路由排序）；迭代复用 VersionManager 的灰度/A/B（0048 决策 ⑥ 记的
    # 「能力已存在、无调用者」在此接上调用者），改写走与 SOP 同一注入接缝
    # （skills 不 import LLM 抽象）。
    # 版本管理器在此显式构造并注入（0050 决策 4）：`SkillIterator` 内部自建的那份拿不到，
    # 落盘需由组合根持有；顺带把「灰度/A-B 指标 = 各版本成功率」口径显式化。
    skill_iterator = SkillIterator(
        skill_library,
        skill_feedback,
        writer=sop_writer_with(_llm_text),
        versions=VersionManager(
            skill_library,
            metrics=lambda skill_id, version: skill_feedback.success_rate(skill_id, version),
            path=_skill_state_path("skill-versions.json"),
        ),
        tracker=effect_tracker,
    )

    # 神通注册（0057）：20 神兽独有神通进全局技能库，供**按兽作用域**路由（见 _beast_loop）。
    # 此前 build_innate_skills/register_innate_skills 零生产调用方（账本 E3）。
    beast_registry: BeastRegistry | None = None
    if not config.is_disabled("beast"):  # 门控：关闭时**连注册也不做**（注册即装配期副作用）
        beast_registry = BeastRegistry()
        register_innate_skills(skill_library, beast_registry)

    # 文档化记忆（0106）：canonical Markdown 真相层 + Consult→Build→Update 循环。NoteStore 经
    # 可插拔 `MarkdownBackend` 落盘（实现既有 `MemoryBackend` Protocol，**不改契约**）；内置循环
    # 技能由组合根构造并注册（notes 包不向上依赖 L3 skills）。与 RAG 语义召回层并列、互不交叉。
    note_store = NoteStore(path=_notes_path())
    skill_library.register(_notes_workflow_skill())

    def _consult_notes(task: str) -> str:
        """任务前 Consult：确定性读命中笔记 + 清单（loop 不 import notes，组合根注入闭包）。"""
        return note_store.digest(task)

    def _loop_hooks(
        domain: str | None = None,
    ) -> tuple[Callable[[str], list[SkillHint]], TurnObserver]:
        """每 loop 一组钩子闭包（命中注入 + 收尾反馈）：状态不跨 loop 共享。

        路由 → 版本解析 → 记命中 → 纯 dict 快照（loop 不 import skills）；收尾按本轮
        实际注入的 ``(技能, 版本)`` 记结果并顺势定夺/触发迭代，再把轨迹转交 SOP 观察者。

        ``domain`` 透传技能路由的专属作用域（神兽传自身 agent_id，其余不传）。
        """
        surfaced: list[tuple[Skill, str]] = []

        def hints(task: str) -> list[SkillHint]:
            result: list[SkillHint] = []
            for matched in skill_router.match(task, domain=domain):
                skill = matched.skill
                version, text = skill_iterator.resolve(skill)
                skill_feedback.record_hit(skill.skill_id, version=version)
                surfaced.append((skill, version))
                result.append(skill_hint(skill.skill_id, version, text))
            return result

        def on_turn(task: str, steps: list[str], ok: bool) -> None:
            for skill, version in surfaced:
                skill_feedback.record_outcome(skill.skill_id, version=version, ok=ok)
                skill_iterator.decide(skill)  # 两版本样本齐备 → A/B 定夺
                if not ok:
                    skill_iterator.consider(skill)  # 失败轮触发迭代（阈值门在迭代器内）
            surfaced.clear()
            sop_extractor.observe(task, steps, ok=ok)
            note_store.observe_turn(task, steps, ok=ok)  # 任务后 Update：成功轮覆盖式写回笔记

        return hints, on_turn

    loop_hints, loop_turn = _loop_hooks()
    # MCP 消费侧安全（0054）：stdio 子进程经沙箱资源配额拉起、http 出站经白名单；
    # 策略与沙箱共用一个实例（同口径）。白名单经配置注入（change 0071 / 账本 B5）：
    # `permission.sandbox.host_allowlist`（逗号分隔主机名，ConfigSpec 单一真源）；
    # 缺省空 = fail-closed 全拒出站（安全默认不变）。
    mcp_policy = SandboxPolicy(host_allowlist=config.sandbox_host_allowlist())
    mcp_client = MCPClient(sandbox=SandboxManager(policy=mcp_policy), policy=mcp_policy)
    dispatcher = InstallDispatcher(
        skill_library=skill_library, tool_provider=tools, mcp_client=mcp_client
    )
    # uninstaller 须对称注入（change 0108 / 账本 E33）：否则 `tools.uninstall` 只从 `_assets` 摘账，
    # 不做 kind 分发的真实回退（skill 移除 / cli·mcp 工具摘除）。
    installer = PluginInstaller(
        source_resolver=dispatcher.resolve,
        installer=dispatcher.install,
        uninstaller=dispatcher.uninstall,
        # 安装账本（change 0109 / 账本 E36）：与 CLI 同一真源 —— `tools.install` 与
        # `plugin install` 共享跨进程账本，构造期水合既有记录（否则两个入口各说各话）。
        store=default_install_store(),
    )
    # 插件安装工具接进生产工具面（change 0108 / 账本 E33，规格 tool-use「插件安装工具」）：
    # 须与组合根 installer 同一实例（否则装一次性注册表 = 谎报），注册排在 installer 构造之后。
    for install_op in (install_tool(installer), uninstall_tool(installer), list_tool(installer)):
        tools.register(install_op)
    # MCP 端点注册表（change 0074 / 账本 B4）：`mcp add` 的成果落 $CORE_STATE_DIR，
    # 装配期读回并经**同一安装管线**连接、把远端工具注册进本地工具集（`mcp.<端点名>.<工具>`）。
    # **单个端点不可达只告警跳过**：坏端点不得让整个系统不可用。
    for endpoint_record in MCPEndpointRegistry(mcp_endpoints_path()).list():
        try:
            dispatcher.install(endpoint_record.asset())
        except Exception as exc:  # noqa: BLE001 — 单端点故障降级，不阻断装配
            warnings.warn(f"MCP 端点不可用，已跳过: {endpoint_record.name}（{exc}）", stacklevel=2)
    # 插件安装账本（change 0109 / 账本 E36）：`plugin install --kind cli|skill` 的成果落
    # $CORE_STATE_DIR/plugin-installs.json；装配期读回并经**同一安装管线**重建物化
    # （cli → 工具面注册；skill → 技能库注册，本为 upsert ⇒ 幂等）。
    # 只重建**本账本**：mcp 类资产的物化由上面端点循环负责（同一资产不两处装配）。
    # 单条记录重建失败只告警跳过：坏记录不得让整个系统不可用。
    for install_record in PluginInstallRegistry(plugin_installs_path()).list():
        try:
            dispatcher.install(install_record.asset())
        except Exception as exc:  # noqa: BLE001 — 单条记录故障降级，不阻断装配
            warnings.warn(
                f"插件安装记录不可用，已跳过: {install_record.plugin_id}（{exc}）", stacklevel=2
            )

    # 上下文装配接线（P0）：两级 Core.md 的宪法 → constitution:v1 coeffect、
    # 项目信息 → ContextEngine 上下文。此前 build_runtime 从不传 assembler=，
    # planner._assembler 恒为 None，事实/宪法注入在生产从未发生
    # （Phase 17.5 §3.1 只改了装配器内部，未把它接上 runtime）。
    profile_engine = CoreProfileEngine(resolver=resolver)
    profile_engine.load_global()
    profile_engine.load_project()
    profile = profile_engine.assemble()
    # 人格分区 → L0 记忆层（core-profile spec「双语义分区」）：稳定 id 幂等写入，
    # 避免每次启动重复；L0 层优先级最高，读时随候选带出、受预算截断约束。
    if profile.personality:
        memory.write(
            "L0",
            MemoryEntry(
                id="core-profile:personality",
                layer="L0",
                content="\n".join(profile.personality),
                tags=["core-profile", "personality"],
                source="core-profile",
                trace_id="core-profile:startup",
            ),
        )
    if assembler is None:
        assembler = DynamicAssembler(
            memory=memory,
            constitution=list(profile.coeffect.get("constitution:v1", [])),
            project_info=list(profile.context),
        )
    planner = LLMPlanner(
        llm,
        model=app.llm.model,
        reasoning_effort=app.llm.reasoning_effort,
        assembler=assembler,
        skill_router=loop_hints,
        tools=tools,
    )
    # 门控（0067）：evolution 关闭 ⇒ 引擎/worker 不建，loop 冷路径与 trace 完成回调一并置 None
    # （不为「未装配」造空转闭包 —— DefaultLoop 本就接受 cold_path / trace_observer =None）。
    evolution: EvolutionWorker | None = None
    cold_path: Callable[[], None] | None = None
    trace_observer: Callable[[str], None] | None = None
    if not config.is_disabled("evolution"):
        evolution_engine = EvolutionEngine(
            diagnoser=Diagnoser(),
            proposer=Proposer(),
            validator=Validator(),
            evaluator=Evaluator(),
            library=skill_library,
            memory=backend,
            memory_crystallizer=Crystallizer(),
            observations=ObservationRegistry(path=_skill_state_path("observations.json")),
            pending=PendingQueue(path=_skill_state_path("evolution-pending.json")),
        )
        evolution_worker = EvolutionWorker(
            tracer=tracer, engine=evolution_engine, trigger=EvolutionTrigger()
        )
        evolution = evolution_worker

        def _cold_path() -> None:
            """收尾维护节拍的冷路径机会：跑一轮进化（阈值门在 worker 内，未达则不做事）。"""
            evolution_worker.maybe_run()

        cold_path = _cold_path
        # 主 loop 每轮收尾登记本轮 trace（热路径只登记、不触发；不随维护节拍节流）
        trace_observer = evolution_worker.on_trace_complete

    failure_threshold, cooldown_s = config.circuit_breaker()
    constraints_chain = build_constraints_chain(
        failure_threshold=failure_threshold, cooldown_s=cooldown_s
    )

    # 循环预算上限（change 0098）：可经配置链设定，token 预算由 llm.context_window 派生
    # （窗口 - 输出预留；未配窗口回落缺省 65536）。四个 loop（主 / 子 agent / 神兽 / 宠物）
    # 同源同参。
    max_rounds, token_budget = config.loop_limits()

    loop = DefaultLoop(
        planner=planner,
        memory=memory,
        tools=tools,
        gate=guard,
        tracer=tracer,
        router=router if jev is not None else None,
        approver=approver,
        compactor=context_compactor,
        turn_observer=loop_turn,
        notes_consult=_consult_notes,
        cold_path=cold_path,
        trace_observer=trace_observer,
        middlewares=[constraints_chain.middleware],
        action_observers=[constraints_chain.observe_result],
        max_rounds=max_rounds,
        token_budget=token_budget,
    )

    # 子 Agent 独立 loop：各自 ToolProvider（不含 tools.delegate，结构上杜绝再委托），
    # 共享 memory / tracer / gate / approver（知识沉淀与权限口径统一）
    def _agent_tools() -> ToolProvider:
        provider = ToolProvider(
            coeffect_resolver=resolver, effect_tracker=effect_tracker, gate=guard, approver=approver
        )
        for tool in builtin_tools:
            provider.register(tool)
        return provider

    def _agent_loop(provider: ToolProvider) -> LoopPlugin:
        agent_hints, agent_turn = _loop_hooks()
        sub_planner = LLMPlanner(
            llm,
            model=app.llm.model,
            reasoning_effort=app.llm.reasoning_effort,
            assembler=assembler,
            skill_router=agent_hints,
            tools=provider,
        )
        return cast(
            LoopPlugin,
            DefaultLoop(
                planner=sub_planner,
                memory=memory,
                tools=provider,
                gate=guard,
                tracer=tracer,
                router=router if jev is not None else None,
                approver=approver,
                compactor=context_compactor,
                turn_observer=agent_turn,
                notes_consult=_consult_notes,
                middlewares=[constraints_chain.middleware],
                action_observers=[constraints_chain.observe_result],
                max_rounds=max_rounds,
                token_budget=token_budget,
            ),
        )

    def _beast_loop(beast: Beast) -> LoopPlugin:
        """按兽装配独立 loop：域内技能路由（专属神通） + 共享记忆/闸门/追踪。

        与 ``_agent_loop`` 同构，唯一差异是 ``_loop_hooks(beast.agent_id)`` —— 神兽只在
        自身域内看到自己的神通（beast-mode spec R4/R5）。
        """
        beast_hints, beast_turn = _loop_hooks(beast.agent_id)
        provider = _agent_tools()
        beast_planner = LLMPlanner(
            llm,
            model=app.llm.model,
            reasoning_effort=app.llm.reasoning_effort,
            assembler=assembler,
            skill_router=beast_hints,
            tools=provider,
        )
        return cast(
            LoopPlugin,
            DefaultLoop(
                planner=beast_planner,
                memory=memory,
                tools=provider,
                gate=guard,
                tracer=tracer,
                router=router if jev is not None else None,
                approver=approver,
                compactor=context_compactor,
                turn_observer=beast_turn,
                notes_consult=_consult_notes,
                middlewares=[constraints_chain.middleware],
                action_observers=[constraints_chain.observe_result],
                max_rounds=max_rounds,
                token_budget=token_budget,
            ),
        )

    # 多 Agent 运行时：coding / research 两个正交子 Agent，主 Agent 可委托并等待结果
    subagents = [
        AgentProfile(
            agent_id="coding",
            capabilities=["coding", "代码", "写代码", "实现", "开发", "编程"],
            loop=_agent_loop(_agent_tools()),
        ),
        AgentProfile(
            agent_id="research",
            capabilities=["research", "调研", "搜索", "检索", "查询", "资料"],
            loop=_agent_loop(_agent_tools()),
        ),
    ]
    # 通用兜底画像：capability 无命中的子任务回落此处，不再整条失败（NO_AGENT_MATCH 仅对
    # 自定义「无 fallback」装配生效）；同样是独立 loop，工具面无 delegate
    general_agent = AgentProfile(
        agent_id="general",
        capabilities=["default"],
        loop=_agent_loop(_agent_tools()),
    )
    agent_router = MultiAgentRouter(subagents, fallback=general_agent)

    async def _dispatch(task: str) -> dict[str, object]:
        try:
            profile = agent_router.match(task)
        except OrchestrationError as exc:
            return {"ok": False, "error": f"无匹配子 Agent: {exc}"}
        if profile.loop is None:
            return {"ok": False, "error": f"子 Agent {profile.agent_id} 无可用 loop"}
        result = await profile.loop.arun(task)
        return {"ok": not result.failed, "reply": result.reply}

    async def _delegate(task: str) -> dict[str, object]:
        """委托工具：按能力标签匹配子 Agent，阻塞等待其 LoopResult 并回传 reply。

        入站即做委托深度护栏（纵深防御；子 Agent 工具面已不含 delegate）。
        """
        if _DELEGATE_DEPTH.get() >= 1:
            return {"ok": False, "error": "已达委托深度上限（子 Agent 不可再委托）"}
        token = _DELEGATE_DEPTH.set(_DELEGATE_DEPTH.get() + 1)
        try:
            return await _dispatch(task)
        finally:
            _DELEGATE_DEPTH.reset(token)

    tools.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.delegate",
                description=(
                    "将子任务委托给匹配的子 Agent（coding/research）执行，阻塞等待结果并回传汇总"
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "要委托给子 Agent 的任务目标"},
                    },
                    "required": ["task"],
                },
                coeffects=["agent:delegate"],  # 驱动子 loop 属跨边界能力（默认不出暴露面，账本 B7）
                reversible=False,
                timeout_s=_DELEGATE_TIMEOUT_S,
            ),
            handler=_delegate,
        )
    )
    store = CheckpointStore(_checkpoint_path())  # 落盘：跨进程续跑/崩溃恢复可读
    checkpoints = CheckpointManager(store)
    time_travel = TimeTravel(store, effect_tracker=effect_tracker)
    crash_recovery = CrashRecovery(store)

    def _checkpoint(task_id: str, outcomes: list[SubtaskOutcome], plan: Plan) -> None:
        _write_checkpoint(task_id, outcomes, plan, done=False)

    def _finalize(task_id: str, outcomes: list[SubtaskOutcome], plan: Plan) -> None:
        _write_checkpoint(task_id, outcomes, plan, done=True)

    def _write_checkpoint(
        task_id: str, outcomes: list[SubtaskOutcome], plan: Plan, *, done: bool
    ) -> None:
        checkpoints.create_checkpoint(
            task_id,
            "default",
            {
                "plan": plan_to_dict(plan),  # 计划随检查点持久化（续跑重建）
                "outcomes": [
                    {
                        "subtask_id": o.subtask_id,
                        "ok": o.ok,
                        # 依赖交接上下文（续跑重建用）
                        "reply": o.reply,
                    }
                    for o in outcomes
                ],
                "trace_ids": [o.trace_id for o in outcomes if o.trace_id],
                "done": done,
            },
        )

    orchestrator = TaskScheduler(
        decomposer=SubtaskDecomposer(
            planner=LLMSubtaskPlanner(llm, model=app.llm.model),
            verifier=LLMVerifier(llm, model=app.llm.model),
        ),
        router=agent_router,
        state_machine=StateMachine(),
        checkpoint=_checkpoint,
        on_done=_finalize,
        tracer=tracer,
    )

    # DefaultLoop 与 LoopPlugin 协议签名存在既有错位（astream/act async 方向相反），
    # 全仓以 cast 桥接（见 entry._build_ui）；此处沿用，行为不变。
    # 门控（0067）：pet 关闭 ⇒ 注册表不建（**不读** pets.json）、激活器不接。
    pet_manager: PetManager | None = None
    pet_activator: PetActivator | None = None
    if not config.is_disabled("pet"):
        # 受限探索工具集（R11）：白名单真源 = Explorer 清单（真实工具 id）；安全边界（R12）：
        # 词汇表同为真实工具 id，半径缺省 = 启动目录（宠物只在家门口探索），可构造面替换。
        pet_explorer = Explorer()
        pet_allowed = set(pet_explorer.available())
        pet_safety = SafetyBounds(allowed_prefixes=[str(Path.cwd())])
        pet_notifier = AsyncNotifier(channel=_pet_notification_sink)

        def _pet_notify(message: str) -> None:
            """生产即投递：唤醒收尾入队后即经宿主节拍 flush（账本 E16）。

            ``AsyncNotifier`` 的「notify 只入队、不阻塞」语义不变；投递点在宠物唤醒收尾
            （生产者唯一调用点），故两步相邻执行。
            """
            pet_notifier.notify(message)
            pet_notifier.flush()

        def _pet_tools() -> ToolProvider:
            """受限探索工具集（账本 E25 / R11）：只注册白名单内的**真实**工具。

            未注册的工具在 loop 侧是结构化拒绝（不存在即不可调用），且模型**看不到**越界工具
            —— fail-closed by construction，而非事后拦截。
            """
            provider = ToolProvider(
                coeffect_resolver=resolver,
                effect_tracker=effect_tracker,
                gate=guard,
                approver=approver,
            )
            for tool in builtin_tools:
                if tool.definition.tool_id in pet_allowed:
                    provider.register(tool)
            return provider

        def _pet_loop() -> LoopPlugin:
            """宠物**专属** loop（账本 E25）：受限工具集 + 安全中间件。

            此前宠物直接复用**主 loop**（`cast(LoopPlugin, loop)`）⇒ 可调用全部工具、安全边界
            不在路径上。专属 loop 沿用 `_agent_loop`/`_beast_loop` 同一形状（planner + 共享
            记忆/闸门/追踪），差异有二：① 工具集被白名单收窄（`_pet_tools`）；② 只挂安全中间件
            —— **不**共享 constraints 熔断链（宠物流量不应污染主线/神兽的熔断态），亦不接技能路由
            （pet 任务与结晶链路无关）。越界 ⇒ 本轮终止 + 通知主人，会话保持 ACTIVE。
            """
            provider = _pet_tools()
            return cast(
                LoopPlugin,
                DefaultLoop(
                    planner=LLMPlanner(
                        llm,
                        model=app.llm.model,
                        reasoning_effort=app.llm.reasoning_effort,
                        assembler=assembler,
                        tools=provider,
                    ),
                    memory=memory,
                    tools=provider,
                    gate=guard,
                    tracer=tracer,
                    approver=approver,
                    compactor=context_compactor,
                    middlewares=[build_safety_middleware(pet_safety, notify=_pet_notify)],
                    max_rounds=max_rounds,
                    token_budget=token_budget,
                ),
            )

        pet_loop = _pet_loop()
        pet_microtasks = MicrotaskRunner()
        pet_manager = PetManager(
            _pet_state_path(),
            factory=lambda record: PetSession.restore(
                record,
                loop=pet_loop,
                memory=memory,
                explorer=pet_explorer,
                safety=pet_safety,
                notifier=_pet_notify,
                microtasks=pet_microtasks.run,
            ),
        )
        pet_activator = PetActivator(
            pet_manager,
            loop=pet_loop,
            memory=memory,
            explorer=pet_explorer,
            safety=pet_safety,
            notifier=_pet_notify,
            microtasks=pet_microtasks.run,
        )

    # 神兽运行时桥接（0057）：专用路由器（画像不与 coding/research 混）+ 惰性按兽 loop +
    # 共享记忆；三入口（CLI / 斜杠 / 自然语言）至此落到**同一**已装配 manager。
    beast_manager: BeastManager | None = None
    beast_activator: BeastActivator | None = None
    if beast_registry is not None:  # 同一判据：注册表在则 beast 模块在（门控判据见上）
        beast_manager = BeastManager(
            registry=beast_registry,
            router=MultiAgentRouter([]),
            loop_factory=_beast_loop,
            memory=memory,
        )
        beast_activator = BeastActivator(beast_manager)

    return Runtime(
        app=app,
        config=config,
        llm=llm,
        memory=memory,
        tools=tools,
        tracer=tracer,
        router=router,
        rag=rag,
        loop=loop,
        skill_router=skill_router,
        skill_feedback=skill_feedback,
        skill_iterator=skill_iterator,
        skill_extractor=sop_extractor,
        installer=installer,
        mcp_client=mcp_client,
        evolution=evolution,
        orchestrator=orchestrator,
        checkpoints=checkpoints,
        time_travel=time_travel,
        crash_recovery=crash_recovery,
        pet_manager=pet_manager,
        pet_activator=pet_activator,
        beast_manager=beast_manager,
        beast_activator=beast_activator,
    )


def _recover_incomplete(
    checkpoints: CheckpointManager, recovery: CrashRecovery
) -> list[RestoreHandle]:
    """扫描检查点，对无 done 标记的任务 restore + resume（幂等续跑）。"""
    done_tasks: set[str] = set()
    for cp in checkpoints.list_checkpoints():
        try:
            snapshot = checkpoints.get_snapshot(cp.checkpoint_id)
        except DurabilityError:
            continue  # 损坏检查点按未完成处理，交给 restore 回退更早检查点
        if snapshot.state.get("done"):
            done_tasks.add(cp.task_id)
    handles: list[RestoreHandle] = []
    seen: set[str] = set()
    for cp in checkpoints.list_checkpoints():
        if cp.task_id in done_tasks or cp.task_id in seen:
            continue
        seen.add(cp.task_id)
        handle = recovery.restore(cp.task_id)
        recovery.resume(handle)
        handles.append(handle)
    return handles
