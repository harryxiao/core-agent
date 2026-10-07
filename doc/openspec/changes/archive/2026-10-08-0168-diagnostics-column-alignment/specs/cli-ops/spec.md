# cli-ops 规格 delta：diagnostics-column-alignment

## MODIFIED Requirements

### Requirement: 诊断视图列对齐

诊断源的**全部**列表型视图 —— `render_sessions` / `render_config` / `render_mcp` / `render_skills` /
`render_notes` / `collect_status` —— 在等宽终端下各数据列 SHALL 对齐。列宽 SHALL 按**显示宽度**计算
（东亚宽 / 全角字符按 2 列计、其余按 1 列），SHALL NOT 按字符数（`len()`）计算 —— 按字符数补齐时
含中日韩字符的清单列起点仍随内容错位（一条中文标题会把后列整体推右）。列间分隔符 SHALL 为两个空格，
SHALL NOT 使用制表符（`\t`，其宽度由终端自定，正是本次缺陷的根源）。

视图分两形态，各自的对齐口径：

- **表格型**（多行多列：会话 / MCP 端点 / 笔记）：**每列**按列内最长显示宽度补齐；
- **键值型**（一组 `标签 值` 行：配置 / 技能 / 运行状态）：**标签列**按标签中最长显示宽度补齐。

对齐 SHALL NOT 改变各行取值（只补空白）、SHALL NOT 改变 `Report` 接口与各视图签名。

#### Scenario: 笔记清单等宽列

- **WHEN** 笔记库存在多条笔记且 note_id / title 长度不一
- **THEN** `render_notes` 输出的每行中 note_id、title 列分别按清单内最长**显示宽度**补齐对齐
- **AND** 列间分隔符为两个空格，行内容不包含制表符（`\t`）

#### Scenario: 含中日韩字符的清单仍对齐

- **WHEN** 清单内某条笔记的 title 含中日韩宽字符（其显示宽度大于字符数）
- **THEN** 各行时间戳列的**起始显示列**一致（按字符数补齐会使该行整体右移）

#### Scenario: title 回退对齐

- **WHEN** 某笔记 title 为空而 note_id 较长
- **THEN** 该行 title 回退显示 note_id，且回退后 title 列宽不小于清单内最长 title

#### Scenario: 会话与 MCP 端点清单等宽列

- **WHEN** 会话注册表 / MCP 端点表存在多行且各列长度不一
- **THEN** 各行同一列的**起始显示列**一致（每列按列内最长显示宽度补齐）
- **AND** 列间分隔符为两个空格，行内容不包含制表符（`\t`）

#### Scenario: 键值型视图标签列对齐

- **WHEN** 配置 / 技能 / 运行状态视图输出多行 `标签 值`
- **THEN** 各行**值的起始显示列**一致（标签列按标签中最长显示宽度补齐）
- **AND** 行内容不包含制表符（`\t`）；技能视图的逐条明细行（`· …`）原样透出、不参与补齐
