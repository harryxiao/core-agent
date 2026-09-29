# Change: Judgment 决策模型接入——JEV/TypeSafe System One 决策小模型横切能力

## Why

JEV（TypeSafe 官方）不是普通生成式 LLM，而是「System One」决策小模型：以 `POST /v1/systemone` 接收 state + 类型化问题（typed questions），返回类型化答案（typed answers）+ probability + confidence，专司快速结构化决策而非文本生成。当前 core-agent 的决策点全部压在通用生成式 LLM 上：

1. **决策精度与成本倒挂**：AgentLoop 的路由选择、记忆压实的内容筛选、约束守卫的放行判断，用生成式 LLM 做「选择/评分/判断」既慢又贵，且无结构化置信度可据以回退。
2. **无决策原语抽象**：现有 `loop / orchestration / evolution` 无 choice/score/noul 三类决策原语，决策逻辑散落在生成式 prompt 里，不可观测、不可回退、不可审计。
3. **缺 JEV 接入层**：litellm_provider 支持 api_key/base_url/model，但无面向 JEV「System One」协议（typed questions/answers + 置信度）的适配器。

## What Changes

- **决策原语路由**（judgment，ADDED）：choice（选项路由）/ score（评分筛选）/ noul（布尔判断）三类决策原语，统一决策入口。
- **JEV 提供方接入**（judgment，ADDED）：经 TypeSafe 专有 REST 端点（api_key/base_url/model）挂 TypeSafe `/v1/systemone`，适配 typed questions/answers（答案按原语分形）。
- **置信度回退**（judgment，ADDED）：决策置信度低于阈值回退主 LLM（生成式），保证决策质量下限。
- **决策审计**（judgment，ADDED）：决策轨迹（输入 state、原语、选项、结果、置信度、是否回退）落 observability 链路，供进化/审批消费。
- **决策模型配置**（configuration，ADDED）：judgment 的 provider/model/base_url/api_key/confidence_threshold 纳入 ConfigSpec 单一真源，api_key 分级存储，未配置时主 LLM 兜底。

## Impact

- **Affected specs**：`judgment/spec.md`（4 ADDED，全新 capability）；`configuration/spec.md`（1 ADDED，扩展既有 capability）
- **Affected docs**：`03-interfaces/judgment-interface.md`（新建）；`00-product/requirements.md`（新增 1.29）；`00-product/design-completeness-eval.md`（数字口径 27→29，补 beast-mode 漂移）；`01-architecture/architecture-overview.md`（横切能力 + 组件表 + 目录树）；`01-architecture/adr.md`（新增 ADR-0042）
- **Affected code**：`src/core/judgment/`（DecisionRouter / JEVProvider / Compactor / Guardrail 四接口 + JEV 接入）、`llm_provider`（JEV endpoint 挂载）——后续 M 阶段
- **Dependencies**：`observability`（决策轨迹）、`permission`（guardrail noul 判断）、`evolution`（评测消费决策轨迹）；无新三方依赖（JEV 为 HTTP API）
