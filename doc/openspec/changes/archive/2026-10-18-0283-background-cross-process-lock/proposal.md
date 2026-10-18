# Proposal 0283 — 后台登记跨进程归属与写锁

## Why

change `0279` 的后台任务登记（`background-tasks.json`）假定**同一状态目录只有一个进程在用**：

- 加载时无条件把落盘的 `running` 映射为 `interrupted`（ADR-0269 局限①）—— 当另一个
  `core-agent` 进程仍持有该任务时，后启动的进程会把**仍在运行**的任务误标为中断，模型
  随即可能 `tools.task_retry` 重入队，造成同一任务双跑。
- 每次写都是**整体重写**文件 —— 两个进程并发写时后写者覆盖先写者，丢失对方的登记
  （任务凭空消失，`tools.tasks` 查不到）。

长任务无人值守场景下，CLI `task`、`serve`、TUI 可能共用 `CORE_STATE_DIR`，上述两条从
「已知局限」变成可复现的数据损坏。

## What Changes

1. **按条目记录 owner**：持久化新增 `owner_pid` / `owner_start`（进程启动标识，Linux 取
   `/proc/<pid>/stat` 第 22 字段，用于识别 pid 复用）。加载 `running` 条目时：
   - owner 存活（pid 存在且启动标识一致）⇒ **保持 `running`**，不映射、不取消、不重放通知；
   - owner 缺失（旧格式）、已退出或启动标识不符（pid 复用）⇒ 维持既有
     `running → interrupted` 映射。
2. **短独占建议锁 + 读-合并-写**：写盘前获取同目录 `.{name}.lock` 的独占锁（POSIX
   `fcntl.flock` / Windows `msvcrt.locking`），在锁内重新读取磁盘登记，只把**本实例变更过**
   的条目（dirty set）覆盖到磁盘视图，再整体原子替换；其他进程的条目与更新保持不变。
   取锁失败降级为直接写（尽力而为，与引入前一致）。

## Impact

- 受影响规格：`orchestration`「后台任务跨重启登记与重入队」（MODIFIED，复制全部旧场景，
  修订 running 映射并新增存活 owner / 并发写场景）。
- 代码：`src/core/orchestration/background.py`（`BackgroundTaskInfo` 字段、
  `_restore_info`、`_save` 合并、锁与进程探测）。
- 兼容性：缺省 `state_path=None` 纯内存路径不变；旧格式登记文件照常加载（按中断处理）；
  不新增配置项、不新增三方依赖。
- 文档：ADR-0273、known-risk E219、test-cases §195。

## 不做（边界）

- 不做跨进程任务**调度/抢占**（存活 owner 的任务只会被观察，不会被本进程接管或取消）。
- 不做锁超时后的强制抢锁（`flock` 阻塞等待，`msvcrt` 有界重试；取锁失败即降级直写）。
- 不做分布式一致性（同一主机文件系统语义；NFS 等网络文件系统的锁语义不保证）。
- 不改 `tools.task_retry` 的既有拒绝语义（`running` 仍结构化拒绝）。
