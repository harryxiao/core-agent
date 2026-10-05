# tasks — pet 通知三环接线（change 0079 / 账本 E16）

## 1. 测试先行（红）
- [x] 1.1 `tests/test_pet_core.py`：`test_wake_notifies_owner_on_feedback_cycle`（周期命中 → notifier 收到 `report()` 文案，且含宠物名/状态）
- [x] 1.2 `tests/test_pet_core.py`：`test_wake_stays_silent_off_cycle`（未命中周期 → 不产出）
- [x] 1.3 `tests/test_pet_core.py`：`test_wake_without_notifier_is_silent`（兜底：无 notifier 不报错、行为不变）
- [x] 1.4 `tests/test_pet_wiring.py`：`test_production_pet_notification_reaches_sink`（组合根产出的会话持有的通知可调用体 → 调用即达 stderr sink）
- [x] 1.5 红证：实现前 1.1 / 1.4 失败（生产者零调用 / 无通道）

## 2. 实现（绿）
- [x] 2.1 `src/core/pet/core/session.py`：`wake()` 收尾 `_notify_owner()`；抽 `_on_feedback_cycle()` 并让 `report()` 复用
- [x] 2.2 `src/core/runtime.py`：`_pet_notification_sink`（stderr）+ 组合根把「入队 + flush」收成 `_pet_notify` 注入 `PetManager.factory` 与 `PetActivator`
- [x] 2.3 绿证：全量 pytest 通过（基线 955 + 新增）+ 四门全绿

## 3. 规格
- [x] 3.1 判**规格中性**（`skip_specs`）：`pet-mode/spec.md` 既有 Pet Notification / Safety Bounds / Runtime Wiring 条款已覆盖，同 change `0070`/`0078`
- [x] 3.2 `openspec validate 0079-pet-notification-wiring` 通过

## 4. 文档
- [x] 4.1 `doc/01-architecture/adr.md`：ADR-0076 + 变更追踪行
- [x] 4.2 `doc/03-interfaces/pet-mode-interface.md`：§1 依赖注入注记 + §5 表「反馈」行补投递点
- [x] 4.3 `doc/02-modules/pet.md`：通知环节接线描述（若列举）
- [x] 4.4 `doc/04-testing/test-cases.md`：TC-PET 通知投递用例

## 5. 收口
- [x] 5.1 `coding-plan/phase-19.md`：§1 表 E16 行 → 已关闭；§4 E16 段；新增转出项（安全越界通知 / surprise·microtask 零调用方 / IM 零装配 / 无宿主驱动 wake）；§0/§9 相应处
- [x] 5.2 `coding-plan/README.md`：状态行同步
- [x] 5.3 手动归档（`skip_specs` 无 delta ⇒ 仅移动目录）+ `openspec validate --all` 全绿（30/30）
- [x] 5.4 记忆更新 + 提交
