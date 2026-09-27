# Tasks

> 设计落地，实现依赖后续 coding 阶段。

## 1. 配置加载器（P0）

- [x] 1.1 config.yaml 解析 + env 覆盖 + 默认值兜底（单一收口）
- [x] 1.2 LLM 配置必选校验（缺失阻断启动 + 明确错误）
- [x] 1.3 配置项读取 API（供各 capability 获取配置）

## 2. feature flag（P1）

- [x] 2.1 features 段解析
- [x] 2.2 模块级开关：关闭则不加载、不初始化

## 3. 密钥解析（P0）

- [x] 3.1 `${VAR}` 引用解析（env/keychain）
- [x] 3.2 日志/报错密钥脱敏（对齐 observability）

## 4. schema 校验（P1）

- [x] 4.1 config.yaml schema 定义与校验
- [x] 4.2 校验失败拒绝生效 + 报明确错误

## 5. 变更生效与回滚（P1）

- [x] 5.1 配置变更即生效
- [x] 5.2 写入失败回滚不留半写状态（对齐 ui spec）

## 6. 挂接与收敛（P1）

- [x] 6.1 llm-provider 配置语义挂载点引用（关 0006 Open Question）
- [x] 6.2 im-gateway 账户/凭证配置挂载点引用
- [x] 6.3 ui / git 配置语义挂载点引用
