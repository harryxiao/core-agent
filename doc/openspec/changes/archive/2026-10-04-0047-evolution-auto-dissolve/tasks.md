# Tasks: 观察期回归自动溶解（evolution auto-dissolve）

## 1. 规格先行

- [x] 1.1 `specs/evolution/spec.md` delta：ADDED「观察期回归自动溶解（auto-dissolve）」
      （开窗 / 判定 / 冻结 / 可追溯，5 个 Scenario）
- [x] 1.2 `openspec validate 0047-evolution-auto-dissolve` 全绿

## 2. 契约与接口文档

- [x] 2.1 `03-interfaces/evolution-interface.md`：观察期接口（`ObservationRegistry` /
      `observe`）+ 口径表 + `dissolved` 结局
- [x] 2.2 `01-architecture/adr.md`：ADR-0052（独立注册表 + 绝对分差 + 采样接缝不调度 +
      教训条目承载审计）
- [x] 2.3 `02-modules/evolution.md`：§3.5 结晶与溶解补观察期自动溶解

## 3. 测试先行（先红）

- [x] 3.1 `tests/test_evolution.py`：`ObservationRegistry`——`open` 建窗 / `sample` 未开窗目标
      被忽略（不建窗）/ 样本不足不判定 / 达标且越线触发 / 未越线不触发
- [x] 3.2 `tests/test_evolution.py`：`freeze` 生效（期内不累积不触发）与冷却期结束恢复采样
      （用注入 `now` 断言，确定性）
- [x] 3.3 `tests/test_evolution.py`：`crystallize` 成功后开窗（基线 = 评测 `held_out_score`）
- [x] 3.4 `tests/test_evolution.py`：`engine.observe` 回归 → 自动溶解（技能 `deprecated`）+
      教训条目含基线/均分/样本数 + 返回 `status="dissolved"`
- [x] 3.5 `tests/test_evolution.py`：未开窗目标 `observe` → `None`（不抛异常）；未回归
      `observe` → `None` 且技能仍 `active`
- [x] 3.6 回归：既有 `dissolve` 用例语义不变

## 4. 实现

- [x] 4.1 `src/core/evolution/observation.py`：`ObservationWindow` + `ObservationRegistry`
- [x] 4.2 `src/core/evolution/engine.py`：`crystallize` 开窗 + `observe()` 采样/溶解/冻结
- [x] 4.3 `src/core/evolution/__init__.py` 导出；`models.py` 的 `status` 取值注释补 `dissolved`

## 5. 门禁与归档

- [x] 5.1 ruff check / format 全绿
- [x] 5.2 pyright（src）0 error
- [x] 5.3 `.venv/bin/pytest -q` 全绿
- [x] 5.4 `openspec validate --all` 全绿 → 手动归档（delta 合并进 specs/ + mv 到 archive/）
