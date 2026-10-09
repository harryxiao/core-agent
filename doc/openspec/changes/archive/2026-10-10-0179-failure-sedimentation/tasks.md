# Tasks: 失败经验的独立沉淀面（failure sedimentation）

**测试先行**：每层先写测试（红），再实现（绿）。四门禁直连二进制、**禁** `uv run`。

## Layer A —— 纯函数 `failure_digest`

- [ ] A1. 测试：`tests/test_loop_failure_memory.py`（新）先写 `failure_digest` 用例
  （红：`ImportError: failure_digest`）—— 任务/原因/失败轮行/失败步行齐备 / `reason=""` 走兜底文案 /
  无失败轮时仍非空 / 逐行脱敏 / 整体有界（≤ `_MAX_MEMORY_ENTRY`）—— pin「执行循环」新增 Scenario ③
- [ ] A2. 实现：`src/core/loop/default.py` 新增 `failure_digest` + `_FAILURE_REASON_FALLBACK` + `_FAILURE_STEP_MARK`

## Layer B —— 写入接线 `src/core/loop/default.py`

- [ ] B1. 测试：追加 `tests/test_loop_failure_memory.py`（红：无 `loop.failure.*` 条目）——
  失败轮另立条目（id / tags / kind / source / trace / session 断言）/ 成功轮**不写**（逐字回归锚）/
  预算终止（`limit_reason` 入内容）/ 不可解析输出（`turn_failed` 另一来源）/ 未注入 memory 无写 /
  按 trace 回滚即消失 —— pin「执行循环」新增 Scenario ①②
- [ ] B2. 实现：`remember` 增 `failed` / `reason` / `task` 三参数 + 第三条写入；`loop/protocol.py` 同步签名；
  调用点 `default.py:445` 传参

## Layer C —— 压实豁免 `src/core/memory/store.py`

- [ ] C1. 测试：追加 `tests/test_memory.py`（红：failure 条目被吸收/被迁 L4）——
  压实跳过 `failure` 条目（仍在 L2、摘要 tags 不含它、同批普通条目迁 L4）/ `forget` 不豁免 /
  failure 条目可被 `read()` 命中 —— pin「记忆压实」新增 Scenario ①②
- [ ] C2. 实现：`_PRESERVE_TAGS` + `_episodic_groups()` 一处 `continue`

## Layer D —— 收尾

- [ ] D1. 规格 delta：`specs/loop/spec.md`（MODIFIED「执行循环」）、`specs/memory/spec.md`（MODIFIED「记忆压实」）
  —— 已完成（既有 Scenario 逐字保留：loop 36 → 39、memory 17 → 19）
- [ ] D2. `doc/01-architecture/adr.md`：**ADR-0170** + 追踪行
- [ ] D3. 模块文档：`doc/02-modules/loop.md` §3.3（失败另立条目）、`doc/02-modules/memory.md` §4（失败条目不进压实材料）
- [ ] D4. 接口文档：`doc/03-interfaces/loop-interface.md`（`remember` 三参数 + 新条目）、
  `doc/03-interfaces/memory-interface.md`（压实材料排除 `failure` 标签）
- [ ] D5. `doc/04-testing/test-cases.md`：新增 `## 92. 失败经验的独立沉淀面（TC-FAILMEM）` + 基线 bump
- [ ] D6. `coding-plan/known-risk.md`：§1 新 **E116** 行 + §3 ADR-0170 局限行
- [ ] D7. 四门禁 + `openspec validate <全目录名>` + 手工归档 + `openspec validate --all`
- [ ] D8. 记忆（`MEMORY.md` + `coding-plan-leftover-walkthrough.md`）+ **单次提交**
