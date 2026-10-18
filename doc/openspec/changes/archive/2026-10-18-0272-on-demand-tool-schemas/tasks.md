# Tasks 0272 — 工具参数按需注入

## 1. 配置层

- [x] 1.1 `loop.tool_scope` 进 ConfigSpec 三面（缺省 `auto`）
- [x] 1.2 `_loop_errors` 校验 `all` / `auto`（非法阻断启动）；`ConfigManager.tool_scope()` 访问器

## 2. 工具与循环

- [x] 2.1 `builtin.schema_read(catalog)`：无参目录 / 按 id 返回 schema / unknown
- [x] 2.2 `LoopContext.loaded_tools`（回合内集合）
- [x] 2.3 `LLMPlanner(tool_scope=...)` + `_tool_schemas(ctx)` 过滤（核心集 / 阈值 / 回落）
- [x] 2.4 系统提示按需加载说明行（`auto` 生效时）
- [x] 2.5 循环吸收 `schema_read` 成功调用的 id（下一轮生效）
- [x] 2.6 组合根注册 `schema:read` coeffect + `tools.schema_read` + 主 planner 传 `config.tool_scope()`

## 3. 测试与门禁

- [x] 3.1 `tests/test_tool_scope.py`：配置三面 / 非法值 / planner 过滤 / 加载可见 / 阈值 /
      回落 / `all` / 目录不收窄 / 吸收 / 新回合重置 / schema_read 行为 / 权限只读
- [x] 3.2 反证：摘过滤 / 忽略 loaded / 摘吸收 / 忽略开关 ⇒ 对应用例红；复原 `md5sum` 同
- [x] 3.3 四门禁 + `openspec validate --all`；archive + ADR-0262 + 台账 E208 + 测试节 §184
      + 模块/接口文档 + 单次提交
