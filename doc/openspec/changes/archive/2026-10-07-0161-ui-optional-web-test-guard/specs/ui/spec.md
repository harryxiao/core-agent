## ADDED Requirements

### Requirement: 可选 Web 依赖测试守卫
Web 能力的测试文件（如 `tests/test_serve.py`）对可选依赖（fastapi/starlette 等）的模块级导入 MUST 位于 `pytest.importorskip` 守卫之后；守卫 SHALL 作为文件首个导入动作执行。在未安装 Web 可选依赖的环境中，测试文件 SHALL 整体优雅 skip，不产生 collection error。

#### Scenario: 缺依赖环境优雅跳过
- **GIVEN** 测试环境未安装 fastapi/starlette 可选依赖
- **WHEN** 运行 pytest 收集 `tests/test_serve.py`
- **THEN** 该文件所有测试标记为 skipped，无 collection error，其他测试文件的执行不受影响

#### Scenario: 有依赖环境行为不变
- **GIVEN** 测试环境已安装 fastapi/starlette
- **WHEN** 运行 pytest 收集 `tests/test_serve.py`
- **THEN** 全部测试正常收集与执行，行为与守卫调整前一致

#### Scenario: 新增可选依赖导入的守卫合规
- **GIVEN** 后续向 Web 测试文件新增可选依赖的模块级导入
- **WHEN** 审查该导入位置
- **THEN** 该导入位于 `importorskip` 守卫之后（可带 `# noqa: E402`），不得先于守卫裸导入
