"""组合根（runtime）：唯一被允许 import 全模块、专职装配的地方。

把 Phase 0–11 的 DI 友好构造串成可运行系统：ConfigManager.load → resolve_secret
→ StdlibLLMProvider → MemoryStore / ToolProvider / Tracer → judgment（DecisionRouter /
Compactor / Guardrail）→ LLMPlanner → PermissionGuard → DefaultLoop，供 entry 三入口复用。

架构约束：全仓库除本文件外，任何模块不得 import core.runtime（test_architecture 断言）。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import cast

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
    Proposer,
    Validator,
)
from core.judgment import Compactor, DecisionRouter, Guardrail, JEVProvider, SkillMatcher
from core.llm_provider import LLMProvider, LLMRequest, Message, StdlibLLMProvider
from core.loop import Approver, DefaultLoop, LoopPlugin, TurnObserver
from core.loop.planner import LLMPlanner, SkillHint
from core.memory import (
    Crystallizer,
    FileBackend,
    MemoryBackend,
    MemoryEntry,
    MemoryStore,
    batch_embed,
    summarize_with,
)
from core.observability import Tracer
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
from core.permission import PermissionGuard
from core.plugin_registry import CoeffectResolver, EffectTracker, PluginInstaller
from core.plugins import InstallDispatcher
from core.rag import LLMEmbedder
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
    web_fetch,
)


@dataclass
class Runtime:
    """组合根产物：已装配运行系统，所有依赖非空。"""

    app: AppConfig
    config: ConfigManager
    llm: LLMProvider
    memory: MemoryStore
    tools: ToolProvider
    tracer: Tracer
    router: DecisionRouter
    loop: DefaultLoop
    skill_router: SkillRouter
    skill_feedback: SkillFeedback
    skill_iterator: SkillIterator
    skill_extractor: SopExtractor
    installer: PluginInstaller
    evolution: EvolutionWorker
    orchestrator: TaskScheduler
    checkpoints: CheckpointManager
    time_travel: TimeTravel
    crash_recovery: CrashRecovery

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


def _skill_state_path(name: str) -> Path:
    """技能态落盘路径：$CORE_STATE_DIR（缺省 ~/.core/state）/<name>。

    同检查点 / 记忆的状态目录约定；技能态是可变快照，故用单文件 JSON（见 skills.persist）。
    """
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / name


# 子 Agent 委托运行完整子循环（多次 LLM 往返 + 工具轮），远超 ToolDef 默认 30s
_DELEGATE_TIMEOUT_S = 600.0

# 委托深度护栏：子 Agent 工具面已不含 delegate，此处为纵深防御
_DELEGATE_DEPTH: ContextVar[int] = ContextVar("delegate_depth", default=0)


def build_runtime(  # noqa: PLR0915, PLR0913, C901
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
    tracer = tracer if tracer is not None else Tracer()
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
    # 记忆 embedding 来源（0040）：llm.embedding_model 非空时以该模型**另构造** provider
    # （聊天模型名打 /embeddings 通常 404），经 rag LLMEmbedder → batch_embed 适配为
    # memory 的批量契约；密钥复用 api_key（已登记脱敏）。未设置则不注入 → 0039 词法路径，
    # 远端不可达由调用期降级兜底，均不阻断启动。
    if embedder is None and app.llm.embedding_model:
        embed_provider = StdlibLLMProvider(
            api_key=api_key,
            base_url=app.llm.endpoint or None,
            model=app.llm.embedding_model,
        )
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
    resolver = CoeffectResolver()
    resolver.register("filesystem:read", True)
    resolver.register("filesystem:write", True)
    resolver.register("process:spawn", True)
    resolver.register("network:outbound", True)
    tools = ToolProvider(
        coeffect_resolver=resolver, effect_tracker=effect_tracker, gate=guard, approver=approver
    )
    builtin_tools = (file_read(), file_write(), file_patch(), code_run(), web_fetch())
    for tool in builtin_tools:
        tools.register(tool)

    # 技能态落盘（0050）：四类运行态注入 $CORE_STATE_DIR 下状态文件 → 重启恢复；
    # 此前技能库/反馈/样本/灰度全活进程内，结晶链路每进程从零开始（账本 A3）。
    skill_library = SkillLibrary(path=_skill_state_path("skills.json"))
    # 语义兜底（0044）：仅 JEV 配置时注入打分器；否则纯词法（词法命中零模型调用）
    skill_router = SkillRouter(
        skill_library,
        memory=memory,
        scorer=SkillMatcher(router).score if jev is not None else None,
    )
    # SOP 提炼接线（0043）：成功任务收尾的轨迹经提炼器归组、达阈值提炼为技能入库——
    # 此前技能库只有注册/路由/版本三段，无任何产生技能的入口（生产恒为空）。
    sop_extractor = SopExtractor(
        skill_library,
        writer=sop_writer_with(_llm_text),
        effect_tracker=effect_tracker,
        path=_skill_state_path("sop-samples.json"),
    )
    # 技能迭代接线（0045）：命中注入 + 执行反馈 + 迭代闭环。反馈默认落盘（缺省进程内，
    # 0050 注入路径）；迭代复用 VersionManager 的灰度/A/B（0048 决策 ⑥ 记的「能力已存在、
    # 无调用者」在此接上调用者），改写走与 SOP 同一注入接缝（skills 不 import LLM 抽象）。
    # 版本管理器在此显式构造并注入（0050 决策 4）：`SkillIterator` 内部自建的那份拿不到，
    # 落盘需由组合根持有；顺带把「灰度/A-B 指标 = 各版本成功率」口径显式化。
    skill_feedback = SkillFeedback(path=_skill_state_path("skill-feedback.json"))
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

    def _loop_hooks() -> tuple[Callable[[str], list[SkillHint]], TurnObserver]:
        """每 loop 一组钩子闭包（命中注入 + 收尾反馈）：状态不跨 loop 共享。

        路由 → 版本解析 → 记命中 → 纯 dict 快照（loop 不 import skills）；收尾按本轮
        实际注入的 ``(技能, 版本)`` 记结果并顺势定夺/触发迭代，再把轨迹转交 SOP 观察者。
        """
        surfaced: list[tuple[Skill, str]] = []

        def hints(task: str) -> list[SkillHint]:
            result: list[SkillHint] = []
            for matched in skill_router.match(task):
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

        return hints, on_turn

    loop_hints, loop_turn = _loop_hooks()
    dispatcher = InstallDispatcher(skill_library=skill_library, tool_provider=tools)
    installer = PluginInstaller(source_resolver=dispatcher.resolve, installer=dispatcher.install)

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
    evolution_engine = EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=Proposer(),
        validator=Validator(),
        evaluator=Evaluator(),
        library=skill_library,
        memory=backend,
        memory_crystallizer=Crystallizer(),
        observations=ObservationRegistry(path=_skill_state_path("observations.json")),
    )
    evolution = EvolutionWorker(tracer=tracer, engine=evolution_engine, trigger=EvolutionTrigger())

    def _cold_path() -> None:
        """收尾维护节拍的冷路径机会：跑一轮进化（阈值门在 worker 内，未达则不做事）。"""
        evolution.maybe_run()

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
        cold_path=_cold_path,
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
                coeffects=[],
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

    return Runtime(
        app=app,
        config=config,
        llm=llm,
        memory=memory,
        tools=tools,
        tracer=tracer,
        router=router,
        loop=loop,
        skill_router=skill_router,
        skill_feedback=skill_feedback,
        skill_iterator=skill_iterator,
        skill_extractor=sop_extractor,
        installer=installer,
        evolution=evolution,
        orchestrator=orchestrator,
        checkpoints=checkpoints,
        time_travel=time_travel,
        crash_recovery=crash_recovery,
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
