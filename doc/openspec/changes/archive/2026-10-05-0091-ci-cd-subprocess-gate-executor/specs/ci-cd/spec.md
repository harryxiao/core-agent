# CI-CD Specification Delta

## MODIFIED Requirements

### Requirement: 交付流水线
系统 SHALL 提供 lint/typecheck/test/build 四道质量门禁；任一门禁失败阻断交付，门禁实现引用 development-toolchain。生产**缺省**门禁执行器 SHALL 以 **stdlib `subprocess`** 执行既有 `GATE_COMMANDS` 命令基准（零第三方依赖、不经 shell），并按**退出码**判定该门禁通过与否；命令**跑不起来**（工具缺失 / 超时）与**跑失败**（非零退出）SHALL 同样归一为「该门禁未通过」的结果载体（`reason` 为有界输出尾部），SHALL NOT 向调用方抛裸异常。

#### Scenario: 门禁全通过交付
- **GIVEN** 一次交付提交
- **WHEN** CICDPipeline 顺序执行 lint/typecheck/test/build
- **THEN** 四道门禁全部通过，交付放行

#### Scenario: 门禁失败阻断
- **GIVEN** 某道门禁失败
- **WHEN** CICDPipeline 执行到该门禁
- **THEN** 阻断交付，返回失败门禁与原因

#### Scenario: 缺省执行器真跑门禁命令
- **GIVEN** 未注入执行器的 CICDPipeline
- **WHEN** 执行某道门禁
- **THEN** 以 stdlib `subprocess` **真实执行**该门禁对应的 `GATE_COMMANDS` 命令，并据退出码判定通过与否（零第三方依赖）

#### Scenario: 门禁运行异常归一为未通过
- **GIVEN** 门禁命令非零退出 / 找不到可执行文件 / 超过超时阈值
- **WHEN** 缺省执行器处理结果
- **THEN** 返回「该门禁未通过」的结果载体并附原因，由 CICDPipeline 按「门禁失败阻断」处理，不抛裸异常
