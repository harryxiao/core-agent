# Tasks — 基准会话隔离与 CJK token 估算（change 0245）

## 1. 规格

- [x] 1.1 `evolution/spec.md`「评测基建」MODIFIED：基准会话不写全局派生 + 1 Scenario
- [x] 1.2 `openspec validate 2026-10-17-0245-benchmark-isolation-and-cjk-tokens`

## 2. 红测试

- [x] 2.1 基准会话压实：会话摘要与归档照常、派生抽取与提升 0 调用
- [x] 2.2 非基准会话照常派生（对照，防误伤）
- [x] 2.3 组合根接线：执行面开 ⇒ `ephemeral_sessions` 含 `bench`；关 ⇒ 空
- [x] 2.4 CJK 估计：纯中文按字计、纯 ASCII 与旧口径一致、空串仍为 1
- [x] 2.5 记忆读预算按 CJK 估计裁剪（同预算下中文条目更早触顶）
- [x] 2.6 三层窗口：中层字符上界按 2 字符/token 换算

## 3. 实现

- [x] 3.1 `core/tokens.py`（中性估计器）
- [x] 3.2 `context.budget` 改用共享估计器；`memory._truncate` 同步
- [x] 3.3 `context.window._CHARS_PER_TOKEN = 2`
- [x] 3.4 `MemoryStore.ephemeral_sessions` + `_summarize_sessions` 守卫
- [x] 3.5 组合根按执行面门控传 `("bench",)`
- [x] 3.6 接口/模块文档同步

## 4. 门禁与反证

- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`
- [x] 4.4 `.venv/bin/pytest -q`
- [x] 4.5 反证：摘 `ephemeral` 守卫 ⇒ 1 红；拆 `core.tokens` 回 `len//4` ⇒ 2 红；
      窗口改回 4 ⇒ 1 红；复原 md5 同

## 5. 收口

- [x] 5.1 归档到 `doc/openspec/changes/archive/2026-10-17-0245-benchmark-isolation-and-cjk-tokens/`
- [x] 5.2 ADR-0233 + 变更追踪表
- [x] 5.3 台账 E180（`known-risk.md` §1/§3）+ 测试节 §156（`test-cases.md`）
- [x] 5.4 接口文档同步（`memory-interface.md` / `context-interface.md`）
- [x] 5.5 单次提交（change 0245 / ADR-0233 / 台账 E180）
