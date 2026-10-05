# 0090 — git 真实后端（stdlib subprocess，零三方依赖）（Phase 20 C2）

## 为什么

账本 `coding-plan/phase-20.md` §1 C2：git 是 C 类中**唯一零凭证**项 —— 抽象（`GitBackend` Protocol）、
核心操作（`GitClient`）、.git 保护、高危审批**全部已落地且已测**，唯一缺的是**生产后端实现**：
`build_backend()` 直接抛「离线未接」（`backend.py:50-55`），`GitBackend` 在生产**无任何实现**。
`git-architecture.md` §1 明文「Git 独立为 capability（**非 tool-use 内置工具**）」⇒ 无循环工具面待接，
缺的就是底层适配器本身。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/git/subprocess_backend.py` | **新增 `SubprocessGitBackend`**：stdlib `subprocess` 直调 git CLI 实现 13 项原语；异常归一领域错误码；错误信息**不回显** stderr（可能含凭据/私有地址） |
| `src/core/git/backend.py` | `build_backend()` 由「抛离线未接」改为返回 `SubprocessGitBackend()` |
| `src/core/git/errors.py` | 新增错误码 `GIT_COMMAND_FAILED`（通用子命令失败 —— 既有 4 码不含「本地命令非零退出」） |
| `src/core/git/__init__.py` | 导出 `SubprocessGitBackend` |
| `doc/openspec/specs/git/spec.md` | MODIFIED「GitClient 抽象接口与依赖注入隔离」：补缺省后端 = stdlib subprocess + 归一错误码；补 2 场景 |
| `doc/03-interfaces/git-interface.md` | §3 补生产后端口径；§4 增 `GIT_COMMAND_FAILED` 行 |
| `doc/12-git/git-architecture.md` | §2 组件表「Git 操作器」落到实现 |
| `doc/01-architecture/adr.md` | ADR-0085 + 映射表行 |
| `doc/04-testing/test-cases.md` | TC-GIT-12/13 |
| `tests/test_git_subprocess.py` | 新：真实临时仓库往返（init/commit/status/log/diff/branch/checkout/merge 冲突/stash） |

## 决策

- **stdlib `subprocess` 直调 git CLI**（不引 gitpython / dulwich）：对齐 ADR-0044「核心零三方依赖」红线，
  也是 `git-interface.md` §3 已列的首选项（「subprocess 直调 git CLI」）。
- **新增 `GIT_COMMAND_FAILED`**：既有 4 码（AUTH/TIMEOUT/WORKTREE_DIRTY/CONFLICT）无「本地子命令非零退出」
  的落点；真后端必须有通用失败码。改动**纯加法**，既有码语义不变。
- **错误信息不回显原始 stderr**：规格 R3「不泄露凭据与私有仓库地址」—— 归一为固定的中文提示，
  不把 git 的 stderr（可能含 `https://user:token@host`）带进异常文本 / 日志 / 记忆。

## 明确不做（**偏离 phase-20 §4.1 原记，理由如下**）

- **不做组合根装配、不做 `git` CLI 入口**：git 是 **capability 非 tool**（`git-architecture.md` §1），其消费者是
  **尚未存在的 coding 工作流**。此刻把 `GitClient` 塞进 `Runtime` 或加一个 `core-agent git <verb>` 入口 =
  **无消费者的空接缝**（与 `phase-20.md` §2 对 E27 的判定同理）。补齐真实后端后，装配**待消费者出现时**并入
  该消费者的 change。故 C2 的「代码半」以**后端实现 + 测试**收口，装配另行。
- **不做远程凭据 keychain 集成**（规格 R3 的凭据半）：归 Phase 19 §5（需系统 keychain）。
- **不做远程重试 / 连接释放**（规格 R5）：属远程可靠性半，本变更只保证错误**归一**（超时 → `GIT_REMOTE_TIMEOUT`），
  不实现退避重试策略（无远程消费者，YAGNI）。
