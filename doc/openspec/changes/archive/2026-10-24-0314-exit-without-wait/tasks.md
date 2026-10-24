# Tasks — TUI 退出不等待在途阻塞工作（0314）

## 1. 规格与测试先行

- [x] 1.1 `proposal.md` / `design.md` / `specs/ui/spec.md`（ADDED ×1）
- [x] 1.2 新增 `tests/test_repl_exit.py`（红）：
      - `_DaemonExecutor`：结果交付 / 异常转交 / `shutdown` 后拒绝提交 /
        `shutdown(wait=True)` 对在途任务立即返回（`threading.Event` 卡住 worker，< 0.5s）
      - `run_repl`（monkeypatch `build_app`）：假 app 收到**非空** `loop`，且其默认执行器为
        `_DaemonExecutor`；假 app 起一个阻塞执行器任务后返回 ⇒ `run_repl` 1s 内返回
      - 空闲路径：假 app 立即返回 ⇒ `run_repl` 立即返回、`loop` 已关闭

## 2. 实现

- [x] 2.1 `src/core/ui/repl.py`：模块级 `_DaemonExecutor`（守护线程 + 不 join 的 shutdown）
- [x] 2.2 `_close_loop(loop)`：取消残留任务 → `shutdown_asyncgens` → `close`（**不** join 执行器）
- [x] 2.3 `run_repl`：自建 loop + 装配执行器 + `app.run(loop=loop)`；收尾 `_close_loop`

## 3. 门禁

- [x] 3.1 聚焦跑：`uv run pytest tests/test_repl_exit.py tests/test_repl.py` —— **118 passed**
- [x] 3.2 全量 `uv run pytest`（基线 3629）—— **3636 passed**（+7）
- [x] 3.3 `uv run ruff check` / `uv run ruff format --check`（改动文件）—— 全绿
- [x] 3.4 `uv run pyright`（`src` 0 error）—— 0 error
- [x] 3.5 反证（`cp` 到 `/tmp` + `md5sum` 复原）—— **3/3 见红**：
      ① 默认执行器换回系统 `ThreadPoolExecutor` ⇒ 入口用例红 + pty 退出 **21.9s**；
      ② `shutdown` 改为 join（`super().shutdown(wait=wait)`）⇒ 不成立（内部执行器无线程），
         改用「线程 `daemon=False`」⇒ daemon 判定用例红；
      ③ `run_repl` 换回 `app.run()` ⇒ 入口用例 ×2 红 + pty 退出 **22.1s**
- [x] 3.6 真实进程复跑：pty 起 TUI → Ctrl+Q —— 空闲退出 **0.27s**；在途 45s 阻塞工作下
      **0.36s**（退出码 0）

## 4. 文档与收口

- [x] 4.1 `doc/01-architecture/adr.md`：ADR-0304（守护线程执行器 + 显式 loop；被拒方案见
      design §3.3）
- [x] 4.2 `coding-plan/known-risk.md`：E250 + §3 局限行
- [x] 4.3 `doc/04-testing/test-cases.md`：§227（TC-EXIT-*）
- [x] 4.4 `doc/03-interfaces/ui-interface.md` / `ui-scheme.md` 同步退出语义
      （`ui-scheme.md` 无既有退出一节，未改；`ui-interface.md` 增段落）
- [x] 4.5 `openspec validate --all` 全绿（**32 passed, 0 failed**，含本 active change）；
      全量 pytest 实测数与反证结果已回填本文件
- [ ] 4.6 用户确认后归档 + 提交；回填 walkthrough / MEMORY.md
