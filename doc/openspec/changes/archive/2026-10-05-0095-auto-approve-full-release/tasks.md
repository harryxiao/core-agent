# tasks — 0095 auto-approve 全放行 + 只读判定子串修复

## 1. 规格先行
- [x] 1.1 `specs/permission/spec.md` delta：MODIFIED「权限模式」（auto-approve 全放行 + 与红线正交 + 原四场景作锚）+ MODIFIED「分级权限体系」（词元判定 + 字面量豁免 + 3 新场景）
- [x] 1.2 `openspec validate` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_permission.py`：改 `test_permission_mode_auto_approve_low_risk` → `..._full_release`（高危/出站网络/不可归类全放行、`allowed is True and approval_required is False`）；增 classify 4 例（`tools.whatever`→HIGH_RISK / `agent:delegate`→READ / `agent:other`→HIGH_RISK / `tools.file_write` 不判 READ）
- [x] 2.2 `tests/test_permission_auto_approve.py`（新）：ToolProvider 无 approver 下放行不可逆写 / 出站网络 / 不可归类 + guardrail 仍 deny + read-only / high-risk-block 仍拒 + `DefaultLoop` 无 approver 执行不可逆动作正向回归
- [x] 2.3 红：以上用例在实现前失败

## 3. 实现（绿）
- [x] 3.1 `policy.py`：`PermissionModeGate.authorize` AUTO_APPROVE 顶部短路
- [x] 3.2 `policy.py`：删 `_READ_TOKENS` 的 `"ls"` + 增 `_DELEGATE_COEFFECT` 字面量只读规则
- [x] 3.3 `guard.py`：`self._mode` + 不可逆写分支感知 AUTO_APPROVE
- [x] 3.4 绿：全部用例通过

## 4. 四门
- [x] 4.1 `ruff check src tests`
- [x] 4.2 `ruff format --check src tests`
- [x] 4.3 `pyright`（0 errors / 0 warnings / 0 informations）
- [x] 4.4 `.venv/bin/pytest -q` 全绿

## 5. 文档
- [x] 5.1 `doc/03-interfaces/permission-interface.md` §2 分级契约（字面量 vs 子串）+ §6 AUTO_APPROVE 全放行
- [x] 5.2 `doc/02-modules/permission.md` §3.1 补「模式覆盖」段
- [x] 5.3 `doc/01-architecture/adr.md`：ADR-0090 + 映射表行
- [x] 5.4 `doc/04-testing/test-cases.md`：TC-PERM-08 / TC-PERM-09

## 6. 归档与记账
- [x] 6.1 手动合并 delta → `doc/openspec/specs/permission/spec.md`；`shutil.move` 变更目录到 archive
- [x] 6.2 账本：`phase-19.md` §9 步 10 后续行（auto-approve 名实不符 → 0095 关闭；文档漂移 `RiskClassifier`/`AuditTrail`、`git/backend.py:5` docstring 一并销账或转留）
- [x] 6.3 记忆更新
- [x] 6.4 提交 `feat(permission): auto-approve 全放行（change 0095）`
