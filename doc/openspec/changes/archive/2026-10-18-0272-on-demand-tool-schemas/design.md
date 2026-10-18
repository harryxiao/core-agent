# Design 0272 — 工具参数按需注入

## D1 只过滤请求侧 schema，不动注册面

`ToolProvider.active_tools()` 保持**全量**：权限分级、coeffect 校验、撤销闭包、动作去重、
不可逆判级都以全量为真源。收窄只发生在 `LLMPlanner._tool_schemas(ctx)`——即
`LLMRequest.tools` 这一份**发给端点的副本**。

这样：

- 模型若经文本 JSON 动作直接调用未注入 schema 的工具，执行面照常工作（**不是**访问控制）；
- 第三方 provider 不感知本机制；
- 回滚 / 审批 / 观测链路零改动。

## D2 两个 scope 与阈值

| `loop.tool_scope` | 行为 |
|---|---|
| `all` | 恒注入全部已注册工具 schema（与引入前**逐字一致**，kill-switch） |
| `auto`（缺省） | 已注册工具数 **≤ 8** ⇒ 全量注入；否则只注入核心集 + 本回合已加载 + `schema_read` |

`auto` 生效还需 `tools.schema_read` **已注册**；未注册 ⇒ 回落全量注入（fail-open：不得造出
「模型看得见名字却无法加载参数」的工具面）。

阈值 8 = 核心集 7 + `schema_read` 1：小工具面（子 Agent 内置七件、宠物白名单）即使误开
`auto` 也全部注入，机制天然只作用于主工具面，无需按 loop 类型分叉。

## D3 核心集

`tools.file_read`、`tools.file_write`、`tools.file_patch`、`tools.code_run`、
`tools.web_fetch`、`tools.context_read`、`tools.delegate`。

判据是「几乎每轮都可能用」：文件读写改、执行、取网页、按信息地图取详情、委托。按需集的
共同特征是**情境触发**：`tools.process` / `tools.process_kill`（先有后台命令）、
`tools.gate_run`（交付门禁）、`tools.install` / `tools.uninstall` / `tools.list`
（插件管理）、`tools.tasks`（先起后台任务）、`mcp.*`（特定端点）。

## D4 `tools.schema_read`

- 形状：`tool_ids?: string[]`（数组，元素字符串）。
- 无参 ⇒ `{"tools": [{tool_id, description}, ...]}`（全量目录，与系统提示目录同源）。
- 有参 ⇒ `{"schemas": [{tool_id, description, parameters}, ...], "unknown": [...]}`。
  参数 schema 放进**工具观察**而不只依赖请求侧注入：文本 JSON 动作路径的模型也能读到。
- `coeffects=["schema:read"]`、`reversible=True` ⇒ 只读放行（权限分词含 `read` 词元）。
- 组合根注册 `schema:read` coeffect；catalog 用**闭包** `tools.active_tools`，因此返回内容
  始终反映调用时的真实注册面（含 MCP 动态工具）。
- **只挂主工具面**（同 `gate_run` / `tasks`）：子 Agent / 宠物不注册、也不需要。

## D5 加载吸收与生命周期

`LoopContext.loaded_tools: set[str]`（**回合内**集合）。循环在动作提交阶段、`observe` 之前：

```
if 动作成功 and tool_id == "tools.schema_read":
    for id in args["tool_ids"] 中已注册的字符串:
        ctx.loaded_tools.add(id)
```

下一轮 `_build_request(ctx)` 即携带其 schema。集合随 `perceive()` 新建上下文包而清空
（每回合重置）；不写记忆、不跨会话。

吸收放在循环而非工具处理器：`schema_read` 工具本身不感知 `LoopContext`（L1 不依赖 loop），
且只有循环知道「本轮」的边界。

## D6 系统提示

目录块保持全量（`- {tool_id}: {description}`）；`auto` 生效时追加一行：

```
- 说明：未注入参数 schema 的工具，先调用 tools.schema_read 获取参数（下一轮生效）
```

这一行是模型行为的**唯一提示**，成本远低于被裁掉的 schema JSON。`all` 模式不产该行
（提示词逐字不变）。

## D7 配置

- `ConfigSpec("loop.tool_scope", "--loop.tool-scope", "CORE_LOOP_TOOL_SCOPE", default="auto",
  map_to="loop.tool_scope", exposure=ADVANCED)`。
- `_loop_errors`：非 `all` / `auto` 字符串（大小写不敏感、去首尾空白）⇒ 阻断启动，
  错误信息指明键名与合法取值；布尔视作非法。
- 访问器 `ConfigManager.tool_scope() -> str`：返回归一后的 `all` / `auto`；未加载配置 ⇒ `auto`。
- **构造缺省分工**：`LLMPlanner(tool_scope="all")` 保证既有直接构造的测试 / 嵌入方零变化；
  生产主 planner 由组合根显式传 `config.tool_scope()`。这与 `max_rounds` 的「实现类与配置
  缺省同步」不同——此处**故意分叉**：planner 是库级组件，缺省必须保守；`auto` 是产品面默认。

## D8 反证与门禁

- 摘掉过滤：auto 收窄用例红（仍注入 `tools.gate_run`）。
- 过滤忽略 `loaded_tools`：加载后可见用例红。
- 摘掉吸收：下一轮可见用例红。
- 忽略 `tool_scope`：`all` 全量用例红。
- 阈值 / `schema_read` 缺失回落用例各钉一个分支。

## D9 已知局限

1. `auto` 缺省改变主 loop 的请求形状：依赖原生 tool_calls 的模型在未加载前**不能**直接调用
   按需工具（这是机制本身，不是缺陷）；文本 JSON 动作路径不受限。
2. 每多一次按需加载就多一轮模型往返；单轮只用核心集时净省 token，反复加载多工具时可能更贵。
3. 「核心集」是静态启发式（同 embedding 端点表）：任务型负载若长期以 `gate_run` / MCP 为主，
   需显式 `tool_scope=all` 或后续扩核心集。
4. 已加载集合按回合重置：多轮长任务中每回合都要重新加载按需工具。
5. MCP 工具数量多时收益最大，但端点不可达的告警与连接行为完全不变。
