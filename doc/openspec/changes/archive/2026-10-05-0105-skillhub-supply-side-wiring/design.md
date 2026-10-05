# 设计 — skillhub 供给侧接线（change 0105）

## 1. 核心矛盾：CLI 是一次性进程

供给侧三件套今天只活在单测的直接调用里，且**两处状态都是进程内的**：

| 状态 | 位置 | 跨进程后果 |
|---|---|---|
| 市场目录 | `MarketIndex._sources`（内存 dict） | 上个进程 `publish` 的条目下个进程 `search` 看不到 |
| 发布源映射 | `SkillPublisher._published`（内存 dict） | 上个进程 `publish` 的技能下个进程 `review` 判「未发布」 |

⇒ 只补 CLI 入口不解决问题：会得到一条**看似闭环、实则每步都空转**的链路（同 change `0074`
mcp 端点「`mcp add` 的成果无处可寻」、change `0104` rag「进程内 `_hashes` 跨进程必失效」的同一教训）。

## 2. 决策

### ① 市场目录落盘：`MarketIndex(path=…)`

- 形状（`core.persistence.write_state`，**原子** tmp + `os.replace`；`read_state` 缺失/损坏 → `None`）：
  `{"sources": {<name>: {"skills": {<skill_id>: <MarketSkill dict>}}}}`。
- `path=None`（缺省）⇒ 纯内存，**既有单测与组合根行为逐字不变**。
- 写入时机：`put()` 即落盘（发布与审核**共用同一写路径** —— 不新增 `save()` 之类的第二个入口）。
- 装载：`read_state` 非 dict / 结构不符（`AttributeError/KeyError/TypeError/ValueError`）⇒
  `warnings.warn` **降级为空目录**（change 0064/0074 口径：状态损坏不阻断启动）；
  装载后 `setdefault("official", …)` 保证官方源恒存在（防手工编辑的文件缺官方源）。
- 新增 `locate(skill_id) -> tuple[str, MarketSkill] | None`：**跨源按 id 定位**（不带健康探测 ——
  这是查找不是路由）。

### ② `SkillPublisher._published` 删除，改由目录定位

审核需要知道「发布到了哪个源」。这个事实**已经写在目录里**（`MarketSkill.source` 随条目落盘），
进程内再存一份 `_published` 就是**第二真源**，且跨进程必失效。故 `review` 改为
`self._index.locate(skill_id)`：未找到 ⇒ `SKILL_NOT_ACTIVE`（**错误码与语义不变**，既有用例仍绿）。
审核改动状态后经 `self._index.put(source, market)` 回写（复用同一落盘路径）。

### ③ 发布 = 元数据上架 + 制品入库（`SkillPublisher(artifacts=…)`）

消费侧 `download` 需要 fetcher 提供**技能体**；目录按规格只存元数据（「不拉取完整技能体」）。
故本地市场需要**制品库**：`SkillLibrary(path=$CORE_STATE_DIR/skillhub-artifacts.json)`
（复用既有落盘技能库，零新存储抽象）。

- 制品入库**放在 `SkillPublisher.publish` 内**（可选注入 `artifacts`），不在 CLI 里做第二次写入 ——
  否则「发布」的语义散成两处，任何别的发布入口都会漏掉制品。
- 顺序：先 `index.put`（源不存在即 `SOURCE_NOT_FOUND`，**此时不入制品**）再 `artifacts.register`。

### ④ CLI 面

| 命令 | 接的组件 |
|---|---|
| `skill publish <skill_id> [--source S]` | `SkillPublisher.publish`（内部用 `TrustVerifier.sign` + `MarketIndex.put` + `artifacts.register`） |
| `skill review <skill_id> <approved\|rejected>` | `SkillPublisher.review`（内部 `MarketIndex.locate/put` + `VersionManager.promote`） |
| `skill search` / `skill install`（既有） | 改走**同一落盘目录** + 本地市场制品 fetcher |

- 三件套在 CLI 侧**同源装配**：`_build_market_index()` / `_build_market_artifacts()` /
  `_build_publisher()`（镜像既有 `_build_skill_library()` 的「与组合根同源」约定）。
- `VersionManager` 的 `path=$CORE_STATE_DIR/skill-versions.json`，与 `runtime._skill_state_path`
  **同一文件** ⇒ 审核通过的版本提升对后续会话可见。

### ⑤ 已否决

- **install 仅限 `published` 的消费闸门**：phase-22 §4.2 验收序列为 publish → search → install
  （中间无审核），既有 CLI 用例的市场项状态亦非 `published` ⇒ 加闸门是**新增契约**，不在「接线」范围。
- **`skill market list` 子命令**：`MarketIndex.list` 已在生产路径上（`SkillHubClient.search` 内部调用）。
- **新错误码**：既有 `SIGNATURE_INVALID`（拉取失败/验签失败）、`SKILL_NOT_ACTIVE`（未发布）、
  `SOURCE_NOT_FOUND`（源不存在）、`PUBLISH_REJECTED`（驳回）已足。
- **首个远端市场 fetcher**（网络 + 凭据）：仍为凭证半；本地市场属**零凭据**可离线验收的部分。

## 3. 验收

一条端到端（全程走 CLI、跨 `main()` 调用、每步重开落盘对象）：本地注册技能 → `skill publish`
→ 重开目录断言 pending → `skill search` 命中 → `skill review approved` → 重开目录断言 published 且
版本 v2 → `skill install` → 重开技能库断言 draft。反例两条：**publish 未注册技能**（退出 1、不落盘）、
**制品被篡改后 install**（末端验签失败、退出 1、不落盘）。
