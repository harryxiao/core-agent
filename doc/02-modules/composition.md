# 模块设计：组合与分发层（L5 Composition）

> 对应规格：`doc/openspec/specs/composition/spec.md` ｜ 接口：`doc/03-interfaces/composition-interface.md`

---

## 1. 模块定位

L5 让 CORE **可组合、可分发、可覆盖**。它是 CORE-Harness 唯一的静态层：只有组合代数、没有业务逻辑、永不进化。它通过 profile（命名组合）/ bundle（分发格式）/ patch.yml（用户覆盖）三要素，把已结晶的技能与插件按需组合、跨部署分发、按用户差异覆盖，实现「一切皆插件 + 可逆组合」的基底。

> **组合不产生新逻辑**：组合层只装配已结晶产物，不承载业务逻辑，永不进化——进化交给 L4 Evolution Engine，组合层只做「按需装配」。

---

## 2. 三要素与层叠解析

```
profile(命名组合) ─► 层叠多个 bundle ─► 叠加 patch.yml ─► 解析出最终插件集
        ▲                                                          │
        └─────────────────── 可逆、可回退 ──────────────────────────┘
```

| 要素 | 类型 | 职责 | 归属 |
|---|---|---|---|
| **profile** | 命名组合 | 一个命名指向一个可复用插件组合集合（如 web / headless / sdk-minimal） | 全局 |
| **bundle** | 分发格式 | 已结晶技能打包、跨部署复用 | 跨部署 |
| **patch.yml** | 用户覆盖 | 不改 profile 与 bundle 前提下按用户差异局部覆盖 | profile 内部 |

---

## 3. 关键设计

### 3.1 profile 命名组合

- 一个 profile 命名一个可复用的插件组合集合，用户或部署按名选用即解析出完整插件集。
- 典型 profile：web（全功能）、headless（无 GUI）、sdk-minimal（最小 SDK）。
- 组合只**引用**插件，不复制插件逻辑——保持单一数据源。

### 3.2 bundle 分发格式

- 已结晶技能打包为 bundle，跨部署引入即复用同一批技能，无需重新结晶。
- bundle 携带版本 / 依赖 / 哈希元数据，保证跨部署分发一致性。

### 3.3 patch.yml 用户覆盖

- 对 profile 组合做局部覆盖，原 profile 与 bundle 保持不变。
- 覆盖只作用于组合结果，不污染组合定义——保证可逆。

### 3.4 层叠解析（确定顺序、可逆）

- 解析顺序固定：「bundle 层叠 → patch.yml 覆盖」，同名项由 patch.yml 覆盖。
- 解析结果可逆：卸载 patch.yml 可回退到覆盖前状态，永不丢历史。回退由 `ResolvedSet.layered`
  （覆盖前分层结果）+ `ProfileResolver.revert` 承载（幂等、返回新结果）；覆盖值须为整数 generation，
  布尔按 `PATCH_CONFLICT` 拒绝（change `0136`）。

---

## 4. 唯一静态层约束

- **无业务逻辑**：不承载推理 / 记忆 / 工具调用等任何运行时逻辑。
- **永不进化**：进化产物经 L4 结晶后进入 L0/L1 插件仓库，组合层只消费、不改造。
- 实现本模块时以这两条约束做回归校验（防止组合层越界）。

---

## 5. 错误处理与边界

| 场景 | 行为 |
|---|---|
| profile 引用不存在的插件 | 解析失败，报缺失插件名，不静默跳过 |
| patch.yml 覆盖项与 bundle 同名 | 按确定顺序，同名项由 patch.yml 覆盖 |
| bundle 哈希 / 版本不符 | 拒绝引入，报不一致，避免脏分发 |
| 卸载 patch.yml | 回退到覆盖前状态，可逆（`revert`，change `0136`） |
| patch.yml 覆盖值为布尔 | 报 `PATCH_CONFLICT`（bool 非 generation，change `0136`） |

---

## 6. 关联

- 规格：`doc/openspec/specs/composition/spec.md`
- 插件来源：`doc/openspec/specs/plugin-registry/spec.md`
- 进化：`doc/02-modules/evolution.md`（结晶产物进入插件仓库，组合层消费）
- 接口：`doc/03-interfaces/composition-interface.md`
- 架构：`core_harness_architecture.md` L5
