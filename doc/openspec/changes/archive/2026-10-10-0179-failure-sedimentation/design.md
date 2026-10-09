# Design: 失败经验的独立沉淀面（change `0179` / ADR-0170 / 台账 E116）

## D1 另立失败条目（loop 侧，`src/core/loop/default.py`）

`DefaultLoop.remember` 增**三个 keyword-only 参数**（缺省 ⇒ 逐字一致）：

```python
def remember(self, trace_id, trajectory, *, session_id="", steps=(),
             failed=False, reason="", task="") -> None:
```

`failed=True` 时，在既有两条之外**再立第三条**（既有两条**内容逐字不变**）：

```python
MemoryEntry(
    id=f"loop.failure.{trace_id}", layer="L2", kind="episodic",
    content=failure_digest(trajectory, steps, reason=reason, task=task),
    tags=["loop", "failure"],
    source=self._source, trace_id=trace_id, session_id=session_id,
)
```

`failure_digest(trajectory, steps, *, reason="", task="") -> str`（**新模块级纯函数**，与
`_trajectory_line` / `_action_steps` 同层同风格）：

1. 首行 `任务：{task}`（`task` 非空才加；有界 `_MAX_STEP_LINE`）
2. 次行 `失败：{reason}`（`reason` 空 ⇒ 恒定兜底文案 `_FAILURE_REASON_FALLBACK`）
3. 失败轮行＝`trajectory` 中 dict 项且 `not data.get("ok")` ⇒ **复用 `_trajectory_line`**
   （已渲染 `round N failed <error>`）
4. 失败步行＝`steps` 中**含** `_FAILURE_STEP_MARK`（`"错误："`，`_summarize_result` 的失败渲染）的行
5. 逐行 `redact_secrets`、整体 `"\n".join(...)[:_MAX_MEMORY_ENTRY]`（与 `loop.steps` 条目**同源纪律**）

**无失败 ⇒ 不写该条目**。既有守卫 `if not trajectory or self._memory is None: return` 保持不变，
第三条写入置于守卫之后。

> **任务原文入条目**是刻意的：否则条目无法回答「什么失败了」、检索也难命中。代价＝用户原话
> **首次进入 L2 记忆面**（此前只在转录与 notes 里；与二者同源，逐行脱敏）——记入局限④。

## D2 压实豁免（memory 侧，`src/core/memory/store.py`）

新增模块常量 + `_episodic_groups()`（`store.py:600-612`）内**一处**追加：

```python
_PRESERVE_TAGS = frozenset({"failure"})  # 压实材料不得吸收（change 0179 / ADR-0170）
...
        if _PRESERVE_TAGS.intersection(entry.tags):
            continue          # 追加在既有 kind/layer 过滤之后
```

效果：失败条目**永不进摘要/关键事实材料**、**永不被 `_commit_summary` 迁 L4**。
`forget()`（`store.py:457-476`）**不动** ⇒ 仍按自然衰减归档（**有界**）。

## D3 注入面：**零改动**

不加 planner 块、不加上下文预算记账、不动 `_system_prompt` 次序 —— 失败条目靠既有按相关度检索命中。

## D4 接线（`src/core/loop/default.py:445-450`）

```python
self.remember(
    trace_id, [*ctx.trajectory, {"reply": ctx.reply}],
    session_id=session_id, steps=_action_steps(ctx),
    failed=bool(limit_reason) or turn_failed, reason=limit_reason, task=_task_text(ctx),
)
```

`limit_reason` / `turn_failed` / `_task_text(ctx)` 在该点**均已在作用域内**。同步 `Protocol`
（`src/core/loop/protocol.py:170-181`）。

## D5 契约不变量（must-hold，逐条对应测试）

| # | 条件 | 必须成立 |
|---|---|---|
| I1 | 成功轮 | **不写** `loop.failure.*`；既有两条条目逐字不变 |
| I2 | `failed=True` 且 `task=""` / `reason=""` | 仍写一条（首行恒非空）；有界 |
| I3 | 未注入 `memory` | 无写入、无异常（既有守卫） |
| I4 | 失败条目写入 | 必过 `redact_secrets`（逐行）；密钥只引用不读取 |
| I5 | 失败条目 | **可逆**（`write`→`_persist`→`_tracker.record`，按 trace 回滚即消失） |
| I6 | 压实 | 摘要条目 `tags` **不含** failure 条目 id；failure 条目 `layer` 仍 `L2`；同批普通条目照常迁 L4 |
| I7 | 遗忘 | failure 条目**不豁免**（老 `ts` ⇒ 仍迁 L4） |
| I8 | 检索 | failure 条目可被 `read()` 命中 |
| I9 | `beast.*` / `pet` 命名空间 | 沿用 `source=self._source` ⇒ 既有封存语义与 `("beast.","pet")` 排除项**逐字不动** |

## D6 配置面

**模块常量**，不新增配置键（同 `_ROUND_THRESHOLD` / `_IMPORTANCE_FLOOR` 纪律）。

## 已知局限（写进 ADR-0170 + `coding-plan/known-risk.md` §3）

① 只覆盖**轮级失败**；轮内自愈的工具失败不入失败条目（仍在 `loop.steps` 条目里）——按用户裁决。
② **记忆面 → 诊断面仍无桥**：`Diagnoser` 只吃 `Trace.success`，`src/core/evolution/` 对 memory 只写不读
   ⇒ 失败条目目前只服务**检索/上下文**，**不驱动进化**（本 change 外，另立账）。
③ 失败条目最终仍会被**遗忘**归档 L4（按用户裁决；`_FORGET_THRESHOLD=0.05`，衰减缓慢）。
④ 用户**任务原文首次进入 L2 记忆面**（为让条目自解释）；与转录 / notes 同源，逐行脱敏。
⑤ 若注入 `importance_scorer`（生产缺省 UNWIRED，见 `runtime.py:384-393`），失败条目仍受写入侧闸门约束
   （可能降层/拒收）；本 change **不豁免**（不触碰 0177 的闸门语义）。
⑥ 失败条目**不进摘要** ⇒ 会话整体摘要不含失败内容；失败信息仍可经**同轮的轨迹条目**进入摘要
   （有意：摘要不该被失败噪音主导）。
⑦ 跨会话「同类失败」仍只能靠语义相似命中（`loop.failure.<trace_id>` 按 session 隔离读取）。
