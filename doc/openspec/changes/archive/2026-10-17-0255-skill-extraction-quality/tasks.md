# Tasks 0255 — 技能提炼质量门

## 1. 规格

- [x] 1.1 `skills` delta：MODIFIED「原子技能库」（字段上界 + 1 scen）。
- [x] 1.2 `skills` delta：MODIFIED「SOP 提炼」（确定性门 + 重复拦截 + 2 scen，既有场景全保留）。

## 2. 红测试（先写）

- [x] 2.1 `tests/test_skill_extraction_quality.py`：
      - 单步 / 超短文本 ⇒ 不入库、清组、留痕只报组键
      - 两步文本 ⇒ 正常发布
      - 判定门在确定性门之后仍生效
      - 与既有技能 instructions 逐字相同 ⇒ 不入库
      - `register` 越界字段 ⇒ `INVALID_SKILL_SCHEMA`（五类字段参数化）
- [x] 2.2 既有单步桩改为两步（`test_skills.py` / `test_skill_retirement.py`）。

## 3. 实现

- [x] 3.1 `skills/models.py`：字段上界常量（单一定义）。
- [x] 3.2 `skills/library.py`：`register` 上界校验。
- [x] 3.3 `skills/sop.py`：确定性门（长度 / 步骤数 / 逐字重复）+ 清组留痕。
- [x] 3.4 `evolution/content.py`：私有别名指向 `skills.models` 常量。

## 4. 验证

- [x] 4.1 探针：逐点摘除 ⇒ 对应用例红；复原 md5 一致。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate 2026-10-17-0255-skill-extraction-quality --strict` → 归档。

## 5. 文档与收口

- [x] 5.1 ADR-0246；`coding-plan/known-risk.md` E192 + §3 行。
- [x] 5.2 `doc/04-testing/test-cases.md` §168；接口文档补写发布门与字段上界。
- [x] 5.3 单次提交 `feat(skills): ... change 0255 / ADR-0246 / 台账 E192`；更新记忆。
