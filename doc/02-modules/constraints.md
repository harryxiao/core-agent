# 模块设计：约束与中间件（Constraint & Middleware）

> 对应规格：`doc/openspec/specs/constraints/spec.md` ｜ 接口：`doc/03-interfaces/constraints-interface.md`
> 定位：**横切层**，在模型执行前后插入标准化校验逻辑，系统性降低输出错误率。

---

## 1. 模块定位

LLM 输出是自由文本，直接驱动执行会引入非法指令、格式错误、单点失败拖垮全流程等问题。

本模块在 **loop 的推理→行动之间**与**行动→记忆之间**插入中间件链，把自由输出转化为结构化、可验证、可容错的执行指令。

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
- 非法调用返回结构化错误（对齐 `tool-use` 的错误码）。

### 3.2 异常容错中间件

| 中间件 | 行为 |
|---|---|
| CircuitBreaker | 连续 N 次失败 → 打开（快速失败）→ 冷却期后半开试探 |
| RetryPolicy | 指数退避重试，幂等操作才重试，避免重复副作用 |
| Fallback | 失败降级：备用工具 / 简化路径 / 转人工 |
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

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 输出解析失败 | 重试（有限次）→ 请求模型修正 → 标记 FAILED |
| 熔断器打开 | 快速失败，短路后续调用，冷却后自动半开 |
| 重试超过上限 | 触发 Fallback → 仍失败则 Rollback + 转人工 |
| 回滚失败 | 进入 QUARANTINE（对齐 plugin-registry） |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/constraints-interface.md`
- 规格：`doc/openspec/specs/constraints/spec.md`
- 测试：`doc/04-testing/test-cases.md`（CNS 系列）
