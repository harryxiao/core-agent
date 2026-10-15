# Tasks �?evolution-rejected-lesson-writeback�?234�?

## 1. Specification
- [x] 1.1 delta ADDED「未过门教训写回」（L2 全文 / L3 短指�?/ issue 有界 / 脱敏 /
      未注入跳�?/ 与人�?reject 并存）；`openspec validate` �?change 全绿�?

## 2. Tests（先红）
- [x] 2.1 L2：id=`evolution.gate_rejected.<candidate_id>`、layer=L2、内容含 target /
      issue / review；issue 超长时截断至 400 字符�?
- [x] 2.2 L3：id=`evolution.gate_rejected.l3.<candidate_id>` 并存；content �?`ref=` 指向
      L2 id�?*不等�?* L2 全文�?*不含**完整 issue 长文�?
- [x] 2.3 `memory=None` 时零写、不抛异常�?
- [x] 2.4 与人�?`reject()` 条目（`evolution.rejected.<id>`）可并存�?
- [x] 2.5 no_evidence/manual/frozen/rollback/pending 分支回归：无新增 `gate_rejected*`�?

## 3. Implementation
- [x] 3.1 `engine.py` 引入 `redact_secrets`；常�?`_MAX_ISSUE_CHARS = 400`�?
- [x] 3.2 新增 `_write_rejected_lesson`：L2 全文（issue 有界�? L3 短指针；未注入跳过�?
- [x] 3.3 `run_cycle` rejected 分支�?`_pending.record` 后调用该方法�?

## 4. Gates & Archive
- [x] 4.1 `openspec validate --all` 全绿�?
- [x] 4.2 四门禁通过�?
- [x] 4.3 归档：提�?`fix(evolution): 未过门候选教训写回（change 0234）`�?
