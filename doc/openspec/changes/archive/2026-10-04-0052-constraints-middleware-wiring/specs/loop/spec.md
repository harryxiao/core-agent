# loop spec delta — constraints-middleware-wiring

## MODIFIED Requirements

### Requirement: 横切中间件插入
系统 SHALL 支持在循环关键节点插入横切中间件（权限、约束、遥测、上下文）。中间件分两类接缝：
① **动作前链**（`middlewares`）：每个动作执行前按注册序调用，接收（`LoopContext`, `Action`），
可改写动作或返回 `None`；任一返回 `None` 即短路（动作不执行，本轮以已拒绝回复终止）。
② **结果侧观察者链**（`action_observers`）：每个**非终止**动作完成后按注册序回调，接收
（`LoopContext`, `Action`, `ActionResult`）；**仅通知** —— 观察者抛错降级为遥测、
**不改变本轮的结局与终止语义**；终止动作（空 `tool_id`）不触发观察者。

#### Scenario: 中间件按序执行
- **GIVEN** 已注册一组横切中间件
- **WHEN** loop 执行到对应节点
- **THEN** 中间件按注册顺序执行，任一拒绝即短路

#### Scenario: 中间件拒绝短路
- **GIVEN** 权限中间件拦截了当前动作
- **WHEN** loop 尝试执行该动作
- **THEN** 动作不执行，loop 转入等待审批/修正分支

#### Scenario: 结果侧观察者按序执行
- **GIVEN** 已注册一组结果侧观察者，且一轮推理产出一个非终止动作
- **WHEN** 该动作执行完成后
- **THEN** 观察者按注册顺序各被调用一次，收到（上下文、动作、执行结果）

#### Scenario: 观察者异常降级不中断本轮
- **GIVEN** 已注册的结果侧观察者执行时抛错
- **WHEN** 该动作执行完成后
- **THEN** 该错误被降级留痕，本轮正常推进（回复与终止语义不变）

#### Scenario: 终止动作不触发结果侧观察者
- **GIVEN** 一轮推理产出终止动作（空 `tool_id`，如本轮回复）
- **WHEN** 该动作「执行」完成后
- **THEN** 结果侧观察者不被调用
