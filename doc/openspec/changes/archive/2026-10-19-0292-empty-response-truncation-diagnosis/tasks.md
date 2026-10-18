# 任务 — 0292 空响应的截断成因诊断

## 1. 规格

- [x] 1.1 `specs/loop/spec.md`：MODIFIED「推理动作解析与失败可见」——空内容分支读取
      `finish_reason`，`length` 时明示截断/预算可能被思考耗尽；信号不可用时维持原文案；
      失败语义不变。
- [x] 1.2 同 delta 新增两个 Scenario（截断信号 / 无截断信号）。
- [x] 1.3 `openspec validate 2026-10-19-0292-empty-response-truncation-diagnosis` 全绿。

## 2. 代码（测试先行）

- [x] 2.1 `tests/test_loop_output_protocol.py`：空内容 + `finish_reason="length"` ⇒
      `reply` 含 `LLM_PLAN_PARSE_FAILED` 且含截断/预算成因；`failed is True`、无工具执行。
- [x] 2.2 同文件：空内容 + `finish_reason` 缺失/空串/`stop` ⇒ `reply` 逐字
      `LLM_PLAN_PARSE_FAILED: 空响应`（既有断言保持）。
- [x] 2.3 同文件：空白串（`"   "`）+ `finish_reason="length"` 同样命中截断文案。
- [x] 2.4 `src/core/loop/planner.py`：`_parse` 空内容分支按 `finish_reason == "length"`
      追加有界成因；其余分支逐字不变。

## 3. 文档

- [x] 3.1 `doc/01-architecture/adr.md`：ADR-0282（含被拒方案与局限）。
- [x] 3.2 `coding-plan/known-risk.md`：E228 行 + ADR-0282 局限索引。
- [x] 3.3 `doc/04-testing/test-cases.md`：§205。
- [x] 3.4 `doc/02-modules/loop.md`：失败措辞补「空内容 + length」分支。

## 4. 门禁

- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`
- [x] 4.4 `.venv/bin/pytest -q`（3252 → 3254）
- [x] 4.5 反证 1/1（cp 到 /tmp，禁 `git checkout`；复原后 md5sum 一致）：
      去掉 `finish_reason == "length"` 分支 ⇒ 截断文案用例红。
- [x] 4.6 `openspec validate --all` 全绿（归档前）。

## 5. 收尾

- [x] 5.1 `openspec archive -y 2026-10-19-0292-empty-response-truncation-diagnosis`
- [x] 5.2 仅暂存本 change 路径与实现/测试/文档路径并提交（不 `git add -A`）。
