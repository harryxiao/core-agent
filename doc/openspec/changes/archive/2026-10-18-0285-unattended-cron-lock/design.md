# Design 0285 — 续跑批次单实例锁与 cron 运维闭环

## 1. 决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | 只做跨进程单实例锁，不做队列/守护进程 | cron 的重叠是常态；排队会让进程堆积。跳过 + 下一次 tick 重试已足够 |
| D2 | 新增 fail-closed 的 `try_exclusive_file_lock`，不改既有 fail-open 的 `exclusive_file_lock` | 既有助手用于后台登记/工作树 sidecar，取不到锁时**无锁写**是刻意降级；互斥场景必须 fail-closed |
| D3 | 三态 `acquired / busy / unavailable`，不压成 bool | 忙（正常重叠）与锁不可用（权限/磁盘故障）运维含义不同：前者退出 0，后者显式入口退出 1 |
| D4 | 锁在 `pending_resumes()` **之前**获取，持有到批次结束 | 扫描、逐任务执行、`AutoResumeState` 读改写都是批次的一部分；只罩扫描仍会双跑 |
| D5 | 函数体拆为 `_run_auto_resume_locked` | 架构门禁统计 `with/if/for/try` 嵌套 ≤3；不拆会把既有深度 3 推到 4 |
| D6 | 锁文件 `$CORE_STATE_DIR/.auto-resume.json.lock`，释放时**不删除** | 与状态文件同目录；删除会让两个进程可能锁到不同 inode。崩溃后由内核释放，残留空文件不阻塞 |
| D7 | 锁范围只到续跑批次 | `CheckpointStore` 仍是共享 `.tmp` + 最后写者胜；fresh `task` / `--resume` / `serve` 不受锁约束，文档不得暗示全局多写者安全 |
| D8 | 运维止血靠文档，不新增删除 CLI | 用户裁决本 change 只做文档 + 锁；无 `task --forget` 的缺口记入 known-risk |

## 2. 状态机

```
_run_auto_resume
  └─ try_exclusive_file_lock($CORE_STATE_DIR/.auto-resume.json)
       ├─ unavailable → stderr [resume_skipped] 续跑锁不可用；返回 True（显式入口退出 1）
       ├─ busy        → stderr [resume_skipped] 另一个续跑实例正在运行；返回 False（退出 0）
       └─ acquired    → _run_auto_resume_locked(...)
                          ├─ pending_resumes() 扫描
                          ├─ AutoResumeState.retain
                          └─ 逐任务：due 判定 → record_attempt → 执行 → clear/保留
```

- 锁在 `with` 块内交给 locked body；**不得**先退出上下文再执行函数体。
- 自动模式（`orchestration.auto_resume=true`）返回值本就被丢弃：两种跳过都不阻止新任务。
- 锁文件打开失败（父目录不可建/不可写）一律 `unavailable`，**绝不**降级为无锁续跑。

## 3. 锁助手

```python
LockOutcome = Literal["acquired", "busy", "unavailable"]

@contextmanager
def try_exclusive_file_lock(path: Path) -> Generator[LockOutcome, None, None]:
    lock_path = path.with_name(f".{path.name}.lock")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        yield "unavailable"
        return
    locked = _try_lock_fd(fd)
    try:
        yield "acquired" if locked else "busy"
    finally:
        if locked:
            _unlock_fd(fd)
        os.close(fd)
```

- POSIX 用 `flock(LOCK_EX | LOCK_NB)`（不是 `lockf`）：同进程两次 `open` 是独立 open file
  description，测试无需子进程即可观察争用。
- Windows 取锁前 `lseek(fd, 0)`，锁/解锁恰好 1 字节（沿用 `_unlock_fd` 的既有做法）。
- 不删除锁文件；不写任何任务数据；fd 由 PEP 446 默认不可继承，批次内子进程不会继承锁。

## 4. 退出码与提示

| 结果 | stderr | `task --resume-all` 退出码 | 自动模式 |
|---|---|---|---|
| acquired + 无待续 | `无未完成任务（续跑扫描为空）` | 0 | 继续新任务 |
| acquired + 全部成功 | — | 0 | 继续新任务 |
| acquired + 有失败/超时 | 既有逐任务告警 | 1 | 继续新任务 |
| busy | `[resume_skipped] 另一个续跑实例正在运行` | 0 | 跳过续跑，继续新任务 |
| unavailable | `[resume_skipped] 续跑锁不可用（无法创建锁文件）` | 1 | 跳过续跑，继续新任务 |

提示前缀固定为 `[resume_skipped]`，便于 cron 日志检索；不打印锁路径、任务正文或密钥。

## 5. 被拒方案

- **阻塞等待/超时抢锁**：cron tick 会堆积；重叠本就可以留到下一次。
- **PID 文件 + 过期检测**：内核已保证进程退出释放，PID 复用反而引入误判。
- **只靠外部 `flock(1)` 包命令**：不覆盖自动模式路径；Windows 不可移植。
- **全局任务锁（fresh/`--resume`/`serve`）**：`serve` 与 REPL 是长驻进程，会长期占锁；
  真正解决需要状态存储多写者改造，超出本 change。
- **守护进程/队列**：生命周期、升级、日志与崩溃恢复成本高，P1 明确先做低成本形态。

## 6. 局限

- 建议锁：绕过入口直接改文件、或网络盘不保证互斥；手册限定单机本地盘。
- 挂死批次占锁到进程退出；无锁超时与诊断命令。
- 强制 `--resume-all` 每 tick 重试永久失败任务并重复通知。
- 锁只覆盖续跑批次；同一 `$CORE_STATE_DIR` 仍按单写者假设使用。
- Windows 未做手工端到端验证。
