# Tasks 0283 — 后台登记跨进程归属与写锁

> 验证目标：落盘带 `owner_pid` / `owner_start`；存活 owner 的 `running` 条目跨进程加载后
> 保持 `running`（不误标中断、不可重入队）；死 owner / 旧格式仍映射 `interrupted`；
> 并发写经短锁 + 读-合并-写，不丢其他进程的登记、不回滚其更新。

## 1. 规格与测试先行

- [x] 1.1 spec delta：`orchestration` MODIFIED（复制全部旧场景，修订 running 映射，新增
      存活 owner / 并发写 / pid 复用场景）。
- [x] 1.2 新 `tests/test_background_ownership.py`（归属字段 / 存活判定 / 旧格式 / 复用 /
      合并写 / 锁文件）；改 `tests/test_background_persistence.py` 的重启用例为死 pid。

## 2. 归属字段与加载

- [x] 2.1 `BackgroundTaskInfo.owner_pid / owner_start`；`_info_record` 落盘；`info()` 不暴露。
- [x] 2.2 `_pid_alive`（POSIX `os.kill(pid,0)`；Windows ctypes）与 `_owner_alive`（pid +
      启动标识）；`_process_start_token`（Linux `/proc/<pid>/stat`）。
- [x] 2.3 `_restore_info`：owner 存活 ⇒ 保持 running；缺失 / 死 / 标识不符 ⇒ interrupted。

## 3. 写入合并与锁

- [x] 3.1 `_dirty` 集合（spawn / 终态 / 加载判中断）。
- [x] 3.2 短独占锁上下文（flock / msvcrt；0600；取锁失败降级）。
- [x] 3.3 `_save`：锁内读盘 → dirty 覆盖 → 有界 → 原子替换；非 dirty 保留磁盘版本。

## 4. 验证

- [x] 4.1 四门禁（ruff check / ruff format --check / pyright / pytest）。
- [x] 4.2 反证 3/3（摘存活判定 / 改整体覆盖 / 摘 dirty ⇒ 各红；复原 `md5sum` 同）。
- [x] 4.3 `openspec validate --all` 全绿后归档。

## 5. 文档与登记

- [x] 5.1 ADR-0273；台账 E219；`doc/04-testing/test-cases.md` §195。
- [x] 5.2 `doc/02-modules/orchestration.md`、`doc/03-interfaces/orchestration-interface.md`。
- [x] 5.3 单次提交 `feat(orchestration): ...` + Co-Authored-By。
