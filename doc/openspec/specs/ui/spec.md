# UI Specification

## Purpose
UI 界面与启动模式是 core-agent 面向用户的统一呈现层：CLI / Web / Desktop 三种入口共享同一内核与同一 LLM 配置源，行为、鉴权、日志保持一致；用户在 Web 与桌面 UI 内即可配置 LLM API；桌面与 Web 复用同一前端构建产物实现体验一致；并支持图像、语音等多模态输入的统一接入。

## 技术选型
- **CLI**：Python 原生 Textual，取 Ink 的声明式 + 响应式交互哲学，同进程复刻折叠块/流式/多面板，避免 Node 桥接
- **Web**：自研单 SPA（Svelte 前端）+ 统一后端 API（HTTP + SSE）
- **Desktop**：Tauri 壳复用同一 SPA 构建产物 + sidecar 拉起 Python 后端，体积远小于 Electron
- **统一 API 解耦**：三种模式共走同一后端 API，CLI 不绕过内核直连，保证鉴权/日志/行为一致

## Requirements

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

#### Scenario: 密钥持久化失败
- **GIVEN** 系统持久化 LLM API key 时发生磁盘写满或权限不足
- **WHEN** 保存配置失败
- **THEN** 回滚本次配置变更并提示用户，不留下半写状态，密钥不进入错误日志

### Requirement: CLI 友好交互
系统 SHALL 在 CLI 模式提供声明式、响应式的终端交互（折叠块、流式输出、多面板、焦点管理），复刻 Claude Code 式 Ink 体验。

实现：Textual（Python 原生）

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

实现：Svelte SPA

#### Scenario: 浏览器访问
- **GIVEN** 用户启动 Web 模式
- **WHEN** 浏览器打开服务地址
- **THEN** 加载 SPA，可发起会话并实时看到流式回复

#### Scenario: SSE 断线重连
- **GIVEN** Web 会话的 SSE 流式连接因网络抖动或服务端重启而断开
- **WHEN** 连接中断
- **THEN** 客户端按指数退避自动重连并恢复流式推送，期间以心跳探测连接存活，避免流式输出卡死

### Requirement: 桌面打包
系统 SHALL 支持将桌面端打包为可执行安装文件（Windows / macOS / Linux），并内置拉起本地后端的能力。

实现：Tauri 壳 + sidecar

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

### Requirement: 多模态输入
系统 SHALL 支持图像与语音等多模态输入的接入，并统一路由到具备对应能力的模型处理。

#### Scenario: 图像输入理解
- **GIVEN** 用户在 UI 中附加图片（截图/照片）
- **WHEN** 发起会话
- **THEN** 图片经统一输入管道交给具备视觉能力的模型理解，结果并入上下文

#### Scenario: 语音输入转写
- **GIVEN** 用户以语音方式输入
- **WHEN** 语音被采集
- **THEN** 系统先转写为文本再进入统一内核，必要时保留原始音频引用

#### Scenario: 模态能力缺失降级
- **GIVEN** 当前配置的模型不具备某模态理解能力
- **WHEN** 用户提交该模态输入
- **THEN** 系统明确提示不支持并给出可替换建议，不静默丢弃输入

### Requirement: 实时语音输出
系统 SHALL 支持将内核生成的文本回复以流式 TTS 合成语音实时播报，允许用户在播报过程中打断（barge-in），并保留语音与文本会话上下文的双向引用。

#### Scenario: 流式 TTS 播报
- **GIVEN** 内核产生分片文本回复
- **WHEN** 用户开启了语音播报
- **THEN** 分片文本被增量送入 TTS 合成并连续播报，不等待整段回复完成

#### Scenario: 用户打断（barge-in）
- **GIVEN** 语音播报正在进行
- **WHEN** 用户开口说话或按下打断键
- **THEN** 系统立即停止当前播报并转入语音输入处理，被打断的文本不丢失并保留在会话记录中

#### Scenario: 语音上下文引用
- **GIVEN** 会话中既有语音输入又有语音播报
- **WHEN** 用户后续引用或追问先前内容
- **THEN** 语音与文本共享同一会话记录可相互引用，必要时保留原始音频引用

### Requirement: Web Client 分离
系统 SHALL 支持 Web 前端作为纯静态资源独立托管，与常驻 Harness Host 后端解耦部署：前端经统一后端 API 连接 Host，前端升级不要求后端重启。

#### Scenario: 纯静态独立托管
- **GIVEN** Web SPA 构建产物
- **WHEN** 部署到任意静态托管
- **THEN** 前端可加载并连接常驻 Harness Host 后端 API 正常会话

#### Scenario: 前后端解耦升级
- **GIVEN** Web Client 与 Host 后端独立部署
- **WHEN** 前端发布新版本
- **THEN** 前端可独立升级，无需重启 Host 后端（后端 API 兼容时）
