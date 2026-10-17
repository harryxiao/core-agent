## ADDED Requirements

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
