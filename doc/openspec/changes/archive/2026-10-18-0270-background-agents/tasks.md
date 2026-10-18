# Tasks 0270 — 后台子 Agent、完成通知与模型侧任务清单

## 1. 注册表

- [x] 1.1 `BackgroundAgentRegistry`：有界 spawn / 终态 / 取消 / 强引用
- [x] 1.2 完成通知：按会话记录、一次性 drain、每会话 32 条上界、渲染有界
- [x] 1.3 `list` / `get` 只读面（有界返回）

## 2. 工具面

- [x] 2.1 `tools.delegate` 增 `background` 参数（缺省 false，阻塞路径逐字不变）
- [x] 2.2 新 `tools.tasks`（list / status，只读，`task:read`）
- [x] 2.3 权限：`tools.tasks` 字面量豁免判 read（不放宽为词元）

## 3. Loop 接缝

- [x] 3.1 `LoopContext.notices` 字段 + `DefaultLoop(notices_consult=…)`
- [x] 3.2 planner 独立块「后台任务通知：」；缺省空 ⇒ 提示词逐字不变
- [x] 3.3 异常降级留痕（`notices_consult_failed`）

## 4. 组合根

- [x] 4.1 构造注册表、接 `delegate(background=…)`、注册 `tools.tasks` 与 `task:read`
- [x] 4.2 `notices_consult` 只接主 loop（子 Agent 不取）

## 5. 测试与门禁

- [x] 5.1 `tests/test_background_agents.py`：立即返回 / 完成通知 / 一次性 / 会话隔离 /
      有界 / failed / cancelled / 清单 / 权限 / 子 Agent 不可见 / 提示词逐字锚
- [x] 5.2 反证：摘关键分支对应用例红，复原 `md5sum` 同；四门禁 + `openspec validate --all`
- [x] 5.3 archive + ADR-0260 + 台账 E206 + 测试节 §182 + 模块/接口文档 + 单次提交
