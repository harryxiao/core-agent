# Proposal 0217 — 「既往失败教训」注入块（`loop.failure_lessons`，缺省关）

## Why（缺口）

四类记忆里，**失败经验已有沉淀**（`loop.failure.<trace_id>`，`0179` / ADR-0170：`tags=["loop","failure"]`、
`kind="episodic"`、承载「任务 + 失败原因 + 失败轮次与失败动作」）—— 但**没有专属注入面**：

| 记忆面 | 沉淀 | 专属注入面 | 现状 |
|---|---|---|---|
| 成功经验 | 技能库 / 笔记 | 「可用技能」块 ＋ 「相关笔记」块 | ✅ 有 |
| 失败经验 | `loop.failure.*` | **无** | ⚠️ 只能靠通用「相关事实」碰运气 |
| 语义事实 | `keyfact.*` / relation | 「相关事实」块 | ✅ 有 |
| 压缩产物 | `compaction.*` | 「历史摘要（长期/中期）」块 | ✅ 有 |

`Diagnoser` 消费失败条目，但只进**诊断报告**、**不回灌推理提示** ⇒ 下一轮推理**看不见上一轮怎么失败的**。
通用「相关事实」面按**相关性**排序取数：失败条目的检索词命中纯属偶然，长会话里极易被高分事实挤出。
缺口 = **缺一个按会话、按时间倒序的失败教训专块**（同「常驻笔记」/「历史摘要」的独立块口径）。

## What Changes

1. **零效应读面**：`MemoryStore.failure_lessons(session_id, *, limit=5) -> list[MemoryEntry]`，取该会话
   `tags` 含 `failure` 的条目，`ts` **降序**、**至多 `limit` 条**、**层无关**（归档至 L4 者仍可读）。
   **绝不**经 `read()`（`_reinforce` 会 +1 `reuse_count` 并落盘效应）。
2. **上下文字段**：`LoopContext.failure_lessons: str = ""`（独立字段）。
3. **规划器块**：`_system_prompt` 非空该字段 ⇒ 追加**独立系统块**「既往失败教训：」，紧随「相关笔记」。
4. **闭包注入**：`DefaultLoop(failure_lessons_consult=…)`（入参为本轮会话标识；镜像
   `pinned_notes_consult` 的降级留痕口径）。**只注主 loop**（子 / 神兽 / 宠物不接）。
5. **事实面条件化**：`runtime.py` 的 `exclude_fact_tags` 在块启用时**追加** `failure`
   （专块承载 ⇒ 退出事实面，同 `0185`/`0186` 口径）。
6. **配置键** `loop.failure_lessons`（bool，**缺省 `False`**，`ADVANCED`，结构化段 ⇒ `_loop_errors` 校验）。

**缺省关 ＋ 逐字不变**：键缺省 False ⇒ 组合根不注入钩子、`exclude_fact_tags` 逐字为既有
`frozenset({"steps"})`、`LoopContext.failure_lessons` 恒空 ⇒ 提示词与事实面**逐字不变**。

## Impact

- **代码**（`src/`）：`memory/store.py`（新 `failure_lessons`）、`loop/protocol.py`（新字段）、
  `loop/planner.py`（新块）、`loop/default.py`（新参 + 新 loader + `astream` 调用）、
  `configuration/manager.py`（新 ConfigSpec + 访问器 + `_loop_errors`）、`runtime.py`（闭包 + 接线 + 条件化）。
- **规格**：`memory` **MODIFIED**「情景链」（首段「两件事」→「三件事」、（e）**条件化**、新 **(h)** 只读读面，
  **既有 7 Scenario 逐字保留** ＋ ADD Scenario ×3）；`loop` **MODIFIED**「执行循环」（块句 ＋ ADD Scenario ×2，
  **既有 41 Scenario 逐字保留**）。
- **测试**：+16（`tests/test_failure_lessons.py`），基线 2441 → **2457**。
- **不做**：不改失败条目的**写入**口径（`0179` 逐字不动）；不把教训做成**因果**推断（机制是时序倒序取用）；
  不给子 / 神兽 / 宠物 loop 接该钩子；不登记新配置以外的任何键。
