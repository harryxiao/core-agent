# Tasks — pet-runtime-wiring

## 1. 规格先行
- [x] 1.1 pet-mode delta（MODIFIED Multi-Pet Management[跨进程落盘] + ADDED Pet Session Runtime Wiring）
- [x] 1.2 `openspec validate 0053-pet-runtime-wiring` 全绿

## 2. 测试先行（先红）
- [x] 2.1 `PetSession.snapshot()`/`restore()` 往返：id/状态/任务/偏好/唤醒计数保真
- [x] 2.2 `PetManager(path=)` 落盘：注册后新 manager 加载可见；stop 后落盘同步
- [x] 2.3 `PetActivator` 注入依赖：激活的会话持有注入的 loop/memory（identity）
- [x] 2.4 生产装配：`build_runtime` 后 `runtime.pet_activator` 激活的会话 `loop is runtime.loop`、`memory is runtime.memory`
- [x] 2.5 生产装配：偏好经生产激活的宠物落 runtime 共享 L2（`runtime.memory`）
- [x] 2.6 `UIAPILayer.activate_pet` 返回会话 id 且会话进 `PetManager`
- [x] 2.7 回归：`tests/test_pet_core.py` 既有三入口 / 多宠物隔离用例不变

## 3. 实现
- [x] 3.1 `pet/core/session.py`：`snapshot()` + `restore(record, **deps)`
- [x] 3.2 `pet/core/manager.py`：`path`/`factory` + `_load`/`_persist`（注册/启停后落盘）
- [x] 3.3 `pet/core/activator.py`：可选依赖注入 → `_activate` 透传
- [x] 3.4 `runtime.py`：组装 pet 依赖 + `_pet_state_path` + `Runtime` 两字段
- [x] 3.5 `entry.py`：`_pet` 改用 runtime；`_build_ui` 注入 `pet_activator`
- [x] 3.6 `ui/api.py`：`pet_activator` 注入 + `activate_pet(user_input)`

## 4. 文档同步
- [x] 4.1 `doc/03-interfaces/pet-mode-interface.md`（注入面 + 快照/恢复 + 注册表落盘 + 三入口装配）
- [x] 4.2 `doc/02-modules/pet.md`（组合根接线）
- [x] 4.3 `doc/01-architecture/adr.md` ADR-0056 + 文末映射表行

## 5. 门禁与归档
- [x] 5.1 四门全绿：ruff check/format · pyright · pytest · openspec validate
- [x] 5.2 手动归档（合 delta → mv 到 `archive/<date>-0053-pet-runtime-wiring/`）
- [x] 5.3 `openspec validate --all` 全绿
- [x] 5.4 账本：E4 关闭 + 后续行（IM 通知 flush / daemon 调度）
- [x] 5.5 提交（`feat(pet): 宠物子系统纳入组合根（运行时注入 + 注册表落盘，change 0053）`）
