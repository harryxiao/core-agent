# tasks — 0087 pet 微任务真实化与空闲自治睡眠

## 1. 规格先行
- [x] 1.1 `specs/pet-mode/spec.md` delta：MODIFIED「Background Pet Session Lifecycle」（任务出队 / 空闲入睡 / 新任务唤醒 + 3 新场景）
- [x] 1.2 `specs/pet-mode/spec.md` delta：MODIFIED「Pet Micro-tasks」（真实产出 + 空闲触发 + 2 新场景）
- [x] 1.3 `openspec validate 0087-pet-microtask-and-idle-sleep` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_pet_core.py`：唤醒消费队首（队列由 N → N-1）
- [x] 2.2 `tests/test_pet_core.py`：队列清空 ⇒ 入睡（让行态），唤醒被拒 `PET_YIELDING`
- [x] 2.3 `tests/test_pet_core.py`：`dispatch()` 新任务 ⇒ 清让行态（自动唤醒）
- [x] 2.4 `tests/test_pet_core.py`：空闲入睡前触发微任务一次、上报其真实产出
- [x] 2.5 `tests/test_pet_core.py`：微任务返回 `None` ⇒ 不上报
- [x] 2.6 `tests/test_pet_core.py`：微任务抛异常 ⇒ 照常入睡（fail-soft）
- [x] 2.7 `tests/test_pet_microtask.py`：`terminal_walk` 注入探针 ⇒ 只报条数、不泄内容；不可读 ⇒ `None`
- [x] 2.8 `tests/test_pet_microtask.py`：`system_hint` 负载不显著 ⇒ `None`；显著 ⇒ 真实产出
- [x] 2.9 改写既有断言：`test_wake_stays_silent_off_feedback_cycle`（派 3 任务）、`test_session_snapshot_restore_roundtrip`（派 2、唤醒后剩 1）、`test_run_known_task_deterministic`（注入探针）
- [x] 2.10 红：`git stash push -u -- src/` 后新增用例失败 → `git stash pop`

## 3. 实现（绿）
- [x] 3.1 `session.py`：`wake()` 出队消费；`_tasks` 空 ⇒ `_go_idle()`；`busy`/让行守卫抛 `PET_YIELDING`
- [x] 3.2 `session.py`：`_go_idle()` 置让行态 + （有通知面）触发微任务、上报真实产出、异常 fail-soft
- [x] 3.3 `session.py`：`__init__`/`restore()` 增 `microtasks` 注入面；`dispatch()` 清让行态
- [x] 3.4 `activator.py`：`PetActivator` 增 `microtasks` 透传
- [x] 3.5 `microtask.py`：三条任务真实化（`terminal_walk` 只报条数 / `system_hint` 真探负载 / `nonsense_comment` 真写回）；无产出 ⇒ `None`；探针可注入
- [x] 3.6 `runtime.py`：组合根装配 `MicrotaskRunner()`，`microtasks=runner.run` 注入 activator 与恢复工厂

## 4. 四门
- [x] 4.1 `ruff check src tests`
- [x] 4.2 `ruff format --check src tests`
- [x] 4.3 `pyright`（0 errors）
- [x] 4.4 `.venv/bin/pytest -q` 全绿

## 5. 文档
- [x] 5.1 `doc/03-interfaces/pet-mode-interface.md`：§1 注入面 + §5 表「空闲/微任务」行
- [x] 5.2 `doc/02-modules/pet.md`：§3.5 / §5 订正（微任务已接线）
- [x] 5.3 `doc/01-architecture/adr.md`：ADR-0082 + 映射表行
- [x] 5.4 `doc/04-testing/test-cases.md`：TC-PET-07

## 6. 归档与记账
- [x] 6.1 手动合并 delta → `doc/openspec/specs/pet-mode/spec.md`；`shutil.move` 变更目录到 `archive/2026-10-05-0087-…`
- [x] 6.2 `openspec validate --all` 全绿
- [x] 6.3 账本：`phase-19.md` E26 全关闭 + `coding-plan/README.md`
- [x] 6.4 记忆 `coding-plan-leftover-walkthrough.md` + `MEMORY.md`
- [x] 6.5 提交 `feat(pet): 微任务真实化与空闲自治睡眠（change 0087）`
