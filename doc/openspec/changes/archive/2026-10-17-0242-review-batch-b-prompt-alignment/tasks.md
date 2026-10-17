# Tasks — 批次 B：prompt 对齐与技能内容容错/有界

## 1. 规格

- [x] 1.1 `memory/spec.md`「记忆压实」MODIFIED：摘要 prompt 产出上界与 `MAX_SUMMARY_CHARS` 同源 + 1 Scenario
- [x] 1.2 `memory/spec.md`「结构化实体抽取（关键事实）」MODIFIED：prompt 名额与 `cap(n)` 同源 + 1 Scenario
- [x] 1.3 `memory/spec.md`「实体关系抽取（relations）」MODIFIED：prompt 名额同源 + 中文变体展示 + 2 Scenario
- [x] 1.4 `evolution/spec.md`「技能候选内容生成」MODIFIED：围栏容错 + 内容有界 + 3 Scenario
- [x] 1.5 `openspec validate 2026-10-17-0242-review-batch-b-prompt-alignment`

## 2. 红测试

- [x] 2.1 summary prompt：含 `MAX_SUMMARY_CHARS`、不含 800
- [x] 2.2 默认抽取器 prompt 名额自适应（200 条 ⇒ `KEY_FACTS_MAX`；20 条 ⇒ `KEY_FACTS_MIN`）
- [x] 2.3 默认关系抽取器 prompt 名额自适应
- [x] 2.4 关系 prompt 展示全部中文变体
- [x] 2.5 writer 容忍代码围栏 / 前后杂文
- [x] 2.6 writer 裁剪超长字段；`validate_skill_content` 拒绝超界内容

## 3. 实现

- [x] 3.1 `summarize._PROMPT_HEAD` 由 `MAX_SUMMARY_CHARS` 插值
- [x] 3.2 `extract_with` / `extract_relations_with` 缺省名额改为按 `cap(n)` 计算
- [x] 3.3 关系 prompt 谓词表由 `RELATION_PREDICATES` 派生并展示中文变体
- [x] 3.4 `skill_content_writer_with` 容忍围栏/杂文（首 `{` 至末 `}`）
- [x] 3.5 `SkillContent` 字段上界常量 + writer 裁剪 + `validate_skill_content` 拒绝超界

## 4. 门禁与反证

- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`
- [x] 4.4 `.venv/bin/pytest -q`
- [x] 4.5 反证五组（摘要 800 / 名额缺省 / 纯英文谓词 / 去围栏容错 / 去裁剪），复原 md5 同

## 5. 收口

- [x] 5.1 归档到 `doc/openspec/changes/archive/2026-10-17-0242-review-batch-b-prompt-alignment/`
- [x] 5.2 ADR-0230 + 变更追踪表
- [x] 5.3 台账 E177（`known-risk.md` §1/§3）+ 测试节 §153（`test-cases.md`）
- [x] 5.4 接口文档同步（`memory-interface.md` / `evolution-interface.md`）
- [x] 5.5 单次提交（change 0242 / ADR-0230 / 台账 E177）
