# 提案 — skillhub 供给侧接线（change 0105）

## 背景与缺陷

Phase 22 §4 一手核实（行号精确）：

- `SkillPublisher`（`skillhub/publisher.py`）/ `MarketIndex`（`skillhub/index.py`）/
  `TrustVerifier`（`skillhub/trust.py`）**零生产调用**；仅消费侧 `SkillHubClient`（search/install）
  活于 `entry.py`（change 0092 / Phase 20 C5）。
- 根因：C5 只把「从市场**拉取/安装**技能」接上了，**「发布 / 索引上架 / 信任验证」从未接** ——
  技能只能进不能出，市场只有消费没有供给。
- 且供给侧三件套**全程只活在单测的直接调用里**：`MarketIndex` 仅内存、`SkillPublisher._published`
  仅进程内 ⇒ 即便补 CLI 入口，publish 的成果在下一个进程（search/install）中也**不可见**
  （CLI 是**一次性进程**，同 change `0074` mcp 端点注册表 / change `0104` rag 指纹的同一教训）。

## 用户裁决

`coding-plan/phase-22.md` §4.2 提供 (a) 接线 / (b) 诚实降级 二选一；用户选 **(a) 接线**。

## 变更目标

闭合「**本地技能 → 发布 → 索引 → 消费侧 search/install**」离线闭环（跨进程、零凭据）：

1. **市场目录可落盘**：`MarketIndex(path=…)`（未注入 path 时仍为纯内存，既有行为逐字不变）。
2. **发布 = 元数据上架 + 制品入库**：`SkillPublisher` 增可选 `artifacts`（本地市场制品库），
   使消费侧 `download` 的 fetcher 能从本地市场取到技能体。
3. **审核跨进程可续**：`SkillPublisher._published`（进程内映射）删除，改由 `MarketIndex.locate`
   （跨源按 `skill_id` 定位）——**落盘索引即真源**；审核通过后版本提升经 `VersionManager`
   （`path` 与组合根同源）落盘。
4. **CLI 供给面**：`skill publish <skill_id> [--source S]` / `skill review <skill_id> <approved|rejected>`；
   消费面 `skill search` / `skill install` 改走**同一个落盘市场**。

## 非目标 / 已否决

- **不做**「install 仅限 `published`」的消费闸门：phase-22 §4.2 验收序列为
  publish → search → install（中间**无**审核），且既有 CLI 用例的市场项状态并非 `published`
  ——加闸门是**新增契约**而非接线。
- **不做**远端市场 fetcher（网络 + 市场凭据）——仍为**凭证半**，如实报错不静默成功。
- **不做** `skill market list` 子命令：`MarketIndex.list` 已在生产路径上
  （`SkillHubClient.search` 内部即 `index.list(source=…)`）。

## 影响面

- 规格：`skillhub` 三条 Requirement MODIFIED（发现 / 可信下载 / 发布审核流）+ 6 新场景。
- 代码：`skillhub/index.py`（落盘 + `locate`）、`skillhub/publisher.py`（制品入库 + 索引定位）、
  `entry.py`（publish/review 子命令 + 消费侧同源装配）。
- 文档：接口 §2/§3/§4、模块 §3.1/§3.3/§4、ADR-0098、测试用例、`contracts_summary.md` skillhub 行。
