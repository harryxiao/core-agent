## ADDED Requirements

### Requirement: 思考过程回显（Think）
系统 SHALL 在**三端**（TUI / Web / APP）以**折叠块**呈现模型的思考原文（`loop.reasoning` 事件），**缺省收起**、用户可展开查看全文；同一轮的思考增量 SHALL **归并到同一个折叠块**（增量更新，SHALL NOT 逐段新建块）。思考原文 SHALL ONLY 经该事件面呈现，SHALL NOT 写入转录 / 记忆 / 日志 / trace 遥测（思考回显是**纯呈现层**）。
**未开启**思考回显时（`llm.show_thinking` 缺省 `false`）系统 SHALL NOT 产出该事件、三端呈现 SHALL NOT 出现思考块，事件面与既有缺省**逐字一致**。Web / APP 端 SHALL 复用既有 SSE 事件通道呈现（SHALL NOT 新建端点、SHALL NOT 新建第二数据源）；APP 复用与 Web 相同的 SPA 产物。

#### Scenario: TUI 思考折叠回显
- **GIVEN** 思考回显已开启，且模型逐段返回思考原文
- **WHEN** TUI 消费 `loop.reasoning` 事件
- **THEN** 思考文本落入**单个**缺省收起的折叠块（标题可见、正文藏于折叠区），随增量持续更新且可展开查看全文；同一轮的主回复呈现（流式增量与终态收口）**不受影响**

#### Scenario: Web 思考折叠回显
- **GIVEN** 思考回显已开启，Web 会话正在流式产出思考原文
- **WHEN** 前端消费 `loop.reasoning` 帧
- **THEN** 思考文本落入**单个**缺省收起的折叠块（`details` 式），增量**追加**到同一块（不逐段新建、不渲染 JSON 载荷），终态帧不改写该块

#### Scenario: 未开启思考回显时三端不呈现
- **GIVEN** 思考回显未开启（缺省），且模型响应携思考原文
- **WHEN** 一轮对话在三端任一端结束
- **THEN** 事件面**不产** `loop.reasoning`，三端呈现中**不出现**思考块，输出与既有缺省**逐字一致**
