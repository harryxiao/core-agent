# Tasks 0195 — 长任务端到端门禁

## 1. 规格（规格中性）

- [x] 判定**规格中性**：零 `src/` 改动、只补测试锚 ⇒ `.openspec.yaml` `skip_specs: true`
      （沿 `0156` / `0189` 先例），**不**产出 spec delta
- [x] ADR-0185（`doc/01-architecture/adr.md`）

## 2. 端到端门禁（`tests/test_longtask_e2e.py`）

- [x] **压实产物 → 下一轮真实装配的 system prompt**（补此前两端分离的缺口：
      `test_loop.py` 只断言记忆态、`test_history_replay.py` 手播摘要）
- [x] **越界摘要尾部 → 投喂摘要器的 prompt**（change `0193` 端到端锚；注意锚点位置是
      **摘要器 prompt 的既有摘要槽**，非循环注入面）
- [x] **关历史回放 → 摘要仍进装配后的 prompt**（change `0194` 端到端锚）
- [x] **防过空断言**：①断言注入内容 = **上一轮压实产物**（非任意文本）；③断言尾部**锚点字串**
      与中略标记；④断言历史原文**不回灌**
- [x] **反证（门禁非空过）**：逐条临时回退其目标行为，确认对应用例转红后复原
      （①禁 `memory.compact` ⇒ 红；③改纯头截断 ⇒ 红；④恢复 `history_turns` 闸 ⇒ 红）

## 3. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] `openspec validate 2026-10-11-0195-longtask-e2e-gates`
- [x] 手工归档（规格中性 ⇒ 仅移入 `archive/`，无 delta 合并）
- [x] `doc/04-testing/test-cases.md` 新 TC 节 + 基线 bump；台账 E132（`known-risk.md` §1）
- [x] 单次提交 `test(loop): …`
