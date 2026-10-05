# 0092 — skillhub 接入 CLI（`skill search` / `skill install`）（Phase 20 C5）

## 为什么

账本 `coding-plan/phase-20.md` §1 C5 / §4.4：`SkillHubClient` / `MarketIndex` / `TrustVerifier` / `SkillPublisher`
**全部实现、DI 完整**，但**零生产调用方** —— `entry._skill_search(SkillLibrary(), query)`（`entry.py:730-739`）
搜的是**本地库**（且是**新建的空库**：`SkillLibrary()` 不带路径 ⇒ 进程内一次性），故 `skill search` **恒空**；
`skill install` 只是 `plugin install --kind skill` 的别名（`entry.py:620`，`--source` 参数**声明了却零消费**）；
`skill remove` 同样作用于**空的一次性库** ⇒ **永远删不掉运行时真正注册的技能**。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/entry.py` | `skill search` / `skill install` 经 `SkillHubClient`（市场搜索 / 签名校验下载）；`_build_skill_library()` 与组合根**同源**（`$CORE_STATE_DIR/skills.json`）；`skill search` 增 `--source`（与 install 侧既有 `--source` 对称） |
| `doc/openspec/specs/skillhub/spec.md` | MODIFIED「技能市场与技能发现」+「签名校验与可信下载」：补生产触达点（CLI）+ 技能库同源 + 3 场景 |
| `doc/03-interfaces/skillhub-interface.md` | §2 补 CLI 触达点与技能库同源 |
| `doc/02-modules/skillhub.md` | 补「生产触达点」段 |
| `doc/01-architecture/adr.md` | ADR-0087 + 映射表行 |
| `tests/test_skillhub_cli.py` | 新：市场搜索可见 / 安装落 draft 且**跨进程可见** / 签名失败拒绝且不落盘 / 市场未接如实报错 / remove 作用于持久库 |

## 决策

- **`skill search` → 市场搜索**（`SkillHubClient.search`）：这是 ledger 明列的代码半。**不是回归** —— 今日的本地库搜索**恒空**
  （新建 `SkillLibrary()` 无路径 ⇒ 无内容），改后至少「市场未接」时**如实**报「未找到」，且市场接入后立即可见。
- **`skill install` → 市场下载**（`SkillHubClient.download`：签名校验 → 注册 draft）：让**已声明的 `--source`** 真正生效；
  本地路径安装仍走 `plugin install --kind skill`（不动）。
- **技能库与组合根同源**（`SkillLibrary(path=$CORE_STATE_DIR/skills.json)`，与 `runtime._skill_state_path` 同一约定）：
  否则「已安装」是**谎报**（写进一次性库、下个进程消失），`skill remove` 也永远删不掉真技能。这条不是扩大范围，
  是让 C5 的 install/remove **成立**的最小前提（同 E21/E22「配置单一真源」取向）。
- **错误归一**：`SkillHubError`（源不可达 / 签名失败 / 市场未接）→ stderr + 退出码 1，**不抛裸异常**（对齐 CLI 既有惯例）。

## 明确不做（**凭证半**）

- **真实市场 fetcher（网络 + 市场凭据）**：缺省 `fetcher=None` ⇒ `skill install` 在接入前**如实**报
  「无法下载技能（市场缺失或未接入拉取）」；缺省 `MarketIndex` 只有空的 `official` 源 ⇒ `skill search` 如实返回空。
  这正是 ledger 的**凭证半**，归 Phase 19 §5；本变更交付的是**可注入可离线验证**的接线 + 与组合根同源的技能库。
- **`skill publish` 子命令**：规格有发布审核流，但 CLI 侧从未声明该子命令（`_skill` 无 publish 分支），
  不属本次接线范围。
