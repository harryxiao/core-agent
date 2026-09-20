# Tasks

## 1. 组合与分发核心（P1）

- [ ] 1.1 profile 命名组合：一个 profile 命名一个可复用插件组合集合，层叠多个 bundle 并叠加用户 patch.yml
- [ ] 1.2 bundle 分发格式：已结晶技能打包为 bundle、跨部署复用
- [ ] 1.3 patch.yml 用户覆盖：不改 profile 与 bundle 前提下按用户差异局部覆盖
- [ ] 1.4 层叠解析：按确定顺序合并，同名项由 patch.yml 覆盖，可逆、可回退
