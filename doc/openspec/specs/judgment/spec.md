# Judgment Specification

## Purpose
决策（judgment）能力让智能体在决策点调用 JEV/TypeSafe「System One」决策小模型，以结构化原语（choice/score/noul）替代生成式 LLM 的开放决策：提供决策原语路由（decision primitive routing）、JEV 提供方接入（JEV provider）、置信度回退（confidence fallback）与决策审计（decision audit）四类能力，作为 loop「决策点路由」、memory「记忆压实」、permission「守卫判断」的横切决策底座。

## Requirements

### Requirement: 决策原语路由
系统 SHALL 提供 choice（选项路由）、score（评分筛选）、noul（布尔判断）三类决策原语作为统一决策入口，供 loop/orchestration/evolution 在决策点调用。

#### Scenario: choice 选项路由
- **GIVEN** 一个决策点存在多个候选分支
- **WHEN** 上层以 choice 原语提交选项集合
- **THEN** 返回唯一选中项及概率分布/置信度

#### Scenario: score 评分筛选
- **GIVEN** 一批待筛选内容（如记忆条目）
- **WHEN** 上层以 score 原语提交评分请求
- **THEN** 返回各条目评分，供保留/丢弃决策

#### Scenario: noul 布尔判断
- **GIVEN** 一个需守卫判断的动作
- **WHEN** 上层以 noul 原语提交判断请求
- **THEN** 返回放行/拦截结论（是/否）

### Requirement: JEV 提供方接入
系统 SHALL 支持经 TypeSafe 专有 REST 端点（api_key/base_url/model）挂接 JEV/TypeSafe `POST /v1/systemone`，适配 System One 协议（state + typed questions → typed answers，答案按原语分形：noul→noul / choice→choice+probabilities+confidence / score→score+legend+probabilities+confidence）。

#### Scenario: 挂接 JEV 端点
- **GIVEN** 配置了 JEV/TypeSafe 的 api_key/base_url/model
- **WHEN** 上层调用决策原语
- **THEN** 经 /v1/systemone 返回 typed answers（map<id, Answer>，按原语分形）

### Requirement: 置信度回退
系统 SHALL 在决策置信度低于配置阈值时回退主 LLM（生成式）执行决策，保证决策质量下限，并标注回退轨迹（choice/score 以 confidence 判定；noul 无 confidence，以是/否概率接近 0.5 判定）。

#### Scenario: 低置信度回退
- **GIVEN** 一次决策的 confidence 低于阈值
- **WHEN** 决策原语返回结果
- **THEN** 回退主 LLM 重新决策，轨迹标注回退

### Requirement: 决策审计
系统 SHALL 将每次决策的轨迹（输入 state、原语类型、选项、结果、置信度、是否回退）落 observability 链路，供进化与审批消费。

#### Scenario: 决策轨迹落盘
- **GIVEN** 一次决策完成
- **WHEN** 决策结果返回
- **THEN** 决策轨迹写入 observability，含置信度与回退标记
