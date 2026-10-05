# tasks — pet「Runtime Wiring」loop 措辞订正（change 0082 / 账本 E29）

## 1. 规格（**真 delta**，非 skip_specs）
- [x] 1.1 `specs/pet-mode/spec.md`：MODIFIED「Pet Session Runtime Wiring」（Requirement + 口径说明段 + Scenario THEN 同步）
- [x] 1.2 `openspec validate 0082-pet-wiring-loop-wording` 通过

## 2. 文档
- [x] 2.1 全仓核实：除该规格外无其他现行文档仍称宠物唤醒用「主 loop」（接口 §5.1 / 模块 §3.5·§4 已在 `0081` 订正）

## 3. 收口（零代码变更）
- [x] 3.1 四门绿（基线 968 passed）—— 本次无代码/测试改动，验证零回归
- [x] 3.2 `coding-plan/phase-19.md`：§1 新行 **E29** + §9 相应处；`coding-plan/README.md` 状态行同步
- [x] 3.3 手动归档（合并 delta + `shutil.move`）+ `openspec validate --all` 全绿
- [x] 3.4 记忆更新 + 提交
