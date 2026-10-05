# tasks — 上下文压实「出厂默认阈值」守护用例（change 0097）

## 1. 事实核定（改前）
- [x] 1.1 核默认轮数阈值：`_ROUND_THRESHOLD = 10`（`context/compactor.py:20`）
- [x] 1.2 核默认 token 预算：`token_budget = 65536`（`loop/default.py:121`），组合根未覆盖
- [x] 1.3 核既有覆盖：谓词 + loop 级各有用例，但**全部注入自定义阈值** ⇒ 默认值零断言

## 2. 测试（红→绿）
- [x] 2.1 新增 `tests/test_context_compaction.py`：默认轮数边界 / 默认预算边界 / 缺省装配恰触发一次
- [x] 2.2 绿证：`pytest tests/test_context_compaction.py` = 3 passed
- [x] 2.3 全量 pytest **1105 passed**（基线 1102 + 3）；四门全绿
- [x] 2.4 `src/` 零改动

## 3. 规格
- [x] 3.1 判**规格中性**（`skip_specs`）：规格「上下文自动压实」已含「轮数或 token 达阈值」条款，数值属实现缺省
- [x] 3.2 `openspec validate 2026-10-05-0097-context-compaction-default-threshold-tests` 通过

## 4. 收口
- [x] 4.1 `coding-plan/phase-19.md` §9 步 10：补 0097 后续行
- [x] 4.2 手动归档（`shutil.move` 进 `archive/2026-10-05-0097-...`）+ `openspec validate --all` 全绿
- [x] 4.3 记忆更新 + 提交（`test(context): 压实默认阈值守护用例（change 0097）`）
