# tasks — 写类工具按次快照（回滚不再恢复错文件）（change 0129 / phase-34 E64）

## 1. 规格（先行）
- [x] 1.1 `specs/tool-use/spec.md`：MODIFIED「撤销与时间旅行回滚」—— 正文补「撤销函数 SHALL 按次生成
      （每次成功执行取得一份绑定**该次**写入前快照的闭包）；同一工具实例跨多次调用 SHALL 各持独立快照
      （按 trace 的 LIFO 序），SHALL NOT 被后续调用覆写；撤销第 N 次 SHALL 恢复**该次**内容」
- [x] 1.2 同 delta：新增 2 Scenario「同一工具多次写入各自独立回滚」「跨 trace 不串」（其余 Scenario 逐字保留）
- [x] 1.3 `openspec validate 0129-tool-per-call-snapshots` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_tool_use.py`：同一 `file_write` 写 A（A 原存在）再写 B（B 原不存在）⇒ 回滚后
      **A 复原 / B 删除**（现状：两次 undo 都作用于 B ⇒ A 停留在写入后内容 ⇒ 红）
- [x] 2.2 同文件：三次写 + `file_patch` **交错**（write → patch → write）⇒ 逆序逐次还原到最初内容
      （现状：write 的共享 `snap` 被最后一次覆写 ⇒ 第一次撤销还原成中间态 ⇒ 红）
- [x] 2.3 同文件：**跨 trace** —— `t1` 写 A、`t2` 写 B 后只回滚 `t1` ⇒ A 复原且 B **逐字不变**
- [x] 2.4 同文件：空栈取撤销闭包 ⇒ **no-op**（不抛异常、不动文件系统）
- [x] 2.5 同文件：既有 `test_undeclared_write_warning` 的 `undo=lambda: None` 桩随契约改为工厂形态
- [x] 2.6 红：2.1 / 2.2 / 2.3 在实现前**必失败**

## 3. 实现
- [x] 3.1 `src/core/tools/tool.py`：`Tool.undo` 类型改 `Callable[[], Callable[[], None]] | None`，
      docstring 写明「按次生成的撤销闭包工厂」
- [x] 3.2 `src/core/tools/builtin.py`：`file_write` / `file_patch` 取消闭包级共享 `snap` ⇒ 每次调用
      **写入成功后**压一份快照，`undo()` LIFO 弹出并返回绑定该快照的闭包（`_restore` 签名不变）
- [x] 3.3 `src/core/tools/provider.py`：记录 Effect 时取 `tool.undo()`（该次调用的闭包）

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`（须 0/0/0）
- [x] 4.4 `.venv/bin/pytest -q`（基线 1610 passed ⇒ 新增后按实累加）
- [x] 4.5 `openspec validate --all`（归档前后各一次，30 passed / 0 failed）

## 5. 归档
- [x] 5.1 手工合并 delta 进 canonical `doc/openspec/specs/tool-use/spec.md`（`### Requirement:` 正文紧接、
      `#### Scenario:` 后不留空行）
- [x] 5.2 目录 `shutil.move` 至 `doc/openspec/changes/archive/2026-10-06-0129-tool-per-call-snapshots/`

## 6. 文档与账本
- [x] 6.1 `doc/01-architecture/adr.md`：**ADR-0122**（为何取「闭包自带身份」而非「弹出栈顶」/ 契约变更面 /
      已知局限：并发同工具调用不在保证内；变更追踪表行）
- [x] 6.2 `doc/03-interfaces/tool-use-interface.md` §2：补 `Tool.undo` 工厂契约与其理由
- [x] 6.3 `doc/02-modules/tool-use.md`（若记 undo 语义则同步）；`doc/04-testing/test-cases.md` 增 TC 行
- [x] 6.4 `coding-plan/phase-34.md`：§1 真缺陷表 **E64** 行标「已落地（change `0129` / ADR-0122）」；
      §9 台账行同步；`coding-plan/README.md` 索引同步
- [x] 6.5 记忆：`coding-plan-leftover-walkthrough.md` + `MEMORY.md`

## 7. 提交
- [x] 7.1 单次提交：`fix(tool-use): 写类工具按次快照（change 0129）`
- [x] 7.2 **不提交**：`config.yaml`、`.claude/settings*.json`（D4 不动）、`coding-plan/phase-3-prompt.md`、
      `AI-SoftwareEngineer-4.md`、`coding-plan/phase-32.md`、`src-tauri/Cargo.lock`、`node_modules/`、
      `frontend/dist/`
