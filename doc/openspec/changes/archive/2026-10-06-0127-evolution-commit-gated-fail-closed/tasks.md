# tasks — 落地只认门禁全过的制品（fail-closed 收口）（change 0127 / phase-34 E69）

## 1. 规格（先行）
- [x] 1.1 `specs/evolution/spec.md`：MODIFIED「架构级候选的原生实施（可选）」——「复核（review）」
      bullet 补「**待复核**仅指门禁全过（`gated=True`）的制品；未过门 SHALL NOT 列为待复核项」
- [x] 1.2 同 delta：「落地（commit）」bullet 补「SHALL 只认门禁全过的制品；无制品或未过门
      （含筹备异常 / 进程中断残留）⇒ SHALL 结构化拒绝（`IMPLEMENT_REJECTED`）并提示重新筹备，
      SHALL NOT fail-open」
- [x] 1.3 同 delta：新增 Scenario「未过门的残留制品不被放行落地」（保留既有 Scenario 逐字）
- [x] 1.4 `openspec validate 0127-evolution-commit-gated-fail-closed` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_evolution_executor.py`：门禁执行**抛异常**中断筹备 ⇒ 台账留下 `gated=False`
      残留制品、工作树已回退；随后带**合格复核单**落地 ⇒ 抛 `IMPLEMENT_REJECTED`、工作区逐字不变、
      状态仍 `confirmed`（现状：**放行落地** ⇒ 红）
- [x] 2.2 同文件：`executor.staged()` / `executor.staged_all()` 均**不**列出该残留制品，但
      `queue.implementation_of()` **仍可见**（留痕，不抹掉）
- [x] 2.3 同文件：**回归** —— 筹备成功路径 `staged()` / `staged_all()` 正常列出且 `gated is True`
- [x] 2.4 红：2.1 / 2.2 在实现前**必失败**

## 3. 实现
- [x] 3.1 `src/core/evolution/executor.py:staged`：判据补 `record.gated`；docstring 写明
      「未过门 ⇒ `None`」
- [x] 3.2 `src/core/evolution/pending.py:staged`：判据补 `r.implementation.gated`；docstring 与
      实际谓词对齐
- [x] 3.3 `src/core/evolution/executor.py` 模块 docstring：落地阶段补一句「只认门禁全过的制品」

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`（须 0/0/0）
- [x] 4.4 `.venv/bin/pytest -q`（基线 1602 passed ⇒ 新增后按实累加）
- [x] 4.5 `openspec validate --all`（归档前后各一次，30 passed / 0 failed）

## 5. 归档
- [x] 5.1 手工合并 delta 进 canonical `doc/openspec/specs/evolution/spec.md`（对齐既有排版：
      `### Requirement:` 正文紧接、`#### Scenario:` 后不留空行）
- [x] 5.2 目录 `shutil.move` 至 `doc/openspec/changes/archive/2026-10-06-0127-evolution-commit-gated-fail-closed/`

## 6. 文档与账本
- [x] 6.1 `doc/01-architecture/adr.md`：**ADR-0120**（判据只加在读取面 / 不新增错误码 / 不静默丢弃
      残留制品 / 已知局限：`_run_gates` 异常路径仍不自动清账；变更追踪表行）
- [x] 6.2 `doc/03-interfaces/evolution-interface.md`（若记 `staged` / `commit` 契约则同步）
- [x] 6.3 `doc/04-testing/test-cases.md` 增 TC 行
- [x] 6.4 `coding-plan/phase-34.md`：§1 真缺陷表 **E69** 行标「已落地（change `0127` / ADR-0120）」；
      §9 台账行同步；`coding-plan/README.md` 索引同步
- [x] 6.5 记忆：`coding-plan-leftover-walkthrough.md` + `MEMORY.md`

## 7. 提交
- [x] 7.1 单次提交：`fix(evolution): 落地只认门禁全过的制品（change 0127）`
- [x] 7.2 **不提交**：`config.yaml`、`.claude/settings*.json`（D4 不动）、`coding-plan/phase-3-prompt.md`、
      `AI-SoftwareEngineer-4.md`、`coding-plan/phase-32.md`、`src-tauri/Cargo.lock`、`node_modules/`、
      `frontend/dist/`
