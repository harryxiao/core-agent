# 设计：crash-recovery-e2e（E12）

## 1. 缺陷判定：为什么这算「实现偏离规格」而非「规格未要求」

规格 durability「崩溃恢复」正文写「**已持久化结果不丢失**」，场景一写「已完成步骤的结果不丢失」。
现实现的写入是 `write_text`（truncate → write）——**中断即整体丢失**，与上述承诺直接冲突。
按仓库纪律「实现偏离规格时，先改规格再改代码」：本变更**保留**规格承诺、**明确化**其要求
（原子提交），并改代码使其成立。

## 2. 原子提交的最小实现

```python
def _persist(self) -> None:
    if self._path is None:
        return
    lines = [...]
    tmp = self._path.with_name(self._path.name + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, self._path)   # 同文件系统内原子替换
```

- **为什么是 `os.replace` 而不是 `fsync` + `rename`**：`os.replace` 在 POSIX 上等价于
  `rename(2)`，对**进程崩溃**是原子的（读者要么看到旧文件、要么看到新文件）。E12 的场景是
  进程被 `SIGKILL`，不是掉电，故 `fsync` 不在本变更范围（proposal 已列为 Non-goal）。
- **临时文件名固定（非随机）**：同一 store 实例的写入由 `self._lock`（`RLock`）串行化，
  不会有两个写入者竞争同一 tmp；跨实例并发写同一路径不在当前契约内（与旧实现同）。
- **不做清理逻辑**：崩溃残留的 `.tmp` 会被下次写入覆盖；`_load` 只读 `path`，不受影响。

## 3. 「半写」如何被确定性地测出来

真实 `SIGKILL` 落在哪一微秒不可控，**不能**用它来测「恰好写一半」。故拆两条：

| 用例 | 手段 | 覆盖 |
|---|---|---|
| 写入中断不损坏 | 打桩「写入抛错且已截断目标」模拟半写（`Path.write_text` → 先清空再抛 `OSError`） | 原子性**性质**（失败于提交点之前，既有文件不受影响） |
| 真实进程崩溃续跑 | 子进程 `sys.executable -c`：建检查点 → 写副作用 → `os.kill(os.getpid(), SIGKILL)`；父进程重载 | 端到端：**真**信号杀进程后存储可读、最近检查点可恢复、续跑幂等 |

前者是**白盒性质测试**：它在旧实现上必红（目标被截断 → 检查点丢失），在新实现上必绿
（失败发生在 tmp 上，真文件未动）。测试 docstring 会说明「以截断模拟半写」这一约定，不假装
它是一次真实崩溃。

## 4. 子进程用例的构成

```
父：tmp 路径 → 起子进程（PYTHONPATH=src）→ 子：
      CheckpointStore(path) → 建 cp1（含游标 state）→ 追加一行"副作用"到 effects 文件
      → 再建 cp2（游标前进）→ os.kill(getpid(), SIGKILL)
父：waitpid → 断言 returncode == -SIGKILL（真被杀，非正常退出）
    → 新 CheckpointStore(path)：cp1/cp2 **均在**（持久化跨进程可见，无丢失）
    → CrashRecovery.restore(task) → 最近有效检查点 = cp2
    → resume(handle, replay=按游标续跑的函数) → effects 文件**仍只有 1 行**（不重复副作用）
    → 再次 resume(同 handle) → 仍 1 行（同句柄幂等）
```

**关键**：`replay` 函数以 **cp2 快照里的游标**为准判断是否已应用，这正是规格
「未完成步骤幂等续跑」的分工（跨进程幂等由调用方游标保证）——用例把这条分工**验证**出来，
而不是发明新语义。

## 5. 回归面

- `tests/test_durability.py` 既有 20 例（内存 + 落盘 store）应**全绿不变**：成功路径的写入
  内容与格式未变。
- 组合根接线（`runtime.py:563`）不受影响（构造签名未变）。
- 无新增依赖；`os` 已在 `store.py` 之外的模块中普遍使用（本文件新增 `import os`）。
