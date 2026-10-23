"""组合根（runtime）：唯一被允许 import 全模块、专职装配的地方。

把 Phase 0–11 的 DI 友好构造串成可运行系统：ConfigManager.load → resolve_secret
→ StdlibLLMProvider → MemoryStore / ToolProvider / Tracer → judgment（DecisionRouter /
Compactor / Guardrail）→ LLMPlanner → PermissionGuard → DefaultLoop，供 entry 三入口复用。

架构约束：全仓库除本文件外，任何模块不得 import core.runtime（test_architecture 断言）。
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
import warnings
from collections.abc import Callable, Coroutine, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

from core.beast import BeastActivator, BeastManager, BeastRegistry, register_innate_skills
from core.beast.models import Beast
from core.ci_cd import (
    GATE_COMMANDS,
    Gate,
    GateResult,
    build_gate_executor,
    crystallization_gates,
)
from core.configuration import ConfigManager
from core.configuration.models import AppConfig
from core.context import Compactor as ContextCompactor
from core.context import DynamicAssembler, InfoMap
from core.core_profile import CoreProfileEngine
from core.durability import (
    Checkpoint,
    CheckpointManager,
    CheckpointStore,
    CrashRecovery,
    DurabilityError,
    RestoreHandle,
    RetentionManager,
    RetentionPolicy,
    TimeTravel,
)
from core.evolution import (
    BenchmarkRegistry,
    BenchmarkScorer,
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

# 原生实施（0112，可选能力）：执行器与补丁生产者接缝按子模块引入 —— 不进包出口
# （它们的消费方只有组合根与操作面；包出口保持「进化闭环本体」的语义）。
from core.evolution.author import patch_author_with
from core.evolution.content import skill_content_writer_with
from core.evolution.executor import EvolutionExecutor, source_reader
from core.evolution.validator import review_with, run_gate_tests
from core.hooks import HookManager, entries_from_config
from core.judgment import (
    Compactor,
    DecisionRouter,
    Guardrail,
    JEVProvider,
    SkillMatcher,
    sop_gate_with,
)
from core.llm_provider import LLMProvider, LLMRequest, Message, StdlibLLMProvider
from core.loop import (
    Action,
    ActionObserver,
    ActionResult,
    Approver,
    DefaultLoop,
    LoopContext,
    LoopEvent,
    LoopPlugin,
    LoopResult,
    Middleware,
    TurnAfter,
    TurnBefore,
    TurnObserver,
    collect_result,
    current_event_sink,
    current_session_id,
    current_trace_id,
)
from core.loop.constraints_adapter import build_constraints_chain
from core.loop.fault_adapter import build_fault_chain
from core.loop.planner import LLMPlanner, SkillHint
from core.loop.protocol import ActFn
from core.mcp import MCPClient, MCPEndpointRegistry, mcp_endpoints_path
from core.memory import (
    Crystallizer,
    FileBackend,
    MemoryAuditLog,
    MemoryBackend,
    MemoryEntry,
    MemoryStore,
    TranscriptStore,
    consolidate_with,
    extract_relations_with,
    extract_with,
    score_with,
    summarize_with,
)
from core.notes import (
    NoteStore,
    Sedimenter,
    candidate_writer_with,
    promote_session_summary,
)
from core.observability import BufferedExporter, JSONLExporter, Tracer
from core.orchestration import (
    AgentProfile,
    BackgroundAgentRegistry,
    LLMSubtaskPlanner,
    LLMTaskVerifier,
    LLMVerifier,
    MultiAgentRouter,
    OrchestrationError,
    Plan,
    StateMachine,
    SubtaskDecomposer,
    SubtaskOutcome,
    TaskResume,
    TaskScheduler,
    WorkspaceLease,
    WorktreeManager,
    background_tasks_tool,
    changed_files,
    plan_from_dict,
    plan_to_dict,
    task_retry_tool,
    worktree_tools,
)
from core.permission import PermissionGuard, SandboxManager, SandboxPolicy
from core.pet.core import PetActivator, PetManager, PetSession
from core.pet.explore import Explorer
from core.pet.library import persona_from_record
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
from core.rag.vector_store import VectorStore
from core.skills import (
    RETIRE_AFTER_DEGRADATIONS,
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
    builtin_tools,
    context_read,
    gate_run,
    install_tool,
    list_tool,
    schema_read,
    uninstall_tool,
)
from core.tools.env_shell import EnvironmentSnapshot, probe_environment
from core.tools.workspace import use_workspace

# 门控名单（change 0067 / 账本 E10）：组合根装配的**可选**模块 —— 本元组是单一真源，
# configuration 层不认识模块名。名单内模块缺省装配（未声明即开，兼容既有行为），仅显式
# `features.<模块>: false` 才完全**不装配**（不构造实例、不产生装配期副作用、入口拒绝）；
# 名单外的名字不触发任何裁剪。见 configuration spec「功能开关（feature flag）」。
GATABLE_MODULES: tuple[str, ...] = ("pet", "beast", "evolution")

# 缺省关名单（change 0112 / DS1-a）：与上一份名单**极性相反**的第二个单一真源 —— 名单内模块
# **未声明即视为关闭**（fail-closed），仅显式 `features.<模块>: true` 才装配。自改代码一类的
# 能力须「关得住、且是关着的」（同 `permission.mode` / `sandbox.host_allowlist` 取向），塞进
# `GATABLE_MODULES` 会反转为缺省开 —— 故两极性各由**独立名单**承载，不共用一个名单的两种默认。
# 两个名单之**并**即「已知模块名集合」（供 configuration 的未知开关名告警，账本 E20①）。
# `evolution_benchmark_runner`（change 0212 / ADR-0202）：结晶通路的**真实基准执行器** ——
# 注入后留出评测会**真实调用模型**跑样本（同 `evolution_executor` 的「能烧钱的自改/执行面」性质）
# ⇒ 同极性（缺省关、显式 true 才装）。**注册基准 ≠ 同意执行**：旗关时即便基准已落盘，留出评测
# 仍判 `freeze`（不产分数、不烧 token）。
OPT_IN_MODULES: tuple[str, ...] = ("evolution_executor", "evolution_benchmark_runner")
KNOWN_FEATURE_MODULES: tuple[str, ...] = GATABLE_MODULES + OPT_IN_MODULES


@dataclass
class Runtime:
    """组合根产物：已装配运行系统。

    除 `GATABLE_MODULES` 三项与缺省关的 `OPT_IN_MODULES` 对应的字段（见各字段旁注，关闭时为空）
    外，所有依赖非空。
    """

    app: AppConfig
    config: ConfigManager
    llm: LLMProvider
    # 后台派生调用（摘要/抽取/SOP/沉淀/进化）的独立 provider（change 0296）：超时/重试
    # 由 `llm.background_*` 控制，与用户交互调用解耦。
    background_llm: LLMProvider
    memory: MemoryStore
    tools: ToolProvider
    tracer: Tracer
    router: DecisionRouter
    rag: RagService
    loop: DefaultLoop
    transcript: TranscriptStore  # 对话转录（主 loop 的会话历史来源；见 change 0115）
    skill_router: SkillRouter
    skill_feedback: SkillFeedback
    skill_iterator: SkillIterator
    skill_extractor: SopExtractor
    installer: PluginInstaller
    mcp_client: MCPClient
    evolution: EvolutionWorker | None  # 空 = features.evolution: false（未装配）
    # 空 = features.evolution_executor 未开启（缺省关；见 OPT_IN_MODULES）
    evolution_executor: EvolutionExecutor | None
    orchestrator: TaskScheduler
    # 后台子 Agent 注册表（change 0270 / ADR-0260）：完成通知按会话堆积，主 loop 轮首取用。
    background_tasks: BackgroundAgentRegistry
    # 子 Agent 工作树管理器（change 0284 / ADR-0274）：空 = 开关关闭（未装配）。
    worktrees: WorktreeManager | None
    checkpoints: CheckpointManager
    time_travel: TimeTravel
    crash_recovery: CrashRecovery
    pet_manager: PetManager | None  # 空 = features.pet: false（未装配）
    pet_activator: PetActivator | None
    beast_manager: BeastManager | None  # 空 = features.beast: false（未装配）
    beast_activator: BeastActivator | None
    # 运行环境事实（change 0240）：与四个 planner 共用启动时的一次探测；UI 按有效缺省命名。
    env_snapshot: EnvironmentSnapshot

    def recover(self) -> list[RestoreHandle]:
        """启动时扫描检查点，恢复无 done 标记的任务（返回续跑句柄）。"""
        return _recover_incomplete(self.checkpoints, self.crash_recovery)

    def recover_turns(self) -> list[tuple[str, str]]:
        """启动时扫描**未完结的会话轮**（`(task_id, session_id)`，按 ts 升序）。

        **只读**（`list_checkpoints` + `get_snapshot`）⇒ 零副作用、零续跑句柄：会话轮**不**经
        `task --resume` 恢复（**续聊即恢复**）—— 本面只供呈现「上次有哪些轮被中断」
        （change 0214 / ADR-0204）。
        """
        return _turn_incomplete(self.checkpoints)

    def pending_resumes(self) -> list[TaskResume]:
        """扫描未完成编排任务并重建续跑入参（**只读**、零副作用；change 0278）。

        仅当 `task` 入口显式 `--resume-all` 或开启 `orchestration.auto_resume` 时消费；
        `recover()` 的呈现语义不变（只呈现不重执行）。
        """
        return _task_resumes(self.checkpoints)


def _checkpoint_path() -> Path:
    """检查点落盘路径：$CORE_STATE_DIR（缺省 ~/.core/state）/checkpoints.jsonl。

    与 entry 的全局状态目录约定一致；env 覆盖便于测试隔离。
    """
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / "checkpoints.jsonl"


def _background_state_path() -> Path:
    """后台子 Agent 登记路径：$CORE_STATE_DIR（缺省 ~/.core/state）/background-tasks.json。"""
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / "background-tasks.json"


def _worktree_root() -> Path:
    """工作树状态根：$CORE_STATE_DIR（缺省 ~/.core/state）/worktrees（change 0284）。"""
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / "worktrees"


def _memory_path() -> Path:
    """记忆落盘路径：$CORE_STATE_DIR（缺省 ~/.core/state）/memory.jsonl。

    与检查点共用全局状态目录约定；env 覆盖便于测试隔离。
    """
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / "memory.jsonl"


def _memory_audit_path() -> Path:
    """记忆治理审计路径：$CORE_STATE_DIR（缺省 ~/.core/state）/memory.audit.jsonl。

    与 `memory.jsonl` / `memory-deleted.jsonl` 同目录约定；append-only、0600
    （change 0308 / ADR-0298）。
    """
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / "memory.audit.jsonl"


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


# 进信息地图的 rag 文档数**硬上限**：目录层指针块不受预算裁剪（装配器 `_gather_pointers`
# 只按**每文档**条数设上界）⇒ 文档数无界即每步无界注入。取值与「一份千页文档」同阶。
_RAG_INFO_MAP_MAX_DOCS = 16


def _index_rag_docs(info_map: InfoMap, store: VectorStore) -> None:
    """把 rag 库已索引文档建成信息地图目录索引（change 0210 / ADR-0200）。

    用 ``index``（产出**目录指针**）而非 ``register``（仅缓存原文 ⇒ 走线性扫描兜底）；
    原文由块文本按**块序号**拼回（定长切片 ⇒ 无损）。**跳过** ``_CORE_PROFILE_DOC_ID``：
    该文档已由 ``profile.context`` 分支以**真源**（Core.md 原文）建索引，此处再 `index` 会用
    块拼回文本覆盖真源、丢 `#` 标题 ⇒ 建不出 heading 指针。

    逐文档**降级不炸**：地图是**增益**面，装配必须成功 ——
    单文档读取失败只跳过它（契约 `chunk_texts` 本身 fail-soft，此处再兜一层防坏库）；
    ``document_ids`` 整体失败则**全部不进**（同降级方向）。
    """
    try:
        doc_ids = store.document_ids()
    except Exception:  # 坏库不得阻断装配（增益面整体降级）
        return
    # **先滤后截**：上限是「**rag** 文档总量」的上界，`core-profile` 不占配额
    # （先截后滤会让被跳过的档白占一个名额 ⇒ 实际入图数 < 上限）。
    others = [doc_id for doc_id in doc_ids if doc_id != _CORE_PROFILE_DOC_ID]
    for doc_id in others[:_RAG_INFO_MAP_MAX_DOCS]:
        try:
            text = "".join(store.chunk_texts(doc_id))
        except Exception:  # 单文档坏档只跳过它（增益面逐档降级）
            continue
        if text:
            info_map.index(doc_id, text)


def _skill_state_path(name: str) -> Path:
    """技能态落盘路径：$CORE_STATE_DIR（缺省 ~/.core/state）/<name>。

    同检查点 / 记忆的状态目录约定；技能态是可变快照，故用单文件 JSON（见 skills.persist）。
    """
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / name


#: 基准样本执行时的**会话标识**：与用户会话隔离，防 `loop.<trace>` 条目污染全局记忆层。
_BENCH_SESSION = "bench"


def _run_coro(coro: Coroutine[Any, Any, Any]) -> Any:
    """在**无运行中事件循环**的线程里执行协程（评测发生在冷路径线程 / CLI 主线）。

    基准执行器的调用方是**同步**的（`Runner = Callable[[dict], Any]`），而被调的是 loop 的
    `async arun`。调用线程已在事件循环里（未来新调用方）⇒ 换一条（无循环的）工作线程执行
    —— 免得把 ``RuntimeError: asyncio.run() cannot be called from a running event loop``
    当成评测失败抛给 `Evaluator`。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _run_bench_sample(loop: LoopPlugin, sample: dict[str, Any]) -> Any:
    """执行一个基准样本：以**会话隔离**跑一轮 loop，产出的实际结果交 scorer 与期望比对。

    失败 ⇒ ``None``（scorer 语义：无产出 ⇒ 完成度 0），SHALL NOT 把失败谎报成回复。
    异常**冒泡**（受信执行面 — 不吞成 0 分、不吞成通过），评测器据此判 `freeze`。
    """
    result = _run_coro(loop.arun(str(sample.get("input", "")), session_id=_BENCH_SESSION))
    return None if result.failed else result.reply


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
        description=(
            "文档化记忆循环：先 Consult 相关笔记、再 Build、最后沉淀候选（晋升后成为 canonical）"
        ),
        task_types=["notes", "documentation", "remember", "决策记录", "研究笔记", "解决过程"],
        preconditions=[],
        param_schema={},
        instructions=(
            "1) Consult：任务前先读相关 canonical 笔记（NoteStore.consult）与笔记清单；"
            "2) Build：在既有结论之上执行任务；"
            "3) Update：任务后只沉淀**候选** —— 组合根会把成功轮的写效应轨迹提炼为结构化候选"
            "（notes-candidates.json，对 Consult 不可见）；确需固定为 canonical 时用 "
            "`notes candidate-promote` 显式晋升，不要直接覆盖 canonical 文件。"
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

# 前台委托的实况事件（change 0298 / ADR-0288）：子 Agent 生命周期 → `agent.*`。
# 载荷逐类白名单（与编排层 `_PROGRESS_FIELDS` 同口径）：不把子 Agent 的原始对话 / 思考 /
# 完整工具输出直接灌进父事件流；args/output 已由 loop 侧有界化。
_AGENT_TITLE_MAX = 60
_AGENT_REPLY_MAX = 4000
_AGENT_PROGRESS_FIELDS: dict[str, tuple[str, ...]] = {
    "action_started": ("round", "tool_id", "args"),
    "action_completed": ("round", "tool_id", "ok", "duration_ms", "output"),
    "step_completed": ("round", "failed"),
    "loop.compacting": ("round",),
    "loop.compacted": ("round", "elapsed_ms", "timeout"),
}


def _agent_title(task: str) -> str:
    """子 Agent 标签标题：任务首个非空行、空白折叠、有界。"""
    line = next((part.strip() for part in task.splitlines() if part.strip()), "")
    line = " ".join(line.split())
    return line if len(line) <= _AGENT_TITLE_MAX else f"{line[: _AGENT_TITLE_MAX - 1]}…"


def _emit_agent_event(
    sink: asyncio.Queue[LoopEvent] | None, event_type: str, payload: dict[str, object]
) -> None:
    """向父循环的事件侧信道写一条 `agent.*`；无订阅方（后台 / arun）⇒ 零事件。"""
    if sink is not None:
        sink.put_nowait(LoopEvent(event_type, payload))


def _relay_agent_progress(
    sink: asyncio.Queue[LoopEvent] | None, agent_id: str, event: LoopEvent
) -> None:
    """把子循环事件按白名单转成 `agent.progress`（表外类型静默丢弃）。"""
    fields = _AGENT_PROGRESS_FIELDS.get(event.type)
    if sink is None or fields is None:
        return
    raw = event.payload
    payload = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
    data = {key: payload[key] for key in fields if key in payload}
    _emit_agent_event(
        sink,
        "agent.progress",
        {"agent_id": agent_id, "event": event.type, "data": data},
    )


def _agent_reply_excerpt(reply: str) -> str:
    """子 Agent 终态回复的**事件**节选（工具返回值仍为全文）。"""
    text = str(reply)
    return text if len(text) <= _AGENT_REPLY_MAX else f"{text[: _AGENT_REPLY_MAX - 1]}…"


def _failure_lookup(backend: MemoryBackend) -> Callable[[str], str | None]:
    """失败摘要查询接缝（change 0188 / ADR-0179）：按 id 取 `loop.failure.<trace_id>` 正文。

    走 `MemoryBackend.search("")`（**不**经 `MemoryStore.read`）⇒ **零写入、零效应**（不强化
    `reuse_count`、不落盘），且**层无关** —— 条目被 `forget` 迁 L4 后**仍可读**（失败证据不应
    因归档而从诊断面消失）。按 **id 精确**取：同一 trace 还可能有轨迹 `loop.<trace_id>` 与步序
    `loop.steps.<trace_id>`，三者 `source` 同为 `"loop"`（见 change 0186）。

    `Diagnoser` 只依赖注入的可调用体、**不** import memory（依赖倒置，同 `review_with(_llm_text)`
    的接缝纪律）；本闭包即组合根（L5）的接线。
    """

    def lookup(trace_id: str) -> str | None:
        wanted = f"loop.failure.{trace_id}"
        for entry in backend.search(""):
            if entry.id == wanted:
                return entry.content
        return None

    return lookup


# 任务级步序单行上界（token 有界；与 skills.sop._MAX_STEP_CHARS 同口径）
_MAX_TASK_STEP_CHARS = 400
# 任务级步序聚合总长上界（token 有界）
_MAX_TASK_STEPS_CHARS = 2000


def _steps_lookup(backend: MemoryBackend) -> Callable[[str], list[str]]:
    """子任务步序查询接缝（change 0197 / ADR-0187）：按 id 取 `loop.steps.<trace_id>` 正文。

    与 `_failure_lookup` **同形**：走 `MemoryBackend.search("")`（**不**经 `MemoryStore.read`
    ⇒ **零写入、零效应**、层无关，不强化 `reuse_count`）。条目在**写入时**已脱敏
    （`loop/default.py` 的 `redact_secrets`）⇒ 本接缝**不引入**新的密钥暴露面。
    无条目 ⇒ **空列表**（不伪造证据）。
    """

    def lookup(trace_id: str) -> list[str]:
        wanted = f"loop.steps.{trace_id}"
        for entry in backend.search(""):
            if entry.id == wanted:
                return [line for line in entry.content.splitlines() if line.strip()]
        return []

    return lookup


def compose_task_steps(
    plan: Plan,
    outcomes: list[SubtaskOutcome],
    lookup: Callable[[str], list[str]],
) -> list[str]:
    """把一次编排任务的**过程**装配为任务级 SOP 观察面（change 0197 / ADR-0187）。

    按 `plan.order` 遍历子任务，取各子任务 `trace_id` 经 `lookup` 回读步序，渲染为
    「子任务 <目标>：<步序行>」；无 `trace_id` / 无步序的子任务**跳过**（乱序 outcomes 不改
    输出顺序，缺 trace 不炸）。每行截断至 `_MAX_TASK_STEP_CHARS`、总量封顶
    `_MAX_TASK_STEPS_CHARS`（token 有界）。
    """
    by_id = {o.subtask_id: o for o in outcomes}
    goal_by_id = {s.id: s.goal for s in plan.subtasks}
    order = plan.order or [s.id for s in plan.subtasks]
    lines: list[str] = []
    used = 0
    for subtask_id in order:
        outcome = by_id.get(subtask_id)
        if outcome is None or not outcome.trace_id:
            continue
        steps = lookup(outcome.trace_id)
        if not steps:
            continue
        head = f"子任务 {goal_by_id.get(subtask_id, subtask_id)}："
        for step in steps:
            line = f"{head}{step}"[:_MAX_TASK_STEP_CHARS]
            if used + len(line) > _MAX_TASK_STEPS_CHARS:
                return lines
            lines.append(line)
            used += len(line)
    return lines


# 信息地图的长文档源（change 0140 / 账本 E77）：Core.md「## 项目信息」段为启动期唯一
# 长文档，建索引后由装配器注入**目录层**（指针，非全文）、由 `tools.context_read` 取详情。
_CORE_PROFILE_DOC_ID = "core-profile"
_CORE_PROFILE_SECTION = "项目信息"

# 委托深度护栏：子 Agent 工具面已不含 delegate，此处为纵深防御
_DELEGATE_DEPTH: ContextVar[int] = ContextVar("delegate_depth", default=0)

# 会话轮级检查点的**独立命名空间**（change 0214 / ADR-0204）与状态语义标记。前缀是**命名空间
# 守卫**（快照损坏、`kind` 读不出时仍能把轮面与编排任务分开），`kind` 是**语义真源**（呈现分流
# 读它）。二者任一命中即判为轮面（`_is_turn_task`）—— 轮面**不**入 `task --resume` 续跑面
# （续聊即恢复，语义不同）。
_TURN_TASK_PREFIX = "turn."
_TURN_KIND = "turn"

# 「既往失败教训」注入块的**条数上界**（change 0217 / ADR-0207）：单块至多收最近 N 条失败教训
# ⇒ 块长有界（每条正文在写入时已受单条 L2 沉淀条目长度上界约束）。
_FAILURE_LESSON_LIMIT = 5

# 教训块的**独立预算**（change 0244）：单条折叠后 ≤500 字符、整块正文 ≤1500 字符 —— 教训块
# 不占事实预算名额，但自身必须有界，避免若干条长教训挤掉事实 / 历史块。
_FAILURE_LESSON_MAX_CHARS = 500
_FAILURE_LESSON_TOTAL_CHARS = 1500


def _render_failure_lessons(entries: Sequence[MemoryEntry]) -> str:
    """渲染「既往失败教训」块（**有界**；change 0244）。

    每条先折叠为一行（与既往渲染一致），再按单条上界截断；整块正文累计到总预算即停止
    （最后一条按剩余预算截断）。空输入 ⇒ 空串（planner 不产块）。
    """
    lines: list[str] = []
    budget = _FAILURE_LESSON_TOTAL_CHARS
    for entry in entries:
        if budget <= 0:
            break
        text = " ".join(entry.content.split())[: min(_FAILURE_LESSON_MAX_CHARS, budget)]
        lines.append(f"- {text}")
        budget -= len(text)
    return "\n".join(lines)


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
        # 审计标签按配置注入（change 0184 / ADR-0175）：`LLMResponse.provider` 反映
        # `llm.provider`（该键必填、校验非空），不再是与配置无关的硬编码 `"stdlib"`。
        provider=app.llm.provider,
        # 超时 / 重试按配置注入（change 0232 / ADR-0221）：未配置时取值与类缺省逐字一致
        # （60.0 / 3）⇒ 行为零改变；配置后操作者可收窄「单次调用等待上限」。
        timeout=app.llm.timeout,
        max_retries=app.llm.max_retries,
    )
    # 后台派生调用独立 provider（change 0296）：会话摘要 / 关键事实与关系抽取 / 情景归纳 /
    # SOP 提炼 / 沉淀候选蒸馏 / 进化 review 共用；独立超时与重试（缺省 60s / 0 次），
    # 不把交互调用的重试放大叠到收尾路径；主 provider 的超时与重试语义不变。
    background_llm = StdlibLLMProvider(
        api_key=api_key,
        base_url=app.llm.endpoint or None,
        model=app.llm.model,
        provider=app.llm.provider,
        timeout=app.llm.background_timeout,
        max_retries=app.llm.background_max_retries,
    )
    # 缺省导出面（change 0089）：JSONL 落 $CORE_STATE_DIR，经缓冲/退避重试包装 ——
    # 导出失败降级为内存缓冲，绝不抛进主循环（规格「遥测故障不阻塞主循环」）；注入者优先。
    tracer = (
        tracer
        if tracer is not None
        else Tracer(exporter=BufferedExporter(JSONLExporter(_trace_path())))
    )
    tracer.register_secret(api_key)

    # 生命周期钩子（change 0269 / ADR-0259）：缺省关闭 ⇒ 不构造管理器、不注入任何接缝，
    # 既有路径逐字不变。开启 ⇒ 条目由 `hooks.entries` 校验（非法逐条告警跳过、超时截断），
    # 明文密钥登记进同一脱敏链；`session.end` 由管理器在进程退出时投递。
    hooks: HookManager | None = None
    if config.hooks_enabled():
        hook_timeout = config.hooks_timeout_s()
        hook_on_error = config.hooks_on_error()
        hooks = HookManager(
            entries=entries_from_config(
                config.hooks_entries(),
                default_timeout_s=hook_timeout,
                default_on_error=hook_on_error,
            ),
            tracer=tracer,
            mode="runtime",
            default_timeout_s=hook_timeout,
            default_on_error=hook_on_error,
        )
        hooks.register_secret(api_key)

    # 接缝适配器（同一管理器跨四个 loop 复用）：tool 类经中间件/观察者，turn / session 经
    # 轮首轮尾注入点；无管理器 ⇒ 空列表 / `None`（各 loop 构造参数逐字不变）。
    hook_middlewares: list[Middleware] = []
    hook_observers: list[ActionObserver] = []
    hook_turn_before: TurnBefore | None = None
    hook_turn_after: TurnAfter | None = None
    if hooks is not None:

        async def _hook_before_action(ctx: LoopContext, action: Action) -> Action | None:
            if action.is_terminal:
                return action
            allowed = await hooks.before_tool(
                action.tool_id, action.args, ctx.session_id, current_trace_id.get()
            )
            return action if allowed else None

        async def _hook_after_action(
            ctx: LoopContext, action: Action, result: ActionResult
        ) -> None:
            await hooks.after_tool(action.tool_id, result, ctx.session_id, current_trace_id.get())

        async def _hook_turn_before(
            session_id: str, trace_id: str, turn_index: int, text: str
        ) -> bool:
            await hooks.start_session(session_id)
            return await hooks.before_turn(session_id, trace_id, turn_index, text)

        async def _hook_turn_after(session_id: str, trace_id: str, ok: bool, steps: int) -> None:
            await hooks.after_turn(session_id, trace_id, ok, steps)

        hook_middlewares = [_hook_before_action]
        hook_observers = [_hook_after_action]
        hook_turn_before = _hook_turn_before
        hook_turn_after = _hook_turn_after

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
        # 无人值守允许面（change 0280）：空配置 ⇒ None（全放行，与引入前逐字一致）。
        allowed_coeffects=frozenset(config.permission_auto_approve_coeffects()) or None,
        # 命令级允许面（change 0282）：空映射 ⇒ {}（不限制，与引入前逐字一致）。
        allowed_commands=config.permission_auto_approve_commands(),
    )
    backend = memory_backend if memory_backend is not None else FileBackend(_memory_path())
    effect_tracker = EffectTracker()
    # 语义 embedding 来源（0040 / 0104 共用）：有效模型非空时以该模型**另构造** provider
    # （聊天模型名打 /embeddings 通常 404），memory 通路经 rag LLMEmbedder.embed_many
    # 直接满足批量契约（一次检索多批调用）、rag 通路直接消费 LLMEmbedder；
    # 密钥复用 api_key（已登记脱敏）。
    # 有效模型 = 显式 embedding_model，或按端点推导的默认值（change 0271 / ADR-0261）。
    # 为空则不构造 → memory 走 0039 词法路径、rag 走离线 HashEmbedder 降级基线，
    # 远端不可达由调用期降级兜底，均不阻断启动。
    embedding_model = app.llm.effective_embedding_model
    embed_provider = (
        StdlibLLMProvider(
            api_key=api_key,
            base_url=app.llm.endpoint or None,
            model=embedding_model,
        )
        if embedding_model
        else None
    )
    if embedder is None and embed_provider is not None:
        embedder = LLMEmbedder(embed_provider).embed_many

    # 记忆摘要接缝（0041）：LLM 提炼经 summarize_with 适配为 memory 的摘要契约
    # （与 embedding 同一依赖方向：memory 不 import LLM 抽象，组合根注入模型调用）。
    def _llm_text(prompt: str) -> str:
        """prompt → 文本：摘要（memory）/ 提炼（skills）/ 补丁（evolution）三条 DI 接缝共用。

        后台派生调用（change 0296）：走独立 provider（`llm.background_timeout` /
        `llm.background_max_retries`），与用户交互调用的超时/重试解耦。
        """
        response = background_llm.completion(
            LLMRequest(messages=[Message(role="user", content=prompt)], model=app.llm.model)
        )
        return response.content

    # 文档化记忆（0106）：canonical Markdown 真相层 + Consult→Build→Update 循环。
    # NoteStore 经 `MarkdownBackend` 落盘（实现既有 `MemoryBackend` Protocol，不改契约）。
    # **先于** MemoryStore 构造：半自动提升钩子（0153 / G3）需引用之
    # （memory 只报越界、notes 才落盘，零反向依赖）。
    note_store = NoteStore(path=_notes_path())
    # 两段式沉淀（0295）：成功轮先产**候选**（不直写 canonical），`notes candidate-promote`
    # 显式晋升后才进 truth 层。writer 缺省接线（`notes.candidate_distill` kill-switch 关闭
    # ⇒ None ⇒ 零模型调用）；候选区与 notes 目录同级，独立 JSON、不进 digest/search。
    sedimenter = Sedimenter(
        note_store,
        writer=candidate_writer_with(_llm_text) if config.notes_candidate_distill() else None,
        path=_notes_path().parent / "notes-candidates.json",
        auto_promote=config.notes_candidate_auto_promote(),
    )

    def _promote_summary(session_id: str, summary: MemoryEntry) -> object:
        """半自动提升（0153 / G3）：会话摘要首次越过滚动上界 ⇒ 落 canonical（不自动 pin）。"""
        return promote_session_summary(note_store, summary, session_id=session_id, pin=False)

    summarizer = summarize_with(_llm_text)
    memory = MemoryStore(
        backend=backend,
        effect_tracker=effect_tracker,
        compactor=Compactor(router) if jev is not None else None,
        embedder=embedder,
        summarizer=summarizer,
        summary_promoter=_promote_summary,
        # 结构化关键事实抽取（0155 / 路线图 G4）：同一 `_llm_text` 接缝；脱敏在 store 侧无条件执行。
        # 门控（0216 / ADR-0206）：键 `memory.key_fact_extract` **缺省 True**（既在用能力的
        # kill-switch）⇒ 缺省恒走原分支，与引入本键前逐字等价；显式关闭才不接线。
        key_fact_extractor=extract_with(_llm_text) if config.key_fact_extract() else None,
        # 实体关系抽取（0203 / ADR-0193）：**缺省不接线**（`memory.relation_extract` 缺省关）
        # ⇒ 未配置时压实逐字不变。与关键事实**刻意分离**：合并会改 0155 的提示词字节。
        relation_extractor=extract_relations_with(_llm_text) if config.relation_extract() else None,
        # 写入侧重要度闸门（0181 / ADR-0172）：缺省不评分（逐字不变）；显式开启才构造评分器。
        # 同一 `_llm_text` 接缝；系统管道派生产物（compaction/context/extraction）在 store 侧豁免。
        importance_scorer=score_with(_llm_text) if config.importance_gate() else None,
        # 情景归纳（0218 / ADR-0208）：**缺省不接线**（`memory.episodic_extract` 缺省关）⇒ 未配置
        # 时压实逐字不变。与关键事实 / 关系**刻意分离**：三者 prompt 材料口径各不相同。
        episodic_extractor=consolidate_with(_llm_text) if config.episodic_extract() else None,
        # 基准执行隔离（change 0245 / ADR-0233）：执行面开启时把基准会话登记为 ephemeral ⇒
        # 压实只做会话级摘要与归档，不写全局派生（关键事实/关系/episodic）与 canonical 提升；
        # 门控关（缺省）⇒ 空集，本键不存在时压实语义逐字不变。
        ephemeral_sessions=(
            (_BENCH_SESSION,) if config.is_enabled("evolution_benchmark_runner") else ()
        ),
        # 语义遗忘面（0204 / ADR-0194）：缺省关 ⇒ 派生事实（extraction/relation）不参与遗忘
        # （与摘要类同不受影响，逐字不变）；显式开启才放行其参与同一衰减归档。
        semantic_forgetting=config.semantic_forgetting(),
        # L2 活跃层软上限（0230 实现 / 0251 接线 + ADR-0241）：缺省未配置 ⇒ None ⇒ 写入路径
        # 逐字不变；配置后写入即收口（先忘记、再按 ts 最旧迁 L4，全部可撤销）。
        l2_soft_max_entries=config.l2_soft_max_entries(),
        # 记忆写入观察者（change 0269）：钩子开启时接线；不可否决、异常吞掉（store 侧隔离）。
        write_observer=hooks.memory_write if hooks is not None else None,
        # 固化单一开关（change 0307 / ADR-0297）：缺省 `active` ⇒ True ⇒ 压实逐字不变；
        # `off` ⇒ compact 为 no-op（forget / 中层摘要不受影响）。
        consolidation_enabled=config.consolidation_mode() != "off",
        # 治理审计旁路（change 0308 / ADR-0298）：缺省开 ⇒ 事件落
        # `$CORE_STATE_DIR/memory.audit.jsonl`（0600、不含正文）；显式关闭 ⇒ None（零文件）。
        audit_log=MemoryAuditLog(_memory_audit_path()) if config.audit_log_enabled() else None,
    )
    # 上下文压实接线（0041）：多轮历史 → persist 落 L2；此前 context.Compactor 与
    # memory.compact 都无生产调用方（死路径），现由 loop 的**工具步数**/预算阈值触发。
    # 步数阈值经配置注入（0182 / ADR-0173）：缺省 6 < `max_rounds` 缺省 20 ⇒ 该维度可提前触发。
    context_compactor = ContextCompactor(memory=memory, step_threshold=config.compact_steps())
    # rag 主链路装配（0104）：落盘索引 + 语义优先 / 离线降级的 embedding + 生成融合，
    # 由 RagService 门面收口（CLI / 宿主只调用门面，不各自拼四个对象）。
    rag_store = SqliteVectorStore(_rag_index_path())
    rag = RagService(
        LLMEmbedder(embed_provider) if embed_provider is not None else HashEmbedder(),
        rag_store,
        generator=RagGenerator(llm, model=app.llm.model),
    )
    resolver = CoeffectResolver()
    resolver.register("filesystem:read", True)
    resolver.register("filesystem:write", True)
    resolver.register("process:spawn", True)
    resolver.register("process:read", True)  # 后台任务巡检（change 0259 / ADR-0249）
    resolver.register("process:write", True)  # 后台任务终止（不可逆，确认门约束）
    resolver.register("network:outbound", True)
    resolver.register("agent:delegate", True)  # 委托能力：显式声明供默认暴露面识别（B7）
    resolver.register("task:read", True)  # 后台任务清单（只读；change 0270 / ADR-0260）
    resolver.register("task:write", True)  # 后台任务重入队（需审批；change 0279 / ADR-0269）
    resolver.register("schema:read", True)  # 工具参数查询（只读；change 0272 / ADR-0262）
    # 子 Agent 工作树隔离（change 0284 / ADR-0274）：缺省关 ⇒ 不构造 manager、不注册 coeffect、
    # 不挂工具面；开启时工作树工具**只**上主工具面（子 Agent provider 用 `_agent_tools()` 另建）。
    worktrees = (
        WorktreeManager(_worktree_root()) if config.orchestration_worktree_isolation() else None
    )
    if worktrees is not None:
        resolver.register("worktree:read", True)
        resolver.register("worktree:write", True)
    tools = ToolProvider(
        coeffect_resolver=resolver, effect_tracker=effect_tracker, gate=guard, approver=approver
    )
    for tool in builtin_tools():  # 零注入五件（单一真源：`core.tools.builtin_tools`）
        tools.register(tool)
    # 工具参数按需查询（change 0272 / ADR-0262）：catalog 用闭包取**调用时**的注册面
    # （含后续注册的 gate/context/delegate/插件类工具与 MCP 动态工具）。只挂主工具面。
    tools.register(schema_read(catalog=tools.active_tools))

    # 门禁工具面（0111 / phase-27 切片 S1）：把 ci-cd 既有门禁执行器暴露为原子工具，
    # 门禁名与命令取自**单一真源** `GATE_COMMANDS`；执行器**注入**（L1 不依赖 L5）。
    # 只挂主工具面：子 Agent / 宠物 loop 的注入点不动（不扩散越界暴露面）。
    gate_executor = build_gate_executor()

    def _run_gate(kind: str) -> GateResult:
        return gate_executor(Gate(gate_id=f"gate.{kind}", kind=kind))

    tools.register(gate_run(gates=tuple(GATE_COMMANDS), run_gate=_run_gate))

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
    # 任务级 SOP 提炼接线（0197 / ADR-0187）：与单轮面**同库、异样本文件、异命名空间**的第二个
    # 实例 —— 长任务跨轮时单轮面归组键逐轮漂移（永不达阈），任务级面以「任务目标 + 子任务步序」
    # 为单位、随任务成功收尾（`DONE`）提交一次。两路步序语义不同（子任务骨架 vs 工具调用行）
    # ⇒ 隔离是**正确性**要求（namespace 使组键与 skill_id 各落独立空间）。
    sop_task_extractor = SopExtractor(
        skill_library,
        writer=sop_writer_with(_llm_text),
        effect_tracker=effect_tracker,
        path=_skill_state_path("sop-task-samples.json"),
        namespace="task",
        # 自动质量门（0198 / ADR-0188）：noul 判定「该 SOP 是否可发布」；未过 ⇒ 不发布 + 清组
        # + 留痕（只报组键）。沿仓内惯例——judgment 背书的接缝**仅在 JEV 配置时启用**
        # （同 `Guardrail(router) if jev is not None else None`）⇒ 缺省无 JEV 时发布路径逐字不变。
        gate=sop_gate_with(router) if jev is not None else None,
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
        # SOP 技能退役（0205 / ADR-0195）：开关缺省关 ⇒ `None` ⇒ 退化只丢草稿、不碰 status
        # （迭代行为逐字不变）；开启 ⇒ 连续退化达阈自动退役（`skills.deprecate` 可逆效应）。
        retire_after=RETIRE_AFTER_DEGRADATIONS if config.skill_retirement() else None,
    )

    # 神通注册（0057）：20 神兽独有神通进全局技能库，供**按兽作用域**路由（见 _beast_loop）。
    # 此前 build_innate_skills/register_innate_skills 零生产调用方（账本 E3）。
    beast_registry: BeastRegistry | None = None
    if not config.is_disabled("beast"):  # 门控：关闭时**连注册也不做**（注册即装配期副作用）
        beast_registry = BeastRegistry()
        register_innate_skills(skill_library, beast_registry)

    # 文档化记忆（0106）：NoteStore 已**先于** MemoryStore 构造（供半自动提升钩子 G3 引用）；内置
    # 循环技能由组合根构造并注册（notes 包不向上依赖 L3 skills）。与 RAG 语义召回层并列、互不交叉。
    skill_library.register(_notes_workflow_skill())

    def _consult_notes(task: str) -> str:
        """任务前 Consult：确定性读命中笔记 + 清单（loop 不 import notes，组合根注入闭包）。"""
        return note_store.digest(task)

    def _pinned_notes() -> str:
        """常驻注入（0149）：**零参**取常驻笔记全文块（与当轮任务无关 ⇒ 每轮无条件在场）。"""
        return note_store.pinned_digest()

    def _failure_lessons(session_id: str) -> str:
        """既往失败教训（0217）：**按会话**零效应取失败条目，渲染有界块（loop 不 import 语义面）。

        走 ``MemoryStore.failure_lessons``（**零效应只读** —— 不走 ``read()``，后者会强化
        ``reuse_count`` 并落盘效应）；**至多** `_FAILURE_LESSON_LIMIT` 条、每条**折叠为一行**
        （正文已在写入时逐行脱敏，此处无需二次脱敏），渲染由 `_render_failure_lessons` 按
        单条 / 整块预算截断（change 0244）。无教训 ⇒ 空串 ⇒ planner 不产块。
        """
        return _render_failure_lessons(
            memory.failure_lessons(session_id, limit=_FAILURE_LESSON_LIMIT)
        )

    def _loop_hooks(
        domain: str | None = None,
    ) -> tuple[Callable[[str], list[SkillHint]], TurnObserver]:
        """每 loop 一组钩子闭包（命中注入 + 收尾反馈）：状态不跨 loop 共享。

        路由 → 版本解析 → 记命中 → 纯 dict 快照（loop 不 import skills）；收尾按本轮
        实际注入的 ``(技能, 版本)`` 记结果并顺势定夺/触发迭代，再把轨迹转交 SOP 观察者。

        ``domain`` 透传技能路由的专属作用域（神兽传自身 agent_id，其余不传）。
        """
        surfaced: list[tuple[Skill, str]] = []

        def hints(task: str, session_id: str = "") -> list[SkillHint]:
            result: list[SkillHint] = []
            for matched in skill_router.match(task, domain=domain, session_id=session_id):
                skill = matched.skill
                version, text = skill_iterator.resolve(skill)
                skill_feedback.record_hit(skill.skill_id, version=version)
                surfaced.append((skill, version))
                result.append(skill_hint(skill.skill_id, version, text))
            return result

        def on_turn(task: str, steps: list[str], ok: bool, reply: str) -> None:
            for skill, version in surfaced:
                skill_feedback.record_outcome(skill.skill_id, version=version, ok=ok)
                skill_iterator.decide(skill)  # 两版本样本齐备 → A/B 定夺
                if not ok:
                    # 失败轮触发迭代（阈值门在迭代器内）；把本轮实际步骤作为失败实况一并交给
                    # 改写 prompt（change 0223 —— 迭代器内做有界 + 脱敏）。
                    skill_iterator.consider(skill, failure_steps=steps)
            surfaced.clear()
            sop_extractor.observe(task, steps, ok=ok)
            # 任务后 Update（0295）：成功轮只产候选，不再直写 canonical（两段式沉淀）
            sedimenter.observe_turn(task, steps, ok=ok, reply=reply)

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
        # 信息地图接线（change 0140 / 账本 E77）：把 Core.md 项目信息段建成**目录索引**
        # 注入装配器 ⇒ `build()` 真的读地图（此前只构造、从不查）。
        info_map = InfoMap()
        if profile.context:
            info_map.index(
                _CORE_PROFILE_DOC_ID,
                f"# {_CORE_PROFILE_SECTION}\n" + "\n".join(profile.context),
            )
        # rag 文档进信息地图（change 0210 / ADR-0200）：把 rag 库已索引文档的**块拼回原文**
        # 建目录索引 ⇒ 模型先看目录指针、再 `context_read` 取详情。旗关（缺省）⇒ 目录层逐字不变。
        if config.rag_info_map():
            _index_rag_docs(info_map, rag_store)
        assembler = DynamicAssembler(
            memory=memory,
            info_map=info_map,
            constitution=list(profile.coeffect.get("constitution:v1", [])),
            project_info=list(profile.context),
            # 神兽记忆分区封存（beast-mode spec `:89`）：主 loop 装配不命中 `beast.*`
            # （神兽轨迹由 `_beast_loop` 以 `source=beast.<agent_id>` 落库，见下）
            # 宠物命名空间封存（pet-mode：「Pet Session Runtime Wiring」）：主 loop 装配不命中 `pet`
            # —— `session_id` 为空时（未带会话）会话面不过滤，此处是唯一防线（见 `_pet_loop`）
            exclude_source_prefixes=("beast.", "pet"),
            # 压缩产物退出事实面（change 0185 / ADR-0176）：会话长期/中期摘要
            # （`source="compaction"`）的正文已由「历史摘要（长期）/（中期）」专块每轮注入
            # ⇒ 不再重复进「相关事实」块。
            # 压缩产出的事实/未决（`source="context"`）无专块承载，仍在事实面。
            exclude_fact_sources=("compaction",),
            # 原始步序素材退出事实面（change 0186 / ADR-0177）：`loop.steps.<trace>`（`tags` 含
            # `steps`）的声明角色是**抽取器素材**（其信息已由同轮轨迹 / 失败摘要承载）
            # ⇒ 不进 prompt。
            # 三者 `source` 同为 `"loop"` ⇒ 来源面不可分，故按 **tags** 排除。
            # 失败教训退出事实面（change 0217 / ADR-0207）：教训块**启用**时失败条目改由
            # 「既往失败教训」专块承载 ⇒ 追加 `failure` 挡在事实面外（同 0185/0186 口径）。
            # **关（缺省）⇒ 逐字为既有 `{"steps"}`** ⇒ 事实面行为**逐字不变**。
            exclude_fact_tags=(
                frozenset({"steps", "failure"})
                if config.failure_lessons()
                else frozenset({"steps"})
            ),
        )
    # 取详情的消费面（change 0140）：模型经工具面按指针取片段，不由全文顶替。
    # 注入装配器时同样接线（装配面由调用方给定，消费面不在其管辖内）。
    tools.register(context_read(fetch_detail=assembler.fetch_detail))
    # 请求侧输出上限（change 0183 / ADR-0174）：注入**四个 loop** 的全部 planner —— 与
    # `token_budget` 派生同源（预算 = 窗口 − 预留），使「预留」从记账假设变为端点上界。
    max_tokens = config.output_reserve()
    # 上下文区块配比（change 0201 / ADR-0191）：与上面的 `max_tokens` 同型 —— 算一次，注入
    # **四个 loop** 的全部 planner。缺省**关** ⇒ 注入预算沿用字面量 ⇒ 提示词逐字不变。
    block_plan = config.block_plan()
    causal_links = config.causal_links()
    # 解析失败回喂重试（change 0227 / ADR-0217）：与上面两参同型 —— 算一次，注入**四个 loop**
    # 的全部 planner。缺省**关** ⇒ 解析失败路径逐字不变。宠物 loop 也接：这是**协议层**自愈
    # （推理输出协议），不是记忆/转录面（宠物隔离注记约束的是后者的注入面）。
    parse_retry = config.parse_retry()
    # 运行环境事实（change 0237）：探测一次，主 / 子 / 神兽 / 宠物 planner 共用同一快照。
    env_snapshot = probe_environment()
    planner = LLMPlanner(
        llm,
        model=app.llm.model,
        reasoning_effort=app.llm.reasoning_effort,
        # 思考回显**只注入主 planner**（change 0145 / ADR-0137）：子任务 / 神兽 / 宠物 planner
        # 不注入 ⇒ 思考原文不上子任务运行态回流通道（红线，见 loop「异步流式执行」）。
        show_thinking=app.llm.show_thinking,
        assembler=assembler,
        skill_router=loop_hints,
        tools=tools,
        max_tokens=max_tokens,
        block_plan=block_plan,
        parse_retry=parse_retry,
        env_snapshot=env_snapshot,
        # 工具参数注入范围（change 0272 / ADR-0262）：只注主 planner —— 子 Agent / 神兽 /
        # 宠物工具面 ≤ 阈值，构造缺省 `all` 即全量，无需按 loop 类型分叉。
        tool_scope=config.tool_scope(),
    )
    # 门控（0067）：evolution 关闭 ⇒ 引擎/worker 不建，loop 冷路径与 trace 完成回调一并置 None
    # （不为「未装配」造空转闭包 —— DefaultLoop 本就接受 cold_path / trace_observer =None）。
    evolution: EvolutionWorker | None = None
    evolution_executor: EvolutionExecutor | None = None
    cold_path: Callable[[], None] | None = None
    trace_observer: Callable[[str], None] | None = None
    if not config.is_disabled("evolution"):
        # 候选台账在此显式构造并注入（0112）：实施制品与候选**同一条记录**，故执行器必须与
        # 引擎共用同一实例（各持一份 ⇒ 制品落在对方看不见的库里，跨进程复核不成立）。
        pending_queue = PendingQueue(path=_skill_state_path("evolution-pending.json"))
        # 结晶面门的**数据面**（0119）：基准集与基线落盘（跨进程可读，运维/人工注册），
        # 与评测器共用**同一**实例（各持一份 ⇒ 注册的基准对评测不可见）。
        benchmarks = BenchmarkRegistry(path=_skill_state_path("evolution-benchmarks.json"))

        # 结晶通路的**执行面**（change 0212 / ADR-0202）：门控开 ⇒ 为 `EvolutionWorker` 生产
        # 产出的两个 `task_type`（`module_health` / `tool_use`，见 worker.py）注入真实执行器。
        # 执行器跑 **`general` 兜底子 profile**（晚绑定 —— 评测只发生在 `build_runtime` 返回之后）
        # 而**非主 loop**：子 loop 无 `cold_path` / `trace_observer` ⇒ `scorer→runner→loop→冷路径`
        # 的**递归结构上不存在**（主 loop 会递归，今日仅靠 900s 节拍闸挡，脆）。
        # 门控**缺省关** ⇒ `runners=None` ⇒ 今日 `freeze` 判定**逐字不变**（注册基准 ≠ 同意执行）。
        def _bench_runner(sample: dict[str, Any]) -> Any:
            return _run_bench_sample(cast("LoopPlugin", general_agent.loop), sample)

        runners = (
            {"module_health": _bench_runner, "tool_use": _bench_runner}
            if config.is_enabled("evolution_benchmark_runner")
            else None
        )
        # 技能内容面（change 0236）：先工厂再注入；与 `require_skill_content` 同开同关。
        skill_content_writer = skill_content_writer_with(_llm_text)
        evolution_engine = EvolutionEngine(
            # 记忆面 → 诊断面桥（change 0188 / ADR-0179）：注入失败摘要查询接缝（依赖倒置，
            # Diagnoser 不 import memory）⇒ 已沉淀的 `loop.failure.<trace_id>` 并入诊断报告。
            diagnoser=Diagnoser(failure_lookup=_failure_lookup(backend)),
            proposer=Proposer(writer=skill_content_writer),
            # 结晶面门的**判定面**（0120）：review 接组合根模型接缝 `_llm_text`（与摘要/补丁同一
            # 依赖方向：evolution 不 import LLM 抽象），运行时测试跑**按标记派生**的结晶面门禁
            # 子集（`lint` + `test`；命令仍只有单一真源 `GATE_COMMANDS` 一份），执行器复用门禁工具面
            # 那份 `gate_executor`（不造第二份执行面）。两判据均 fail-closed：未注入 / 模型不可用 /
            # 门禁跑不起来 ⇒ 门未过 ⇒ 不发布（此前 `Validator()` 无参 = 两个恒通过桩，门恒开）。
            # 代价如实登记：冷路径**同步**跑子进程门禁（ADR-0113 已知局限①，reopen：冷路径异步化）。
            # change 0236：装配内容 writer 时同开技能内容判据（空壳 fail-closed）。
            validator=Validator(
                review=review_with(_llm_text),
                tests=run_gate_tests(run_gate=_run_gate, gates=crystallization_gates()),
                require_skill_content=True,
            ),
            # 留出评测接**真实打分器**（0119）：留出分由绑定基准的样本经执行器真实执行产出。
            # 执行器映射（`task_type` → 可调用体）由组合根注入 —— **门控开**才接（change 0212 /
            # ADR-0202，`runners` 见上）；门控关（缺省）⇒ `runners=None` ⇒ 产线仍判 `frozen`
            # （无法评测 ⇒ 不下发、不发布），与未引入执行面时**逐字一致**。
            evaluator=Evaluator(
                registry=benchmarks, score_fn=BenchmarkScorer(benchmarks, runners=runners)
            ),
            library=skill_library,
            memory=backend,
            memory_crystallizer=Crystallizer(),
            observations=ObservationRegistry(path=_skill_state_path("observations.json")),
            pending=pending_queue,
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

        # 原生实施执行器（0112，**缺省关**）：只在显式开启时装配。门禁复用**同一** `_run_gate`
        # / `gate_executor`（同 `GATE_COMMANDS` 单一真源，不为执行器另立第二份门禁清单），
        # 补丁生产者复用 `_llm_text`（同一条 DI 接缝），制品落**同一个** `pending_queue`。
        # 只由操作面显式驱动（`evolve implement`）：不入工具面、不挂热/冷路径节拍。
        if config.is_enabled("evolution_executor"):
            _source_root = Path(__file__).resolve().parents[2]  # 仓根（源码树）
            evolution_executor = EvolutionExecutor(
                author=patch_author_with(_llm_text, read_source=source_reader(_source_root)),
                run_gate=_run_gate,
                gates=tuple(GATE_COMMANDS),
                effects=effect_tracker,
                queue=pending_queue,
                root=_source_root,
            )

    failure_threshold, cooldown_s = config.circuit_breaker()
    constraints_chain = build_constraints_chain(
        failure_threshold=failure_threshold, cooldown_s=cooldown_s
    )

    # 容错重试链（change 0209 / ADR-0199）：`constraints.retry_attempts` 缺省 `0` ⇒ 不构造
    # （`_fault_wrapper` 返回 None ⇒ `act_wrapper=None` ⇒ 既有路径逐字不变）。**按 provider 建**
    # （可逆集合按 provider 的工具面算）；**宠物 loop 不接**（沿 `:1146` 隔离注记 —— 宠物流量
    # 不应污染主线/神兽的容错态）。
    retry_attempts = config.retry_attempts()

    def _fault_wrapper(provider: ToolProvider) -> Callable[[ActFn], ActFn] | None:
        if retry_attempts <= 0:
            return None
        return build_fault_chain(provider, max_attempts=retry_attempts).wrap

    # 循环预算上限（change 0098）：可经配置链设定，token 预算由 llm.context_window 派生
    # （窗口 - 输出预留；未配窗口回落缺省 65536）。四个 loop（主 / 子 agent / 神兽 / 宠物）
    # 同源同参。
    max_rounds, token_budget = config.loop_limits()

    # 对话转录（change 0115）：**只注入主 loop** —— 会话维度是主 Agent 的门面概念，
    # 子 / 神兽 / 宠物 loop 不接（零行为变化）。回灌轮数经独立访问器（不走 loop_limits()）。
    transcript = TranscriptStore(_skill_state_path("messages.jsonl"))

    # 会话轮级检查点（change 0214 / ADR-0204）：`loop.turn_checkpoint` 缺省关 ⇒ 传 `None`
    # ⇒ 主循环**零调用、零 I/O**（既有路径逐字不变）。`checkpoints` / `retention*` 在本函数
    # **之后**才装配 ⇒ 闭包按**晚绑定**读取（同 `_bench_runner` 先例，ADR-0202 D3）：只在本轮
    # 运行时（装配已完成）被调用。持久化失败只告警降级 —— 轮级留痕**不改变本轮结局**。
    def _turn_checkpoint(trace_id: str, session_id: str, goal: str, done: bool) -> None:
        try:
            checkpoints.create_checkpoint(
                f"{_TURN_TASK_PREFIX}{trace_id}",
                session_id,
                {"kind": _TURN_KIND, "goal": goal, "done": done},
            )
        except DurabilityError as err:
            warnings.warn(
                f"会话轮级检查点写入失败（trace={trace_id}）: {err.code.value}", stacklevel=2
            )
            return
        # 保留策略：**新检查点已落盘之后**清理（同 `_write_checkpoint`，change 0208/0214）——
        # 否则轮级写入只增不减，长跑下无限增长。
        if retention_policy is not None:
            retention.apply(retention_policy)

    # 后台子 Agent（change 0270 / ADR-0260）：注册表先于主 loop 构造 —— 轮首通知取用闭包
    # 只注入主 loop（子 Agent / 神兽 / 宠物 loop 不接，与会话维度注入面同口径）。
    # 元数据跨重启登记（change 0279 / ADR-0269）：重启后运行中任务记为 interrupted，
    # 可由 `tools.tasks` 查询、`tools.task_retry` 显式重入队。
    background_tasks = BackgroundAgentRegistry(state_path=_background_state_path())

    loop = DefaultLoop(
        causal_links=causal_links,
        planner=planner,
        memory=memory,
        tools=tools,
        gate=guard,
        tracer=tracer,
        router=router if jev is not None else None,
        approver=approver,
        compactor=context_compactor,
        compact_timeout=config.compact_timeout(),
        turn_observer=loop_turn,
        notes_consult=_consult_notes,
        pinned_notes_consult=_pinned_notes,
        # 既往失败教训：**只**注入主 loop（子 Agent / 神兽 / 宠物 loop 不接 —— 教训按会话维度取用，
        # 同 `transcript` / `turn_checkpoint` 的注入面）；门控缺省关 ⇒ `None`（逐字不变）。
        failure_lessons_consult=_failure_lessons if config.failure_lessons() else None,
        # 后台任务完成通知：轮首一次性取用（缺省注册表为空 ⇒ 恒无通知 ⇒ 提示词逐字不变）。
        notices_consult=background_tasks.render_notices,
        cold_path=cold_path,
        trace_observer=trace_observer,
        middlewares=[constraints_chain.middleware, *hook_middlewares],
        action_observers=[constraints_chain.observe_result, *hook_observers],
        turn_before=hook_turn_before,
        turn_after=hook_turn_after,
        max_rounds=max_rounds,
        token_budget=token_budget,
        transcript=transcript,
        history_turns=config.history_turns(),
        act_wrapper=_fault_wrapper(tools),
        # 轮级检查点：**只**注入主 loop（子 Agent / 神兽 / 宠物 loop 不接 —— 会话维度是主
        # Agent 的门面概念，同 `transcript` 的注入面；change 0214 / ADR-0204）。
        turn_checkpoint=_turn_checkpoint if config.turn_checkpoint() else None,
    )

    # 子 Agent 独立 loop：各自 ToolProvider（不含 tools.delegate，结构上杜绝再委托），
    # 共享 memory / tracer / gate / approver（知识沉淀与权限口径统一）
    def _agent_tools() -> ToolProvider:
        provider = ToolProvider(
            coeffect_resolver=resolver, effect_tracker=effect_tracker, gate=guard, approver=approver
        )
        for tool in builtin_tools():
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
            max_tokens=max_tokens,
            block_plan=block_plan,
            parse_retry=parse_retry,
            env_snapshot=env_snapshot,
        )
        return cast(
            LoopPlugin,
            DefaultLoop(
                causal_links=causal_links,
                planner=sub_planner,
                memory=memory,
                tools=provider,
                gate=guard,
                tracer=tracer,
                router=router if jev is not None else None,
                approver=approver,
                compactor=context_compactor,
                compact_timeout=config.compact_timeout(),
                turn_observer=agent_turn,
                notes_consult=_consult_notes,
                pinned_notes_consult=_pinned_notes,
                middlewares=[constraints_chain.middleware, *hook_middlewares],
                action_observers=[constraints_chain.observe_result, *hook_observers],
                turn_before=hook_turn_before,
                turn_after=hook_turn_after,
                max_rounds=max_rounds,
                token_budget=token_budget,
                act_wrapper=_fault_wrapper(provider),
            ),
        )

    def _beast_loop(beast: Beast) -> LoopPlugin:
        """按兽装配独立 loop：域内技能路由（专属神通） + 共享记忆/闸门/追踪。

        与 ``_agent_loop`` 同构，三处差异：① ``_loop_hooks(beast.agent_id)`` —— 神兽只在
        自身域内看到自己的神通（beast-mode spec R4/R5）；② ``source=beast.<agent_id>`` ——
        轨迹落**独立记忆命名空间**（spec `:54`），与主 Agent ``source=loop`` 隔离；
        ③ **派生装配器**放行**自身**命名空间（``with_allow_source_prefixes``）—— 主侧封存
        （排除 `beast.*`）不再把兽自己的轨迹一并挡掉，他兽仍被排除（spec「自身轨迹可召回」）。
        """
        beast_hints, beast_turn = _loop_hooks(beast.agent_id)
        provider = _agent_tools()
        beast_planner = LLMPlanner(
            llm,
            model=app.llm.model,
            reasoning_effort=app.llm.reasoning_effort,
            assembler=assembler.with_allow_source_prefixes(beast.agent_id),
            skill_router=beast_hints,
            tools=provider,
            max_tokens=max_tokens,
            block_plan=block_plan,
            parse_retry=parse_retry,
            env_snapshot=env_snapshot,
        )
        return cast(
            LoopPlugin,
            DefaultLoop(
                causal_links=causal_links,
                planner=beast_planner,
                memory=memory,
                tools=provider,
                gate=guard,
                tracer=tracer,
                router=router if jev is not None else None,
                approver=approver,
                compactor=context_compactor,
                compact_timeout=config.compact_timeout(),
                turn_observer=beast_turn,
                notes_consult=_consult_notes,
                pinned_notes_consult=_pinned_notes,
                middlewares=[constraints_chain.middleware, *hook_middlewares],
                action_observers=[constraints_chain.observe_result, *hook_observers],
                turn_before=hook_turn_before,
                turn_after=hook_turn_after,
                source=beast.agent_id,
                max_rounds=max_rounds,
                token_budget=token_budget,
                act_wrapper=_fault_wrapper(provider),
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
        loop = profile.loop
        lease: WorkspaceLease | None = None
        if worktrees is not None:
            try:
                lease = await asyncio.to_thread(worktrees.create, agent_id=profile.agent_id)
            except OrchestrationError as exc:  # fail-closed：绝不回退主工作区
                return {"ok": False, "error": str(exc)}
        # 前台委托实况（change 0298 / ADR-0288）：生命周期 + 白名单进度写入父循环侧信道。
        # 无订阅方（后台 / arun）⇒ sink 为 None，零额外事件。
        sink = current_event_sink.get()
        agent_id = f"{profile.agent_id}:{uuid.uuid4().hex[:8]}"
        _emit_agent_event(
            sink,
            "agent.started",
            {"agent_id": agent_id, "agent": profile.agent_id, "title": _agent_title(task)},
        )

        # 委托轨迹归入发起会话（change 0247 / ADR-0235）：`DefaultLoop` 在动作期设置；
        # 缺省空串 = 未归属，与 delegate 引入前的归属语义一致。
        # 工作区（change 0284）：仅相对路径与省略 cwd 的 code_run 受影响（不是安全沙箱）。
        async def _run() -> LoopResult:
            with use_workspace(lease.path if lease is not None else None):
                if sink is None:  # 无订阅方 ⇒ 原路径逐字不变
                    return await loop.arun(task, session_id=current_session_id.get())
                return await collect_result(
                    loop.astream(task, session_id=current_session_id.get()),
                    on_event=lambda event: _relay_agent_progress(sink, agent_id, event),
                )

        try:
            result = await _run()
        except Exception as exc:
            _emit_agent_event(
                sink,
                "agent.completed",
                {
                    "agent_id": agent_id,
                    "ok": False,
                    "reply": f"子 Agent 执行异常：{type(exc).__name__}",
                },
            )
            raise
        _emit_agent_event(
            sink,
            "agent.completed",
            {
                "agent_id": agent_id,
                "ok": not result.failed,
                "reply": _agent_reply_excerpt(result.reply),
            },
        )
        payload: dict[str, object] = {"ok": not result.failed, "reply": result.reply}
        if lease is not None:
            payload["worktree"] = lease.as_metadata(await asyncio.to_thread(changed_files, lease))
        return payload

    async def _delegate(  # noqa: C901, PLR0911 — 逐种拒绝原因早退
        task: str, background: bool = False
    ) -> dict[str, object]:
        """委托工具：按能力标签匹配子 Agent。

        缺省（``background=False``）阻塞等待 LoopResult 并回传 reply —— 与引入后台能力前
        逐字一致。``background=True`` 立即返回 ``task_id``；子 Agent 在事件循环上后台执行，
        终态与完成通知由注册表按会话投递（change 0270 / ADR-0260）。

        入站即做委托深度护栏（纵深防御；子 Agent 工具面已不含 delegate）。
        """
        if _DELEGATE_DEPTH.get() >= 1:
            return {"ok": False, "error": "已达委托深度上限（子 Agent 不可再委托）"}
        token = _DELEGATE_DEPTH.set(_DELEGATE_DEPTH.get() + 1)
        try:
            if not background:
                return await _dispatch(task)
            try:
                profile = agent_router.match(task)
            except OrchestrationError as exc:
                return {"ok": False, "error": f"无匹配子 Agent: {exc}"}
            if profile.loop is None:
                return {"ok": False, "error": f"子 Agent {profile.agent_id} 无可用 loop"}
            try:  # 先查上限：满额时不得先创建出无人持有的工作树
                background_tasks.ensure_capacity()
            except OrchestrationError as exc:
                return {"ok": False, "error": str(exc)}
            lease: WorkspaceLease | None = None
            if worktrees is not None:
                try:
                    lease = await asyncio.to_thread(worktrees.create, agent_id=profile.agent_id)
                except OrchestrationError as exc:
                    return {"ok": False, "error": str(exc)}
            try:
                task_id = background_tasks.spawn(
                    profile.loop,
                    task,
                    agent_id=profile.agent_id,
                    session_id=current_session_id.get(),
                    workspace=lease,
                )
            except OrchestrationError as exc:  # 运行中上限 ⇒ 不排队，结构化拒绝
                if worktrees is not None and lease is not None:
                    await asyncio.to_thread(worktrees.remove_quiet, lease)
                return {"ok": False, "error": str(exc)}
            payload: dict[str, object] = {
                "ok": True,
                "task_id": task_id,
                "status": "running",
                "agent": profile.agent_id,
            }
            if lease is not None:
                payload["worktree"] = lease.as_metadata()
            return payload
        finally:
            _DELEGATE_DEPTH.reset(token)

    tools.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.delegate",
                description=(
                    "将子任务委托给匹配的子 Agent（coding/research）执行。缺省阻塞等待结果；"
                    "background=true 立即返回 task_id，完成后下一轮收到通知，可用 tools.tasks 查询"
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "要委托给子 Agent 的任务目标"},
                        "background": {
                            "type": "boolean",
                            "description": "true = 后台执行并立即返回（缺省 false = 阻塞等待）",
                        },
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
    # 模型侧任务清单（change 0270 / ADR-0260）：**只挂主工具面** —— 子 Agent 的 provider
    # 由 `_agent_tools()` 各自构造，结构上既不能起后台任务也查不到清单。
    tools.register(background_tasks_tool(registry=background_tasks))
    # 重入队（change 0279 / ADR-0269）：按原任务正文重新路由；只挂主工具面，需审批。
    tools.register(
        task_retry_tool(registry=background_tasks, match=agent_router.match, worktrees=worktrees)
    )
    # 工作树清单 / 显式丢弃（change 0284 / ADR-0274）：**只挂主工具面**；开关关闭时零注册。
    if worktrees is not None:

        def _worktree_busy(worktree_id: str) -> str | None:
            for info in background_tasks.list():
                if info.status == "running" and info.worktree.get("id") == worktree_id:
                    return info.task_id
            return None

        for worktree_tool in worktree_tools(manager=worktrees, is_running=_worktree_busy):
            tools.register(worktree_tool)

    store = CheckpointStore(_checkpoint_path())  # 落盘：跨进程续跑/崩溃恢复可读
    checkpoints = CheckpointManager(store)
    time_travel = TimeTravel(store, effect_tracker=effect_tracker)
    crash_recovery = CrashRecovery(store)
    # 保留策略接线（change 0208 / ADR-0198）：两通道皆缺省 ⇒ policy=None ⇒ `_write_checkpoint`
    # 短路，零清理、逐字不变。存储配额通道留库能力（超配额抛 RETENTION_QUOTA_EXCEEDED，不接）。
    retention = RetentionManager(store)
    _ret_max_count, _ret_window_s = config.retention_limits()
    retention_policy = (
        RetentionPolicy(
            max_count=_ret_max_count,
            time_window=timedelta(seconds=_ret_window_s) if _ret_window_s is not None else None,
        )
        if (_ret_max_count is not None or _ret_window_s is not None)
        else None
    )

    def _checkpoint(
        task_id: str, outcomes: list[SubtaskOutcome], plan: Plan, session_id: str = ""
    ) -> None:
        _write_checkpoint(task_id, outcomes, plan, done=False, session_id=session_id)

    def _finalize(
        task_id: str, outcomes: list[SubtaskOutcome], plan: Plan, session_id: str = ""
    ) -> None:
        _write_checkpoint(task_id, outcomes, plan, done=True, session_id=session_id)
        # 任务级 SOP 观察（change 0197 / ADR-0187）：成功 `DONE` 时把「任务目标 + 子任务步序」
        # 提交给任务级提炼器（达阈值才提炼）。步序经零效应 `_steps_lookup` 回读内存条目；
        # 该回调已由 change 0196 卸载出事件循环 ⇒ 此处模型调用不阻塞流式产出。提炼失败不中断。
        steps = compose_task_steps(plan, outcomes, _steps_lookup(backend))
        sop_task_extractor.observe(plan.goal, steps, ok=True)

    def _write_checkpoint(
        task_id: str,
        outcomes: list[SubtaskOutcome],
        plan: Plan,
        *,
        done: bool,
        session_id: str = "",
    ) -> None:
        checkpoints.create_checkpoint(
            task_id,
            # 发起会话标识：实参原值（空串 = 未归属照实记录；change 0190 去占位值）
            session_id,
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
        # 保留策略：**新检查点已落盘之后**清理（最新 ts 最大 ⇒ 永不误删刚写者；change 0208）。
        if retention_policy is not None:
            retention.apply(retention_policy)

    orchestrator = TaskScheduler(
        decomposer=SubtaskDecomposer(
            planner=LLMSubtaskPlanner(llm, model=app.llm.model),
            verifier=LLMVerifier(llm, model=app.llm.model),
        ),
        router=agent_router,
        state_machine=StateMachine(),
        # 调度策略与并发上限由组合根注入（change 0123）：不接线则上限判据在产线**空转**
        # （构造缺省 4 恰与既有行为同值，会掩盖未接线）。
        max_concurrency=config.orchestration_max_concurrency(),
        difficulty_policy=config.orchestration_difficulty_policy(),
        # 子任务交接超时（change 0247）：0 = 不设限（不接线则不暴露，故必须显式传）。
        subtask_timeout=config.orchestration_subtask_timeout(),
        # 整任务 token 预算（change 0280）：0 = 关闭（与引入前行为一致）。
        task_token_budget=config.orchestration_task_token_budget(),
        # 任务级判定器（change 0248）：与 planner 生成标准同批落地，缺省开启。
        success_checker=LLMTaskVerifier(llm, model=app.llm.model),
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
            for tool in builtin_tools():
                if tool.definition.tool_id in pet_allowed:
                    provider.register(tool)
            return provider

        def _pet_loop() -> LoopPlugin:
            """宠物**专属** loop（账本 E25）：受限工具集 + 安全中间件。

            此前宠物直接复用**主 loop**（`cast(LoopPlugin, loop)`）⇒ 可调用全部工具、安全边界
            不在路径上。专属 loop 沿用 `_agent_loop`/`_beast_loop` 同一形状（planner + 共享
            记忆/闸门/追踪），差异有三：① 工具集被白名单收窄（`_pet_tools`）；② 只挂安全中间件
            —— **不**共享 constraints 熔断链（宠物流量不应污染主线/神兽的熔断态），亦不接技能路由
            （pet 任务与结晶链路无关）；③ 轨迹落**独立命名空间**（`source="pet"`，pet-mode spec
            「Pet Session Runtime Wiring」）—— 主装配器已封存 `pet`，故此处须用**派生**装配器
            放行自身，否则宠物读不到自己的轨迹（与 `_beast_loop` 的 E54 同型）。
            越界 ⇒ 本轮终止 + 通知主人，会话保持 ACTIVE。
            """
            provider = _pet_tools()
            return cast(
                LoopPlugin,
                DefaultLoop(
                    causal_links=causal_links,
                    planner=LLMPlanner(
                        llm,
                        model=app.llm.model,
                        reasoning_effort=app.llm.reasoning_effort,
                        assembler=assembler.with_allow_source_prefixes("pet"),
                        tools=provider,
                        max_tokens=max_tokens,
                        block_plan=block_plan,
                        parse_retry=parse_retry,
                        env_snapshot=env_snapshot,
                    ),
                    memory=memory,
                    tools=provider,
                    gate=guard,
                    tracer=tracer,
                    approver=approver,
                    compactor=context_compactor,
                    compact_timeout=config.compact_timeout(),
                    middlewares=[
                        build_safety_middleware(pet_safety, notify=_pet_notify),
                        *hook_middlewares,
                    ],
                    action_observers=[*hook_observers],
                    turn_before=hook_turn_before,
                    turn_after=hook_turn_after,
                    max_rounds=max_rounds,
                    token_budget=token_budget,
                    source="pet",
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
                persona_factory=persona_from_record,
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
        background_llm=background_llm,
        memory=memory,
        tools=tools,
        tracer=tracer,
        router=router,
        rag=rag,
        loop=loop,
        transcript=transcript,
        skill_router=skill_router,
        skill_feedback=skill_feedback,
        skill_iterator=skill_iterator,
        skill_extractor=sop_extractor,
        installer=installer,
        mcp_client=mcp_client,
        evolution=evolution,
        evolution_executor=evolution_executor,
        orchestrator=orchestrator,
        background_tasks=background_tasks,
        worktrees=worktrees,
        checkpoints=checkpoints,
        time_travel=time_travel,
        crash_recovery=crash_recovery,
        pet_manager=pet_manager,
        pet_activator=pet_activator,
        beast_manager=beast_manager,
        beast_activator=beast_activator,
        env_snapshot=env_snapshot,
    )


def _is_turn_task(task_id: str, state: dict[str, Any] | None = None) -> bool:
    """轮面判据（change 0214 / ADR-0204）：命名空间前缀**或**状态标记 `kind == "turn"`。

    **或**（不是与）是刻意的：快照损坏时读不出 `kind`，前缀仍能把轮面与编排任务分开 ——
    与「损坏检查点按未完成处理」的既有降级方向一致（轮面宁可漏一句提示，**不**产生错的
    `task --resume turn.x` 提示）。
    """
    if task_id.startswith(_TURN_TASK_PREFIX):
        return True
    return state is not None and state.get("kind") == _TURN_KIND


def _turn_incomplete(checkpoints: CheckpointManager) -> list[tuple[str, str]]:
    """未完结的会话轮：`(task_id, session_id)`，按 ts 升序；**只读**、零副作用。

    判据与 `_recover_incomplete` 的「已完成」口径**不同**：轮面看**最新可读快照**（轮首写在途、
    轮末写完结 ⇒ 最新态即真态；编排任务侧沿用「任一快照 done 即视为完成」的历史口径，故不共用
    扫描实现）。损坏快照跳过（读不出即不冒错提示）。
    """
    latest: dict[str, tuple[float, str, bool]] = {}
    for cp in checkpoints.list_checkpoints():
        try:
            state = checkpoints.get_snapshot(cp.checkpoint_id).state
        except DurabilityError:
            continue
        if not _is_turn_task(cp.task_id, state):
            continue
        current = latest.get(cp.task_id)
        if current is None or cp.ts >= current[0]:
            latest[cp.task_id] = (cp.ts, cp.session_id, bool(state.get("done")))
    open_turns = [
        (ts, task_id, session_id) for task_id, (ts, session_id, done) in latest.items() if not done
    ]
    return [(task_id, session_id) for _, task_id, session_id in sorted(open_turns)]


def _warn_corrupt_tasks(corrupt_tasks: set[str], readable: set[str]) -> None:
    """只对**全部**快照都不可读的任务告警（仍有可读快照者静默回退；只报 task id）。"""
    for task_id in sorted(corrupt_tasks - readable):
        if not _is_turn_task(task_id):
            warnings.warn(f"任务 {task_id} 无可恢复检查点，跳过续跑", stacklevel=2)


def _completed_outcomes(state: dict[str, Any]) -> tuple[set[str], dict[str, str]]:
    """检查点 `outcomes` → （已完成子任务 id，依赖交接回复）；只收 `ok=true`。"""
    completed: set[str] = set()
    results: dict[str, str] = {}
    raw = state.get("outcomes")
    if not isinstance(raw, list):
        return completed, results
    for item in cast(list[Any], raw):
        if not isinstance(item, dict):
            continue
        outcome = cast(dict[str, Any], item)
        if not outcome.get("ok"):
            continue
        subtask_id = str(outcome.get("subtask_id", ""))
        if not subtask_id:
            continue
        completed.add(subtask_id)
        results[subtask_id] = str(outcome.get("reply", ""))
    return completed, results


def _task_resumes(checkpoints: CheckpointManager) -> list[TaskResume]:
    """未完成编排任务的重建包（`task --resume-all` / `orchestration.auto_resume`）。

    取每个任务**时间戳最新**的可读快照（与 `--resume` 同口径；`>=` 使同 ts 后者胜）；
    `done=true`、会话轮（`turn.` 前缀或 `kind="turn"`）、损坏快照跳过；计划缺失/非 dict
    告警后跳过（只报 task id，不回显任务正文）。**只读**、零副作用。
    """
    latest: dict[str, tuple[float, Checkpoint, dict[str, Any]]] = {}
    corrupt_tasks: set[str] = set()
    for cp in checkpoints.list_checkpoints():
        try:
            state = checkpoints.get_snapshot(cp.checkpoint_id).state
        except DurabilityError:
            corrupt_tasks.add(cp.task_id)
            continue
        if _is_turn_task(cp.task_id, state):
            continue
        current = latest.get(cp.task_id)
        if current is None or cp.ts >= current[0]:
            latest[cp.task_id] = (cp.ts, cp, state)
    _warn_corrupt_tasks(corrupt_tasks, set(latest))

    resumes: list[TaskResume] = []
    for task_id, (_, cp, state) in sorted(latest.items()):
        if state.get("done"):
            continue
        plan_raw = state.get("plan")
        if not isinstance(plan_raw, dict):
            warnings.warn(f"任务 {task_id} 的检查点缺少计划，跳过续跑", stacklevel=2)
            continue
        plan = plan_from_dict(cast(dict[str, Any], plan_raw))
        completed, results = _completed_outcomes(state)
        session_id = cp.session_id or ""
        if session_id == "default":  # 旧占位值视作未归属（与 `--resume` 同口径）
            session_id = ""
        resumes.append(
            TaskResume(
                task_id=task_id,
                goal=plan.goal,
                plan=plan,
                completed=frozenset(completed),
                results=results,
                session_id=session_id,
            )
        )
    return resumes


def _recover_incomplete(
    checkpoints: CheckpointManager, recovery: CrashRecovery
) -> list[RestoreHandle]:
    """扫描检查点，对无 done 标记的任务 restore + resume（幂等续跑）。

    **轮面分流**（change 0214 / ADR-0204）：会话轮级检查点**不**入续跑面（`turn.x` 交给
    `CrashRecovery.restore` 会产出「把一轮对话当一个任务续跑」的错提示）—— 其呈现走
    `_turn_incomplete` / :meth:`Runtime.recover_turns`。
    """
    done_tasks: set[str] = set()
    turn_tasks: set[str] = set()
    for cp in checkpoints.list_checkpoints():
        try:
            snapshot = checkpoints.get_snapshot(cp.checkpoint_id)
        except DurabilityError:
            continue  # 损坏检查点按未完成处理，交给 restore 回退更早检查点
        if _is_turn_task(cp.task_id, snapshot.state):
            turn_tasks.add(cp.task_id)
            continue
        if snapshot.state.get("done"):
            done_tasks.add(cp.task_id)
    handles: list[RestoreHandle] = []
    seen: set[str] = set()
    for cp in checkpoints.list_checkpoints():
        if cp.task_id in done_tasks or cp.task_id in seen:
            continue
        # 快照全损坏 ⇒ 上面的 kind 读不出；此处再按前缀兜一次（轮面永不续跑）
        if cp.task_id in turn_tasks or _is_turn_task(cp.task_id):
            continue
        seen.add(cp.task_id)
        try:
            handle = recovery.restore(cp.task_id)
        except DurabilityError:
            # 该任务检查点全无有效快照 ⇒ 降级跳过（一坏任务不炸全扫；change 0191，
            # 与首轮 get_snapshot 对 corrupt 的捕获同口径）。只报 task id，不回显正文。
            warnings.warn(f"任务 {cp.task_id} 无可恢复检查点，跳过", stacklevel=2)
            continue
        recovery.resume(handle)
        handles.append(handle)
    return handles
