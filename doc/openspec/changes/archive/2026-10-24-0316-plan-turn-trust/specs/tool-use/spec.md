# Spec Delta — tool-use（0316 计划轮可信度）

## MODIFIED Requirements

### Requirement: 插件安装工具

系统 SHALL 提供 install / uninstall / list 三个工具，使 Agent 可经对话/工具调用通道安装、卸载、列出插件；安装经 SafetyGate 副作用校验与权限审批流约束，危险操作走审批。

`list` 工具 SHALL 只列出**经插件安装面安装的插件**，SHALL NOT 被表述为可用工具全集。其工具
描述与返回载荷 SHALL 明示「内置原子工具（如 `tools.web_fetch` / `tools.code_run` / 文件工具）
与插件安装状态无关、始终按系统提示的「可用工具」可用」，使模型 SHALL NOT 因插件清单为空而
断言没有可用工具。

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

#### Scenario: 空插件清单不误导模型
- **GIVEN** 运行时未通过插件安装面安装任何插件
- **WHEN** 调用 list 工具
- **THEN** 返回的 `installed` 为空数组，且描述与载荷明示「内置原子工具与插件安装状态无关、
  清单为空不代表无可用工具」
