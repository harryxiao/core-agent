# Tasks

## 1. M5 — configuration CLI 覆盖层 + ConfigSpec（P0，本 Phase）

- [ ] 1.1 优先级链 CLI flag > env > config.yaml > 默认值
- [ ] 1.2 ConfigSpec 每项声明 cli_flag/env_var/default/map_to
- [ ] 1.3 暴露面分级 core/advanced/hidden
- [ ] 1.4 单一真源校验：非法 map_to 阻断启动

## 2. M6 — permission-mode 四档（P0，本 Phase）

- [ ] 2.1 read-only / interactive / auto-approve / high-risk-block 四档
- [ ] 2.2 映射 config.permission.mode + CLI --permission-mode
- [ ] 2.3 危险 action 走配置层声明 risk

## 3. M4 — cli-ops 命令面（契约层，代码随 Phase 3）

- [ ] 3.1 命令集六组：生命周期/状态/资产/连接/安全/网关
- [ ] 3.2 参数映射优先级链 + 一一对应模型
