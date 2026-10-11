# Tasks 0215 — 提示词文本 pin

## 1. 规格（规格中性）

- [x] 判定**规格中性**：零 `src/` 改动、只补测试锚 ⇒ `.openspec.yaml` `skip_specs: true`
      （沿 `0156` / `0189` / `0195` / `0199` 先例），**不**产出 spec delta
- [x] ADR-0205（`doc/01-architecture/adr.md`）

## 2. 测试锚（`tests/test_prompt_pinning.py`，12 用例）

- [x] **逐字头 ×9**：`extract._PROMPT_HEAD` / `extract._RELATION_PROMPT_HEAD` /
      `summarize._PROMPT_HEAD` / `importance._PROMPT_HEAD` / `sop._PROMPT_HEAD` /
      `iteration._PROMPT_HEAD` / `planner._SYSTEM_PROMPT` / `_DECOMPOSE_SYSTEM` / `_VERIFY_SYSTEM`
      —— 各自独立副本逐字比较（含承重措辞，不只首句）
- [x] **结构不变量 ×3**：① 六 builder 产物恒以 `_PROMPT_HEAD` 开头且条目行 `- ` 前缀；
      ② 模板占位符解析（`{max}`/`{predicates}` 无残留、8 谓词全量）；③ 超长正文节选有界

## 3. 反证（门禁非空过）

- [x] ① 改一字符 ⇒ 对应用例红；② 删承重句 ⇒ 红；③ 删谓词 ⇒ 结构锚红；④ 放大上界 ⇒ 有界锚红；
      复原后 12 绿（实测记录见 design.md §2.3）

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] `git diff --stat src/` 为空（零 `src/` 改动）
- [x] `openspec validate 2026-10-11-0215-prompt-text-pinning`
- [x] 手工归档（规格中性 ⇒ 仅移入 `archive/`，无 delta 合并）
- [x] `doc/04-testing/test-cases.md` 新 TC 节 §128 + 基线 bump；台账 E152（`known-risk.md` §1）
- [x] 单次提交 `test(memory): …`（change 0215 / ADR-0205 / 台账 E152）
