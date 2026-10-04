# 任务：pet-host-driven-wakeup（E17）

## 1. 判定（先行）

- [x] 1.1 逐字核对 `specs/pet-mode/spec.md`：无 daemon / 调度线程条款（Lifecycle「每次唤醒…逐次执行」、
      Yielding「同步 + 锁（RLock）」）
- [x] 1.2 核对实现无违反：`wake()` 同步薄壳、`suspend()`/`busy()` 让行
- [x] 1.3 核对宿主形态：`entry._pet` 为一次性进程（激活后退出）⇒ 进程内 daemon 无宿主
- [x] 1.4 用户裁决：**规格中性收口**（登记已知语义，不实现 daemon）→ `skip_specs: true`

## 2. 文档登记

- [x] 2.1 `doc/03-interfaces/pet-mode-interface.md` §5：新增「驱动归属」块（宿主驱动 / 不常驻 / 三条理由）
- [x] 2.2 `doc/02-modules/pet.md` §3.2 + §4：同口径登记（免两处漂移）

## 3. 实现 / 测试

- [x] 3.1 **无**（`src/` 与 `tests/` 零改动；`wake()` 既有单测已覆盖同步薄壳与让行语义）

## 4. 验证与收尾

- [x] 4.1 四门全绿（ruff / format / pyright / pytest —— 无代码改动，应为基线不变）
- [x] 4.2 `openspec validate 0065-pet-host-driven-wakeup` → 手动归档 → `openspec validate --all`
- [x] 4.3 账本 E17 行关闭 + §3（E4 段内 E17 子条目 + 新增 E17 已关闭段）+ §9 步骤 9
- [x] 4.4 `coding-plan/README.md` 同步
- [x] 4.5 提交 `docs(pet): 唤醒由宿主驱动登记（规格未要求 daemon，change 0065）`
