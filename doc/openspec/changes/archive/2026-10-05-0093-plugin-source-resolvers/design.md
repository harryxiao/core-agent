# design — 0093 插件四源解析器

## 决策

### ① 解析器落 `core/plugins/sources.py`（执行层），不动 `plugin_registry` 基座

`plugin_registry` 是 **BASE_MODULES**（底座，只依赖彼此 + stdlib，见 `tests/test_architecture.py:56`），其
`_default_resolve` 保持「未接入」空壳；真实解析天然属于**执行层** `plugins`（`InstallDispatcher` 已承担
resolver + installer 双职责，见 `install.py:48`）。故新增模块 `core/plugins/sources.py`，
`InstallDispatcher.resolve` 四源分派。

### ② 外部边 = **stdlib 缺省实现 + 可注入缝**

三类来源的真正难点是「外部世界」：git 远端 / 市场 HTTP / MCP 端点。处置与 `SkillHubClient`
（`client.py:22` `Fetcher`）同形 —— **可注入**，但**缺省不是 `None` 而是真实的 stdlib 实现**：

| 边 | 缺省实现 | 注入缝 |
|---|---|---|
| git 克隆 | `build_backend().clone(...)`（**change 0090** 的 stdlib subprocess 后端） | `Cloner = Callable[[str, Path], None]` |
| 市场拉取 | `urllib.request` GET（同 `tools/builtin.py:204` / `judgment/provider.py`） | `Fetcher = Callable[[str], dict]` |
| MCP 端点 | 无（纯字符串合成，零网络） | — |

**缺省为真**（非 skillhub 的 `None`）的理由：git-repo / market-registry 的**成功路径可完全离线验证**
（本地仓库克隆即可），无需凭证，与 C2/C3「真后端 + 真缺省」同口径；skillhub 之所以缺省 `None` 是因其
市场索引本身含签名/健康语义，插件市场侧无此结构。

### ③ `core-plugin.json` 约定（**新的外部契约**）

仓库内**零既有 manifest 文件名约定**（全仓检索无命中）。git-repo 来源必须以某个固定入口读 manifest，
故定义 `MANIFEST_FILENAME = "core-plugin.json"`：命名空间前缀 `core-` 避免与仓库自有的
`package.json` / `plugin.json` 撞名。常量与约定写入接口文档 §8 与规格（因为是**对外契约**）。

**路径固定为仓库根目录**，不做「可指定子路径」—— 无消费者，YAGNI。

### ④ 临时工作区可逆

`tempfile.TemporaryDirectory(prefix="core-plugin-")` 包住「克隆 → 读 manifest」全段，`with` 退出即删除；
克隆目标 `dest = tmp / "repo"`（不与 tmp 根混淆）。⇒ 解析**零残留**，不回写 `$CORE_STATE_DIR`。

### ⑤ 回显脱敏 `_safe`

`ADR-0085`（git 后端）立下「**不回显可能含凭据的地址**」红线。本变更的两处失败信息沿用：
`_safe(url)` 经 `urlsplit` / `urlunsplit` **剥掉 userinfo 与 query**。市场凭据的正道是**注入 fetcher 携带**
（不进 URL），`_safe` 是纵深防御的第二层 —— URL 里若被塞了 token 也不会进异常文本 / 日志 / 记忆。
**不用 `parts.port`**（畸形端口会 raise），改 `netloc.rpartition("@")[2]`，无解析风险。

### ⑥ mcp-endpoint 解析期零网络

`resolve_mcp_endpoint` 只做「端点串 → `{"name": ..., "url": ...}`」。端点名复用 `core.mcp` 既有的
`default_endpoint_name`（URL → 主机名），**不另立解析**。可达性归 install 期 `MCPClient.add` —— 与
`mcp add`「先连通验证再落盘」同一口径；解析期探测会引入「解析成功但装不上」的双重语义。

### ⑦ CLI `plugin install --source`（**完成既有入口的既有契约**）

`plugin install` **已存在**，但其 `_plugin_install` 把来源**硬编码**为 `PluginSource.LOCAL_PATH`，
而同一入口背后的 `PluginSource` 声明四值、规格要求四源 ⇒ **入口自述的能力与实际能力不符**。补 `--source`
（choices = 四源，缺省 `local-path` 保持向后兼容）属**补齐既有入口的既有契约**，与 C5 的
`skill search --source` 同性质；**不是**新增命令面（对比 C2/C3 拒绝的「无消费者的新入口」）。

### ⑧ 顺带修 `_build_installer` 的技能库同源

`_build_installer()` 用 `SkillLibrary()`（**无路径** ⇒ 进程内一次性库），故 `plugin install --kind skill`
装完即丢 ——「已安装」是谎报，`plugin list` 仅在**同一进程**可见。这与 `ADR-0087`（C5）诊断的
**同一根因族**。改为 `_build_skill_library()`（`$CORE_STATE_DIR/skills.json`，与组合根同源）是一行改动，
且是 `--source git-repo` 能"真的装上"的前提。**mcp / cli 分支不受影响**：工具面本就进程内，
MCP 端点的持久化归端点注册表（`mcp add` 路径），不经此处。

### ⑨ 不做

`mcp add` 改走 `MCP_ENDPOINT` 来源（无收益重构）、`install_tool` 接线（安全决策 + 非 C6 症状）、
市场索引语义（`skillhub` 已有，插件侧无消费者）。详见 `proposal.md`「明确不做」。

## 影响面

- `InstallDispatcher.__init__` 增 2 个 keyword-only 参数（纯加法，既有调用点零改动）。
- `_plugin_install` 增 1 个位置参数（内部函数，唯一调用点已改）。
- 既有 `tests/test_entry.py:485/495`（`plugin install --kind skill`）继续通过：缺省 source 仍是 `local-path`。
- `tests/test_architecture.py`：`plugins` **不在** `EXPECTED_PACKAGES` / `BASE_MODULES` /
  `CAPABILITY_MODULES` 任一名单，也**不在**任何 `forbidden` 映射 ⇒ 新增 `core.git` 依赖不受门禁约束，
  且依赖方向（执行适配层 → 能力横切）正确。
