# Configuration Specification Delta

## MODIFIED Requirements

### Requirement: LLM 提供商配置（必选）
系统 SHALL 要求 LLM 配置（provider/model/endpoint/api_key）为必选项，缺失或不完整时阻断
启动并报明确错误；并 SHALL 支持**可选**子项 `embedding_model`（复用 `endpoint` 与密钥
引用）用于记忆检索的向量化，未设置或不可达时记忆检索回退词法，不影响启动。

#### Scenario: 缺失 LLM 配置阻断启动
- **GIVEN** config.yaml 缺少 llm 段或 api_key 未解析
- **WHEN** 系统启动加载配置
- **THEN** 启动失败，报明确错误指明缺失的 LLM 配置项

#### Scenario: LLM 配置完整正常启动
- **GIVEN** llm 段包含 provider/model/endpoint/api_key 且 api_key 经 env 引用解析成功
- **WHEN** 系统启动加载配置
- **THEN** 系统正常启动并初始化 LLM 客户端

#### Scenario: 配置 embedding 模型启用语义检索
- **GIVEN** llm 段设置 `embedding_model`
- **WHEN** 系统启动装配记忆
- **THEN** 以该模型构造 embedding 客户端并注入 `MemoryStore`（经单条→批量适配器）

#### Scenario: 未配置 embedding 模型回退词法
- **GIVEN** llm 段未设置 `embedding_model`
- **WHEN** 系统启动装配记忆
- **THEN** 记忆检索不注入 embedder，回退词法相似，启动不受影响
