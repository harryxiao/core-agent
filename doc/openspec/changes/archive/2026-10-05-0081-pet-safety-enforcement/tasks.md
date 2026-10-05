# tasks — pet 安全边界强制执行（change 0081 / 账本 E25）

## 1. 规格（**真 delta**，非 skip_specs）
- [x] 1.1 `specs/pet-mode/spec.md`：MODIFIED「Pet Safety Bounds」—— 钉死「暂停」实现口径（本轮终止 + 会话 ACTIVE）+ 新增场景「越界阻断不楔死会话」
- [x] 1.2 `openspec validate 0081-pet-safety-enforcement` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_pet_safety.py`：词汇表订正（真实 id + 只读白名单 + target 可空不做半径）
- [x] 2.2 `tests/test_pet_explore.py`：默认清单 → `tools.file_read`
- [x] 2.3 `tests/test_pet_safety_guard.py`（新）：中间件 —— 终止动作直通 / 放行动作原样返回 / 越界 → 终止 Action（含原因）+ 通知主人 / 无通知器仍阻断
- [x] 2.4 `tests/test_pet_wiring.py`：组合根 —— pet 会话持有**专属 loop**（≠ 主 loop）+ 受限 provider（仅白名单真实工具）+ 越界经 middleware 被阻断并入 sink
- [x] 2.5 红证：实现前 2.3 / 2.4 失败

## 3. 实现（绿）
- [x] 3.1 `src/core/pet/safety/safety.py`：真实不可逆集 + 只读白名单 + `target: str = ""`
- [x] 3.2 `src/core/pet/core/layers.py`：`SafetyLayer.check(op, target="")` 协议签名
- [x] 3.3 `src/core/pet/safety/middleware.py`（新）+ `safety/__init__.py` 导出
- [x] 3.4 `src/core/pet/explore/explorer.py`：默认清单 → `tools.file_read`
- [x] 3.5 `src/core/runtime.py`：`_pet_tools()` / `_pet_loop()`，宠物唤醒脱离主 loop
- [x] 3.6 绿证：四门全绿（基线 959 + 新增）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/pet-mode-interface.md`：新增 §「安全边界与受限探索工具集」（R11/R12 接线 + 「暂停」口径 + 半径默认）
- [x] 4.2 `doc/02-modules/pet.md` §3.5：E25 接线描述 + 剩余零消费项
- [x] 4.3 `doc/01-architecture/adr.md`：ADR-0077 + 变更追踪行
- [x] 4.4 `doc/04-testing/test-cases.md`：TC-PET-03/04（受限工具集 / 越界阻断+通知）

## 5. 收口
- [x] 5.1 `coding-plan/phase-19.md`：§1 E25 行 → ✅ 已关闭（change 0081）；§9 相应处；§0/计数
- [x] 5.2 `coding-plan/README.md`：状态行同步
- [x] 5.3 手动归档（合并 delta + `shutil.move`）+ `openspec validate --all` 全绿
- [x] 5.4 记忆更新 + 提交
