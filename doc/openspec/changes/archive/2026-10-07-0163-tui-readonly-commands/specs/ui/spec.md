## ADDED Requirements

### Requirement: TUI 只读诊断命令

TUI SHALL 提供一组**只读**斜杠命令（`/doctor` / `/status` / `/sessions` / `/config` / `/mcp` / `/skill` /
`/notes`），并把结果**就地**呈现为时间线上的一条结果块。命令名、说明与处理器的对应关系 SHALL 取自命令
登记的**单一真源**（SHALL NOT 与分发各记一份）。

结果 SHALL 来自与 CLI `doctor` / `status` **同一**的只读诊断源（SHALL NOT 各写一份检查逻辑），
并 SHALL NOT 含任何**密钥值**：涉及密钥的项 SHALL ONLY 呈现 `${VAR}` **引用名**与「可解析 / 不可解析」
的**布尔结论**；`/mcp` SHALL NOT 呈现端点 `args`。

只读命令 SHALL **零副作用**：SHALL NOT 追加对话轮次（`run_loop` / `run_task` SHALL NOT 被调用）、
SHALL NOT 写转录 / 记忆 / 笔记、SHALL NOT 改动呈现态（会话标识、时间线内容、子任务折叠块、焦点视图
**逐字不变**）；SHALL NOT 产生用户输入回显（`❯` 前缀行）。

只读命令 SHALL **不豁免忙态**：本轮执行尚未结束时提交 SHALL 被拒绝并提示等待（与 `/resume` 同侧）。

只读命令 SHALL NOT 接受参数（真源中其参数位为空）：带参数提交 SHALL ONLY 提示、SHALL NOT 执行。
真源**未登记**的斜杠输入 SHALL 保持既有行为（作为普通消息进入对话）；既有 6 条命令的语义、提示串与
分发次序 SHALL NOT 改变。

#### Scenario: 浮层列出只读命令并可采纳

- **GIVEN** TUI 就绪
- **WHEN** 用户输入 `/`
- **THEN** 浮层候选包含全部只读命令（顺序即真源顺序）
- **AND THEN** 采纳（`Tab` / `Enter`）SHALL ONLY 改写输入框（无参数位）、SHALL NOT 提交

#### Scenario: 执行命令落结果块且不进对话

- **GIVEN** TUI 就绪且诊断源已接线
- **WHEN** 用户提交 `/doctor`（或 `/status` / `/sessions` / `/config` / `/mcp` / `/skill` / `/notes`）
- **THEN** 时间线新增该命令的一条结果块
- **AND THEN** **无** `❯` 回显行、**无**对话轮次（`run_loop` / `run_task` SHALL NOT 被调用）

#### Scenario: 只读命令零副作用

- **GIVEN** 时间线已有内容、当前会话已登记、记忆与笔记已有若干条目
- **WHEN** 用户提交任一已登记只读命令
- **THEN** 会话标识、转录条数、记忆条目与笔记内容**逐字不变**；时间线除新增结果块外**逐字不变**

#### Scenario: 本轮执行期间拒绝只读命令

- **GIVEN** 一轮执行尚未结束（忙碌）
- **WHEN** 用户提交 `/doctor`
- **THEN** 拒绝执行（提示处理中），时间线**逐字不变**

#### Scenario: 只读输出不含密钥值

- **GIVEN** 配置中的密钥引用可解析（其值存在于环境或 keychain）
- **WHEN** 用户提交 `/config` 或 `/doctor`
- **THEN** 结果块只出现 `${VAR}` 引用名与「可解析」结论，**不出现**其解析结果

#### Scenario: 带参数与未登记前缀走既有路径

- **GIVEN** TUI 就绪
- **WHEN** 用户提交 `/doctor 额外参数` 或 `/zzz`
- **THEN** 前者 ONLY 提示（不执行、不改动呈现态）；后者仍作为普通消息进入对话（既有行为不变）
