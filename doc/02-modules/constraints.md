# 模块设计：约束与中间件（Constraint & Middleware）

> 对应规格：`doc/openspec/specs/constraints/spec.md` ｜ 接口：`doc/03-interfaces/constraints-interface.md`
> 定位：**横切层**，在模型执行前后插入标准化校验逻辑，系统性降低输出错误率。

---

## 1. 模块定位

LLM 输出是自由文本，直接驱动执行会引入非法指令、格式错误、单点失败拖垮全流程等问题。

本模块在 **loop 的推理→行动之间**与**行动→记忆之间**插入中间件链，把自由输出转化为结构化、可验证、可容错的执行指令。

> 生产实际接入：loop 的**动作前链**（`middlewares`）与**结果侧观察者**（`action_observers`）两个接缝；
> 校验在工具层（`ToolProvider._validate_args`）、压缩在 context 层（`core.context.Compactor`）各就其位。
> 见下方 §4「实际接线」与 ADR-0055。

---

## 2. 内部组成

```
MiddlewareChain（横切，洋葱模型）
├── Validator       输入/输出校验：类型约束、格式校验、schema 校验
├── CircuitBreaker  熔断器：连续失败达阈值 → 打开，阻断级联失败
├── RetryPolicy     自动重试：指数退避 + 抖动 + 幂等保护
├── Fallback        降级：失败时切备用策略/简化路径
├── Rollback        错误回滚：复用 EffectTracker 撤销本轮副作用
└── ContextCompressor 上下文压缩中间件：清理无效信息，对抗信息腐烂
```

---

## 3. 关键设计

### 3.1 输入/输出校验

- **输入校验**：工具调用前校验参数 schema、coeffect 权限、类型约束。
- **输出校验**：把模型自由文本输出解析为结构化指令；解析失败则重试或请求修正，**绝不带病执行**。
  生产实现落在 `loop` 的 `LLMPlanner._parse`（动作感知：解析失败 → 终止 Action，工具不执行，
  失败原因回灌下一轮）；本模块的 `Validator.parse_output` 为通用 JSON 解析，**有意不接线**
  （change `0063` 判定，见 `doc/03-interfaces/constraints-interface.md` §2）。
- 非法调用返回结构化错误（对齐 `tool-use` 的错误码）。
- **口径单一真源（change `0059`）**：调用前的 schema 校验（必填 / 类型）唯一实现为
  `Validator.validate_input`；工具层 `ToolProvider._validate_args` **委托**之（不另实现副本），
  两条路径的拒绝口径一致。

### 3.2 异常容错中间件

| 中间件 | 行为 |
|---|---|
| CircuitBreaker | 连续 N 次失败 → 打开（快速失败）→ 冷却期后半开试探；**N 与冷却期可经配置覆盖**（`constraints.failure_threshold` / `constraints.cooldown_s`，change `0068` / 账本 E15） |
| RetryPolicy | 指数退避重试，幂等操作才重试，避免重复副作用；**生产已接线**（change `0209` / ADR-0199，见 §4） |
| Fallback | 失败降级：备用工具 / 简化路径 / 转人工（**库能力 ＋ 单测覆盖，生产未接**——降级回复会静默抑制 trace 回滚并终结 ReAct 自愈） |
| Rollback | 单步失败回滚本轮 effect，不拖垮整个任务 |

### 3.3 上下文压缩中间件

- 自动清理对话历史中的无效信息（已完成子任务、重复内容、过期事实）。
- 与 context 模块的"自动压实"协作：此处是执行期清理，context 是构建期按需加载。

---

## 4. 中间件执行模型（洋葱模型）

```
请求 ─► V1 ─► V2 ─► ... ─► 核心执行 ─► ... ─► V2' ─► V1' ─► 响应
       (输入校验)(熔断/重试)         (回滚)(输出校验)
```

- 中间件可插拔、可排序，由 profile 配置。
- 每个中间件自身也是插件，遵守 plugin-registry 契约（可世代化、可进化）。

**实际接线（生产，change 0052 / ADR-0055）**：loop 只落地两个接缝——
① **动作前链**（loop `middlewares`）：`CircuitBreaker`（**按 `tool_id` 隔离**）的 `before` 命中 OPEN
即转「终止 Action」短路本轮；② **结果侧观察者**（loop `action_observers`）：动作完成后回灌 `record_result`
（**只计执行类失败**，策略性拒绝不计入）。校验由工具层 `ToolProvider._validate_args` **委托本模块 `Validator`** 承担（change `0059`）、上下文压缩由
`core.context.Compactor` 承担（语义等价/同构，均在本模块之外）。**③ 重试接缝**（change `0209` / ADR-0199、
台账 E146）：`src/core/loop/fault_adapter.py` 的 `FaultChain.wrap` 包裹 loop 的 `act`——工具**执行类**
失败（`TIMEOUT` / `EXECUTION_FAILED`，**显式白名单**，未来错误码 fail-closed）且 `tool_id` **可逆**时按
`RetryPolicy` 退避重试；**耗尽原样返回最后一次失败结果**（不降级、不改码）。仅可逆工具（避免部分外写被
重试放大）；效应只在成功后记 ⇒ 重试**不双记账**；缺省 `constraints.retry_attempts=0` ⇒ 不包裹接缝、既有
路径逐字不变（主/子/神兽 loop 注入，**宠物不接**）。
`Fallback` **生产未接**（降级回复会抑制 loop 的 trace 回滚并终结 ReAct 自愈）、`Pipeline` 为可插拔能力，
二者走出零测试状态（**库能力 ＋ 单测覆盖**）；`Rollback` 维持 loop 级既有路径（`rollback(trace_id)` 已满足
规格「失败回滚」Scenario，**单一路径**）。适配层 `src/core/loop/constraints_adapter.py`。
熔断阈值/冷却由 `ConfigManager.circuit_breaker()` 经 `ConfigSpec` **单一真源**读出后注入适配层
（change `0068` / 账本 E15；缺省 `5` / `30.0` 秒，非法取值校验期拒绝并阻断启动）。

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 输出解析失败 | 不执行工具，以解析失败 reply 收尾 → 失败原因回灌下一轮请求模型修正（生产实现：`LLMPlanner._parse`） |
| 熔断器打开 | 快速失败，短路后续调用，冷却后自动半开 |
| 重试超过上限 | **原样返回最后一次失败结果**（不降级、不改码）⇒ 失败致本轮 trace 回滚、工具失败不判轮失败（change `0209` / ADR-0199；`Fallback` 生产未接，设计意图中的「转人工」未实现） |
| 回滚失败 | 进入 QUARANTINE（对齐 plugin-registry） |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/constraints-interface.md`、`doc/03-interfaces/configuration-interface.md` §2.4
- 规格：`doc/openspec/specs/constraints/spec.md`
- 测试：`doc/04-testing/test-cases.md`（CNS 系列）
