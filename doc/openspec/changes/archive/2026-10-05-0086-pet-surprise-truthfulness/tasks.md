# tasks — 0086 pet 惊喜去谎报与上报

## 1. 规格先行
- [x] 1.1 `specs/pet-mode/spec.md` delta：MODIFIED「Periodic Feedback and Surprise」+ 3 新场景
- [x] 1.2 `openspec validate 0086-pet-surprise-truthfulness` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_pet_core.py`：无偏好 ⇒ `surprise()` 返回 `None`（不谎报）
- [x] 2.2 `tests/test_pet_core.py`：有偏好 ⇒ `surprise()` 经 loop 执行且回报**真实结果**（含 loop reply）
- [x] 2.3 `tests/test_pet_core.py`：反馈周期命中 + 无偏好 ⇒ 通知器只收 `report()`（不含惊喜）
- [x] 2.4 `tests/test_pet_core.py`：反馈周期命中 + 有偏好 ⇒ 通知器收 `report()` + 惊喜两条
- [x] 2.5 `tests/test_pet_core.py`：惊喜 loop 抛异常 ⇒ `wake()` 照常返回（fail-soft）
- [x] 2.6 红：`git stash push -u -- src/` 后新增用例失败 → `git stash pop`

## 3. 实现（绿）
- [x] 3.1 `session.py`：`surprise() -> str | None`（无偏好 `None`；有偏好经 loop 真实执行）
- [x] 3.2 `session.py`：`_notify_owner()` 同节拍追加惊喜投递（`None` 不投、异常 fail-soft）

## 4. 四门
- [x] 4.1 `ruff check src tests`
- [x] 4.2 `ruff format --check src tests`
- [x] 4.3 `pyright`（0 errors）
- [x] 4.4 `.venv/bin/pytest -q` 全绿

## 5. 文档
- [x] 5.1 `doc/03-interfaces/pet-mode-interface.md`：§1 签名 + §5 表行
- [x] 5.2 `doc/02-modules/pet.md`：§3.5 / §5 订正
- [x] 5.3 `doc/01-architecture/adr.md`：ADR-0081 + 映射表行
- [x] 5.4 `doc/04-testing/test-cases.md`：TC-PET-1x

## 6. 归档与记账
- [x] 6.1 手动合并 delta → `doc/openspec/specs/pet-mode/spec.md`；`shutil.move` 变更目录到 `archive/2026-10-05-0086-…`
- [x] 6.2 `openspec validate --all` 全绿
- [x] 6.3 账本：`phase-19.md` E26 半关闭（surprise 半边）+ `coding-plan/README.md`
- [x] 6.4 记忆 `coding-plan-leftover-walkthrough.md` + `MEMORY.md`
- [x] 6.5 提交 `feat(pet): 惊喜去谎报与上报（change 0086）`
