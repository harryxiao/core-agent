"""记忆检索质量离线基准（change 0261 / ADR-0251，规格「检索质量离线基准」）。

固定合成语料（26 条：L2 当前事实 / L3 技能 / L4 归档 / 跨会话 / `bench.stale` 陈旧冲突 /
诱饵）＋ 12 条带 gold 的查询，度量：

- **recall@5**：gold 命中比例（阈值 ≥ 0.9）；
- **MRR@5**：首个 gold 命中的倒数排名（阈值 ≥ 0.7）；
- **stale_hits**：陈旧条目排名高于对应当前事实的查询数（阈值 = 0）。

纯离线：纯内存后端、无 embedder、无 LLM、无网络。每条查询**新建 store 重放语料**，避免
`read()` 的 `_reinforce` 改写 `reuse_count` 造成查询顺序耦合。

这是**词法排序的回归门**：语料或阈值变更须显式重定基线（写入 ADR / 测试说明），不得为让实现
变绿而静默放宽。运行 `pytest -q tests/test_memory_quality.py -s` 可查看指标。
"""

from __future__ import annotations

from core.memory import MemoryEntry, MemoryStore

_TOP_K = 5
# 回归门阈值（change 0261）：改动须显式重定基线并记录原因。
_MIN_RECALL = 0.9
_MIN_MRR = 0.7
_MAX_STALE_HITS = 0
_STALE_SOURCE = "bench.stale"
# 冻结新鲜度衰减：所有条目时间戳相同且位于未来 ⇒ recency_decay 恒 1.0（无时钟噪声）。
_FREEZE_TS = 4_000_000_000.0
# 预算只需容纳全部语料（约 100 token）；首条无条件保留不参与本基准的截断语义。
_BUDGET = 4096

_CorpusRow = tuple[str, str, str, str, str]  # id / layer / content / source / session

_CORPUS: tuple[_CorpusRow, ...] = (
    # 当前事实（L2，跨会话 s1/s2/s3）
    (
        "c-pytest",
        "L2",
        "Project tests run with pytest inside the uv virtual environment.",
        "bench",
        "s1",
    ),
    (
        "c-config",
        "L2",
        "Configuration defaults live in the ConfigSpec single source of truth.",
        "bench",
        "s1",
    ),
    (
        "c-backend",
        "L2",
        "The memory store persists entries through FileBackend JSONL.",
        "bench",
        "s1",
    ),
    (
        "c-loop",
        "L2",
        "The loop terminates with LOOP_LIMIT_EXCEEDED when max rounds are reached.",
        "bench",
        "s2",
    ),
    (
        "c-tool",
        "L2",
        "code_run executes shell commands in an isolated process group.",
        "bench",
        "s2",
    ),
    ("c-orch", "L2", "TaskScheduler fans out subtasks by dependency topology.", "bench", "s3"),
    (
        "c-secret",
        "L2",
        "Secrets are referenced by CoeffectResolver and never logged.",
        "bench",
        "s3",
    ),
    # 技能（L3）
    ("s-deploy", "L3", "Skill deploy service with docker build then docker push.", "bench", "s1"),
    ("s-review", "L3", "Skill code review checks ruff pyright and pytest gates.", "bench", "s2"),
    ("s-migrate", "L3", "Skill database migration uses alembic upgrade head.", "bench", "s3"),
    # 归档（L4）
    ("a-old-pytest", "L4", "Legacy note tests previously used unittest discovery.", "bench", "s1"),
    (
        "a-old-config",
        "L4",
        "Legacy note configuration was hardcoded in environment variables.",
        "bench",
        "s2",
    ),
    # 跨会话（s9）
    (
        "x-onboarding",
        "L2",
        "Onboarding docs live under docs onboarding for new contributors.",
        "bench",
        "s9",
    ),
    (
        "x-release",
        "L2",
        "Release checklist requires changelog update and version bump.",
        "bench",
        "s9",
    ),
    # 陈旧冲突（source = bench.stale）
    (
        "st-pytest",
        "L2",
        "Stale project tests run with nose test runner via setup.py.",
        _STALE_SOURCE,
        "s1",
    ),
    (
        "st-config",
        "L2",
        "Stale configuration defaults are hardcoded constants in runtime.",
        _STALE_SOURCE,
        "s1",
    ),
    (
        "st-backend",
        "L2",
        "Stale memory store writes entries to a SQLite database.",
        _STALE_SOURCE,
        "s1",
    ),
    (
        "st-tool",
        "L2",
        "Stale code_run executes commands inside the main thread.",
        _STALE_SOURCE,
        "s2",
    ),
    (
        "st-orch",
        "L2",
        "Stale TaskScheduler runs every subtask sequentially without dependencies.",
        _STALE_SOURCE,
        "s3",
    ),
    # 诱饵（与查询共享部分词元但不是 gold）
    (
        "d-uv",
        "L2",
        "The uv lockfile pins third party dependencies for reproducible builds.",
        "bench",
        "s1",
    ),
    ("d-jsonl", "L2", "Logs are appended to JSONL files under the state directory.", "bench", "s1"),
    ("d-docker", "L2", "Docker images are built nightly in continuous integration.", "bench", "s2"),
    (
        "d-alembic",
        "L2",
        "Alembic revision files are stored in the migrations directory.",
        "bench",
        "s2",
    ),
    (
        "d-changelog",
        "L2",
        "The changelog is generated from conventional commit messages.",
        "bench",
        "s2",
    ),
    (
        "d-keychain",
        "L2",
        "API keys can be stored in the system keychain for local development.",
        "bench",
        "s3",
    ),
    ("d-rounds", "L2", "Loop rounds are displayed in the diagnostics status view.", "bench", "s3"),
)

# (query, gold ids, 与该查询配对的陈旧条目或 None)
_QUERIES: tuple[tuple[str, tuple[str, ...], str | None], ...] = (
    (
        "which test runner pytest virtual environment project tests",
        ("c-pytest",),
        "st-pytest",
    ),
    (
        "where do configuration defaults come from ConfigSpec",
        ("c-config",),
        "st-config",
    ),
    (
        "how does memory store persist entries FileBackend",
        ("c-backend",),
        "st-backend",
    ),
    (
        "how does code_run execute shell commands process group",
        ("c-tool",),
        "st-tool",
    ),
    (
        "how does TaskScheduler fan out subtasks dependencies",
        ("c-orch",),
        "st-orch",
    ),
    ("skill for code review with ruff pyright pytest", ("s-review",), None),
    ("deploy service docker build push", ("s-deploy",), None),
    ("secrets referenced CoeffectResolver never logged", ("c-secret",), None),
    ("database migration alembic upgrade", ("s-migrate",), None),
    ("release checklist changelog version bump", ("x-release",), None),
    ("onboarding docs new contributors", ("x-onboarding",), None),
    ("loop terminates LOOP_LIMIT_EXCEEDED max rounds", ("c-loop",), None),
)


def _build_store() -> MemoryStore:
    """新建纯内存 store 并重放固定语料（每条查询独立，规避强化计数耦合）。"""
    store = MemoryStore()
    for entry_id, layer, content, source, session_id in _CORPUS:
        store.write(
            layer,  # type: ignore[arg-type] — 语料内的层字面量均为合法 Layer
            MemoryEntry(
                id=entry_id,
                layer=layer,  # type: ignore[arg-type]
                content=content,
                tags=[],
                source=source,
                trace_id=f"bench.{entry_id}",
                ts=_FREEZE_TS,
                session_id=session_id,
            ),
        )
    return store


def _top_ids(query: str, *, exclude: tuple[str, ...] = ()) -> list[str]:
    results = _build_store().read(query, budget=_BUDGET, exclude_source_prefixes=exclude)
    return [entry.id for entry in results[:_TOP_K]]


def _metrics() -> tuple[float, float, int]:
    recall_sum = 0.0
    mrr_sum = 0.0
    stale_hits = 0
    for query, gold, stale in _QUERIES:
        ranks = {entry_id: rank for rank, entry_id in enumerate(_top_ids(query), start=1)}
        gold_ranks = [ranks[gold_id] for gold_id in gold if gold_id in ranks]
        recall_sum += len(gold_ranks) / len(gold)
        mrr_sum += 1.0 / min(gold_ranks) if gold_ranks else 0.0
        if stale is not None and stale in ranks:
            gold_rank = ranks.get(gold[0])
            if gold_rank is None or ranks[stale] < gold_rank:
                stale_hits += 1
    count = len(_QUERIES)
    return recall_sum / count, mrr_sum / count, stale_hits


def test_synthetic_corpus_meets_quality_thresholds() -> None:
    """固定语料基线：recall@5 ≥ 0.9、MRR@5 ≥ 0.7、陈旧命中 = 0。"""
    recall, mrr, stale_hits = _metrics()
    print(f"recall@5={recall:.3f} mrr@5={mrr:.3f} stale_hits={stale_hits}")
    assert recall >= _MIN_RECALL
    assert mrr >= _MIN_MRR
    assert stale_hits == _MAX_STALE_HITS


def test_stale_source_prefix_excluded() -> None:
    """`exclude_source_prefixes` 在排名与预算之前剔除陈旧来源，当前事实仍可召回。"""
    for query, _, _ in _QUERIES:
        results = _build_store().read(
            query, budget=_BUDGET, exclude_source_prefixes=(_STALE_SOURCE,)
        )
        assert all(not entry.source.startswith(_STALE_SOURCE) for entry in results)
    query, gold, _ = _QUERIES[0]
    results = _build_store().read(query, budget=_BUDGET, exclude_source_prefixes=(_STALE_SOURCE,))
    assert gold[0] in [entry.id for entry in results]


def test_replay_is_deterministic() -> None:
    """同一语料两次独立重放 ⇒ top-5 序列一致（无时钟 / 随机 / 强化耦合）。"""
    for query, _, _ in _QUERIES:
        assert _top_ids(query) == _top_ids(query)
