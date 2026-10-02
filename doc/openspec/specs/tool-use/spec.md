# Tool Use Specification

## Purpose
工具使用把模型动作转化为带 schema 的可执行调用，通过 coeffect 约束注入副作用契约，是"插件即原子"的运行时侧实现；并提供 install/uninstall/list 插件安装工具（经 SafetyGate + 权限审批流约束）。调用入口同步（invoke）与异步（ainvoke）同构：异步为主、同步为薄壳，支持事件循环内非阻塞与真并发调用。

## Requirements

### Requirement: 工具定义与注册
系统 SHALL 用 schema 定义工具，并在启动时校验注册，非法定义拒绝载入。

#### Scenario: schema 合法注册
- **GIVEN** 一个 schema 合法的工具定义
- **WHEN** 启动时注册
- **THEN** 工具进入可调用集合

#### Scenario: schema 非法拒绝
- **GIVEN** 一个 schema 非法的工具定义
- **WHEN** 启动时注册
- **THEN** 返回 `INVALID_TOOL_SCHEMA` 且不载入

### Requirement: 参数校验
系统 SHALL 在调用前按 schema 校验参数，缺参/错型直接拒绝。

#### Scenario: 参数缺失拒绝
- **GIVEN** 一个工具调用缺少必需参数
- **WHEN** 执行前校验
- **THEN** 调用被拒绝并返回结构化错误

### Requirement: coeffect 副作用契约
系统 SHALL 用 coeffect 声明工具副作用类型（read-only/write/secret/external），执行前由权限引擎校验。

#### Scenario: 副作用校验
- **GIVEN** 一个声明为 `secret` 的工具
- **WHEN** 调用该工具
- **THEN** 权限引擎按 secret 规则校验，未授权则拒绝

#### Scenario: 声明与行为不符告警
- **GIVEN** 工具实际产生超出 coeffect 声明的副作用
- **WHEN** 遥测观测到偏差
- **THEN** 记录偏差并标记该工具待复核

### Requirement: 撤销与时间旅行回滚
系统 SHALL 为每个写类工具提供撤销函数（可逆效应），支持时间旅行回滚。

#### Scenario: 写类工具撤销
- **GIVEN** 一个写类工具（file_write / file_patch 等）已成功执行并产生副作用
- **WHEN** 上层请求撤销
- **THEN** 调用该工具声明的撤销函数，副作用被可逆回滚

#### Scenario: 时间旅行回滚
- **GIVEN** 执行历史记录了各步骤的工具调用与效应
- **WHEN** 需要回滚到某个历史检查点
- **THEN** 沿历史逆序执行各写类工具的撤销函数，状态恢复到检查点

### Requirement: 超时与资源上限
系统 SHALL 为工具执行设置超时/资源上限，异常不拖垮主循环。

#### Scenario: 执行超时
- **GIVEN** 一个工具调用正在执行
- **WHEN** 执行超过超时阈值
- **THEN** 强制终止该调用并返回超时错误，主循环继续运行

#### Scenario: 执行异常兜底
- **GIVEN** 工具 handler 执行中抛出异常（如参数值合法但语义非法，底层库报错）
- **WHEN** 调用经 ToolProvider 执行
- **THEN** 异常归一为 EXECUTION_FAILED 结构化错误返回，主循环继续运行，不向模型抛裸异常

#### Scenario: 资源上限
- **GIVEN** 一个工具调用申请资源（内存 / CPU / 子进程）
- **WHEN** 资源占用超过上限
- **THEN** 限制或终止该调用，防止拖垮主循环

### Requirement: 异步工具调用
系统 SHALL 提供异步工具调用入口 ainvoke，与同步 invoke 共用统一请求 / 响应模型与 schema / coeffect 校验链路；ainvoke 支持事件循环内非阻塞调用与真并发，invoke 保留为薄壳（thin wrapper），内部经事件循环桥接调用对应异步实现，调用方无需感知事件循环、零改动。

#### Scenario: 异步调用入口
- **GIVEN** 内核 loop 运行于事件循环中，需并发执行多个工具
- **WHEN** 经 ainvoke 发起工具调用
- **THEN** 调用不阻塞事件循环，返回 awaitable，多个工具调用可并发执行

#### Scenario: 同步薄壳等价
- **GIVEN** 调用方处于同步上下文
- **WHEN** 调用 invoke 同步入口
- **THEN** 语义与 ainvoke 一致（含 schema 校验与 coeffect 副作用校验），内部经事件循环桥接完成调用，调用方无需改动

#### Scenario: 真并发执行
- **GIVEN** 多个相互独立的工具调用
- **WHEN** 经 ainvoke 并发发起
- **THEN** 各调用真并发执行（非串行阻塞），总耗时约等于最慢单个调用而非各调用耗时之和

### Requirement: 插件安装工具
系统 SHALL 提供 install / uninstall / list 三个工具，使 Agent 可经对话/工具调用通道安装、卸载、列出插件；安装经 SafetyGate 副作用校验与权限审批流约束，危险操作走审批。

#### Scenario: 对话安装插件
- **GIVEN** Agent 需安装一个插件
- **WHEN** 调用 install 工具并给出来源
- **THEN** 经 SafetyGate 副作用校验 + 权限审批流后执行安装，返回安装结果

#### Scenario: 危险安装走审批
- **GIVEN** install 目标被判为高危（如出站下载执行）
- **WHEN** 执行 install
- **THEN** 触发人工审批，未批准则拒绝安装

#### Scenario: 卸载与列出
- **GIVEN** Agent 需管理已装插件
- **WHEN** 调用 uninstall / list 工具
- **THEN** 卸载对应插件 / 返回已安装插件清单

