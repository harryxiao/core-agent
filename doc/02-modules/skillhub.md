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
- **目录可落盘**（注入 `path`，change 0105／ADR-0098）：`put()` 为唯一写路径（发布与审核共用），
  经 `core.persistence` 原子写整体重写；装载缺失 → 空态、损坏 → 告警降级（不阻断启动）。
  缺省 `path=None` 为进程内目录。CLI 落盘于 `$CORE_STATE_DIR/skillhub-index.json`。
- **`locate(skill_id)` 跨源定位**：审核只需技能 id、不必知道发布源 —— 这个事实已在目录里，不必进程内再记一份。

### 3.2 技能下载与签名校验

- 下载流程：`SkillHubClient.download(skill_id)` → `TrustVerifier.verify(签名)` → 通过后 `SkillLibrary.register`。
- 签名校验**失败即拒绝**，不落盘、不注册（杜绝被篡改技能入库）。
- 下载注册的初始状态为 **draft（草稿）**，**不自动启用**：需本地显式激活后才进入可用技能集，保证市场技能不干扰既有运行。

### 3.3 技能发布与审核流

- 发布流程：本地技能经 `SkillPublisher.publish` 上传，进入 `uploaded → pending → published / rejected` 四状态审核流。
- 审核通过（published）后市场版本号递增：`VersionManager` 上 `v1 → v2`，与 skills 的版本管理语义一致。
- 驳回（rejected）的技能可修改后重传，不丢弃。
- **发布 = 元数据上架 + 制品入库**（change 0105）：目录按规格只存元数据，消费侧拉取需要技能体 ⇒ 注入
  `artifacts`（本地市场制品库 `SkillLibrary(path=$CORE_STATE_DIR/skillhub-artifacts.json)`）；顺序为
  先 `index.put` 再 `artifacts.register`（源不存在时不留半份制品），制品存 `replace(skill)` **副本**。
- **审核定位真源是目录**：`review` 经 `MarketIndex.locate` 找到发布源并回写，不再维护进程内
  `skill_id → source` 映射（第二真源跨进程必失效）；制品库在场时把制品本体提升到发布版本并**重新签名**，
  使市场签名与制品内容始终一致（末端验签仍成立）。
- **审核跨进程可续**：`VersionManager` 的 `path` 落盘于 `$CORE_STATE_DIR/skill-versions.json`
  （与组合根 `runtime._skill_state_path` 同源），审核通过的版本提升对后续会话可见。

### 3.4 多源预留与源健康

- `source` 作为一等公民贯穿客户端/索引/发布全链路；当前仅官方源落地，第三方源为预留扩展点。
- **回退语义**（`0134`／ADR-0127／账本 E80）：源不健康时 `list` / `route` **回退官方源并以其结果
  响应**（标记该源不健康，**不阻塞技能获取**）；官方源**亦**不可用（无可用源）才返回
  `SOURCE_UNHEALTHY` —— 规格原文一句内自相矛盾（同句既写「回退官方源」又写「返回
  `SOURCE_UNHEALTHY`」），实现与测试原先都只选后半句 ⇒ 多源退化为单源。`health()` 仍如实探测
  （诊断面不回退），`SOURCE_NOT_FOUND` 仍不回退到未知源。

---

## 4. 市场与技能库的闭环

```
本地技能 ──publish/审核通过──► 市场（SkillPublisher + MarketIndex）
市场技能 ──download/签名校验/register──► 本地 SkillLibrary（draft）
draft ──显式激活──► 可用技能集（进入 skills 的路由/版本管理闭环）
```

- 下载即沉淀、发布即流通，两者都回到 skills 的封装/版本化/路由闭环，不另起炉灶。
- draft 机制保证市场技能"先隔离、后启用"，与灰度发布/验证门同构。
- **消费侧已落地**（change 0092／ADR-0087）：CLI `skill search` / `skill install` 经 `SkillHubClient`
  （市场搜索 / 签名校验下载）；CLI 技能库经 `entry._build_skill_library()` 与组合根**同源**
  （`$CORE_STATE_DIR/skills.json`）⇒ 下载的 draft **落盘并可被后续会话读到**，`skill remove` 也作用于真技能。
- **供给侧已落地**（change 0105／ADR-0098）：CLI `skill publish` / `skill review` 经 `SkillPublisher`
  （落盘目录 + 本地市场制品库 + 落盘版本管理）⇒ 「本地技能 → 发布 → 索引 → search/install 消费」闭环成立，
  且**每一步跨进程可见**（CLI 是一次性进程，进程内状态等于空转）。
- **凭证半（未接）**：**远端**市场 fetcher（网络 + 凭据）。消费侧缺省 fetcher 已接**本地**市场制品库
  （离线、零凭据）；远端接入时替换 `fetcher` 即可，接口面不变。未接入 / 制品缺失时如实报错，**不静默成功**。

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 技能签名校验失败 | 拒绝下载，返回 `SIGNATURE_INVALID`，不落盘不注册 |
| 来源不可达（官方源可用） | 标记该源不健康，**回退官方源并以其结果响应**（不抛错，`0134`/ADR-0127） |
| 无可用源（官方源亦不可达） | 返回 `SOURCE_UNHEALTHY` |
| 发布审核未通过 | 状态回退 `rejected`，允许修改后重传 |
| 下载的技能未激活（draft） | 不进入路由匹配，需显式激活（`skill activate`）后才可用（`0133`/ADR-0126） |
| source 不存在 | 返回 `SOURCE_NOT_FOUND`，不 fallback 到未知源 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/skillhub-interface.md`
- 规格：`doc/openspec/specs/skillhub/spec.md`
- 测试：`doc/04-testing/test-cases.md`（TC-SKILLHUB 系列）
- 上游：`doc/02-modules/skills.md`（SkillLibrary 注册、VersionManager 版本）
