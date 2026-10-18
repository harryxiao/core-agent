# Tasks 0286 — 检查点运维入口

> 验证目标：`--forget` 只删目标任务（含 pinned）并清退避；未知任务非零退出；
> `--prune-checkpoints` 按上限/窗口只删未 pinned、批量落盘；锁忙 fail-closed；
> 既有命令行为逐字不变；四门禁与 `openspec validate --all` 全绿。

## 1. 规格与测试先行

- [x] 1.1 spec delta：orchestration ADDED「检查点运维入口」（6 场景）。
- [x] 1.2 `tests/test_checkpoint_maintenance.py`（新增）与 `tests/test_durability.py`（批量删除）先红。

## 2. 存储与保留

- [x] 2.1 `CheckpointStore.delete_many(ids)`：一次 `_persist`，返回实际删除数。
- [x] 2.2 `RetentionManager.prune(policy) -> int`：复用 max_count/time_window 语义，pinned 保护；
      `apply` 先调 `prune`，quota 分支保持原行为。

## 3. CLI 接线

- [x] 3.1 `_add_task_parser`：`--forget`、`--prune-checkpoints`、`--max-count`、`--older-than-s`。
- [x] 3.2 `_task` 入口互斥与参数校验（缺边界/非法值/组合冲突）。
- [x] 3.3 `_forget_task`：取锁 → 精确删除 → 清 `AutoResumeState` → 计数输出。
- [x] 3.4 `_prune_checkpoints`：取锁 → 保留清理 → 计数输出；锁忙/不可用 `[checkpoints_locked]` 退出 1。

## 4. 文档与台账

- [x] 4.1 ADR-0276（语义/锁/批量删除/被拒方案/局限）。
- [x] 4.2 known-risk E222 + §3 索引；test-cases §198。
- [x] 4.3 orchestration 模块/接口、durability 模块/接口、user-guide、unattended-ops（止血步骤改用 forget）。
- [x] 4.4 alignment §3.8 差距与证据索引；基线更新。

## 5. 验证与收尾

- [x] 5.1 四门禁（ruff check / ruff format --check / pyright / pytest；3196 passed）。
- [x] 5.2 反证 3/3（去锁 / forget 不按任务过滤 / prune 删 pinned；cp 复原 + md5sum）。
      e2e 临时状态目录：空目录 prune 退出 0、未知任务 forget 退出 1、种子 3 条后 forget
      只删目标任务（剩 `c`）。
- [x] 5.3 `openspec validate --all` 32/0（活动期），归档后 31/0。
- [x] 5.4 单次提交 `feat(orchestration): ...` + Co-Authored-By。
