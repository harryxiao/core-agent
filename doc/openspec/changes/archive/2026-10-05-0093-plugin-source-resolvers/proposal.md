# 0093 — 插件四源解析器（git-repo / market-registry / mcp-endpoint）（Phase 20 C6）

## 为什么

账本 `coding-plan/phase-20.md` §1 C6：`PluginInstaller` 四钩子 DI 完整、`InstallDispatcher` 已真装
（`runtime.py:378-381`，CLI `plugin install/list/uninstall` + `mcp add` 同一管线）、`LOCAL_PATH` 已真
（`install.py:48-55`）；但 **`GIT_REPO` / `MARKET_REGISTRY` / `MCP_ENDPOINT` 三种来源一律抛
「来源不可达（未接入 resolver）」**：

- 规格 `plugin-registry/spec.md`「插件来源与安装」明文要求**四类来源**，场景「四类来源安装」已存在
  ⇒ 规格为真、实现为假。
- 抽象层 `PluginSource` 声明四值、`install_tool`（模型面工具）已把 `source` 字符串直接映射成
  `PluginSource(source)` ⇒ **来源不是缺失的概念，是缺失的实现**。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/plugins/sources.py` | **新增**：三类外部来源解析器 `resolve_git_repo` / `resolve_market_registry` / `resolve_mcp_endpoint` + 缺省 stdlib 外部边（`_clone_with_git` 复用 `core.git` 后端、`_http_json` 走 `urllib.request`）+ `MANIFEST_FILENAME` 约定 + `_safe` 回显脱敏 |
| `src/core/plugins/install.py` | `InstallDispatcher.resolve` 由「LOCAL_PATH + 抛错」扩为四源分派；构造增 `cloner` / `fetcher` 两个外部边注入缝 |
| `src/core/plugins/__init__.py` | 导出解析器与 `MANIFEST_FILENAME` |
| `src/core/entry.py` | `plugin install` 增 `--source`（choices = 四源，缺省 `local-path`）；`_build_installer` 技能库改与组合根**同源** |
| `doc/openspec/specs/plugin-registry/spec.md` | MODIFIED「插件来源与安装」：补四源发现契约 + 3 场景 |
| `doc/03-interfaces/plugin-registry-interface.md` | §8 补四源解析契约 / `core-plugin.json` 约定 / CLI `--source` |
| `doc/01-architecture/adr.md` | ADR-0088 + 映射表行 |
| `doc/04-testing/test-cases.md` | TC-PLUGIN-01/02/03 |
| `tests/test_plugins_sources.py` | 新：来源解析单测 + 四源分派 + CLI 端到端（真实临时 git 仓库） |

## 决策

- **解析器落执行层 `core/plugins/sources.py`，不入 `plugin_registry` 基座**：`plugin_registry` 的
  `_default_resolve` 保持「未接入」空壳（基座零外部依赖），真实解析是**执行层**的职责 —— 与
  `InstallDispatcher` 既是 resolver 又是 installer 的既有分工一致。
- **零三方依赖**（ADR-0044）：git-repo 复用 **change 0090** 的 `core.git` stdlib subprocess 后端
  （不新写 shell out、不引 gitpython）；market-registry 走 stdlib `urllib.request`（同
  `tools/builtin.py` / `judgment/provider.py` 既有口径）。
- **`core-plugin.json` 约定**：git-repo 来源以**仓库根目录** `core-plugin.json` 为 manifest 入口
  （仓内零既有约定，须定一个可发现的常量名）。
- **临时工作区可逆**：克隆落 `tempfile.TemporaryDirectory`，`with` 退出即删除 —— 不残留、不污染
  `$CORE_STATE_DIR`（P2 一切副作用可逆的口径）。
- **市场凭据不进 URL**：market-registry 的鉴权经**注入的 fetcher** 携带（header / 凭据注入），
  故 URL 本身无凭据面；回显一律经 `_safe` **剥掉 userinfo 与 query**（对齐 `ADR-0085` git 后端
  「不回显可能含凭据的地址」红线）。
- **mcp-endpoint 解析期零网络**：端点串本身即来源，manifest 由串**合成**；可达性在 **install 期**
  由 `MCPClient.add` 判定（与 `mcp add`「先连通验证再落盘」同一口径，避免解析期多一次无谓连接，
  也避免「解析成功但装不上」的双重语义）。

## 明确不做（记录理由）

- **不重写 `mcp add` 走 `MCP_ENDPOINT` 来源**：`mcp add` 有自己的连通验证 + 端点注册表（落盘）语义，
  且 `runtime` 装配期读回端点表走的是 `dispatcher.install`（不经 `resolve`）。为统一而改属**无收益重构**。
- **不给 `plugin install` 的 `market-registry` / `mcp-endpoint` 补端到端 CLI 测试**：两者缺省外部边
  需真实网络（凭证半），不可离线断言"成功"；离线锚点落在**注入 fetcher / 合成**两条路径上
  （与 `ADR-0087` skillhub 同口径：缺省装配如实报错，不静默成功）。
- **不接线 `install_tool` / `list_tool` / `uninstall_tool`**（模型面安装工具）：三者在 `src/` 内**零生产注册**
  （非 C6 症状；`runtime` 的工具面不含它们）。接线属**安全决策**（模型可发起安装 ⇒ 需审批/沙箱口径），
  记入账本后续行，不在本变更内顺手打开。
- **不做市场注册表索引 / 多源路由**：本变更只做「来源 → manifest」，市场侧的索引语义与健康回退已在
  `skillhub`（`MarketIndex`）落地，插件市场侧无消费者（YAGNI）。
