# Tasks 0199 — Procedural 端到端门禁

## 1. 规格（规格中性）

- [x] 判定**规格中性**：零 `src/` 改动、只补测试锚 ⇒ `.openspec.yaml` `skip_specs: true`
      （沿 `0156` / `0189` / `0195` 先例），**不**产出 spec delta
- [x] ADR-0189（`doc/01-architecture/adr.md`）

## 2. 端到端门禁（`tests/test_procedural_e2e.py`）

- [x] **锚 1**：真 `TaskScheduler` + 真组合根跑 3 次成功任务 ⇒ 任务级 SOP 入库
      （`instructions` = 提炼文本 / `task_types[0]` 带 `task::` 前缀）；2 次时**不入库**（防空过）
- [x] **锚 2**：JEV 配置 + 拒绝门 ⇒ 零入库 + **恰一次**「质量门未过」留痕
- [x] **锚 3**：无 JEV 配置（`gate=None`）⇒ 照常入库（与锚 2 成对 ⇒ 门是唯一差异）
- [x] **锚 4**：捕获投喂提炼器的 prompt ⇒ 含记忆步序条目正文、**不含** `SubtaskOutcome.reply`
- [x] 只桩两个**外部面**（`llm.completion` / 子 Agent `LoopPlugin`）；被测链路零桩

## 3. 反证（门禁非空过）

- [x] ① `_finalize` 去 `observe` ⇒ 4 红；② 去 `namespace="task"` ⇒ 仅锚 1 红；
      ③ `gate=None` ⇒ 仅锚 2 红；④ `compose_task_steps` 读 `outcome.reply` ⇒ 仅锚 4 红；
      复原后 4 绿（实测记录见 design.md §2.3）

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] `git diff --stat src/` 为空（零 `src/` 改动）
- [x] `openspec validate 2026-10-11-0199-procedural-e2e-gates`
- [x] 手工归档（规格中性 ⇒ 仅移入 `archive/`，无 delta 合并）
- [x] `doc/04-testing/test-cases.md` 新 TC 节 + 基线 bump；台账 E136（`known-risk.md` §1）
- [x] 单次提交 `test(skills): …`
