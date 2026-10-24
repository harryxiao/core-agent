# Tasks — TUI 优雅退出 `/exit`（0315）

## 1. 规格与测试先行

- [x] 1.1 `proposal.md` / `design.md` / `specs/ui/spec.md`（ADDED ×1，+4 scen）
- [x] 1.2 新增 `tests/test_exit_graceful.py`（6 条，先红：`AttributeError: 'DefaultLoop' object
      has no attribute 'flush_post_turn'`）：
      - `DefaultLoop.flush_post_turn()`：有在途后台链 ⇒ 等其收束后 `True`；
        上限 0.1s + 阻塞观察者 ⇒ 1s 内 `False` 且 task 未被取消；无在途 ⇒ 立即 `True`
      - `UIAPILayer.flush_post_turn()`：委托并透传布尔；无该接缝的 loop ⇒ `True`；
        未登记会话 ⇒ `UI_SESSION_NOT_FOUND`
- [x] 1.3 `tests/test_repl.py`（4 条，先红）：`/exit` 空闲先 flush 再退出 / 超时仍退出 /
      忙态拒绝 / 带参拒绝；两处硬编码命令清单（功能面与 Textual 浮层）均含 `/exit`

## 2. 实现

- [x] 2.1 `src/core/loop/default.py`：公开 `flush_post_turn(timeout=None)`（包装
      `_await_post_turn`，缺省用 `_post_turn_wait_timeout` = 120s；超时不取消后台任务）
- [x] 2.2 `src/core/ui/api.py`：`async def flush_post_turn(session_id) -> bool`（会话校验 +
      `getattr` 鸭子类型委托；无接缝 ⇒ `True`，pyright strict 用 `cast` 收窄）
- [x] 2.3 `src/core/ui/repl.py`：`_COMMANDS` 登记 `/exit`；分发链在 `_turn_busy` 检查**之前**
      插入 `_handle_exit_command`（忙态专用提示、带参拒绝、置忙 + worker）；
      `_exit_gracefully`（提示 → flush → 明示 → `self.exit()`）

## 3. 门禁

- [x] 3.1 聚焦跑：`uv run pytest tests/test_exit_graceful.py tests/test_repl.py` ⇒ **121 passed**
      in 143.74s
- [x] 3.2 全量 `uv run pytest`（基线 3636）⇒ **3646 passed**, 27 warnings in 226.67s（+10）
- [x] 3.3 `uv run ruff check` ⇒ All checks passed；`uv run ruff format --check` ⇒ 5 files already
      formatted（改动文件）
- [x] 3.4 `uv run pyright` ⇒ 0 errors, 0 warnings, 0 informations
- [x] 3.5 反证 3/3（`cp` 到 `/tmp` + `md5sum` 复原，复原后 `8a16ab72c4947b12ebc8956e2f7d3c2f`）：
      去掉 flush 调用 ⇒ `test_exit_command_flushes_then_exits` 红（`flush_calls 0 != 1`）；
      删除忙态检查 ⇒ `test_exit_command_rejects_while_busy` 红（`flush_calls 1 != 0`）；
      结果文案硬编码为「已保存」⇒ `test_exit_command_timeout_still_exits` 红
- [x] 3.6 真实进程复跑（pty，120×40）：空闲输入 `/exit` ⇒ **0.36s** 退出、status 0；
      同环境 Ctrl+Q ⇒ **0.37s**、status 0（< 2s）。无在途收尾时提示行不保证被绘制
      （flush 同 tick 返回即 `exit()`）；等待路径由 TC-EXIT-FLUSH-02 覆盖

## 4. 文档与收口

- [x] 4.1 `doc/01-architecture/adr.md`：ADR-0305（优雅退出接缝；被拒方案见 design §4）+ 索引行
- [x] 4.2 `coding-plan/known-risk.md`：E251 + §3 ADR-0305 局限行
- [x] 4.3 `doc/04-testing/test-cases.md`：§228（TC-EXIT-FLUSH / API / CMD，含反证与实测数）
- [x] 4.4 `doc/03-interfaces/ui-interface.md` 同步 `/exit`、`flush_post_turn` API 与 §6 决策清单
- [x] 4.5 `openspec validate --all` 全绿；全量 pytest 实测数与反证结果已回填本文件
- [ ] 4.6 用户确认后归档 + 提交；回填 walkthrough / MEMORY.md
