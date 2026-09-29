# Configuration Specification Delta

## ADDED Requirements

### Requirement: 宠物模式配置
系统 SHALL 将宠物模式（pet）接入配置纳入 ConfigSpec 单一真源：pet.enabled（总开关）/ pet.persons_dir（多宠物 persona 目录）；默认关闭，开启后 PetSession 构造时经 resolve() 优先级链（CLI flag > env > config.yaml > 默认值）读取对应 pet.md 人格，禁止 pet 配置绕过 ConfigSpec 另起解析。

#### Scenario: pet 配置经 ConfigSpec 声明
- **GIVEN** 配置了 pet 段的 enabled / persons_dir
- **WHEN** 系统启动加载配置
- **THEN** pet.enabled / pet.persons_dir 经 ConfigSpec 单一真源解析，CLI flag / env / yaml 三面一一对应

#### Scenario: pet 默认关闭不激活
- **GIVEN** 未配置 pet 段或 pet.enabled 为 false
- **WHEN** 系统启动
- **THEN** 宠物模式不激活，其余功能不受影响

#### Scenario: persons_dir 多宠物加载
- **GIVEN** pet.enabled 开启且 pet.persons_dir 指向含多个 <name>.md 的目录
- **WHEN** PetSession 构造 / 激活宠物
- **THEN** 经 resolve() 优先级链读取 persons_dir，加载对应 pet.md 人格（每只宠物一个文件）
