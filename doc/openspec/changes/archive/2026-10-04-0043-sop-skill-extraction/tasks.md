# Tasks: SOP 提炼（skill extraction）

## 1. 规格先行

- [x] 1.1 `specs/skills/spec.md` delta：ADDED「SOP 提炼（skill extraction）」（触发 / 阈值 /
      归组 / 发布 / 降级 / 可逆，7 个 Scenario）
- [x] 1.2 `openspec validate 0043-sop-skill-extraction` 全绿

## 2. 契约与接口文档

- [x] 2.1 `03-interfaces/skills-interface.md`：新增「SOP 提炼」一节（`SopExtractor.observe`
      契约、`SopWriter` 接缝、归组口径、产物字段与 status）
- [x] 2.2 `01-architecture/adr.md`：ADR-0048（生成走 DI 接缝而非 judgment + loop 只持回调 +
      词法归组 + active 发布与 reversibility + 已知缺口）
- [x] 2.3 `03-interfaces/loop-interface.md`：收尾钩子一句

## 3. 测试先行（先红）

- [x] 3.1 `tests/test_skills.py`：达阈值提炼入库（instructions / task_types / active）+ 可被路由命中
- [x] 3.2 未达阈值不提炼；失败轨迹不计入
- [x] 3.3 归组复用已有技能的 task_types
- [x] 3.4 未注入 writer → 不累积不提炼；空提炼不入库
- [x] 3.5 提炼入库可逆（按 trace 回滚移除，重复回滚不报错）
- [x] 3.6 `tests/test_loop.py`：成功任务收尾触发钩子；失败任务不触发；钩子抛错不中断本轮
- [x] 3.7 `tests/test_phase13.py`：`build_runtime` 注入 SopExtractor（未配置模型时不注入）

## 4. 实现

- [x] 4.1 `src/core/skills/sop.py`：`SopWriter` / `build_sop_prompt` / `sop_writer_with` /
      `SopExtractor`（归组 + 累积 + 提炼 + 入库 + 效应）；`__init__.py` 导出
- [x] 4.2 `src/core/loop/default.py`：`sop_observer` 注入点 + 成功收尾调用 + 失败降级留痕
- [x] 4.3 `src/core/runtime.py`：构造 `SopExtractor`（writer 接主模型）并注入主/子 loop

## 5. 门禁与归档

- [x] 5.1 ruff check / format 全绿
- [x] 5.2 pyright（src）0 error
- [x] 5.3 `.venv/bin/pytest -q` 全绿
- [x] 5.4 `openspec validate --all` 全绿 → 手动归档（delta 合并进 specs/ + mv 到 archive/）
