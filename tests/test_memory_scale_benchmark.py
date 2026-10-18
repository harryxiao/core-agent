"""PA-09 方案 B：1 万条记忆检索规模基准（change 0275 / ADR-0265 / 台账 E211）。

**可测性先行**（PA-09 选项 B，零产品行为改动）：在 1 万条固定合成事实语料上度量
**recall@5 / MRR@5** 与**逐查询延迟**，把「万条后检索是否漂移」「是否满足
CORE-NFR-PERF2（<100ms / 1 万条）」变成可复现的数字。

- 纯离线：`MemoryStore()`（内存 `FileBackend`）、无 embedder、无真实 LLM、无网络。
- **延迟目标只报告、不设产品阈值门禁**：本机实测中位 ≈ 0.6s，**未达** 100ms 目标 ——
  这是本基准揭示的既有缺口（另立 change 修复）；断言只用宽松回归上限防「整体再恶化一个
  数量级」，不把不达标写进门禁（避免基准一落地即红）。
- 词法排序在 10k 规模下的回归由 recall/MRR 阈值承载；规模本身由 `len(audit())` 钉住。

规格：`memory`「检索规模离线基准（1 万条）」。
"""

from __future__ import annotations

import statistics
import time

from core.memory import MemoryEntry, MemoryStore

_CORPUS_SIZE = 10_000
_QUERY_STRIDE = 500  # 每 500 条取一条作 gold ⇒ 20 条查询
_L4_OFFSET = 5  # 层分布：每 10 条中 0 号为 L3、5 号为 L4，其余 L2
_TOP_K = 5
_RECALL_MIN = 0.9
_MRR_MIN = 0.7
# 宽松回归上限（产品目标 100ms 的 50 倍）：只抓「整体恶化一个数量级」，不替代产品目标。
_LATENCY_P95_CEILING_MS = 5000.0


def _fact(index: int) -> MemoryEntry:
    """确定性合成事实：每条第 `index` 号唯一编号 `zqNNNNN`（查询的唯一 gold 锚）。"""
    layer = "L3" if index % 10 == 0 else "L4" if index % 10 == _L4_OFFSET else "L2"
    status = ("进行中", "已完成", "已归档", "待评审")[index % 4]
    return MemoryEntry(
        id=f"fact-{index:05d}",
        layer=layer,
        content=(
            f"事实 {index:05d}：项目 {index % 200:03d} 的负责人是 张三{index:05d}，"
            f"状态 {status}，记录编号 zq{index:05d}。"
        ),
        tags=["bench"],
        source="bench",
        trace_id="bench",
        ts=0.0,
    )


def _corpus(size: int = _CORPUS_SIZE) -> list[MemoryEntry]:
    return [_fact(index) for index in range(size)]


def _query(index: int) -> str:
    return f"负责人 张三{index:05d}"


def _build_store() -> MemoryStore:
    store = MemoryStore()
    for entry in _corpus():
        store.write(entry.layer, entry)
    return store


def test_memory_scale_benchmark_at_10k() -> None:
    """1 万条语料：recall@5 / MRR@5 / 延迟全部可复现地输出；准确率过阈值。"""
    store = _build_store()
    assert len(store.audit(None)) == _CORPUS_SIZE, "语料规模必须是 10k（规模本身就是被测面）"

    golds = list(range(0, _CORPUS_SIZE, _QUERY_STRIDE))
    store.read(_query(golds[0]))  # 预热：剔除首调用的一次性开销
    latencies: list[float] = []
    reciprocal_ranks: list[float] = []
    hits = 0
    for index in golds:
        started = time.perf_counter()
        rows = store.read(_query(index), budget=4096)
        latencies.append((time.perf_counter() - started) * 1000.0)
        ids = [entry.id for entry in rows[:_TOP_K]]
        gold = f"fact-{index:05d}"
        if gold in ids:
            hits += 1
            reciprocal_ranks.append(1.0 / (ids.index(gold) + 1))
        else:
            reciprocal_ranks.append(0.0)

    recall = hits / len(golds)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
    ordered = sorted(latencies)
    median_ms = statistics.median(latencies)
    p95_ms = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    print(
        f"10k benchmark: queries={len(golds)} recall@5={recall:.3f} mrr@5={mrr:.3f} "
        f"latency_ms median={median_ms:.1f} p95={p95_ms:.1f} max={max(latencies):.1f}"
    )  # noqa: T201 — 基准输出供人工查看
    assert recall >= _RECALL_MIN
    assert mrr >= _MRR_MIN
    # 产品目标（CORE-NFR-PERF2 <100ms）只报告：当前实现未达标，另立 change 修复。
    assert p95_ms < _LATENCY_P95_CEILING_MS, "延迟整体恶化一个数量级（远超已记录的基线）"


def test_memory_scale_corpus_is_deterministic() -> None:
    """语料生成无随机源：两次独立生成逐条一致（基准数字可复现的前提）。"""
    first = [(entry.id, entry.layer, entry.content) for entry in _corpus()]
    second = [(entry.id, entry.layer, entry.content) for entry in _corpus()]
    assert first == second
