# tasks — 宿主驱动的唤醒节拍（change 0083 / 账本 E28）

## 1. 规格中性
- [x] 1.1 `.openspec.yaml`：`schema` + `skip_specs: true`（pet-mode 规格无「宿主必须是哪个入口」条款，`0065` 已核实）
- [x] 1.2 `openspec validate 0083-pet-wake-driver` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_pet_driver.py`（新）：逐会话唤醒 / 预期态（`PetError`）跳过且不影响其余 / 意外失败隔离（R8）/ 节拍（注入 `sleep` 中断 ⇒ 恰好两轮）
- [x] 2.2 `tests/test_entry.py`：`pet run` 从跨进程注册表恢复会话并交给驱动（断言 interval + 「已驱动 N 只宠物」+ 退出码）
- [x] 2.3 红证：实现前 2.1 / 2.2 失败

## 3. 实现（绿）
- [x] 3.1 `src/core/pet/core/driver.py`（新）：`PetWakeDriver` + `WakeOutcome` + 三态常量
- [x] 3.2 `src/core/pet/core/__init__.py`：导出 `PetWakeDriver` / `WakeOutcome`
- [x] 3.3 `src/core/entry.py`：`pet run` 分支 + `_split_pet_interval` + usage 串补 `run` + 失败上报
- [x] 3.4 绿证：四门全绿（基线 968 + 新增）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/pet-mode-interface.md`：§5 驱动归属段订正（「只有 `ui serve`」→ `ui serve` 或 `pet run`）+ 表格补驱动行
- [x] 4.2 `doc/02-modules/pet.md`：§3.5 / §4 闭环驱动者（`pet run` 为宿主驱动面）
- [x] 4.3 `doc/01-architecture/adr.md`：ADR-0078 + 变更追踪行
- [x] 4.4 `doc/04-testing/test-cases.md`：TC-PET-05（宿主驱动节拍）
- [x] 4.5 `doc/07-mcp-server/` 无关；`doc/00-product/user-guide.md` 如列 pet 用法则补 `pet run`

## 5. 收口
- [x] 5.1 `coding-plan/phase-19.md`：§1 E28 行 → ✅ 已关闭（change 0083）；§9 第 9 项；§0 结论
- [x] 5.2 `coding-plan/README.md`：状态行同步
- [x] 5.3 手动归档（`shutil.move`，无 spec delta）+ `openspec validate --all` 全绿
- [x] 5.4 记忆更新 + 提交
