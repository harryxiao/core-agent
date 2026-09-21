# Context Engineering Specification

## Purpose
上下文工程解决长任务下信息过载与关键信息丢失问题：按需加载、信息地图、自动压实三管齐下，保证每次只把当前任务最需要的上下文装进窗口。

## Requirements

### Requirement: 动态上下文构建
系统 SHALL 按任务阶段按需加载上下文，控制注入 token 上界，超预算裁剪低相关度内容。

#### Scenario: 按需加载与预算控制
- **GIVEN** 一个任务处于某阶段
- **WHEN** 上下文装配器构建上下文
- **THEN** 仅加载该阶段所需事实/技能/约束，token 控制在预算内

#### Scenario: 超预算裁剪保留关键
- **GIVEN** 装配结果 token 超预算
- **WHEN** 预算管理器裁剪
- **THEN** 裁剪低相关度内容，优先保留宪章/未决事项/验收标准

### Requirement: 信息地图
系统 SHALL 把长文档转化为轻量化目录索引，模型按需跳转获取细节，不把全文塞入窗口。

#### Scenario: 地图定位与按需取详情
- **GIVEN** 一份千页级业务文档已建立信息地图
- **WHEN** 模型需要某章节细节
- **THEN** 先用地图定位指针，再 fetch 对应片段，而非加载全文

#### Scenario: 地图失效重建
- **GIVEN** 源文档内容变更导致地图索引失效
- **WHEN** 检测到 hash 不一致
- **THEN** 触发增量重建，期间降级为全文检索

### Requirement: 上下文自动压实
系统 SHALL 对多轮关键信息自动摘要沉淀，写回记忆，避免重复传递冗余内容。

#### Scenario: 触发压实并沉淀
- **GIVEN** 轮数或 token 达到阈值
- **WHEN** 压实器运行
- **THEN** 关键结论/决策/未决事项被摘要沉淀，写回 MemoryStore

#### Scenario: 压实不丢关键信息
- **GIVEN** 压实产物丢失关键信息
- **WHEN** 校验发现关键信息缺失
- **THEN** 不替换原文，返回 `COMPACTION_LOSSY`
### Requirement: 宪法约束注入
系统 SHALL 将 Core Profile 的「宪法与全局规则」分区作为 constitution:v1 coeffect 注入上下文，作为必保约束参与执行。

#### Scenario: 宪法分区注入
- **GIVEN** 全局 Core.md 含「宪法与全局规则」分区
- **WHEN** 上下文装配器构建上下文
- **THEN** 该分区内容作为 constitution:v1 coeffect 注入，并作为必保约束保留

### Requirement: 项目信息注入
系统 SHALL 在载入项目时由 ContextEngine 按 cwd 向上查找项目级 Core.md，将其内容作为项目信息注入上下文窗口。

#### Scenario: 项目信息注入
- **GIVEN** 当前工作目录位于某项目内，且项目根存在 Core.md
- **WHEN** ContextEngine 装配项目上下文
- **THEN** 命中的项目级 Core.md 内容注入上下文，作为项目信息参与任务

#### Scenario: 未命中降级
- **GIVEN** 从 cwd 向上至文件系统根均未发现项目级 Core.md
- **WHEN** ContextEngine 查找失败
- **THEN** 静默降级，不注入项目信息，不影响任务执行
