# Tasks · 0136 composition 覆盖可回退 + 覆盖值类型边界

## 1. 规格（先行）

- [x] 1.1 `specs/composition/spec.md` delta：MODIFIED「层叠解析」（保留覆盖前分层结果 + 回退幂等
      + 覆盖值须整数 generation、布尔按 `PATCH_CONFLICT` 拒绝），原「确定顺序解析」Scenario 逐字保留
- [x] 1.2 `openspec validate 0136-composition-override-revert` 通过

## 2. 测试（先行 · 红）

- [x] 2.1 `tests/test_composition.py::test_revert_restores_pre_patch_layering`
      —— resolve（patch 覆盖 `b`）→ `revert` ⇒ 插件集 == 覆盖前层叠值、`overrides` 清空
- [x] 2.2 `tests/test_composition.py::test_revert_is_idempotent`
      —— 对回退结果再回退，结果不变；且原 `ResolvedSet` 未被就地修改
- [x] 2.3 `tests/test_composition.py::test_revert_without_patch_is_noop`
      —— 无 patch 的 profile：resolve → revert 与 resolve 等价（`layered == plugins`）
- [x] 2.4 `tests/test_composition.py::test_patch_override_bool_rejected`
      —— `overrides={"a": True}` ⇒ `PATCH_CONFLICT`（不静默落为 `1`）
- [x] 2.5 **验红**：暂存实现文件后跑 2.1~2.4 ⇒ 全部失败（`ResolvedSet` 无 `layered` / 无 `revert` /
      `True` 被接受）—— 记录于本文件 §2.5
- [x] 2.6 **验绿**：恢复实现后同一批用例全绿

### 2.5 验红记录

```
.venv/bin/pytest -q tests/test_composition.py -k "revert or bool"
→ 5 failed（AttributeError: 'ResolvedSet' object has no attribute 'layered'；
   'ResolvedSet' object has no attribute 'revert'；'CompositionEngine' object has no attribute 'revert'；
   DID NOT RAISE CompositionError —— True 被当作 generation 1 接受）
```
（测试先行：以上在实现落盘**之前**运行，无需 stash 回退实现。）

## 3. 实现

- [x] 3.1 `models.py`：`ResolvedSet` 增必填 `layered: list[PluginRef]`（覆盖前分层结果；`revert` 的恢复目标）
- [x] 3.2 `resolver.py`：`resolve()` 携带 `layered=merged`
- [x] 3.3 `resolver.py`：新增 `revert(resolved) -> ResolvedSet`（返回新结果、幂等、不改实参）
- [x] 3.4 `resolver.py`：`apply_patch` 拒 `bool`（E70）
- [x] 3.5 `engine.py`：门面 `CompositionEngine.revert` 透出

## 4. 文档

- [x] 4.1 `doc/03-interfaces/composition-interface.md`：§2 `ResolvedSet` 增 `layered`；§3 门面增 `revert`；
      §5 约束补「回退 = 移除 patch 覆盖，幂等，返回新结果」
- [x] 4.2 `doc/01-architecture/adr.md`：ADR-0129 + `## 变更追踪` 行
- [x] 4.3 `doc/04-testing/test-cases.md`：§52（TC-COMPREV，change 0136 / ADR-0129，账本 E75 + E70）

## 5. 门禁（直连二进制，禁 `uv run`）

- [x] 5.1 `.venv/bin/ruff check src tests` —— 绿
- [x] 5.2 `.venv/bin/ruff format --check src tests` —— 绿
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` —— 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` —— 全绿（基线 1634 + 5 = 1639）
- [x] 5.5 `openspec validate --all` —— 30 passed / 0 failed

## 6. 收口

- [x] 6.1 手工归档：delta 并入 canonical → `shutil.move` 至 `archive/2026-10-06-0136-composition-override-revert/`
- [x] 6.2 台账回填：`coding-plan/phase-34.md`（E75 / E70 行 + §9 表）；`coding-plan/README.md` 3 处索引行
- [x] 6.3 记忆更新：`MEMORY.md` + `coding-plan-leftover-walkthrough.md`
- [x] 6.4 单次提交（`fix(composition): 覆盖可回退 + 拒布尔覆盖值（change 0136）`）
