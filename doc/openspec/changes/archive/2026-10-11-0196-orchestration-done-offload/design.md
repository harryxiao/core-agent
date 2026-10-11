# Design 0196 — 任务完成回调卸载

## 1. 问题定位（P3）

| 面 | 事实 | 缺口 |
|---|---|---|
| `scheduler.py:290-292` | `DONE` 后**同步**调 `self._on_done(...)`（在 `astream` 协程内） | 回调落在**事件循环线程**上；一旦回调含模型调用即复现 E103 / ADR-0157 缺陷类 |
| `loop/default.py:466-468` | 每轮观察回调已 `await asyncio.to_thread(...)`（change 0167） | 同一纪律**未**补到编排收尾回路 |
| `orchestration/spec.md`「异步执行单元契约」 | 只覆盖**执行单元**（子任务）的异步接口 | 未覆盖**收尾回调**的非阻塞约束 |

## 2. 设计决策

### 2.1 一处调用点改为 `asyncio.to_thread`（最小外科手术）

```python
# 变更前
if self._on_done is not None:
    self._on_done(task_id, outcomes, plan, session_id)
# 变更后
if self._on_done is not None:
    await asyncio.to_thread(self._on_done, task_id, outcomes, plan, session_id)
```

＋ 文件头 `import asyncio`。**只**改这一处；`_checkpoint`（`:261-262`）**不动**。

### 2.2 为什么是 `_on_done` 而非 `_checkpoint`

风险对象是「**事件循环上的同步模型调用**」。本批次（0197）只在**完成回调** `_on_done` 中接模型
调用（任务级 SOP 提炼）；`_checkpoint` 只做既有廉价文件 IO、不承载模型调用 ⇒ 卸载它属超范围
（P3 局部化：改一条、可归因一条）。

### 2.3 调用时机与次数逐字不变

`asyncio.to_thread` 只改**执行线程**，不改**调用点**（仍在 `DONE` 达成后一次）、不改**顺序**
（仍在 `task_finished` 事件之前、检查点写入之后）、不改**终态判定**与事件载荷。缺省无回调
（`on_done is None`）时行为**逐字不变**。

## 3. 规格落点

`orchestration`「异步执行单元契约」**MODIFIED**：原文段落 + 既有 3 Scenario **逐字保留**，新增
bullet「收尾回路不阻塞」+ Scenario「完成回调不阻塞事件循环」。

## 4. 验证

- 红测试（`tests/test_scheduler*.py`）：桩 `on_done` 记录执行线程 ident ⇒ 断言
  `!= threading.main_thread().ident`（确定性，红：变更前等于主线程 ident）；＋ 反证（临时回退该行转红）。
- 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`。
- `openspec validate 2026-10-11-0196-orchestration-done-offload` → 手工归档
  （断言 canonical 0 行丢失 / 0 Scenario 标题丢失）。

## 5. 已知局限（登记 `coding-plan/known-risk.md` §3）

- 本 change **只**卸载完成回调；同文件 `_checkpoint` 的同步文件 IO 仍在事件循环上（廉价、未接
  模型调用，登记为**可接受**）。
