# design — 0092 skillhub 接入 CLI

## 决策

### ① 触达点 = 既有 `skill` 子命令（不新增命令）

`skill search <query>` → `SkillHubClient.search`；`skill install <name> [--source S]` → `SkillHubClient.download`。
两者**都是既有子命令**（ledger 明列），故 CLI 命令面不变（`_TOP_LEVEL_COMMANDS` 契约不动），只换实现。

### ② 技能库与组合根同源（本变更的**前提**，非附带）

`SkillLibrary()`（无路径）是**内存库**，进程结束即失；而组合根用的是
`SkillLibrary(path=$CORE_STATE_DIR/skills.json)`（`runtime.py:309`）。故今日 CLI 的 search/install/remove
全部作用于**一次性空库**：`skill install` 报「已安装」随后消失（**谎报**）、`skill remove` 永远报「技能未注册」。

新增 `entry._build_skill_library()` = `SkillLibrary(path=_state_path("skills.json"))`，与组合根**同一文件**：

- 下载的技能（draft）**落盘**，随后的 `core-agent` 会话能看到（规格「以 draft 状态注册」有意义）；
- `skill remove` 真的能卸载运行时注册的技能。

**为什么不抽公共 helper 到 runtime**：`entry._state_path` 与 `runtime._skill_state_path` 已是**同一约定**
（`$CORE_STATE_DIR/<name>`）的两份实现；跨模块抽公共函数会引入 `entry → runtime` 之外的新依赖方向，
与既有「各层各自持有 `_*_path`」风格不一致（同 `0089` 对 `_trace_path` 的处置）。

### ③ 客户端构造留缝（可离线验证）

`entry._build_skillhub_client(library) -> SkillHubClient`：缺省 `MarketIndex()`（空 official 源）+ `TrustVerifier()`
+ `fetcher=None`。测试经 `monkeypatch.setattr("core.entry._build_skillhub_client", …)` 注入
**内存 index + 内存 fetcher**，即可端到端验证 search/install 两条路径（ledger 的「注入内存 MarketIndex 即可离线验证」）。

### ④ 错误归一为 stderr + 退出码 1

`search` / `install` 捕获 `SkillHubError`（`SOURCE_UNHEALTHY` / `SOURCE_NOT_FOUND` / `SIGNATURE_INVALID`）→ 打印 + `1`，
与 `_plugin_install` / `_release` 的既有 CLI 惯例一致（**不抛裸异常**）。

### ⑤ `skill search` 增 `--source`

`SkillHubClient.search(source=…)` 本就支持；`install` 侧**早就有** `--source`（此前零消费）。
搜索侧补齐同一参数，使多源在 CLI 上**对称可达**（否则第三方源只能装不能搜）。缺省 `official`。

### ⑥ 输出形状

- search：`{skill_id} ({version}): {description}`（市场**元数据**，不拉技能体 —— 对齐规格「不拉取完整技能体」）；
  空结果沿用既有文案「（未找到匹配技能: {query}）」。
- install：`已安装技能 {skill_id}（draft，需本地显式激活后可用）`（把规格「draft 不自动启用」说到位）。

## 影响面

- **CLI 行为变更**：`skill search` 由「搜本地空库」改为「搜市场」；`skill install` 由「= plugin install --kind skill」
  改为「市场下载」；`skill remove` 改为作用于**持久库**。
- **既有测试**：`tests/test_entry.py::test_skill_remove_missing` 继续通过（`conftest` 已把 `CORE_STATE_DIR`
  隔离到每测试临时目录 ⇒ 库为空 ⇒ 仍报「技能未注册」）。`test_plugin_install_skill_local_path` 走 `plugin install`，不受影响。
- **无 Runtime / loop 改动**；`core/skillhub/` 源码**零改动**（实现早已齐备）。
