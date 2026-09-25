# Change: 新增 skillhub 技能市场 capability（市场管理/下载/发布，对接 skills 模块）

## Why

当前 23 个 capability 中无技能市场：skills 模块仅维护本实例原子技能库，技能无法跨实例交换——既不能从市场获取他人沉淀的技能，也无法将本实例技能发布出去供他人下载。市场语义（发现/下载/发布）与安全语义（下载来源可信、签名校验、审核流）均为空白，`skillhub`/`market` 全库零命中（来源：grep，2026-09-25）。作为"记忆即光谱"闭环的交换层，技能市场是技能沉淀跨越单实例、形成生态的上半场能力。

## What Changes

- **新增 skillhub 独立 capability**（决策 1A，第 24 spec，功能模块非横切），四组件：SkillHubClient（客户端搜索/下载）、MarketIndex（市场索引与多源路由）、SkillPublisher（技能发布）、TrustVerifier（签名校验）。
- **技能市场与技能发现**：source 参数预留多源扩展，默认单官方源（决策 2B 架构 A 起步）；按关键字搜索与按源列出。
- **签名校验与可信下载**：TrustVerifier 校验签名，失败拒绝（`SIGNATURE_INVALID`）；下载成功注册为 draft 不自动启用（决策 3A+C），挂载 `SkillLibrary.register(status=draft)`，需显式激活后进入路由匹配。
- **技能发布与审核流**：`uploaded → pending → published/rejected`（决策 4B）；审核通过 status=published 且 `VersionManager` v1→v2。
- **多源路由与健康回退**：源不可达回退官方源（`SOURCE_UNHEALTHY`），源不存在拒绝路由（`SOURCE_NOT_FOUND`）。
- **skills 三件套**：新建 `02-modules/skillhub.md`、`03-interfaces/skillhub-interface.md`、`openspec/specs/skillhub/spec.md`（照 skills 三件套章节结构）。
- **delta 双写**：`changes/0026-skillhub/`（proposal.md + tasks.md + specs/skillhub/spec.md，spec delta 与 specs 根目录逐字一致）。
- **adr.md**：追加 ADR-0035（技能市场独立 capability + 多源预留 + 签名校验 + 审核流）。
- **architecture-overview.md**：§2 职责表、§3 组件表、§6 目录树共 3 处同步（skillhub 为 L3 功能模块）。

## Impact

- **Affected specs**：`skillhub`（新增，第 24 spec）；`skills` 为挂载点引用（download→SkillLibrary.register+draft；publish→VersionManager v1→v2），仅语义引用，不修改既有 spec
- **Affected docs**：`02-modules/skillhub.md`（新建）、`03-interfaces/skillhub-interface.md`（新建）、`openspec/specs/skillhub/spec.md`（新建）、`openspec/changes/0026-skillhub/`（新建 delta 三件）、`00-product/requirements.md`（+1.24 技能市场）、`04-testing/test-cases.md`（+系列 23 TC-SKILLHUB）、`00-product/design-completeness-eval.md`（模块计数 23→24）、`01-architecture/adr.md`（+ADR-0035）、`01-architecture/architecture-overview.md`（职责表+组件表+目录树 3 处）
- **Affected code**：无（架构设计与设计文档落地；工程实现依赖后续任务）
- **Dependencies**：ADR 编号=当前最大+1（0035）；specs 23→24 需同步 requirements.md 1.x 清单与 design-completeness-eval.md「N 模块」数字口径；test-cases 系列 22→23；不引入新框架
