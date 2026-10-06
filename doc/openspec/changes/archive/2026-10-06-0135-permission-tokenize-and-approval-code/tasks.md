# tasks — permission 分级按词元 + 高危审批门错误码（change 0135 / 账本 E76）

## 1. 规格（先行）
- [x] 1.1 **规格中性**：`permission/spec.md`「分级权限体系」（SHALL 语义分词 / 命名空间子串 SHALL NOT
      影响等级）与错误码表（`APPROVAL_REQUIRED` = 高危操作需人工审批）**均已要求在位** ⇒ 无 spec delta，
      `.openspec.yaml` 置 `schema: spec-driven` + `skip_specs: true`（先例 `0110` / `0083`）
- [x] 1.2 复核：不新增 / 不修改任何 Requirement；两条**判据订正**（raise 不落在 `authorize` /
      `tools.list` 反例改写）见 proposal 与 ADR-0128

## 2. 测试（先写，红）
- [x] 2.1 `tools.target` / `tools.category_sync`（词元非只读、含只读子串）⇒ `HIGH_RISK`；
      目标侧 `/var/log/target` 同理 ⇒ `HIGH_RISK`（红：旧裸子串实现判 `READ`）
- [x] 2.2 切词不误伤：`fs.list` / `tools.file_read` ⇒ `READ`（整词元照旧命中）
- [x] 2.3 命名空间子串反例回归：`tools.whatever` ⇒ `HIGH_RISK`；`tools.file_write` ⇒ `DATA_EDIT`
- [x] 2.4 高危未批 ⇒ `AccessControlError.code is APPROVAL_REQUIRED`（非 `PERMISSION_DENIED`），
      且后端**未被调用**（红：旧实现抛 `PERMISSION_DENIED`）
- [x] 2.5 运行确认**红**（新增 / 改写用例失败、其余全绿）：旧实现下 2.1 判 `READ`、2.4 码为
      `PERMISSION_DENIED` ⇒ 两处均红

## 3. 实现
- [x] 3.1 `src/core/permission/policy.py`：加 `_TOKEN_SPLIT` 与 `_tokens(op, target)`；
      三张词元表 `tuple` → `frozenset`；`classify` 改集合交判定（顺序逐字不变）
- [x] 3.2 `src/core/git/client.py`：`_require_approval` 抛 `APPROVAL_REQUIRED`（行为不变，码归位）
- [x] 3.3 四门全绿（直连二进制，不用 `uv run`）：`1634 passed`（基线 1632 ⇒ 净 +2）、
      ruff check / format --check 通过、pyright `0/0/0`

## 4. 文档
- [x] 4.1 `doc/02-modules/permission.md` §3 判定口径补「`0135` 补齐实现」+ §5 错误表下补
      `APPROVAL_REQUIRED` 的生产 raise 落点
- [x] 4.2 `doc/03-interfaces/permission-interface.md` §2 分级判定契约（切词 + 陷阱例）与 §5 错误码行
- [x] 4.3 `doc/03-interfaces/git-interface.md` §1：审批门错误码（`APPROVAL_REQUIRED`，非交互默认拒）
- [x] 4.4 `doc/01-architecture/adr.md`：**ADR-0128**（两决策 + 两条判据订正 + 已知局限）+ 变更追踪行
- [x] 4.5 `doc/04-testing/test-cases.md`：新增 §51（TC-PERMTOK-01…05）

## 5. 收口
- [x] 5.1 手工归档（无 delta ⇒ 直接 `shutil.move` 进
      `doc/openspec/changes/archive/2026-10-06-0135-permission-tokenize-and-approval-code/`；tick tasks）
- [x] 5.2 `openspec validate --all` 全绿（30 passed / 0 failed）
- [x] 5.3 账本回填（`coding-plan/phase-34.md` §1 E76 行尾 + §9 落地表；`README.md` 索引行）
- [x] 5.4 记忆更新 + 提交（`fix(permission)`，一个 change 一个 commit）
