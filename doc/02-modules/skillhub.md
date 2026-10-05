# 模块设计：技能市场（SkillHub Market）

> 对应规格：`doc/openspec/specs/skillhub/spec.md` ｜ 接口：`doc/03-interfaces/skillhub-interface.md`
> 定位：**L3 技能 ↔ 外部技能生态 之间的交换层**，让技能既可内部沉淀、也可跨实例发布与下载，形成技能的"市场流通"。

---

## 1. 模块定位

core-agent 的"记忆即光谱"闭环解决的是**单一实例内**的技能结晶与溶解；skillhub 把它扩展到**跨实例**：技能可以发布到市场供其他实例下载，也可以从市场获取他人沉淀的技能。

本模块是技能经济闭环的**交换层**，与 skills 的"封装/版本化/路由"正交——skills 管"一个技能怎么用"，skillhub 管"一个技能怎么来、怎么去"。

---

## 2. 内部组成

```
SkillHub（L3）
├── SkillHubClient   市场客户端：搜索/浏览/下载技能
├── MarketIndex      市场索引：技能目录元数据 + 多源路由
├── SkillPublisher   技能发布：上传 → 审核 → 上架
└── TrustVerifier    信任校验：签名验证 + 来源可信度
```

---

## 3. 关键设计

### 3.1 市场索引与多源抽象

- 技能市场按 `source`（来源）组织，默认仅有官方源；接口与数据模型均预留 `source` 参数，未来可接入第三方源/社区源。
- 索引存轻量化元数据（`skill_id`、名称、描述、版本、签名摘要、来源），列表/搜索不拉取完整技能体。
- 查询统一走 `MarketIndex`，由 `source` 路由到对应市场源，上层无感。

### 3.2 技能下载与签名校验

- 下载流程：`SkillHubClient.download(skill_id)` → `TrustVerifier.verify(签名)` → 通过后 `SkillLibrary.register`。
- 签名校验**失败即拒绝**，不落盘、不注册（杜绝被篡改技能入库）。
- 下载注册的初始状态为 **draft（草稿）**，**不自动启用**：需本地显式激活后才进入可用技能集，保证市场技能不干扰既有运行。

### 3.3 技能发布与审核流

- 发布流程：本地技能经 `SkillPublisher.publish` 上传，进入 `uploaded → pending → published / rejected` 四状态审核流。
- 审核通过（published）后市场版本号递增：`VersionManager` 上 `v1 → v2`，与 skills 的版本管理语义一致。
- 驳回（rejected）的技能可修改后重传，不丢弃。

### 3.4 多源预留与源健康

- `source` 作为一等公民贯穿客户端/索引/发布全链路；当前仅官方源落地，第三方源为预留扩展点。
- 源不可达或校验失败时，标记源不健康并回退官方源，不阻塞技能获取。

---

## 4. 市场与技能库的闭环

```
本地技能 ──publish/审核通过──► 市场（SkillPublisher + MarketIndex）
市场技能 ──download/签名校验/register──► 本地 SkillLibrary（draft）
draft ──显式激活──► 可用技能集（进入 skills 的路由/版本管理闭环）
```

- 下载即沉淀、发布即流通，两者都回到 skills 的封装/版本化/路由闭环，不另起炉灶。
- draft 机制保证市场技能"先隔离、后启用"，与灰度发布/验证门同构。
- **生产触达点已落地**（change 0092／ADR-0087）：CLI `skill search` / `skill install` 经 `SkillHubClient`
  （市场搜索 / 签名校验下载）；CLI 技能库经 `entry._build_skill_library()` 与组合根**同源**
  （`$CORE_STATE_DIR/skills.json`）⇒ 下载的 draft **落盘并可被后续会话读到**，`skill remove` 也作用于真技能。
- **凭证半（未接）**：真实市场 fetcher（网络 + 凭据）。缺省装配下 `skill search` 如实返回空、
  `skill install` 如实报「未接入拉取」，**不静默成功**。

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 技能签名校验失败 | 拒绝下载，返回 `SIGNATURE_INVALID`，不落盘不注册 |
| 来源不可达 | 标记源不健康，回退官方源，返回 `SOURCE_UNHEALTHY` |
| 发布审核未通过 | 状态回退 `rejected`，允许修改后重传 |
| 下载的技能未激活（draft） | 不进入路由匹配，需显式激活后才可用 |
| source 不存在 | 返回 `SOURCE_NOT_FOUND`，不 fallback 到未知源 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/skillhub-interface.md`
- 规格：`doc/openspec/specs/skillhub/spec.md`
- 测试：`doc/04-testing/test-cases.md`（TC-SKILLHUB 系列）
- 上游：`doc/02-modules/skills.md`（SkillLibrary 注册、VersionManager 版本）
