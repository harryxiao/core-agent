# Proposal: 三层会话滑窗 —— 短/中/长 + 动态按比例压缩

> 规格：`loop`/`context`/`memory`（**MODIFIED × 3 + ADDED × 1**）

## Why

日常会话记忆有两张**并存且互补**的缺陷（均经逐行核实）：

1. **摘要从不进 prompt**。`MemoryStore.summary_for` 的唯一调用者是 CLI（`entry.py:1615`）——
   会话摘要即便产出，也**从不注入任何 LLM 请求**；`planner._system_prompt` 没有任何「历史摘要」块。
2. **日常会话根本不产摘要**。`loop/default.py` 的 `_maintain` 只做遗忘 + 冷路径；`memory.compact()`
   仅三处调用（CLI / Web「压缩本会话」/ `_compact`），而后者的触发判据 `Compactor.should_compact(ctx.rounds, …)`
   里的 `ctx.rounds` 是**每轮工具步计数**——无工具的日常聊天里恒不触发。**两半缺陷并存**，故日常会话里
   摘要「既不产生、也不注入」。
3. **窗口静默截断无补偿**。`_load_history` → `transcript.tail(sid, history_turns, max_tokens=token_budget//2)`；
   `tail` 从新到旧累计、超预算即 `break` ⇒ **丢最旧、无摘要替换** ⇒ 超 `history_turns` 轮即失忆。
4. **无分层**。单条固定轮数 + 单个 `token_budget//2` 切片，无短/中/长配比，未「按比例压缩」。

## What Changes

把「会话历史回灌」由**单条固定窗口**升级为**三层滑窗**（用户已裁决：完整三层 + 复用既有 summarize 通道）：

1. **短层**（原文逐字）：最近 `short_turns` 轮，仍走 `TranscriptStore`。
2. **中层**（模型摘要）：紧随短层之前的 `mid_turns` 轮 → 经**既有 summarize 通道**（`build_prompt` + `Summarizer`，
   零改动复用）提炼，产物落 `compaction.mid.<session>`（新 id 约定，与既有 `compaction.summary.<session>` 同形）。
3. **长层**（会话摘要）：**复用既有** `compaction.summary.<session>` —— 本 change 把它**首次注入 prompt**。
4. **动态按比例**：三层按固定份额 `0.5 / 0.3 / 0.2` 分配 `history_budget = token_budget // 2`，由**确定性纯函数**
   （无模型调用）给出；`loop.history_turns` 语义由「短层轮数」变为**三层总量**，按比例切分。
5. **物化触发**：扩展既有 **off-loop 维护节拍**（`_maintain`）为会话感知——会话级压实 + 中层摘要物化，
   各自失败降级；不再依赖那个恒不触发的 `_should_compact`。
6. **零回归**：冷会话（无任何摘要）⇒ 退化为**逐字今天的纯回灌**（`tiered=False`）；`history_turns<=0` /
   `session_id==""` / 未注入转录 ⇒ 零读取零注入。

## Impact

- **specs**：
  - `loop/spec.md`——**MODIFIED**「执行循环」（窗口条款 → 三层滑窗；维护节拍条款 → 扩为「会话压实 + 中层物化 + 遗忘 + 冷路径」）。
  - `context/spec.md`——**ADDED**「三层窗口比例分配」（确定性纯函数给出份额与 clamps；LLM 压缩仍统一由记忆压实通道承担，不新增调用点）。
  - `memory/spec.md`——**MODIFIED**「记忆压实」（新增 `summarize_slice` / `mid_summary_for`）与「对话转录持久化（非记忆层级）」（新增分层切分读取）。
- **src**：新增 `src/core/context/window.py`；`memory/transcript.py`、`memory/store.py`、`loop/protocol.py`、
  `loop/default.py`、`loop/planner.py` 接线。**无跨域新 import**（loop 早已 import memory/context）。
- **风险**：中——新增 off-loop 模型调用（每维护节拍最多 ~2–3 次），有节流 + 中带空守卫；冷会话路径零回归。
  CJK `estimate_tokens` 欠估**本 change 不修**（承 ADR-0144 明文 + E96），记为局限。
