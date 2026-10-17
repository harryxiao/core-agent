# Design 0257 — 并行工具调用、重复写抑制与原子写

## D1 动作组：`ActionGroup`

`Action` 是单工具协议，不改造它（避免 20+ 处测试桩与协议消费方漂移）。新增并列类型：

```python
@dataclass
class ActionGroup:
    actions: list[Action]   # 按 provider index 升序，≥ 1
```

- planner 单调用仍返回 `Action`（既有断言逐字不变）；多调用返回 `ActionGroup`。
- `_reason_events` 遇 `ActionGroup` **展开为多个 Action**；loop 收集本次推理产出的全部 Action。
- 批次内任一调用参数 JSON 非法 / 非对象 / 缺 `function.name` ⇒ 整个批次产出一个失败终止动作
  （`LLM_PLAN_PARSE_FAILED`），**零执行**。理由：部分执行会让模型看到的 tool 结果与它发出的
  调用数量不一致，且无法可靠对应 call id。

## D2 主循环：待执行队列

```python
pending: list[Action] = []
while not ctx.done():
    if pending:
        action = pending.pop(0)
    else:
        actions = [item for item in reason_stream if isinstance(item, Action)]
        action, pending = actions[0], actions[1:]
    ...既有单动作执行体（中间件 / 确认门 / act / 观测 / 事件 / 压实阈值）原样复用...
```

- 每个动作仍推进 `ctx.rounds`、`max_rounds` / 预算闸门逐动作生效（与「模型分多轮发起」等价）。
- 事件序：N 个动作 ⇒ N 组 `action_started` / `action_completed` / `step_completed`，无新事件类型。
- 单动作路径与既有路径逐字一致（`pending` 为空时才推理）。

## D3 重复抑制（两层，均只影响**完全相同的**动作）

1. **批内**：`_dedupe_batch(actions)` 按 `(tool_id, canonical(args))` 去重，保留首个；键用
   `json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)`。
2. **轮内紧邻**：写动作（`tools.file_write` 且模式非 `a`/`append`；`tools.file_patch`）与
   **上一条已执行动作**键相同且上次成功 ⇒ 跳过执行，复用上次 `ActionResult`。任何其他动作执行后
   重置「上一条」记忆 ⇒ 轮询 / 读取类重复不被误杀。

被抑制的调用：

- 仍产出 `action_started` / `action_completed`（`duration_ms=0`、`output` 取上次结果摘要）
  与 `step_completed`，载荷键集不变（不新增字段）；
- 仍 `_record_observation` 回灌（模型看到该调用已成功）；
- trace 增 `action_deduplicated`（`scope="batch"|"turn"`、`tool_id`、`round`；**不含**参数正文）。

## D4 `file_write` 原子覆盖

```python
if normalized == "w":
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(tmp := target.with_name(f".{target.name}.{uuid4().hex}.tmp"), flags, 0o666)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content); fh.flush(); os.fsync(fh.fileno())
        if target.exists():
            os.chmod(tmp, stat.S_IMODE(target.stat().st_mode))  # 保留既有权限位
        os.replace(tmp, target)
    except BaseException:
        os.unlink(tmp); raise
```

- `0o666` 经 umask 掩码 ⇒ **新建文件**权限与 `open()` 一致；既有文件复制其权限位。
- `fsync` 只保证内容落盘，不 fsync 目录（跨崩溃的目录项持久化不在本 change 范围）。
- 追加模式保持 `open("a")`；快照仍在**写入成功后**压栈，撤销语义不变。
- 临时文件名以 `.` 开头且带 uuid，`os.replace` 前不暴露给读者。

## 兼容性与回归面

- 单调用 / 文本回复 / 非流式 planner：动作集合长度为 1，事件与观测逐字不变。
- 工具 provider、权限 / 确认门、效应追踪、撤销：零改动（动作逐个进入既有执行体）。
- append 写、读工具、非写工具：重复抑制**不适用**（键判定排除），行为不变。

## 局限（登记）

1. **串行执行**：并行调用按 index 串行；总时长为各调用之和（可预测优先）。
2. **无依赖分析**：后一个调用看不到前一个调用的观测（同一批由模型一次性给出）——这是模型侧
   语义，批次执行不做中途重规划。
3. **紧邻抑制依赖「完全相同」**：参数键序不同但语义相同（如 `path` 写法不同）不抑制。
4. **原子性只覆盖 `file_write` 覆盖模式**；`file_patch` 仍为读-改-写（其写回可后续用同一原子
   助手，未在本 change 展开）。
5. **fsync 成本**：每次覆盖多一次磁盘同步；写小文件时相对开销上升。
