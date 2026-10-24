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
系统 SHALL 为工具执行设置超时/资源上限，异常不拖垮主循环；子进程类工具在超时或取消时 SHALL
终止**整棵进程树**，SHALL NOT 只终止直接子进程而放任后代继续运行。

- 工具外层超时由 `ToolProvider` 的 `asyncio.wait_for` 兜底，超时归一为结构化 `TIMEOUT`。
- `tools.code_run` 的脚本级超时 SHALL 同样归一为 `TIMEOUT`（不再归为 `EXECUTION_FAILED`）。
- `tools.code_run` 的 `timeout` SHALL 接受 `(0, 600]` 内的有限秒数；非有限数或越界 SHALL
  结构化拒绝（`EXECUTION_FAILED`，带明确原因），SHALL NOT 启动子进程。
- POSIX 宿主 SHALL 以独立会话 / 进程组启动子进程，终止时按进程组发送信号；Windows 宿主 SHALL
  以新进程组启动，并以系统 `taskkill /T /F` 递归终止进程树。
- 超时或协程取消后 SHALL 先终止进程树并回收子进程，再返回；SHALL NOT 遗留仍可写文件的子进程。

#### Scenario: 执行超时
- **GIVEN** 一个工具调用正在执行
- **WHEN** 执行超过超时阈值
- **THEN** 强制终止该调用并返回超时错误（`TIMEOUT`），主循环继续运行

#### Scenario: 子进程超时终止整棵进程树
- **GIVEN** `tools.code_run` 启动的脚本派生了一个孙进程（如后台命令），且脚本超过 `timeout`
- **WHEN** 超时触发
- **THEN** 直接子进程与孙进程 SHALL 均被终止，孙进程不得在超时后继续产生副作用；
  调用返回 `TIMEOUT`

#### Scenario: 调用被取消同样终止进程树
- **GIVEN** `tools.code_run` 正在执行
- **WHEN** 上层取消该调用（`CancelledError`，如主循环中断）
- **THEN** 进程树被终止并回收，取消继续向上传播

#### Scenario: 超时参数越界拒绝
- **GIVEN** `timeout` 为 `0`、负数、`inf` 或大于 600
- **WHEN** 调用 `tools.code_run`
- **THEN** 返回 `EXECUTION_FAILED` 且不启动子进程

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

- **同步处理器卸载**：同步（非协程）handler SHALL 经 `asyncio.to_thread` 在工作线程执行，
  SHALL NOT 在事件循环线程内直接调用而阻塞其余任务；协程 handler SHALL 在事件循环上直接 await。
- **超时语义**：外层 `asyncio.wait_for` 超时 SHALL 归一为 `TIMEOUT`；工作线程不可强制终止
  （Python 线程限制）—— 超时停止等待后线程可能继续运行至返回，属已知局限。

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

#### Scenario: 同步处理器不阻塞事件循环
- **GIVEN** 一个同步 handler 正在执行耗时操作，事件循环上另有周期任务
- **WHEN** 经 ainvoke 调用该工具
- **THEN** 周期任务在 handler 执行期间继续推进（事件循环未被阻塞）

#### Scenario: 同步处理器并发
- **GIVEN** 两个同步 handler 各自耗时 T，经 ainvoke 并发发起
- **WHEN** 二者相互独立
- **THEN** 总耗时约等于 T（工作线程重叠执行），而非 2T

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
  一致（本 change 不放宽、不收紧确认门策略）。**输出截断 SHALL 首尾保留**：超出上限时保留头部
  约 1/3 与尾部其余，中间以省略标记（含省略字符数）分隔，总长 SHALL NOT 超过既有上限；
  `stdout_truncated` / `stderr_truncated` 判据不变。该口径 SHALL 仅作用于 `code_run` 前景结果；
  后台日志文件 SHALL NOT 被截断。

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

#### Scenario: 长输出首尾保留

- **GIVEN** `code_run` 的前景 `stdout`（或 `stderr`）长度超过既有上限
- **WHEN** 工具返回结果
- **THEN** 返回文本含**头部**与**尾部**内容，中间有省略标记；总长不超过既有上限；
  `stdout_truncated` / `stderr_truncated` 仍为 `true`

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

### Requirement: 文件写入原子性

`tools.file_write` 的**覆盖模式**（`mode="w"` / `"write"` / `"overwrite"`）SHALL 原子替换目标文件：
先在同目录写入临时文件并 `flush` + `fsync`，完成后以原子重命名替换目标。并发读者 SHALL 只可能
看到**完整的旧内容**或**完整的新内容**，SHALL NOT 看到空文件或半截内容。

- 写入失败（含替换失败）时 SHALL 清理临时文件，目标文件 SHALL 保持写入前的内容**逐字不变**。
- 新建文件的权限 SHALL 与常规 `open()` 创建一致（受 umask 约束）；替换既有文件 SHALL 保留其
  权限位。
- 追加模式（`mode="a"` / `"append"`）SHALL 保持既有追加语义，不受本要求约束。
- 撤销快照与逐次回滚语义 SHALL 不变：快照仍记录写入前的原内容，撤销仍恢复该内容。

#### Scenario: 覆盖写入原子可见
- **GIVEN** 目标文件已有内容
- **WHEN** 以覆盖模式写入新内容
- **THEN** 目标文件最终为新内容，目录中不残留临时文件

#### Scenario: 写入失败目标不变
- **GIVEN** 目标文件已有内容且替换阶段失败
- **WHEN** 覆盖写入抛出错误
- **THEN** 目标文件逐字保持原内容，临时文件被清理

#### Scenario: 追加模式不受影响
- **GIVEN** 目标文件已有内容
- **WHEN** 以追加模式写入
- **THEN** 内容按既有语义追加到末尾

### Requirement: 后台命令执行与进程管理

系统 SHALL 提供后台命令执行能力与配套的进程巡检 / 终止工具，使长命令不阻塞主循环。

- `tools.code_run` SHALL 接受 `background: boolean`（缺省 `false`）；为 `true` 时 SHALL 立即返回
  `pid` 与系统生成的输出文件路径，命令的 stdout 与 stderr 合并写入该文件；`timeout` 对后台
  任务不适用。输出文件 SHALL 以仅属主可读写（0600）创建，路径 SHALL 位于
  `$CORE_STATE_DIR`（缺省 `~/.core/state`）下的运行目录（0700）；SHALL NOT 接受模型指定的
  输出路径。
- 系统 SHALL 维护**有界**的后台任务注册表，记录本进程启动的后台任务，并在进程重启后恢复先前
  登记的条目；每条记录 pid、输出文件、启动时间、运行类型、进程启动标识（可用时）与退出码状态
  （仅本进程任务）；SHALL NOT 记录脚本正文、命令或环境变量。注册表满且无已退出项可淘汰时
  SHALL 拒绝新后台任务。
- 注册表 SHALL 把上述元数据**原子**写入 `$CORE_STATE_DIR` 下的 `processes.json`
  （仅属主可读写 0600）；写入失败 SHALL NOT 阻止后台任务启动与登记。加载时文件缺失、损坏或
  条目非法 SHALL 按空注册表 / 跳过该条处理，SHALL NOT 阻断注册表使用；恢复条目数 SHALL
  遵守注册表上界（保留最新条目）。
- 构造注册表时 SHALL 恢复登记项为**恢复项**（无进程句柄）；`tools.process` 的 `list` /
  `status` / `output` 对恢复项 SHALL 可用，结果 SHALL 带 `restored=true`。恢复项存活 SHALL
  以 `kill(pid, 0)` 探测；Linux 上 SHALL 再与 `/proc/<pid>/stat` 的进程启动时刻比对，
  不符（PID 复用）SHALL 判为已退出。恢复项的退出码 SHALL 为 `null`。
- `tools.process` SHALL 提供 `list`（全部后台任务）、`status`（按 pid）、`output`（按 pid 读取
  输出文件尾部，有界）三个动作；SHALL 为只读工具（可逆、`process:read` coeffect）。
- `tools.process_kill` SHALL 按 pid 终止**本进程启动的**注册表内后台任务进程树；SHALL 为
  不可逆工具（`process:write` coeffect），经确认门约束。恢复项 SHALL 拒绝终止并返回
  `killed=false` / `restored=true`，SHALL NOT 触达该进程；注册表外的 pid SHALL 拒绝，
  SHALL NOT 终止任意系统进程。
- 权限分级：工具标识中的 `process` 词元 SHALL 视为只读动作词（`tools.process` 判 `read`）；
  `tools.process_kill` 因含高危词元 `kill` SHALL 仍判 `high-risk`。

#### Scenario: 后台执行立即返回
- **GIVEN** Agent 需要运行耗时较长的命令
- **WHEN** 调用 `tools.code_run` 且 `background=true`
- **THEN** 调用立即返回 `pid` 与输出文件路径，命令在后台继续运行；`tools.process status`
  可按 pid 查到该任务

#### Scenario: 后台输出可读
- **GIVEN** 一个后台任务已产生输出
- **WHEN** 调用 `tools.process` 且 `action=output`、给出该 pid
- **THEN** 返回输出文件尾部（有界），不阻塞、不消耗该进程

#### Scenario: 终止后台任务
- **GIVEN** 一个由本进程启动的后台任务仍在运行
- **WHEN** 调用 `tools.process_kill` 并为该 pid 获得批准
- **THEN** 该任务及其后代被终止，`tools.process status` 显示已退出状态

#### Scenario: 未知 pid 拒绝
- **GIVEN** pid 不在本进程的后台任务注册表内
- **WHEN** 调用 `tools.process` 或 `tools.process_kill`
- **THEN** 返回 `found=false` 结构化结果，SHALL NOT触及该进程

#### Scenario: 后台任务不随调用返回被终止
- **GIVEN** `tools.code_run` 以 `background=true` 启动了一个任务
- **WHEN** 工具调用返回后主循环继续
- **THEN** 该后台任务持续运行，直至自行结束或被 `tools.process_kill` 终止

#### Scenario: 进程工具权限分级
- **GIVEN** 权限引擎对 `tools.process` 与 `tools.process_kill` 判级
- **WHEN** 执行前判定
- **THEN** `tools.process` 判为 `read` 并放行；`tools.process_kill` 判为 `high-risk`，
  未获审批时返回 `APPROVAL_REQUIRED`

#### Scenario: 重启后仍可巡检
- **GIVEN** 一个后台任务在 core-agent 上一进程退出后仍在运行，且其登记项已落盘
- **WHEN** 新进程构造注册表并调用 `tools.process`
- **THEN** `list` / `status` / `output` 仍可定位该任务（`restored=true`），运行中的任务
  `running=true`，输出文件尾部可读

#### Scenario: PID 复用不误报
- **GIVEN** 恢复项登记的进程启动时刻与当前 `/proc/<pid>/stat` 不符（pid 已被无关进程复用）
- **WHEN** 查询该恢复项状态
- **THEN** 返回 `running=false`，SHALL NOT 报告该无关进程为原后台任务

#### Scenario: 恢复项不可终止
- **GIVEN** 一个从磁盘恢复的登记项（无进程句柄）
- **WHEN** 调用 `tools.process_kill` 并为该 pid 获得批准
- **THEN** 返回 `found=true` / `killed=false` / `restored=true`，SHALL NOT 触达该进程

#### Scenario: 持久化文件损坏不阻断
- **GIVEN** `processes.json` 内容不是合法 JSON 或含非法条目
- **WHEN** 构造后台任务注册表
- **THEN** 加载不抛异常，非法条目被跳过，注册表可继续登记新任务

### Requirement: 工具参数查询
系统 SHALL 提供只读原子工具 `tools.schema_read`，用于在**参数 schema 未随请求注入**时按需
查询工具参数（注入范围见 loop「工具参数按需注入」）：

- 参数：可选 `tool_ids`（字符串数组）。
- 缺省 / 空数组：SHALL 返回全部已注册工具的 `tool_id` 与 `description` 列表。
- 给定 id：SHALL 返回每个已注册 id 的 `tool_id`、`description` 与参数 schema（`parameters`）；
  未注册 id SHALL 记入 `unknown` 列表返回，SHALL NOT 抛错或中断本轮。
- 契约：`coeffects=["schema:read"]`（组合根注册该 coeffect）、`reversible=True`；权限分级
  SHALL 为只读（`read` 词元命中）⇒ 默认放行，不经确认门。
- 本工具 SHALL **只挂主工具面**：子 Agent / 神兽 / 宠物 loop SHALL NOT 注册（其工具面不超过
  按需注入阈值，无需加载）。
- 承载本工具的**受限视图**（如计划轮只读视图，见 ui「会话级执行模式与计划审批」）SHALL 以
  **该视图自身工具面**为目录：无参列表 SHALL NOT 列出视图外工具；按 id 请求视图外工具 SHALL
  记入 `unknown`，SHALL NOT 返回其参数 schema（视图外工具在执行面本就 fail-closed，目录口径
  SHALL 与之同源）。

#### Scenario: 无参列出全部工具
- **GIVEN** 工具面已注册若干工具（含 `tools.schema_read` 自身）
- **WHEN** 模型调用 `tools.schema_read` 且不带参数
- **THEN** 返回全部已注册工具的 id 与描述，不含参数 schema

#### Scenario: 按 id 返回参数 schema
- **GIVEN** 工具面已注册 `tools.process`
- **WHEN** 模型调用 `tools.schema_read` 并请求 `["tools.process"]`
- **THEN** 返回该工具的描述与完整参数 schema；未知 id 记入 `unknown` 且不阻断

#### Scenario: 受限视图不泄漏视图外工具
- **GIVEN** 一个受限工具视图，其工具面**不含** `tools.web_fetch`（根工具面含之）
- **WHEN** 在视图内调用 `tools.schema_read`（先无参，再请求 `["tools.web_fetch"]`）
- **THEN** 无参列表不含 `tools.web_fetch`；按 id 请求时该 id 落在 `unknown`，返回结果不含其
  参数 schema

#### Scenario: 只读放行
- **GIVEN** 权限引擎对动作做风险分级
- **WHEN** 动作工具为 `tools.schema_read`
- **THEN** 判为只读、默认放行（不经人工确认）
