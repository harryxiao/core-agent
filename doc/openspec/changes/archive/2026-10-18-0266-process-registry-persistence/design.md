# Design 0266 — 后台进程跨重启登记

## D1 持久化格式与落盘时机

`$CORE_STATE_DIR/processes.json`（缺省 `~/.core/state/processes.json`），版本化：

```json
{"version": 1, "jobs": [
  {"pid": 1234, "output_path": "/…/run/python-….log", "started_at": 1760000000.1,
   "run_type": "python", "start_ticks": 987654}
]}
```

- **只存元数据**：`ManagedJob` 的可持久化字段；不含命令 / 脚本 / 环境变量（与「不记录脚本正文」
  的既有约束一致）。
- **落盘时机**：`ProcessRegistry.add`（淘汰后、插入后）整体重写；不做增量与删除日志。
- **原子替换**：同目录写临时文件（`O_CREAT|O_EXCL`、0600）→ `flush` + `fsync` →
  `os.replace`；失败清理临时文件。并发双写者未定义（生产只有一个注册表实例）。
- **失败降级**：写失败吞掉（`contextlib.suppress(OSError)`）——后台任务必须照常返回 pid，
  登记持久化是观测辅助。

## D2 恢复项与存活判定

`ManagedJob` 增两字段：`proc: Any | None`、`start_ticks: int | None`。

```python
def is_running(self) -> bool:
    if self.proc is not None:
        return self.proc.poll() is None
    if not _pid_alive(self.pid):
        return False
    return _identity_ok(self.pid, self.start_ticks)
```

- `_pid_alive(pid)`：`os.kill(pid, 0)`；`ProcessLookupError` ⇒ 死；`PermissionError` ⇒ 活
  （存在但无权限）；其它 `OSError` ⇒ 按死处理。
- `_start_ticks(pid)`：Linux 读 `/proc/<pid>/stat`，在最后一个 `)` 之后按空白切分，取
  starttime（字段 22 ⇒ 切分后索引 19）；其它平台返回 `None`。
- `_identity_ok`：`start_ticks is None`（非 Linux 或读取失败）⇒ 只凭存活判定；
  否则当前 starttime SHALL 等于登记值，不等即 PID 复用 ⇒ 视为已退出。
- `info()`：恢复项 `returncode=None`、`restored=True`、`running` 按上；本进程任务
  `restored=False`、`returncode=proc.poll()`，逐字保留既有键（新增 `restored` 为附加键）。
- `_prune_locked` 改用 `is_running()`，恢复项死亡 / 身份不符同样被淘汰（下次 `add` 时）。

## D3 加载与上界

- 构造时读取；文件缺失 / 非 JSON / 结构不符 ⇒ 空注册表（静默）。
- 逐条校验：`pid` 正整数、`output_path` / `run_type` 字符串、`started_at` 有限数、
  `start_ticks` 整数或缺失；不合法条目跳过。
- 超过 `max_jobs` 时按 `started_at` 保留最新 `max_jobs` 条（注册表上界对恢复项同样成立）。
- 同 pid 重复登记后者覆盖（dict 语义）。

## D4 恢复项不终止

进程树终止依赖 `Popen` 句柄（`killpg(pid)` / `taskkill /T /F` 的 pid 参数）。重启后没有句柄，
且非 Linux 无身份核对 ⇒ 恢复项一律拒绝终止：

```python
if job.proc is None:
    return {"pid": pid, "found": True, "killed": False, "restored": True}
```

- 仍经确认门（工具本身 `reversible=False`），但批准后也不会触达进程 —— 结果是结构化的
  `killed=false`，不是错误。
- 处置替代路径：用户按 `output_path` / pid 自行处置；注册表不提供任意 pid kill。
