# Tasks 0279 — 后台子 Agent 跨重启登记与重入队

> 验证目标：登记文件 0600 原子写、最多 64 条、损坏容忍；重启后 `running` 记为
> `interrupted`；`tools.tasks` 可见；`tools.task_retry` 仅对 interrupted/failed/cancelled
> 生效并产生新 task_id；默认（`state_path=None`）纯内存行为逐字不变。

## 1. 规格与测试先行

- [x] 1.1 `specs/orchestration/spec.md`：ADDED「后台任务跨重启登记与重入队」。
- [x] 1.2 新 `tests/test_background_persistence.py`；`tests/test_phase13.py` 工具清单补项。

## 2. 实现

- [x] 2.1 `orchestration/background.py`：`state_path` 参数 + 加载/保存（0600 原子、有界、脱敏）。
- [x] 2.2 `orchestration/background.py`：`running → interrupted` 映射与 `task_retry_tool`。
- [x] 2.3 `runtime.py`：`_background_state_path()`、coeffect `task:write`、注册 `tools.task_retry`。

## 3. 验证

- [x] 3.1 四门禁（ruff / format / pyright / pytest）。
- [x] 3.2 反证：① 去掉 running→interrupted ⇒ 重启可见性红；② 去掉脱敏 ⇒ 密钥 canary 落盘红；
      ③ 去掉状态守卫 ⇒ done/running 可重入队红；复原 `md5sum` 同。
- [x] 3.3 `openspec validate --all` 全绿后归档。

## 4. 文档与登记

- [x] 4.1 ADR-0269（始终登记、重启映射、重入队权限、局限）。
- [x] 4.2 台账 E215；`doc/04-testing/test-cases.md` §191。
- [x] 4.3 `doc/02-modules/orchestration.md`、`doc/03-interfaces/orchestration-interface.md`。
- [x] 4.4 单次提交 `feat(orchestration): ...` + Co-Authored-By。
