# Design 0283 — 后台登记跨进程归属与写锁

## D1 归属字段与存活判定

每条登记的持久化字段增加 `owner_pid`（int）与 `owner_start`（str）：

- `owner_pid` = 启动该后台任务的进程 pid（`os.getpid()`）。
- `owner_start` = 该进程的启动标识。Linux 取 `/proc/<pid>/stat` 最后一个 `)` 之后的
  第 20 个字段（整体第 22 字段 `starttime`，单位 clock tick）；其他 POSIX / Windows
  取不到时为 `""`（此时只按 pid 判存活，pid 复用风险作为局限记录）。

```
_owner_alive(pid, start):
    pid <= 0                              -> False
    not _pid_alive(pid)                   -> False
    start and current_start and start != current_start -> False   # pid 复用
    else                                  -> True
```

`_pid_alive`：POSIX 用 `os.kill(pid, 0)`（`ProcessLookupError` ⇒ 死，`PermissionError` ⇒
存活）；Windows 用 `ctypes` 的 `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` +
`GetExitCodeProcess == STILL_ACTIVE`（**不能**在 Windows 上调用 `os.kill(pid, 0)` —— 它等价于
终止进程）。

## D2 加载映射

`_restore_info` 对 `status=running` 的记录：

| 情形 | 结果 |
|---|---|
| `owner_pid` 缺失 / 非正（旧格式或手工文件） | `interrupted`（既有语义） |
| owner pid 已退出 | `interrupted` |
| owner pid 存活但 `owner_start` 不一致 | `interrupted`（pid 复用） |
| owner 存活且标识一致 | 保持 `running`，`finished_at=None`、`error=""` |

保持 `running` 的条目在本进程没有 `asyncio.Task` 句柄：`cancel()` 返回 `False`，
`wait()` 只返回快照，`tools.task_retry` 按既有规则拒绝 —— **只观察、不接管**。
该条目计入 `running_count()`（共享容量，避免多进程合计无界）。

同一进程构造第二个注册表时 owner 判定同样为「存活」⇒ 保持 `running`（真实反映在途任务）。
「重启」测试须用**已退出进程的 pid** 或旧格式记录模拟，不能再用同进程双实例。

## D3 写入：短锁 + 读-合并-写

维护 `_dirty: set[str]`：`spawn` 新增、`_mark_terminal` 更新、加载时被判中断的条目
（需要把修正落盘）加入；成功写盘后清空。

`_save()`：

1. 获取 `.{name}.lock` 独占锁（`fcntl.flock(LOCK_EX)` / `msvcrt.locking(LK_LOCK, 1)`），
   文件 0600；取锁失败（OSError）⇒ 不打锁直接继续（降级，不阻断任务）。
2. 在锁内读取磁盘文件（缺失 / 损坏 ⇒ 空，不重复告警），解析为 `task_id → record`。
3. 用内存中 **dirty** 条目的记录覆盖磁盘视图；**非 dirty** 条目保留磁盘版本
   （因此其他进程在我们加载后写入的新状态不会被本进程的陈旧快照回滚）。
4. 新条目数超过 `max_records` 时按 `started_at` 保留最新；同目录临时文件 + fsync +
   `os.replace` 原子替换。
5. 释放锁。

为什么不是「内存整体覆盖」：进程 B 加载时看到的 A 任务状态可能已过时（例如 A 刚把它标为
done），整体覆盖会把 A 的终态回滚成 B 快照里的 running。dirty-only 合并让每个进程只对
**自己改过**的条目负责。

## D4 字段暴露

`owner_pid` / `owner_start` 只入状态文件；`BackgroundTaskInfo.info()`（模型可见）不含它们。
读侧对 `owner_pid` / `owner_start` 做类型校验，非法记录整条跳过（与既有一致）。

## D5 兼容与缺省

- `state_path=None`：纯内存路径零变化（不落盘、不加锁、无 liveness 调用）。
- 旧格式（无 owner 字段）的 `running` 记录照旧映射 `interrupted`，保证升级前的在途任务
  不会永远 `running`。
- 不新增配置项；锁文件与登记文件同目录、0600，残留锁文件不影响后续获取。

## 反证（实施后执行）

1. 摘掉 `_owner_alive` 判定（running 一律映射 interrupted）⇒ 存活 owner 用例红。
2. `_save` 改回整体覆盖（不做磁盘合并）⇒ 并发写不丢登记 / 不回滚磁盘新状态用例红。
3. 摘掉 dirty 标记（全部条目都覆盖）⇒ 陈旧 running 回滚磁盘 done 用例红。

每项复原后 `md5sum` 与改动前一致。

## 局限

- 存活 owner 的条目只观察不接管；owner 在本进程加载**之后**死亡，需下次加载才会变成
  `interrupted`。
- `msvcrt.locking` 的重试上限固定（约 10 次 × 1s），极端争用时可能降级为直写。
- 网络文件系统（NFS/SMB）的 `flock` / `locking` 语义不保证。
- `owner_start` 在非 Linux 平台缺失，只能按 pid 判存活，存在 pid 复用误判的残余风险。
- 登记仍最多 64 条（写侧合并后按 `started_at` 保留最新）：高并发进程各自大量任务时，较早的
  条目会被任一进程的写盘淘汰。
