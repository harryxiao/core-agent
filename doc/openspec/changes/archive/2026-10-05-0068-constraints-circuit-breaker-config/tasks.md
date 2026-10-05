# tasks — 0068 熔断阈值/冷却可配

## 1. 规格（先行）
- [x] 1.1 `specs/constraints/spec.md` delta：「容错中间件」MODIFIED + 2 场景

## 2. 测试（红）
- [x] 2.1 `tests/test_constraints_config.py`：缺省 / yaml / env / CLI / 非法取值 / 无未知段告警 / 组合根注入 / 端到端

## 3. 实现
- [x] 3.1 `configuration/manager.py`：两项 ConfigSpec + `circuit_breaker()` + `validate_schema` 校验
- [x] 3.2 `runtime.py`：`build_constraints_chain` 从配置取值

## 4. 文档
- [x] 4.1 `03-interfaces/constraints-interface.md` / `configuration-interface.md`
- [x] 4.2 `02-modules/constraints.md`、`04-testing/test-cases.md`
- [x] 4.3 `01-architecture/adr.md`（ADR-0066 + 映射表行）

## 5. 收口
- [x] 5.1 四门：ruff check / ruff format --check / pyright / pytest
- [x] 5.2 `openspec validate 0068-...` → 手动归档 → `openspec validate --all`
- [x] 5.3 账本 `coding-plan/phase-19.md`（§1 E15 行、§9 第 9 步、§0）+ `README.md`
- [x] 5.4 记忆与提交
