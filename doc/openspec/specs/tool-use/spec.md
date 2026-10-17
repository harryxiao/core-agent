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
系统 SHALL 为每个写类工具提供撤销函数（可逆效应），支持时间旅行回滚。撤销函数 SHALL **按次生成**：每次成功执行后由调用方取得**一份**绑定**该次**写入前快照的撤销闭包——同一工具实例跨多次调用 SHALL **各持独立快照**（按 trace 的 LIFO 序），SHALL NOT 让后续调用覆写先前调用的快照；撤销第 N 次调用 SHALL 恢复**该次**写入前的内容，SHALL NOT 恢复其后调用的快照。

#### Scenario: 写类工具撤销
- **GIVEN** 一个写类工具（file_write / file_patch 等）已成功执行并产生副作用
- **WHEN** 上层请求撤销
- **THEN** 调用该工具声明的撤销函数，副作用被可逆回滚

#### Scenario: 同一工具多次写入各自独立回滚
- **GIVEN** 同一个写类工具实例先后写入文件 A 与文件 B（A 原已存在、B 原本不存在）
- **WHEN** 逆序撤销这两次调用
- **THEN** 先恢复 B 的写入前状态（原本不存在 ⇒ 删除），再恢复 A 的写入前内容；任一次撤销 SHALL NOT 被后续调用的快照覆写

#### Scenario: 跨 trace 不串
- **GIVEN** 同一个写类工具实例先在 trace `t1` 写文件 A、后在 trace `t2` 写文件 B
- **WHEN** 只回滚 `t1`
- **THEN** A 恢复为 `t1` 写入前的内容，而 B **逐字不变**（`t2` 的副作用不被 `t1` 的回滚触及）

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
### Requirement: 内置原子工具（代码执行 / 网页读取）

系统 SHALL 内置代码执行与网页读取原子工具，与文件工具一致地经 schema 校验、coeffect 确认门、
超时与输出截断约束执行。

- **代码执行方言**：`tools.code_run` SHALL 支持 `type` 为 `python`、`bash`、`powershell` 三档。
  - `python`：以当前解释器执行脚本片段（既有语义）。
  - `bash`：经 `bash -c`（或平台等价）执行；目标解释器不在 PATH ⇒ **结构化拒绝**，SHALL NOT
    改跑 powershell 或其它方言。
  - `powershell`：经 PowerShell 执行（优先 `pwsh`，回落 `powershell`）；目标解释器不在 PATH ⇒
    **结构化拒绝**，SHALL NOT 改跑 bash。
- **平台缺省**：调用方未指定 `type` 时，Windows 宿主 SHALL 缺省 `powershell`；Darwin / Linux
  宿主 SHALL 缺省 `bash`；显式 `type` 优先于缺省。未知 / 其它 OS 的缺省 SHALL 保持与历史
  「未传则按 bash 路径解析」兼容或要求显式（实现与 design 钉死一种，测试锚定）。
- **输出解码确定性**：`stdout` / `stderr` SHALL 以 **UTF-8** 解码（非法字节以替换符处理），
  SHALL NOT 依赖宿主 locale 的缺省解码。PowerShell 子进程 SHALL 在用户脚本前设置 UTF-8 输出
  编码（`[Console]::OutputEncoding`，兼容 5.1 与 7+）；Python 子进程 SHALL 以
  `PYTHONIOENCODING=utf-8` 启动（保留其余宿主环境）。
- **工作目录**：`cwd` SHALL 在入口做 `~` 展开（其余不 `resolve` / 不 `abspath`）；每次调用
  独立，SHALL NOT 跨调用保留 `cd` 或环境变量变更。
- **工具面陈述**：工具 description / schema SHALL 明示「显式 `type` 优先于平台缺省」与
  `cwd` 的 `~` 语义。
- **超时与截断 / 确认门**：返回码与 stdout/stderr 截断、不可逆高风险确认门语义 SHALL 与既有
  一致（本 change 不放宽、不收紧确认门策略）。

#### Scenario: 代码执行（python）

- **GIVEN** Agent 需执行一段 Python 代码
- **WHEN** 调用 `tools.code_run` 且 `type` 为 `python`（或等价显式）
- **THEN** 子进程以当前 Python 解释器执行并返回返回码与 stdout/stderr（按上限截断）；
  超时/异常归一为结构化错误；副作用声明经确认门

#### Scenario: 代码执行（bash）

- **GIVEN** Agent 需执行 bash 脚本且宿主 PATH 上存在 bash
- **WHEN** 调用 `tools.code_run` 且 `type` 为 `bash`
- **THEN** 经 bash 执行并返回返回码与输出（截断口径同既有）

#### Scenario: 代码执行（powershell）

- **GIVEN** Agent 需执行 PowerShell 且宿主存在 `pwsh` 或 `powershell`
- **WHEN** 调用 `tools.code_run` 且 `type` 为 `powershell`
- **THEN** 经 PowerShell 执行（优先 pwsh）并返回返回码与输出（截断口径同既有）

#### Scenario: Windows 未指定 type 时缺省 powershell

- **GIVEN** 宿主为 Windows，且调用未指定 `type`
- **WHEN** 调用 `tools.code_run`
- **THEN** 按 `powershell` 方言解析并执行（或因缺解释器而结构化拒绝），SHALL NOT 在未显式
  指定时走 bash

#### Scenario: Darwin/Linux 未指定 type 时缺省 bash

- **GIVEN** 宿主为 Darwin 或 Linux，且调用未指定 `type`
- **WHEN** 调用 `tools.code_run`
- **THEN** 按 `bash` 方言解析并执行（或因缺解释器而结构化拒绝）

#### Scenario: 缺解释器不得改方言

- **GIVEN** 请求的 `type` 为 `bash` 或 `powershell`，但对应解释器不在 PATH
- **WHEN** 调用 `tools.code_run`
- **THEN** 结构化拒绝，SHALL NOT 静默改用另一 shell 方言执行

#### Scenario: 非 UTF-8 locale 下输出解码确定

- **GIVEN** 宿主 locale 不是 UTF-8（如 zh-CN Windows 的 cp936），子进程输出 UTF-8 字节
- **WHEN** 调用 `tools.code_run`
- **THEN** 父进程以 UTF-8 解码 `stdout` / `stderr`（非法字节替换），输出不因 locale 乱码；
  PowerShell 调用在用户脚本前已设置 UTF-8 输出编码，Python 调用带 `PYTHONIOENCODING=utf-8`

#### Scenario: cwd 展开家目录

- **GIVEN** 调用 `tools.code_run` 且 `cwd` 为 `~/work`
- **WHEN** 工具解析参数
- **THEN** 子进程工作目录为当前用户家目录下的 `work`，SHALL NOT 在当前目录下创建字面 `~` 目录

#### Scenario: 网页读取

- **GIVEN** Agent 需读取一个网页
- **WHEN** 调用 `tools.web_fetch`（仅接受 http/https URL）
- **THEN** GET 抓取返回状态码与正文（按字节上限截断），网络错误归一为结构化错误；出站网络
  coeffect 经确认门（高风险需人工审批）
### Requirement: 质量门禁工具
系统 SHALL 把既有的四道质量门禁（lint / typecheck / test / build）暴露为单个原子工具 `tools.gate_run`，使 Agent 可经工具调用通道按**门禁名**触发门禁并取回结构化结果。门禁名集合与门禁命令 SHALL 取自 `ci-cd` 的**单一真源**（`GATE_COMMANDS`），该工具 SHALL NOT 另立一套门禁命令或第二个门禁执行器；门禁执行器 SHALL 经**构造参数注入**（工具层 SHALL NOT 依赖交付流水线层）。该工具 SHALL 诚实声明 `process`/`filesystem` 副作用且为**不可逆**，照旧受确认门约束（高风险需人工审批）；门禁名不在真源内时 SHALL fail-closed 拒绝，SHALL NOT 触达执行器。

#### Scenario: 按名触发门禁
- **GIVEN** Agent 需在改动后自检，且已注入门禁执行器
- **WHEN** 调用 `tools.gate_run` 并给出门禁名（如 `lint`）
- **THEN** 经注入执行器按 `GATE_COMMANDS` 单一真源执行该道门禁，返回结构化结果（门禁名 / 是否通过 / **有界**失败原因）

#### Scenario: 门禁工具不可逆走确认门
- **GIVEN** 未处于无人值守自动放行档
- **WHEN** 执行 `tools.gate_run`
- **THEN** 因声明 `process`/`filesystem` 副作用且不可逆而触发**人工审批**，未批准则结构化拒绝执行（`IRREVERSIBLE_BLOCKED`）

#### Scenario: 未知门禁 fail-closed
- **GIVEN** 门禁名不在单一真源内（如 `deploy`）
- **WHEN** 调用 `tools.gate_run`
- **THEN** 结构化拒绝（`EXECUTION_FAILED`），且**不执行任何命令**、不触达注入的执行器

#### Scenario: 门禁名集合与单一真源一致
- **GIVEN** 组合根装配了该工具
- **WHEN** 读取其 schema 的门禁名枚举
- **THEN** 枚举与 `GATE_COMMANDS` 的键集合**逐字一致**（无第二份门禁名清单）
