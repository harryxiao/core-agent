# ui — TUI 视觉密度预算（change 0299）

## ADDED Requirements

### Requirement: TUI 视觉密度预算

TUI SHALL 以**信息密度优先**呈现：垂直留白、边框与行数须服从本条预算；预算内的
压缩 SHALL NOT 改变既有事件语义、命令分发、标题语法（TUI+Web 共享表）或折叠块的
缺省收起 / 展开即全文语义。

**Chrome 预算**：钉底输入区（含状态行）SHALL 占用 **idle ≤ 4 行、busy（标签栏可见）≤ 5
行**；快捷键提示 SHALL 以**无边框单行**呈现，工作状态行（spinner）SHALL 与其**同行**共存
（SHALL NOT 各自独占带边框的盒子）；边框 SHALL 仅保留于输入框与命令浮层。

**展开体预算**：折叠块展开区 SHALL 无顶部空行（`Contents` 顶部 padding 为 0），左侧缩进
SHALL ≤ 2 列。

**Markdown 预算**：回复内的代码围栏 SHALL 呈现为 N 行内容占 N 行（四周零附加行）；
标题仅在上方留 1 行；水平线 SHALL 占 1 行；段落间 1 行留白 SHALL 保留（可读性，SHALL NOT
压缩为 0）。

**文件工具呈现**：`tools.file_read` / `tools.file_write` / `tools.file_patch` 的展开体
SHALL 首行呈现 **dim 元信息行**（write：`N 字节 · M 行写入`；patch：`+N −M · hunk H`；
read：`N 行`；任一侧数据被事件面节选截断时 SHALL 标注 `节选`，SHALL NOT 谎报全量），
正文 SHALL 按文件后缀语法高亮（patch 用 diff 呈现，未知后缀回退纯文本）；展开体 SHALL
有 **40 行上界**，超出 SHALL 截断并附尾行注明总行数。抽取失败 SHALL 回退为既有纯文本
呈现（SHALL NOT 崩溃或留空）。其他工具的呈现 SHALL 逐字不变。

**横幅与分隔**：启动横幅 SHALL 占 2 行（无边框）；每轮助手回复结束后 SHALL 呈现 1 行
分隔（SHALL NOT 进入既有时间线文本断言面）。

#### Scenario: 底部 chrome 行数预算

- **GIVEN** TUI 就绪（idle，无任务标签栏）
- **WHEN** 度量钉底输入区整体高度
- **THEN** ≤ 4 行；标签栏可见（busy）时 ≤ 5 行；快捷键提示与 spinner 同行且无边框

#### Scenario: 展开体无顶空行

- **GIVEN** 时间线上一个已收起的步骤块
- **WHEN** 用户展开它
- **THEN** 展开区首行即正文（无顶部空行），左侧缩进 ≤ 2 列

#### Scenario: 代码围栏高度预算

- **GIVEN** 回复含一段 N 行内容的代码围栏
- **WHEN** TUI 渲染该回复
- **THEN** 围栏区域高度为 N（四周零附加行）；块背景与正文可辨识（既有不透明背景要求不回退）

#### Scenario: 文件写入块呈现元信息与高亮

- **GIVEN** 一次 `tools.file_write` 完成（args 含 path/content，output 含 bytes_written）
- **WHEN** 用户展开该步骤块
- **THEN** 首行为 dim 元信息行（如 `12 字节 · 1 行写入`），正文按后缀语法高亮；
      超长输出截断至 40 行并附 `…（共 X 行，已截断）` 尾行

#### Scenario: 文件补丁块呈现 diff

- **GIVEN** 一次 `tools.file_patch` 完成（args 含 old_content/new_content）
- **WHEN** 用户展开该步骤块
- **THEN** 首行含 `+N −M · hunk H`；正文以 diff 形态红绿呈现；未命中替换时标注 `未命中`；
      任一侧被节选截断时标注 `节选`

#### Scenario: 抽取失败回退纯文本

- **GIVEN** 某文件工具的 output 形态不在预期（抽取标记缺失）
- **WHEN** 用户展开该步骤块
- **THEN** 正文以既有纯文本呈现，不崩溃、不留空

#### Scenario: 启动横幅与轮次分隔

- **GIVEN** TUI 启动并完成一轮对话
- **WHEN** 查看时间线
- **THEN** 启动横幅占 2 行；该轮回复结束后恰有 1 行分隔
