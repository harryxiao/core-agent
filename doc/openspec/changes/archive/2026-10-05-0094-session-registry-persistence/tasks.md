# tasks — 0094 会话注册表持久化

## 1. 规格先行
- [x] 1.1 `specs/ui/spec.md` delta：ADDED「会话注册表持久化与跨入口共享」（3 场景）
- [x] 1.2 `openspec validate` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_session_registry.py`（新）：持久化重开可见 / `path=None` 内存 / **写时合并不覆盖他进程条目** / `list` 形状 / 损坏文件空态 / 读透见到晚写者（6 例）
- [x] 2.2 `tests/test_ui.py`：跨实例 id 可用 / 默认内存注册表仍拒未知 id（回归锚）/ `list_sessions`
- [x] 2.3 `tests/test_serve.py`：`GET /sessions` 有 / 空
- [x] 2.4 `tests/test_entry.py`：CLI `session create` 对新注册表可见 / `session list` / **`session create` → 另一进程 `run --session`** 端到端（fake loop，不出网）/ 未登记 id 仍拒
- [x] 2.5 红：以上用例在实现前失败（`ImportError: cannot import name 'SessionRegistry'`）

## 3. 实现（绿）
- [x] 3.1 `src/core/ui/sessions.py`（新）：`SessionRegistry`（读透 + 写时合并 + `path=None` 内存）
- [x] 3.2 `src/core/ui/api.py`：`registry` 注入 / `create_session` / `_require_session` / `list_sessions`
- [x] 3.3 `src/core/ui/fastapi_serve.py`：`GET /sessions`
- [x] 3.4 `src/core/ui/__init__.py`：导出 `SessionRegistry`
- [x] 3.5 `src/core/entry.py`：`_build_ui` 注入 / `session` 子命令接共享注册表 + `list` / `sessions` help 消歧
- [x] 3.6 绿：全部用例通过

## 4. 四门
- [x] 4.1 `ruff check src tests`
- [x] 4.2 `ruff format --check src tests`
- [x] 4.3 `pyright`（0 errors / 0 warnings / 0 informations）
- [x] 4.4 `.venv/bin/pytest -q` 全绿（1090 passed）

## 5. 文档
- [x] 5.1 `doc/03-interfaces/ui-interface.md` §1.2 端点表 9 → 10 + §1.3 会话注册表
- [x] 5.2 `doc/01-architecture/adr.md`：ADR-0089 + 映射表行
- [x] 5.3 `doc/04-testing/test-cases.md`：TC-UI-10

## 6. 归档与记账
- [x] 6.1 手动合并 delta → `doc/openspec/specs/ui/spec.md`；`shutil.move` 变更目录到 archive
- [x] 6.2 账本：`phase-19.md` §9 步 10 活 LLM 冒烟销账 + 新增行（会话注册表缺口 / `sessions` vs `session list` 同名异物）
- [x] 6.3 记忆更新
- [x] 6.4 提交 `feat(ui): 会话注册表持久化（change 0094）`
