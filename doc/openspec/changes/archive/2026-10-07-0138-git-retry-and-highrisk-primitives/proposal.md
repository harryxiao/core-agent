# 0138 · git 断线重试 + 高危原语（skip_specs）

> 账本：`coding-plan/phase-34.md` **E79**（「断线重试 / 指数退避」无实现 ＋「删远程分支 / 历史改写」原语缺失）
> 规格面：**无 delta**（`git/spec.md`「与 permission 沙箱协作」`:61-67` 与「远程操作可靠性」`:69-91`
> 早已是硬 SHALL）｜ ADR：**0131**

## Why

`git/spec.md` 两条 Requirement 均为**硬 SHALL**，实现侧纯背离（E79）：

1. **「远程操作可靠性」**（`:69-70`）SHALL「断线自动重试（retry，**指数退避**）」，Scenario
   「断线重试」（`:82-85`）要求「按指数退避自动重试，达上限后失败并保持工作区一致」——
   而 `subprocess_backend.py` 的 `clone` / `pull` / `push` 各**单次** `_run`，`_run`（`:158-163`）
   **无 retry / 无退避**：一次网络抖动即整操作失败。
2. **「与 permission 沙箱协作」**（`:61-62`）SHALL 让高危操作（强制推送、**删除远程分支**、
   **历史改写**）走 permission 审批链 —— 而 `client.py`（`:86-101`）**只有** force-push 走审批，
   `delete_remote_branch` / `rewrite_history` 两个原语**在 13 项原语里不存在**（既无实现也无审批门）。

两条都属「规格已 SHALL、代码背离」⇒ conformance 修复（`skip_specs`，先例 `0110` / `0135` / `0137`）。

## What Changes

1. `src/core/git/subprocess_backend.py`：
   - 构造面增 `attempts=3` / `backoff=0.5` / `sleep=time.sleep`（**可注入睡眠** ⇒ 测试零真实等待）；
   - 新增 `_run_remote(*args)`：可重试错误按**指数退避**（`backoff * 2**(n-1)`）重试至 `attempts` 上限，
     超限抛归一错误；`clone` / `pull` / `push` 改走它；
   - 新增模块级 `_TRANSIENT_MARKERS` + `_is_retryable(error, stderr)`：**只**重试「瞬时网络」类
     （`GIT_COMMAND_FAILED` 且 stderr 命中瞬态特征，如 `could not resolve host` / `connection reset` /
     `rpc failed` / `early eof`）；**认证失败不重试**（凭据不会自愈）、**超时不重试**（spec「远程超时」
     Scenario 要求「中止该操作并返回超时错误」）、**冲突不重试**；
   - 新增 `delete_remote_branch(branch, *, remote="origin")`（`git push <remote> --delete <branch>`）
     与 `rewrite_history(message)`（`git commit --amend`）两个原语。
2. `src/core/git/client.py`：
   - `_require_approval()` 泛化为 `_require_approval(op, reason)`；force-push 传 `"git.push(force)"`；
   - 新增 `delete_remote_branch(...)` / `rewrite_history(...)`：**同型审批门**（新 op id），
     非交互（无回调）恒未批 ⇒ `AccessControlError(APPROVAL_REQUIRED)`，**且在触碰后端前阻断**。
3. `src/core/git/backend.py`：`GitBackend` Protocol 补两原语，docstring「13 项」→「15 项」。

## Impact

- 代码：`src/core/git/{subprocess_backend,client,backend}.py`。
- 测试：`tests/test_git.py`（+6：两个新原语的批准 / 未批、op id 分派、非交互默认拒）、
  `tests/test_git_subprocess.py`（+5：抖动重试成功 + 退避序列、超限放弃、认证不重试、非瞬态不重试、
  超时不重试）⇒ `.venv/bin/pytest -q` **1662 passed**（基线 1651 + 11）。
- 文档：`doc/03-interfaces/git-interface.md`（§1 原语表 + §3 后端面 + §4 重试语义）、
  `doc/04-testing/test-cases.md`（§54）、ADR-0131。
- 兼容：`clone` / `pull` / `push` 语义在**首次成功**时逐字不变（不重试即成功 ⇒ 零可观察差异）；
  新增两个原语与两个构造参数均为可选面，既有调用方零改动。

## 已知局限

- **超时不重试**（有意）：spec「远程超时」Scenario 要求超时即「中止该操作并返回超时错误」，
  与「自动重试」在字面上冲突；本 change 取**超时优先中止**（ADR-0131 决策③记录）。
- **退避为同步阻塞睡眠**：`time.sleep` 在 worker 线程内阻塞，无 async 化（本模块是同步
  subprocess 后端，async 化属另一面改动，不在本账）。
- **无 jitter**：指数退避为确定性序列（`0.5, 1.0`），不引入随机抖动 —— 重试上限仅 3 次、
  面向单机 CLI 场景，抖动收益不抵测试确定性损失。
