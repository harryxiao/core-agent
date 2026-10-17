# Tasks 0250 — 宠物人格固定与故障韧性

## 1. 规格

- [ ] 1.1 `pet-mode` spec delta：MODIFIED `Background Pet Session Lifecycle` / `Multi-Pet Management` /
      `Pet Persona and Prompt` / `Pet Control Surface`，新增 5 Scenario。

## 2. 红测试（先写）

- [ ] 2.1 `tests/test_pet_resilience.py`：
      - 人格快照/恢复往返（snapshot 含 persona → restore 重建同人格）
      - 显式人格优先于快照
      - 无快照人格 + 无工厂 ⇒ `None`（裸任务行为不变）
      - `wake` 抛异常 ⇒ `BACKOFF` + `_fault` 有值 + 异常上抛
      - 控制面 `wake` 对 `BACKOFF` ⇒ `ACTIVE` 且故障清空（非 BACKOFF ⇒ 既有 resume 语义）
      - `PetControl.assign` 后新进程加载注册表可见该任务
      - `_pet_run` tick 落盘：唤醒一次后新进程加载可见 `wake_count=1`、队列少一项
      - 运行时重建（`CORE_STATE_DIR=tmp_path`）后唤醒 prompt 仍含人格

## 3. 实现

- [ ] 3.1 `PetSession.snapshot()` 增 `persona`；`restore` 增 `persona_factory` 解析序。
- [ ] 3.2 `persona_from_record()`（`pet/library/persona.py`）。
- [ ] 3.3 `PetManager.persist()`；`PetControl.sleep/wake/assign` 落盘；`entry._pet_run` on_tick 落盘。
- [ ] 3.4 `PetSession.wake()` try/except → `backoff` → raise；`PetSession.recover()`；
      `PetControl.wake` BACKOFF 分支。
- [ ] 3.5 组合根恢复工厂传 `persona_factory=persona_from_record`。

## 4. 验证

- [ ] 4.1 探针 P1–P6 各自变红（摘机制 → 跑对应测试 → 复原 md5 一致）。
- [ ] 4.2 四门禁：`.venv/bin/ruff check src tests`、`.venv/bin/ruff format --check src tests`、
      `/home/harry/.praisonai/venv/bin/pyright`、`.venv/bin/pytest -q`。
- [ ] 4.3 `openspec validate 2026-10-17-0250-pet-persona-pinning-and-resilience --strict` → 归档。

## 5. 文档与收口

- [ ] 5.1 ADR-0240；`coding-plan/known-risk.md` E186 + §3 局限行。
- [ ] 5.2 `doc/04-testing/test-cases.md` §162；`doc/02-modules/pet-mode.md`、`doc/03-interfaces/pet-interface.md`。
- [ ] 5.3 单次提交 `fix(pet): ... change 0250 / ADR-0240 / 台账 E186`；更新记忆。
