UI 界面与启动模式是 core-agent 面向用户的统一呈现层：CLI / Web / Desktop 三种入口共享同一内核与同一 LLM 配置源，行为、鉴权、日志保持一致；用户在 Web 与桌面 UI 内即可配置 LLM API；桌面与 Web 复用同一前端构建产物实现体验一致。

## ADDED Requirements

### Requirement: 三模统一内核启动
系统 SHALL 提供 CLI、Web、Desktop 三种启动模式，三者共享同一内核与同一 LLM 配置源。

#### Scenario: CLI 直连内核
- **GIVEN** 用户以 CLI 模式启动
- **WHEN** 发起一次会话
- **THEN** 会话通过同一后端 API 层驱动内核 loop，行为与 Web 模式一致

#### Scenario: 配置单一来源
- **GIVEN** 用户在任一模式配置了 LLM API
- **WHEN** 切换到另一模式
- **THEN** 该配置生效且无需重复配置

### Requirement: LLM API 可配置
系统 SHALL 支持在 Web 与桌面 UI 内配置 LLM provider、endpoint、API key 与 base URL。

#### Scenario: UI 内配置 LLM API
- **GIVEN** 用户打开 Web 或桌面设置页
- **WHEN** 填写 provider/endpoint/key/base URL 并保存
- **THEN** 配置写入后端配置源并立即生效，密钥不进入前端日志

#### Scenario: 密钥安全存储
- **GIVEN** 用户保存了 API key
- **WHEN** 系统持久化配置
- **THEN** key 存储在本地受保护配置文件中，不入库、不进遥测

### Requirement: CLI 友好交互
系统 SHALL 在 CLI 模式提供声明式、响应式的终端交互（折叠块、流式输出、多面板、焦点管理），复刻 Claude Code 式 Ink 体验。

#### Scenario: 流式输出
- **GIVEN** 内核产生分片回复
- **WHEN** CLI 收到分片
- **THEN** 终端增量渲染回复，不整块刷新

#### Scenario: 折叠块展示
- **GIVEN** 回复包含长输出或工具结果
- **WHEN** CLI 渲染该回复
- **THEN** 长内容默认折叠，用户可展开/收起

### Requirement: Web 界面访问
系统 SHALL 支持以 HTTP 服务 + 单页应用（SPA）形式提供 Web 界面，流式输出通过 SSE 推送。

#### Scenario: 浏览器访问
- **GIVEN** 用户启动 Web 模式
- **WHEN** 浏览器打开服务地址
- **THEN** 加载 SPA，可发起会话并实时看到流式回复

### Requirement: 桌面打包
系统 SHALL 支持将桌面端打包为可执行安装文件（Windows / macOS / Linux），并内置拉起本地后端的能力。

#### Scenario: 安装包运行
- **GIVEN** 用户安装桌面安装包
- **WHEN** 启动应用
- **THEN** 桌面壳自动拉起本地后端，加载同一 SPA 并可正常会话

### Requirement: Web 与桌面体验一致
系统 SHALL 使桌面端复用与 Web 相同的 SPA 构建产物，保证二者体验 100% 一致。

#### Scenario: 界面一致性
- **GIVEN** 同一版本的 Web 与桌面端
- **WHEN** 打开同一功能页面
- **THEN** 二者界面与交互完全一致
