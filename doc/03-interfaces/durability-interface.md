# 接口设计：持久性（Durability Interface）

> 模块：`02-modules/durability.md` ｜ 规格：`openspec/specs/durability/spec.md`

---

## 1. 实体模型

```python
@dataclass
class Checkpoint:
    """检查点：执行态某时刻的可寻址快照入口。"""
    checkpoint_id: str              # 检查点唯一标识
    ts: float                       # 创建时间戳
    task_id: str                    # 任务归属
    session_id: str                 # 会话归属
    parent_id: str | None           # 父检查点（None 表示根检查点）
    pinned: bool                    # 是否关键检查点（pinned，不受自动清理）

@dataclass
class Snapshot:
    """快照：检查点捕获的执行态（执行上下文/任务状态/中间结果/记忆/会话状态）。"""
    snapshot_id: str
    checkpoint_id: str              # 所属检查点
    state: dict                     # 执行态载荷
    diff: dict | None               # 相对父检查点的差异（None 表示全量快照）

@dataclass
class RestoreHandle:
    """恢复句柄：崩溃恢复后的幂等续跑游标。"""
    handle_id: str
    checkpoint_id: str              # 恢复源检查点
    resume_cursor: str              # 未完成步骤续跑定位
    degraded: bool                  # 是否降级（源检查点损坏回退更早检查点）
```

---

## 2. CheckpointManager 接口

```python
class CheckpointManager:
    def create_checkpoint(self, task_id: str, session_id: str, state: dict) -> Checkpoint:
        """显式创建检查点，捕获当前执行态为快照，返回唯一标识，任务继续执行不被阻塞。"""

    def list_checkpoints(self, *, checkpoint_id: str | None = None,
                         task_id: str | None = None, session_id: str | None = None,
                         ts_range: tuple[float, float] | None = None) -> list[Checkpoint]:
        """按标识或元数据（任务/会话/时间）查询检查点，含创建时间与父检查点关系。"""

    def get_snapshot(self, checkpoint_id: str) -> Snapshot:
        """按检查点标识取回执行态快照。"""
```

---

## 3. CrashRecovery 接口

```python
class CrashRecovery:
    def restore(self, task_id: str) -> RestoreHandle:
        """崩溃后从最近有效检查点恢复执行态，返回续跑句柄；源检查点损坏时回退更早检查点并记录告警。"""

    def resume(self, handle: RestoreHandle) -> None:
        """从恢复句柄续跑未完成步骤，幂等重放不重复产生副作用。"""
```

---

## 4. TimeTravel 接口

```python
class TimeTravel:
    def rollback(self, checkpoint_id: str) -> Snapshot:
        """执行态回滚到历史检查点，沿快照差异逆序撤销副作用（复用 tool-use EffectId undo 栈），返回回滚后快照。"""
```

**CLI 入口**：`core-agent time-travel <checkpoint-id>` —— 经 `build_runtime(...).time_travel` 取
**生产真源**（与 `task` / `run` 同一组合根、同一 `$CORE_STATE_DIR/checkpoints.jsonl`、同一共享
`EffectTracker`），撤销集取该点快照 `state["trace_ids"]`；检查点不存在 ⇒ `CHECKPOINT_NOT_FOUND`
转 stderr + 退出码 1（不伪造成功）。**已知局限**：`Effect` 的 `undo` 为进程内闭包、不可持久化
⇒ 一次性 CLI 进程内撤销循环为空转（快照恢复与失败语义仍生效）；撤销协同在**同进程**入口
（`serve` / REPL / 同一 runtime 内的 `task`）生效（change `0144` / 账本 E73 / ADR-0136）。

---

## 5. RetentionPolicy 接口

```python
@dataclass
class RetentionPolicy:
    """保留策略：数量上限/时间窗口/存储配额，清理策略为时间窗口或 LRU。"""
    max_count: int | None           # 数量上限
    time_window: timedelta | None   # 时间窗口
    storage_quota: int | None       # 存储配额
    strategy: str                   # "time_window" | "lru"

class RetentionManager:
    def apply(self, policy: RetentionPolicy) -> None:
        """按保留策略清理过期检查点并释放存储，保留窗口内检查点。"""

    def pin(self, checkpoint_id: str) -> None:
        """标记关键检查点（pinned），自动清理跳过。"""

    def unpin(self, checkpoint_id: str) -> None:
        """取消关键标记，恢复参与自动清理。"""
```

---

## 6. 错误码

| 错误码 | 含义 |
|---|---|
| `CHECKPOINT_NOT_FOUND` | 检查点不存在 |
| `CHECKPOINT_CORRUPT` | 检查点损坏（回退更早检查点恢复，记录告警） |
| `RESTORE_DEGRADED` | 恢复降级（未命中最近检查点，回退更早） |
| `RETENTION_QUOTA_EXCEEDED` | 存储配额超限（触发保留策略清理） |

---

## 7. 关联

- 模块：`02-modules/durability.md`
- 规格：`openspec/specs/durability/spec.md`
- 挂载：`02-modules/orchestration.md`（断点续跑）、`02-modules/tool-use.md`（时间旅行回滚，复用 EffectId undo 栈）
