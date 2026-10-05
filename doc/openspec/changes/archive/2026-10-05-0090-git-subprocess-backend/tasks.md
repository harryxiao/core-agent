# tasks — 0090 git 真实后端（stdlib subprocess）

## 1. 规格先行
- [x] 1.1 `specs/git/spec.md` delta：MODIFIED「GitClient 抽象接口与依赖注入隔离」（缺省 subprocess 后端 + 归一错误码 + 2 场景）
- [x] 1.2 `openspec validate 0090-git-subprocess-backend` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_git_subprocess.py`（新）：临时仓库 init/commit/status/log/diff 往返（真实 subprocess）
- [x] 2.2 branch/checkout/merge（含冲突走 `MergeResult(merged=False)`）/stash/stash_pop
- [x] 2.3 错误归一：`build_backend()` 返回 `SubprocessGitBackend`；`GIT_COMMAND_FAILED` 兜底
- [x] 2.4 `tests/test_git.py`：`test_no_backend_raises` → 「缺省工厂给出 subprocess 适配器」
- [x] 2.5 红：`git stash push -u -- src/` 后新增用例失败 → `git stash pop`

## 3. 实现（绿）
- [x] 3.1 `src/core/git/errors.py`：新增 `GIT_COMMAND_FAILED`
- [x] 3.2 `src/core/git/subprocess_backend.py`（新）：`SubprocessGitBackend`（13 原语 + `_invoke` / `_classify` / `_parse_branch`）
- [x] 3.3 `src/core/git/backend.py`：`build_backend()` 返回 `SubprocessGitBackend()`
- [x] 3.4 `src/core/git/__init__.py`：导出 `SubprocessGitBackend`

## 4. 四门
- [x] 4.1 `ruff check src tests`
- [x] 4.2 `ruff format --check src tests`
- [x] 4.3 `pyright`（0 errors）
- [x] 4.4 `.venv/bin/pytest -q` 全绿

## 5. 文档
- [x] 5.1 `doc/03-interfaces/git-interface.md`：§3 生产后端 + §4 `GIT_COMMAND_FAILED`
- [x] 5.2 `doc/12-git/git-architecture.md`：§2 组件表落实现
- [x] 5.3 `doc/01-architecture/adr.md`：ADR-0085 + 映射表行
- [x] 5.4 `doc/04-testing/test-cases.md`：TC-GIT-12/13

## 6. 归档与记账
- [x] 6.1 手动合并 delta → `doc/openspec/specs/git/spec.md`；`shutil.move` 变更目录到 `archive/2026-10-05-0090-…`
- [x] 6.2 `openspec validate --all` 全绿
- [x] 6.3 账本：`phase-20.md` §1/§4.1 C2 收口（含「装配待消费者」偏离说明）+ `phase-19.md` §1/§5 + `coding-plan/README.md`
- [x] 6.4 记忆 `coding-plan-leftover-walkthrough.md` + `MEMORY.md`
- [x] 6.5 提交 `feat(git): 真实后端 stdlib subprocess（change 0090）`
