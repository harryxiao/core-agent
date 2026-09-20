"""组合与分发层（L5 Composition）。

CORE-Harness 唯一的静态层：只有组合代数、没有业务逻辑、永不进化。
通过三要素把已结晶的技能与插件按需组合、跨部署分发、按用户差异覆盖：

- **profile**（命名组合）：一个命名指向一个可复用插件组合集合
  （如 web / headless / sdk-minimal），归属全局。
- **bundle**（分发格式）：已结晶技能打包、跨部署复用，携带
  版本 / 依赖 / 哈希元数据，保证跨部署分发一致性。
- **patch.yml**（用户覆盖）：不改 profile 与 bundle 前提下按用户
  差异局部覆盖，归属 profile 内部。

层叠解析顺序固定为「bundle 层叠 → patch.yml 覆盖」，同名项由
patch.yml 覆盖；所有组合 / 覆盖操作可逆、可回退。

实现本模块的两条回归校验约束：

1. **无业务逻辑**：不承载推理 / 记忆 / 工具调用等运行时逻辑。
2. **永不进化**：进化产物经 L4 结晶后进入插件仓库，组合层只消费、不改造。

参照：
- 模块设计：doc/02-modules/composition.md
- 接口契约：doc/03-interfaces/composition-interface.md
- 行为规格：doc/openspec/specs/composition/spec.md
"""
