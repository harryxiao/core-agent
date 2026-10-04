# 崩溃恢复端到端（真实 `kill -9` + 写入原子性，crash-recovery-e2e）

## Why

账本 **E12**：`phase-2.md:122` 要求「崩溃恢复测试：**`kill -9` 后重启，`resume()` 恢复且
无重复副作用**」。现有覆盖只有**内存 store 模拟**的幂等单测
（`tests/test_durability.py:67 test_resume_idempotent` 等）——真实崩溃语义
（半写文件、进程死亡后重载、游标续跑）**从未被验证**。

一手核实（读 `src/core/durability/store.py`）后确认这不只是「缺用例」，还有**真实缺陷**：

- `CheckpointStore._persist`（`:77-91`）用 `Path.write_text` 写 `checkpoints.jsonl` ——
  **先截断、再整写全量**。进程在截断之后、写满之前被终止 → 文件**空**或**半写** →
  `_load`（跳过无法解码的行）后既有检查点**整体丢失**。
- 这直接违反规格 durability「崩溃恢复」正文「**已持久化结果不丢失**」与场景
  「崩溃后自动恢复：已完成步骤的结果不丢失」——即**实现偏离规格**。
- 生产已接线（`runtime.py:563` `CheckpointStore(_checkpoint_path())` → `checkpoints.jsonl`），
  非死代码。

## What Changes

- **规格**：durability「崩溃恢复」MODIFIED —— 正文明确写入须**原子提交**（半写不得损坏既有
  检查点集合），新增场景「持久化写入原子性」「真实进程崩溃后续跑」。
- **实现**：`CheckpointStore._persist` 改为**原子提交** —— 写同目录临时文件 + `os.replace`
  替换（`os.replace` 同文件系统内原子；stdlib，零新依赖）。成功路径行为不变
  （文件内容、格式、`checkpoints.jsonl` 路径均不变）。
- **测试**：新增 `tests/test_durability_crash.py`：
  - **真实子进程** `SIGKILL` 端到端（`sys.executable -c` 子进程建检查点 → 自杀 → 父进程重载
    存储 → `restore()` 取最近有效检查点 → `resume()` 按游标幂等续跑，副作用不重复）；
  - **写入中断（半写）不损坏**：模拟「写入中途进程被终止」（写入抛错且已截断目标）→ 重载后
    既有检查点集合**完好**（旧实现必红，新实现必绿）。

## 影响面与风险

- **仅** `src/core/durability/store.py` 一个文件的行为变更，且是**收敛**（旧的半写损坏窗口消失）。
- `_persist` 全量重写 + `os.replace` 的语义不变：读者永远看到「上一版完整文件或新版完整文件」。
- 临时文件在成功后即被替换；崩溃留下的残留 `.tmp` 不会被 `_load` 读取（只读 `path`）。
- 子进程用例用 `sys.executable -c` + 显式 `PYTHONPATH=src`（对齐 `tests/test_phase16.py:190`
  等既有真进程用例），无三方依赖。

## 明确不做

- **不改 `resume` 的幂等口径**：跨进程「不重复副作用」由**调用方游标**（检查点快照状态）
  达成，这是规格既定分工（`resume(handle, replay)` 只保证同句柄一次）；本变更把它**验证**
  出来，不改变归属。
- **不改其他持久化点**（memory / skills 状态 / pending 队列等）：各自独立评估，不顺手扩面。
- **不做 fsync/掉电语义**：`os.replace` 保证的是**进程崩溃**原子性（E12 场景）；掉电（fsync）
  另属可靠性议题。
