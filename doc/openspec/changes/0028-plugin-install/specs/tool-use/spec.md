# Tool Use Specification

## Purpose
工具使用把模型动作转化为带 schema 的可执行调用，通过 coeffect 约束注入副作用契约，是"插件即原子"的运行时侧实现；并提供 install/uninstall/list 插件安装工具（经 SafetyGate + 权限审批流约束）。调用入口同步（invoke）与异步（ainvoke）同构：异步为主、同步为薄壳，支持事件循环内非阻塞与真并发调用。

## ADDED Requirements

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
