# Tasks 0198 — SOP 自动质量门

## 1. 规格（spec-first）

- [ ] `specs/skills/spec.md`：MODIFIED「SOP 提炼（skill extraction）」（+「自动质量门」bullet
      + 2 Scenario），既有 9 Scenario 标题零丢失
- [ ] ADR-0188（`doc/01-architecture/adr.md`）
- [ ] **judgment 规格零改动**（纯消费已规格化 `noul` 原语）

## 2. 测试先行（红）

- [ ] `test_skills.py`：门拒绝 ⇒ 不入库 + 清组 + 留痕**只报组键**（红：变更前无 `gate` 参数）
- [ ] `test_skills.py`：门放行 ⇒ 照常 `active` 入库
- [ ] `test_skills.py`：未注入门 ⇒ 发布行为不变
- [ ] `test_skills.py`：门**抛异常** ⇒ fail-open 放行
- [ ] `test_judgment.py`：`SopGate` 经桩 router 的真/假映射 + 异常/缺答案 ⇒ 放行

## 3. 实现（绿）

- [ ] `skills/sop.py`：`SopGate` 类型别名 + `gate` kwarg + `observe` 的门分支
- [ ] `judgment/skills.py`：`SopGate` + `sop_gate_with(router)`
- [ ] `runtime.py`：任务级实例接线（`jev is not None` 惯例）

## 4. 门禁与收口

- [ ] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [ ] `openspec validate 2026-10-11-0198-sop-quality-gate`
- [ ] 手工归档（delta 合 canonical，断言 0 行丢失 / 0 Scenario 标题丢失）
- [ ] `doc/04-testing/test-cases.md` §111 + 基线 bump；台账 E135（`known-risk.md` §1）+
      §3 ADR-0188 行；`doc/02-modules/skills.md` / `doc/03-interfaces/skills-interface.md` 对应面
      （§6「已知缺口」改写：质量门缺口**已闭**）
- [ ] 单次提交 `feat(skills): …`
