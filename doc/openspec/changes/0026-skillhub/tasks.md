# Tasks

> 设计落地，实现依赖后续 coding 阶段。

## 1. SkillHubClient 客户端（P0）

- [x] 1.1 search/list/download 接口实现 + source 参数路由（默认单官方源）
- [x] 1.2 下载后调用 TrustVerifier.verify 签名校验，失败拒绝
- [x] 1.3 下载成功 → SkillLibrary.register + status=draft（draft 不自动启用）

## 2. MarketIndex 市场索引（P0）

- [x] 2.1 官方源市场索引维护（技能清单 + 版本 + 签名元数据）
- [x] 2.2 source 多源抽象预留（接口层支持，默认单官方源）

## 3. TrustVerifier 签名校验（P0）

- [x] 3.1 技能包签名校验（verify 接口）
- [x] 3.2 校验失败拒绝下载 + 明确错误码

## 4. SkillPublisher 发布（P1）

- [x] 4.1 publish 接口实现 + 技能包打包/上传
- [x] 4.2 发布成功 → VersionManager v1→v2

## 5. 审核流状态机（P1）

- [x] 5.1 uploaded → pending → published/rejected 状态流转
- [x] 5.2 审核通过 → published；驳回 → rejected（不发布）

## 6. 错误码与收敛（P1）

- [x] 6.1 skillhub 错误码（对齐 skillhub-interface.md 5 错误码）
- [x] 6.2 挂接 skills 模块（SkillLibrary / VersionManager 语义引用）
