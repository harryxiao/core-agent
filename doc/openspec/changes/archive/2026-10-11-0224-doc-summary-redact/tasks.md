# 0224 任务 — 文档摘要落盘前无条件脱敏

- [x] 1. **规格先行**：`notes` MODIFIED「文档摘要笔记（notes.rag）」（＋1 Scenario），既有 4
      Scenario 逐字保留；`rag` 规格不动。
- [x] 2. **测试先行（红）**：`tests/test_rag_summary.py` 增用例 —— 含密钥形态的摘要 ⇒ 落盘正文
      呈 `<redacted>`、原文形态不出现、结构保留；无密钥 ⇒ 逐字不变。
- [x] 3. **实现（绿）**：`src/core/entry.py` —— `from core.memory import … redact_secrets`
      （并入既有 `:67` 导入）；`_doc_summary_note` 正文改用 `redact_secrets(summary.strip())`；
      `_DOC_SUMMARY_PROMPT` 补脱敏措辞。
- [x] 4. **镜像同步**：`doc/03-interfaces/prompts.md` ⑭ 代码块与旁注更新（去「待裁决」）。
- [x] 5. **反证**：摘 `redact_secrets` ⇒ 脱敏用例红；复原 ⇒ md5 相同。
- [x] 6. **四门禁** ＋ `openspec validate --all`。
- [x] 7. **收口**：ADR-0214 ＋ 变更追踪；`known-risk.md` §1 E161／§3；`test-cases.md` §137；
      `Pending-Arbitration.md` PA-03 已闭；归档 ＋ 单次提交。
