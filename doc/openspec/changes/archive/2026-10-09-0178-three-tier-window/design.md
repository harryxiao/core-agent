# Design: 三层会话滑窗（short / mid / long）

## Context

相关前序：ADR-0108（会话历史回灌，`0115`）、ADR-0144（记账以 provider 实报为下界，`0152`）、
ADR-0147（关键事实抽取，`0155`）、ADR-0157（同步模型调用卸载出事件循环，`0167`）、
ADR-0164（记忆材料与引用语义，`0173`）、ADR-0124（`compact` 按会话收窄，`0131`）。
既有压实通道：`MemoryStore._summarize_sessions` / `_commit_summary`（id `compaction.summary.<key>`，滚动合并，来源迁 L4）。

## Goals / Non-Goals

**Goals**：三层滑窗（短原文 / 中摘要 / 长摘要）；动态按比例；摘要**首次进 prompt**；日常会话**能产出**摘要；
冷会话与关闭路径**逐字零回归**。

**Non-Goals**：不修 CJK token 欠估；不修 `_should_compact` 的死轮数维度；不新增配置键；不动 SPA / 转录落盘格式；
不做「压缩产物从事实检索面排除」。

## Decisions

### D1. 三层语义

| 层 | 内容 | 来源 | 生产者 |
|---|---|---|---|
| 短 | 最近 `short_turns` 轮**原文逐字** | `TranscriptStore` 转录行 | 无 |
| 中 | 紧随短层之前的 `mid_turns` 轮 → **模型滚动摘要** | 转录行 → 既有 `Summarizer` | 既有 summarize 通道；产物 `compaction.mid.<session>` |
| 长 | 会话**整体摘要** | 既有 `compaction.summary.<session>` | 既有 `_summarize_sessions`（不动） |

中层材料取**转录**而非 L2 轨迹条目：`_trajectory_line` 只含 `round N ok/failed` + 回复散文，**不含用户提问**；
且 `_commit_summary` 会把来源迁 L4 —— 对「对话窗口」是错误的材料。转录是唯一同时含 user + assistant 的会话基底。

### D2. 策略与机制分离

- **策略**落新增纯模块 `src/core/context/window.py`（stdlib only，零 I/O，零模型调用）：`WindowPlan` + `plan_window`。
- **机制**（切日志）留在 `TranscriptStore.window()`。
- 分离理由：`memory.transcript` **不得** import `core.context`（`context/compactor.py` 已 import `core.memory`，
  反向即循环依赖，违 ADR-0045）。故 `window()` 只收**裸 int**，`WindowPlan` 由 `default.py` 解包传入。

### D3. 压缩层物化（crux）

**中层**：`MemoryStore.summarize_slice(session_id, entries, *, max_chars) -> str | None` +
只读 `mid_summary_for(session_id)`。产物 id `compaction.mid.<key>`、`source="compaction"`、`kind="semantic"`、
`trace_id=f"compaction.mid.<key>"`、写前 `redact_secrets`、有界 `max_chars`、**不 migrate 任何来源**。
滚动合并：`prior = 既有 compaction.mid.<sid>`，`material = [prior, *entries]`（同 `_summarize_sessions` 形态）。
未注入摘要器 ⇒ 返回 `None`、**零写入零效应**。把 `_existing_summary` 的内部提为 `_entry_by_id(target)`，
`summary_for` / `mid_summary_for` / `_existing_summary` 共用（id 约定单一真源）。

**长层**：不新增产物，注入既有只读 `summary_for(session_id)`。

**触发点**：扩展既有 off-loop 维护节拍 `_maintain`（签名加 `session_id: str = ""`），节流判定不变；节流通过后依次
（各自 `try/except` 降级，沿用 `maintenance_failed` 留痕）：① `memory.compact(session_id=…)`（仅 `session_id` 非空）
② `_materialize_mid(session_id)`（读转录 → `window()` 取中带 → 空即返回 → 包 **prompt-only `MemoryEntry` 桩**
→ `summarize_slice(...)`，桩**绝不落库**）③ 既有 `forget()` ④ 既有冷路径。调用点改
`await asyncio.to_thread(self._maintain, trace_id, ctx.session_id)`（仍 off-loop，承 ADR-0157）。

**否决**「loop 局部缓存摘要」（摘要器住在 `MemoryStore` 内，loop 要用它就得新开 DI 接缝；进程重启即失、多会话需自行键控）。
采 memory 化：直接复用既有 `write` / `redact_secrets` / `EffectTracker` / id 约定，改动更小、可撤销、可观测。

### D4. 动态按比例（纯函数）

```python
_CHARS_PER_TOKEN = 4
_SHORT_SHARE, _MID_SHARE, _LONG_SHARE = 0.5, 0.3, 0.2
# history_turns<=0 or budget<=0 ⇒ 全零；tiered=False ⇒ (history_turns, 0, budget, 0) ≡ 今天
short = min(history_turns, max(1, ceil(history_turns * _SHORT_SHARE)))
mid   = max(0, min(history_turns - short, ceil(history_turns * _MID_SHARE)))
short_tokens = max(1, int(budget * _SHORT_SHARE))
mid_chars    = max(0, int(budget * _MID_SHARE) * _CHARS_PER_TOKEN)
```

缺省 20 轮 / `B=32768` ⇒ short=10 轮 / 16384 tok、mid=6 轮 / `mid_chars≈39321`、long=既有摘要（≤2000 字）。
长层无轮数配额（覆盖更早全部）。会话短于计划 ⇒ `window()` 给不足轮数即为所得。

### D5. Prompt 注入

`LoopContext` 增两**独立字段** `summary_long` / `summary_mid`（**绝不**折入 `messages`/`history` —— 承既有分列先例）。
`_system_prompt` 次序：系统提示 → 宪法规则 → 常驻笔记 → **历史摘要（长期）** → **历史摘要（中期）** → 相关事实 →
文档目录 → 相关笔记 → 可用技能 → 可用工具。两新块 `.strip()` 非空才加 ⇒ 空时 prompt 逐字不变。
（会话自身历史比外部检索事实更权威 ⇒ 置于「相关事实」之前。）

### D6. Token 记账

新块住 system prompt ⇒ 已被 `planner._estimate_prompt` 与 provider 实报计入，经 `observe` 的 `max(_context_tokens, probe)` 抬升下界。
**另**把两摘要计入 `_context_tokens`（无探针的纯 callable planner 也看得见），**必须** `if text.strip()` 守卫——
`estimate_tokens("") == 1`，否则空字段各加 1，`test_history_replay.py` 的 `seen == [210]` 立即变红、零回归不变量破产。

### D7. CJK `estimate_tokens` 欠估 —— **OUT**（用户裁决）

承 ADR-0144「已知局限③」明文「不改共享估算器（波及 context 打包与转录切片，另议）」+ E96。
记为 ADR-0169 局限段与 test-cases 该节注明；**不新增台账行**。比例是**等比的**，故欠估影响的是窗口**绝对尺寸**，
非配比本身。

### D8. 配置面 —— 模块常量（不新增配置键）

与 `_ROUND_THRESHOLD` / `_IMPORTANCE_FLOOR` / `MAX_SUMMARY_CHARS` 同纪律。`loop.history_turns` 仍是**唯一**用户可调旋钮。

### D9. 向后兼容不变量

I1 `history_turns<=0` / I2 `session_id==""` / I3 未注入转录 ⇒ 零读取零注入；
I4 未注入 memory 或 summarizer UNWIRED ⇒ `tiered=False`、`summarize_slice` 返回 `None`、零效应；
I5 **冷会话无任何摘要 ⇒ 请求逐字 = 今天**（核心锚点）；
I6 `_maintain` 任一步失败 ⇒ 降级留痕、不破轮；
I7 转录读失败 ⇒ 无历史且无摘要 + `warnings.warn`；
I8 摘要写入必过 `redact_secrets`；
I9 中层产物**不迁移**来源、可经 `trace_id` 回滚；
I10 空摘要字段 ⇒ 无新块、`_context_tokens` 零增量。

### D10. 规格 delta

见 proposal「Impact」：`loop` MODIFIED「执行循环」（窗口 + 维护节拍两处条款）；`context` ADDED「三层窗口比例分配」；
`memory` MODIFIED「记忆压实」+「对话转录持久化（非记忆层级）」。既有 Scenario 逐字保留，新增约 16 条。

## Risks / Trade-offs

1. **成本**：日常会话路径每维护节拍最多 ~2–3 次额外模型调用（会话压实 + 中层摘要）。缓解：节流 + 中带空守卫。
2. **短带在分层激活时收窄**（缺省 20→10 轮原文）——有意；老的原文由摘要承接。
3. **CJK 欠估**（D7）——不在范围，承 E96/E97。
4. **密钥面**：中层摘要输入是会话原文（可能含密钥），产物写回前 `redact_secrets`；「对话原文进 LLM 请求」是既有面（ADR-0147 局限④）。
5. **热路径读放大**：`perceive` 每轮新增两次全库扫描（`summary_for`/`mid_summary_for`），与 `read()` 同量级；仅在四条件齐备时读。
6. **重复暴露**：中层产物会同时经 `read()` 进「相关事实」块 → 与新增「历史摘要（中期）」块可能重复；本 change 不去重。
7. **节拍实例级、会话无关**：多会话进程中每维护间隔只有「正巧活跃」的会话被刷新。
8. **`_should_compact` 死轮数维度未修**（E96 局限②）。

## Migration Plan

无数据迁移。新增 id 约定 `compaction.mid.<session>` 与既有 `compaction.summary.<session>` 并存，互不影响。

## Open Questions

无。（分层激活时短带收窄、CJK 欠估不在范围、配置面为常量 —— 均已裁决。）
