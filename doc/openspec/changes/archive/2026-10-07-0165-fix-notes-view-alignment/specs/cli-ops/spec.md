# cli-ops 规格 delta：fix-notes-view-alignment

## ADDED Requirements

### Requirement: 诊断视图列对齐

`render_notes`（笔记清单视图）在等宽终端下各数据列 SHALL 对齐。列宽 SHALL 按**显示宽度**计算
（东亚宽 / 全角字符按 2 列计、其余按 1 列），SHALL NOT 按字符数（`len()`）计算 —— 按字符数补齐时
含中日韩字符的清单列起点仍随内容错位（一条中文标题会把后列整体推右）。列间分隔符 SHALL 为两个空格，
SHALL NOT 使用制表符（`\t`，其宽度由终端自定，正是本次缺陷的根源）。

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
