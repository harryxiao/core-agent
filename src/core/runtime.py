"""组合根（runtime）：唯一被允许 import 全模块、专职装配的地方。

把 Phase 0–11 的 DI 友好构造串成可运行系统：ConfigManager.load → resolve_secret
→ StdlibLLMProvider → MemoryStore / ToolProvider / Tracer → judgment（DecisionRouter /
Compactor / Guardrail）→ LLMPlanner → PermissionGuard → DefaultLoop，供 entry 三入口复用。

架构约束：全仓库除本文件外，任何模块不得 import core.runtime（test_architecture 断言）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from core.configuration import ConfigManager
from core.configuration.models import AppConfig
from core.context import DynamicAssembler
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
    Proposer,
    Validator,
)
from core.judgment import Compactor, DecisionRouter, Guardrail, JEVProvider
from core.llm_provider import LLMProvider, StdlibLLMProvider
from core.loop import DefaultLoop, LoopPlugin
from core.loop.planner import LLMPlanner
from core.memory import Crystallizer, FileBackend, MemoryBackend, MemoryStore
from core.observability import Tracer
from core.orchestration import (
    AgentProfile,
    MultiAgentRouter,
    StateMachine,
    SubtaskDecomposer,
    SubtaskOutcome,
    TaskScheduler,
)
from core.permission import PermissionGuard
from core.plugin_registry import CoeffectResolver, EffectTracker, PluginInstaller
from core.plugins import InstallDispatcher
from core.skills import SkillLibrary, SkillRouter
from core.tools import ToolProvider, file_patch, file_read, file_write


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
    installer: PluginInstaller
    evolution: EvolutionWorker
    orchestrator: TaskScheduler
    checkpoints: CheckpointManager
    time_travel: TimeTravel
    crash_recovery: CrashRecovery

    def recover(self) -> list[RestoreHandle]:
        """启动时扫描检查点，恢复无 done 标记的任务（返回续跑句柄）。"""
        return _recover_incomplete(self.checkpoints, self.crash_recovery)


def build_runtime(
    config: ConfigManager,
    *,
    assembler: DynamicAssembler | None = None,
    tracer: Tracer | None = None,
    memory_backend: MemoryBackend | None = None,
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
    backend = memory_backend if memory_backend is not None else FileBackend()
    effect_tracker = EffectTracker()
    memory = MemoryStore(
        backend=backend,
        effect_tracker=effect_tracker,
        compactor=Compactor(router) if jev is not None else None,
    )
    resolver = CoeffectResolver()
    resolver.register("filesystem:read", True)
    resolver.register("filesystem:write", True)
    tools = ToolProvider(coeffect_resolver=resolver, effect_tracker=effect_tracker, gate=guard)
    for tool in (file_read(), file_write(), file_patch()):
        tools.register(tool)

    skill_library = SkillLibrary()
    skill_router = SkillRouter(skill_library, memory=memory)
    dispatcher = InstallDispatcher(skill_library=skill_library, tool_provider=tools)
    installer = PluginInstaller(source_resolver=dispatcher.resolve, installer=dispatcher.install)
    planner = LLMPlanner(
        llm,
        model=app.llm.model,
        assembler=assembler,
        skill_router=lambda task: [m.skill.skill_id for m in skill_router.match(task)],
        tools=tools,
    )
    loop = DefaultLoop(
        planner=planner,
        memory=memory,
        tools=tools,
        gate=guard,
        tracer=tracer,
        router=router if jev is not None else None,
    )

    evolution_engine = EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=Proposer(),
        validator=Validator(),
        evaluator=Evaluator(),
        library=skill_library,
        memory=backend,
        memory_crystallizer=Crystallizer(),
    )
    evolution = EvolutionWorker(tracer=tracer, engine=evolution_engine, trigger=EvolutionTrigger())

    agent_router = MultiAgentRouter(
        [AgentProfile(agent_id="main", capabilities=["default"], loop=cast(LoopPlugin, loop))]
    )
    store = CheckpointStore()
    checkpoints = CheckpointManager(store)
    time_travel = TimeTravel(store, effect_tracker=effect_tracker)
    crash_recovery = CrashRecovery(store)

    def _checkpoint(task_id: str, outcomes: list[SubtaskOutcome]) -> None:
        _write_checkpoint(task_id, outcomes, done=False)

    def _finalize(task_id: str, outcomes: list[SubtaskOutcome]) -> None:
        _write_checkpoint(task_id, outcomes, done=True)

    def _write_checkpoint(task_id: str, outcomes: list[SubtaskOutcome], *, done: bool) -> None:
        checkpoints.create_checkpoint(
            task_id,
            "default",
            {
                "outcomes": [{"subtask_id": o.subtask_id, "ok": o.ok} for o in outcomes],
                "trace_ids": [o.trace_id for o in outcomes if o.trace_id],
                "done": done,
            },
        )

    orchestrator = TaskScheduler(
        decomposer=SubtaskDecomposer(),
        router=agent_router,
        state_machine=StateMachine(),
        checkpoint=_checkpoint,
        on_done=_finalize,
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
