# Tasks: 可选 Web 依赖的测试守卫规范

## 1. 测试守卫修复

- [x] 1.1 调整 `tests/test_serve.py` 导入顺序：`pytest.importorskip("fastapi.testclient")` 前置，starlette 导入移至守卫后并标注 `# noqa: E402`（已完成于上一轮闭环）
- [x] 1.2 验证守卫顺序修复后测试逻辑零改动（`status` 用法全部保留）

## 2. 规格固化

- [x] 2.1 在 `ui/spec.md` 追加 Requirement「可选 Web 依赖测试守卫」（specs/ui/spec.md delta）
- [x] 2.2 运行 `openspec validate` 确认全绿（32 items, 0 failed）

## 3. 回归验证

- [x] 3.1 `gate_run: test` 全绿（已完成）
- [x] 3.2 `gate_run: lint` 确认 E402 豁免无副作用（lint 全绿）
- [x] 3.3 人工确认后按 `feat(ui): ...` 提交，归档 change
