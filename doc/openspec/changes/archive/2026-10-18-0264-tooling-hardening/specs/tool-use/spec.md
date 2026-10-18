## MODIFIED Requirements

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
