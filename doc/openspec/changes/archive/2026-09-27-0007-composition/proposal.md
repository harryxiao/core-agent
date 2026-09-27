# Change: Composition 组合与分发层（profile / bundle / patch.yml）

## Why

架构蓝图 L5「组合与分发层」是 CORE-Harness 唯一的静态层，定义 profile（命名组合）/ bundle（分发格式）/ patch.yml（用户覆盖）三要素，是「一切皆插件 + 可逆组合」的基底。但当前 doc/ 文档体系与 openspec specs/ 均无 composition capability，L5 层设计悬空、无法追踪，也无法支撑「已结晶技能跨部署分发」的落地。

## What Changes

- 新增 `composition` capability：定义 profile 命名组合 / bundle 分发格式 / patch.yml 用户覆盖 / 层叠解析 四条 Requirement
- **profile 命名组合**：一个 profile 命名一个可复用的插件组合集合，层叠多个 bundle 并叠加用户 patch.yml
- **bundle 分发格式**：已结晶的技能可打包为 bundle，跨部署复用
- **patch.yml 用户覆盖**：不改 profile 与 bundle 的前提下按用户差异做局部覆盖
- **层叠解析**：按「bundle 层叠 + patch.yml 覆盖」的确定顺序解析，结果可逆、可回退

## Impact

- **Affected specs**：`composition`（新增 capability）
- **Affected docs**：`02-modules/composition.md`（新增）、`03-interfaces/composition-interface.md`（新增，后续步骤）
- **Affected code**：无（L5 为静态组合层，仅声明组合代数与格式，具体实现由后续步骤确定）
- **Dependencies**：依赖 `plugin-registry`（插件注册）作为组合对象的来源；依赖架构蓝图 `core_harness_architecture.md` L5
