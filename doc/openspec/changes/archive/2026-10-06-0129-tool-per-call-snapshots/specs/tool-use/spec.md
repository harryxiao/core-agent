# Tool Use Specification Delta

## MODIFIED Requirements

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
