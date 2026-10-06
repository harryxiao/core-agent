# Tasks · 0138 git 断线重试 + 高危原语（skip_specs）

## 1. 规格（先行）

- [x] 1.1 **无 delta**（`git/spec.md`「与 permission 沙箱协作」`:61-67` + 「远程操作可靠性」`:69-91`
      早已是硬 SHALL，实现侧纯背离 ⇒ conformance）：写 `.openspec.yaml`（`schema: spec-driven` + `skip_specs: true`）
- [x] 1.2 `openspec validate 0138-git-retry-and-highrisk-primitives` 通过

## 2. 测试（先行 · 红）

- [x] 2.1 `tests/test_git.py`：`delete_remote_branch` 未批 ⇒ `APPROVAL_REQUIRED` 且**后端零调用**
- [x] 2.2 `tests/test_git.py`：`delete_remote_branch` 批准 ⇒ 落 `(remote, branch)`
- [x] 2.3 `tests/test_git.py`：`rewrite_history` 未批 / 批准 两条
- [x] 2.4 `tests/test_git.py`：三类高危 op id 分派互异（`git.push(force)` / `git.delete_remote_branch` /
      `git.rewrite_history`）+ 非交互（无回调）默认拒
- [x] 2.5 `tests/test_git_subprocess.py`：瞬态抖动 2 次后成功 ⇒ 返回成功且退避序列 `[0.5, 1.0]`
- [x] 2.6 `tests/test_git_subprocess.py`：恒瞬态失败 ⇒ `attempts` 次后抛 `GIT_COMMAND_FAILED`
- [x] 2.7 `tests/test_git_subprocess.py`：认证失败 / 非瞬态失败 / 超时 ⇒ **各只调 `_invoke` 一次**（不重试）
- [x] 2.8 **验绿**：实现后全绿（红因 `_run_remote` / 两原语 / 注入参数不存在而红）

## 3. 实现

- [x] 3.1 `subprocess_backend.py`：构造面 `attempts` / `backoff` / `sleep`（可注入）+ `_run_remote`
      （指数退避循环）+ `_TRANSIENT_MARKERS` / `_is_retryable`（认证 / 超时 / 冲突 / 非瞬态一律不重试）
- [x] 3.2 `subprocess_backend.py`：`clone` / `pull` / `push` 改走 `_run_remote`；
      新增 `delete_remote_branch` / `rewrite_history`
- [x] 3.3 `client.py`：`_require_approval(op, reason)` 泛化 + 两新原语（同型审批门，新 op id）
- [x] 3.4 `backend.py`：Protocol 补两原语；「13 项」→「15 项」

## 4. 文档

- [x] 4.1 `doc/03-interfaces/git-interface.md`：§1 原语面补两方法 + 审批门注；§3 后端面补重试语义；
      §4 补「可重试分类」段
- [x] 4.2 `doc/01-architecture/adr.md`：ADR-0131 + `## 变更追踪` 行
- [x] 4.3 `doc/04-testing/test-cases.md`：§54（TC-GIT-REL，change 0138 / ADR-0131，账本 E79）

## 5. 门禁（直连二进制，禁 `uv run`）

- [x] 5.1 `.venv/bin/ruff check src tests` —— 绿
- [x] 5.2 `.venv/bin/ruff format --check src tests` —— 绿
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` —— 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` —— **1662 passed**（基线 1651 + 11：test_git +6、test_git_subprocess +5）
- [x] 5.5 `openspec validate --all` —— **31 passed / 0 failed**（active 期含本 change；skip_specs 不增 cap ⇒
      归档后回落 30 / 0）

## 6. 收口

- [x] 6.1 手工归档至 `archive/2026-10-07-0138-git-retry-and-highrisk-primitives/`
- [x] 6.2 台账回填：`coding-plan/phase-34.md`（E79 行 + §9 表）；`coding-plan/README.md` 3 处索引行
- [x] 6.3 记忆更新：`MEMORY.md` + `coding-plan-leftover-walkthrough.md`
- [x] 6.4 单次提交（`fix(git): 断线重试 + 高危原语（change 0138）`）
