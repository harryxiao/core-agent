# tasks — 0088 pet 控制面 `/pet [cmd]`

## 1. 规格先行
- [x] 1.1 `specs/pet-mode/spec.md` delta：ADDED「Pet Control Surface」（寻址 / 动词 / 状态 / 拒绝 / 同进程 + 6 场景）
- [x] 1.2 `openspec validate 0088-pet-control-surface` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_pet_control.py`（新）：`status` 返回结构化字段且**不含**偏好/任务正文
- [x] 2.2 `status` / `sleep` / `wake` / `assign` / `stop` 各自作用于指定会话
- [x] 2.3 `sleep` 后 `wake` 恢复（`sleep` ⇒ `PET_YIELDING`，`wake` ⇒ 可唤醒）
- [x] 2.4 `assign` 入队并清让行态（自动唤醒）
- [x] 2.5 单宠物默认寻址；多宠物未指定 ⇒ 拒绝并列出 id
- [x] 2.6 未知会话 ⇒ `PET_NOT_FOUND`
- [x] 2.7 `tests/test_entry.py`：`pet status` / `pet sleep` / `pet wake` / `pet assign` CLI 端到端（退出码 + 输出）
- [x] 2.8 `tests/test_ui.py`（或既有 ui 测试）：`UIAPILayer.pet_command` 落到同一 `PetControl`
- [x] 2.9 红：`git stash push -u -- src/` 后新增用例失败 → `git stash pop`

## 3. 实现（绿）
- [x] 3.1 `src/core/pet/core/errors.py`：新增 `PET_NOT_FOUND` / `PET_TARGET_AMBIGUOUS`
- [x] 3.2 `src/core/pet/core/control.py`（新）：`PetControl`（verb → 会话操作 + 寻址 + 结构化 status）
- [x] 3.3 `src/core/pet/core/__init__.py`：导出 `PetControl`
- [x] 3.4 `src/core/ui/api.py`：`pet_control` 注入面 + `pet_command(verb, *, session_id=None, goal=None)`
- [x] 3.5 `src/core/entry.py`：`_pet` 增 `status|sleep|wake|assign`（复用 `PetControl`）；`_build_ui` 注入 `pet_control`

## 4. 四门
- [x] 4.1 `ruff check src tests`
- [x] 4.2 `ruff format --check src tests`
- [x] 4.3 `pyright`（0 errors）
- [x] 4.4 `.venv/bin/pytest -q` 全绿

## 5. 文档
- [x] 5.1 `doc/03-interfaces/pet-mode-interface.md`：增控制面契约 + `PET_NOT_FOUND`
- [x] 5.2 `doc/02-modules/pet.md`：§3 控制面小节
- [x] 5.3 `doc/01-architecture/adr.md`：ADR-0083 + 映射表行
- [x] 5.4 `doc/04-testing/test-cases.md`：TC-PET-08
- [x] 5.5 `doc/03-interfaces/ui-interface.md`：`pet_command` + `pet_control`

## 6. 归档与记账
- [x] 6.1 手动合并 delta → `doc/openspec/specs/pet-mode/spec.md`；`shutil.move` 变更目录到 `archive/2026-10-05-0088-…`
- [x] 6.2 `openspec validate --all` 全绿
- [x] 6.3 账本：`phase-19.md`（记 0088 = 用户诉求① 收口）+ `coding-plan/README.md`
- [x] 6.4 记忆 `coding-plan-leftover-walkthrough.md` + `MEMORY.md`
- [x] 6.5 提交 `feat(pet): 控制面 `/pet [cmd]`（change 0088）`
