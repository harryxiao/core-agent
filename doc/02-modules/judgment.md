# 模块设计：决策（Judgment）

> 对应规格：`doc/openspec/specs/judgment/spec.md` ｜ 接口：`doc/03-interfaces/judgment-interface.md`
> 定位：**决策点的结构化决策底座**，以 JEV/TypeSafe「System One」决策小模型 + 三类决策原语（choice/score/noul）替代生成式 LLM 的开放决策，作为 loop「决策点路由」、memory「记忆压实」、permission「守卫判断」的横切底座。

---

## 1. 模块定位

core-agent 的主 LLM 是生成式模型，在决策点输出自由文本再解析，存在不可靠、不可审计的问题；judgment 让智能体在决策点调用 JEV/TypeSafe「System One」决策小模型，以结构化原语返回带类型的结果，替代开放决策。

本模块提供四类能力：决策原语路由（decision primitive routing）、JEV 提供方接入（JEV provider）、置信度回退（confidence fallback）与决策审计（decision audit），是横切于 loop/orchestration/evolution 的决策底座，而非独立业务模块。

---

## 2. 内部组成

```
Judgment（横切决策底座）
├── DecisionRouter   决策路由：以 choice 原语从候选中路由出唯一分支
├── JEVProvider      决策提供方：TypeSafe 专有端点 POST /v1/systemone
├── Compactor        记忆压实：以 score 原语为记忆条目评分筛选
└── Guardrail        守卫判断：以 noul 原语做放行/拦截判断
```

---

## 3. 关键设计

### 3.1 三类决策原语

- 以 choice（选项路由）、score（评分筛选）、noul（布尔判断）三类决策原语作为统一决策入口，供 loop/orchestration/evolution 在决策点调用，替代生成式 LLM 的开放文本决策。
- `DecisionRouter.choose()` 以 choice 原语从候选中路由出唯一分支；`decide()` 接收 `DecisionRequest` 返回类型化结果。
- `Compactor.score()` 以 score 原语为记忆条目评分，供保留/丢弃决策；`Guardrail.check()` 以 noul 原语返回放行/拦截结论。

### 3.2 JEV 提供方接入

- 经 TypeSafe 专有 REST 端点挂接：`api_key`/`base_url`/`model` 三配置项 + `POST /v1/systemone`。
- 适配 System One 协议：`state + typed questions → typed answers`，答案按原语分形——`noul→noul`、`choice→choice+probabilities+confidence`、`score→score+legend+probabilities+confidence`。
- `JEVProvider.query(state, questions)` 是唯一提供方出口，上层经决策原语统一触达，不直接感知端点细节。

### 3.3 置信度回退

- 仅 choice/score 有置信度，noul 以概率接近 0.5 判定；置信度低于阈值时触发主 LLM 回退，保证决策不因小模型低置信度而失准。
- 决策审计记录决策原语、输入 questions、类型化答案与置信度，作为可追溯的决策凭据。

---

## 4. 决策点闭环

```
决策点 ──DecisionRouter.choose/decide──► JEVProvider.query(/v1/systemone)
typed answers ──置信度判定──► 高于阈值直接采用 / 低于阈值回退主 LLM
score 原语 ──Compactor.score──► memory 记忆压实（保留/丢弃）
noul 原语 ──Guardrail.check──► permission 守卫判断（放行/拦截）
```

- 三类原语各归其位：choice 服务路由决策、score 服务记忆压实、noul 服务守卫判断，均回到既有能力闭环，不另起炉灶。

---

## 5. 错误处理

| 错误码 | 含义 |
|---|---|
| `JUDGMENT_PROVIDER_UNREACHABLE` | JEV 端点不可达 |
| `JUDGMENT_SCHEMA_MISMATCH` | 类型化答案与问题 schema 不匹配 |
| `JUDGMENT_LOW_CONFIDENCE` | 置信度低于阈值（触发主 LLM 回退；仅 choice/score 有置信度，noul 以概率接近 0.5 判定） |
| `JUDGMENT_TIMEOUT` | JEV 决策超时（回退主 LLM） |
| `JUDGMENT_INVALID_PRIMITIVE` | 未识别的决策原语 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/judgment-interface.md`
- 规格：`doc/openspec/specs/judgment/spec.md`
- 下游：`doc/02-modules/loop.md`（决策点路由）、`doc/02-modules/memory.md`（记忆压实）、`doc/02-modules/permission.md`（守卫判断）
