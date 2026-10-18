## ADDED Requirements

### Requirement: 续跑批次单实例互斥

系统 SHALL 在扫描未完成编排任务**之前**获取以 `$CORE_STATE_DIR` 为作用域的非阻塞独占锁，
并使锁覆盖整个续跑批次（扫描、逐任务执行与自动续跑状态读写的全过程）。锁 SHALL 使用平台
原生建议锁（POSIX `flock` / Windows `msvcrt.locking`）；锁文件 SHALL 为
`$CORE_STATE_DIR/.auto-resume.json.lock`，SHALL 以 `0600` 创建（平台不支持时为尽力而为），
且 SHALL NOT 在释放时删除。

同一 `$CORE_STATE_DIR` 下已有进程持有该锁时，新的续跑批次 SHALL 立即跳过：SHALL NOT
扫描检查点、SHALL NOT 执行任何任务、SHALL NOT 写自动续跑状态。`core-agent task --resume-all`
SHALL 向 stderr 输出可检索前缀 `[resume_skipped]` 并以退出码 0 结束。
`orchestration.auto_resume=true` 时，锁被占用 SHALL NOT 阻止新任务：自动续跑 SHALL 被跳过，
`task <目标>` SHALL 照常执行新目标。

进程终止（含崩溃）后 SHALL 不再持有该锁（由操作系统释放）；锁文件残留 SHALL NOT 阻止
后续批次。创建锁文件或取锁失败时系统 SHALL fail-closed（跳过续跑），SHALL NOT 降级为
无锁续跑；此时 `task --resume-all` SHALL 输出 `[resume_skipped]` 并以非零退出码结束，
`orchestration.auto_resume=true` 的 `task <目标>` SHALL 仅跳过续跑并照常执行新目标。

不同 `$CORE_STATE_DIR` 的批次 SHALL 互不影响。该锁 SHALL 只串行化**续跑批次**；
`task <目标>`（未开启自动续跑时）、`task --resume <id>`、REPL、后台与 `serve` 路径
SHALL NOT 受其约束，且系统 SHALL NOT 声称检查点文件因此获得跨进程单写者一致性。

#### Scenario: 重叠续跑被跳过且退出码为 0

- **GIVEN** 另一进程持有 `.auto-resume.json.lock`
- **WHEN** 执行 `core-agent task --resume-all`
- **THEN** 不扫描检查点、不执行任务、不写自动续跑状态
- **AND THEN** stderr SHALL 含 `[resume_skipped]`，退出码 SHALL 为 0

#### Scenario: 锁覆盖任务执行阶段

- **GIVEN** 一个续跑批次已取锁并正在执行某个任务
- **WHEN** 同一状态目录下启动第二个 `task --resume-all`
- **THEN** 第二个实例 SHALL 立即跳过，SHALL NOT 执行任何任务
- **AND THEN** 第一个批次 SHALL 继续持有锁直到批次结束

#### Scenario: 锁释放后可继续续跑

- **GIVEN** 上一次批次已结束，或持有锁的进程已终止（含崩溃）
- **WHEN** 执行下一次 `core-agent task --resume-all`
- **THEN** SHALL 获得锁并正常扫描、续跑
- **AND THEN** 残留的锁文件 SHALL NOT 阻止执行

#### Scenario: 自动续跑锁忙不阻塞新任务

- **GIVEN** `orchestration.auto_resume=true` 且另一进程持有续跑批次锁
- **WHEN** 执行 `core-agent task <新目标>`
- **THEN** 自动续跑 SHALL 被跳过并输出 `[resume_skipped]`
- **AND THEN** 新目标 SHALL 照常执行，退出码 SHALL 为 0

#### Scenario: 锁作用域与权限

- **GIVEN** 两个不同的 `$CORE_STATE_DIR`
- **WHEN** 两个进程各自执行续跑批次
- **THEN** 两者 SHALL 互不阻塞
- **AND THEN** 同一状态目录下的锁文件 SHALL 为 `.auto-resume.json.lock` 且模式为 `0600`

#### Scenario: 取锁失败 fail-closed

- **GIVEN** 状态目录不可创建或锁文件不可打开
- **WHEN** 执行 `core-agent task --resume-all`
- **THEN** SHALL 跳过且不执行任何任务，stderr SHALL 含 `[resume_skipped]`
- **AND THEN** 退出码 SHALL 为非零，且 SHALL NOT 降级为无锁续跑
