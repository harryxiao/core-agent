# design — 0090 git 真实后端（stdlib subprocess）

## 决策

### ① 后端形态：`SubprocessGitBackend`（stdlib `subprocess`，零三方依赖）

`git-interface.md` §3 明列首选项就是「subprocess 直调 git CLI」；且 ADR-0044「核心零三方依赖」红线
否决 gitpython / dulwich。故实现为纯 stdlib：`subprocess.run(["git", *args], cwd=…, capture_output=True,
text=True, timeout=…)`。

**`cwd` 归属后端**（构造参数，缺省 `Path.cwd()`）：`GitClient` 无状态、其 13 项原语的多数（status/commit/
log/…）作用于「当前仓库」，故把仓库根绑在**后端实例**上；`init(path)` / `clone(url, path)` 完成后把
`self._cwd` 指向新仓库（与真实「一次会话绑定一个仓库」一致）。

### ② 错误归一（`_classify`）—— **不回显 stderr**

`_invoke` 捕获两类底层异常：
- `subprocess.TimeoutExpired` ⇒ `GIT_REMOTE_TIMEOUT`（超时）；
- `FileNotFoundError`（git 未安装）⇒ `GIT_COMMAND_FAILED`。

子命令非零退出 ⇒ `_classify(stderr.lower())`：
- 命中认证特征（`authentication failed` / `could not read username` / `permission denied (publickey)` /
  `invalid username or password` / `terminal prompts disabled`）⇒ `GIT_AUTH_FAILED`；
- 含 `conflict` ⇒ `GIT_CONFLICT`；
- 其余 ⇒ `GIT_COMMAND_FAILED`。

**关键安全点**：异常**文本是固定中文提示**，**不拼接 stderr** —— git 的 stderr 可能含
`https://user:token@host/...`。对齐规格 R3「不泄露凭据与私有仓库地址」与全局「密钥只引用不读取、绝不进
日志/记忆」。

### ③ 新增 `GIT_COMMAND_FAILED`

既有 4 码语义都不覆盖「本地子命令非零退出」（`GIT_WORKTREE_DIRTY` 字面是「工作区有未提交改动」，硬套是
语义滥用）。**加法式**新增通用码，既有 4 码语义与既有测试不变（`test_git.py` 四码用例继续通过）。

### ④ `merge` 冲突走 **结果**而非异常

`git merge <branch>` 非零退出且 `git diff --name-only --diff-filter=U` 非空 ⇒ 返回
`MergeResult(merged=False, conflict_files=[...])`（对齐 Protocol 与接口 §1「冲突时返回 merged=False 并报告冲突点」）；
非零且**非**冲突 ⇒ 抛 `GitError`。

### ⑤ `status` 解析 `git status --porcelain --branch`

- `## ` 行 → 分支名（去 `...upstream`；`No commits yet on <b>` → `<b>`；`HEAD (no branch)` → `HEAD`）；
- `?? <path>` → untracked；
- XY 含 `U` 或 `AA`/`DD` → conflicted；
- 其余 → changed。

### ⑥ `log` 用 `--pretty=format:` + `\x1f` 分隔

`%H`(commit_id) `\x1f` `%an`(author) `\x1f` `%s`(message) `\x1f` `%aI`(ISO ts)。用不可打印分隔符避免
提交信息里的空格/竖线污染解析。

### ⑦ 不动既有测试语义（除一处必然变更）

`tests/test_git.py::test_no_backend_raises` 断言「`GitClient()` 无后端 ⇒ 抛 `GIT_REMOTE_TIMEOUT`」——
本变更**正是**要改这个行为（缺省后端不再是错误）。替换为「缺省工厂给出 subprocess 适配器」的断言
（`build_backend()` 的 isinstance）。**其余 git 测试零改动**。

> 注意：**不在测试里**对当前仓库真实执行写操作 —— 所有子进程用例都在 `tmp_path` 的临时仓库内，
> 并以 `GIT_AUTHOR_*` / `GIT_COMMITTER_*` 环境变量提供提交身份（免 `git config`）。

## 影响面

- **`GitClient`**：`_require_backend()` 不再可能抛「离线未接」（工厂恒返回实例）；`GitClient()` 现在真的可用。
- **`test_git.py`**：仅 `test_no_backend_raises` 一处变更（行为有意变更）。
- **无 Runtime / CLI / 工具面改动**：git 是 capability 非 tool，消费者（coding 工作流）未出现，故不造空接缝。
