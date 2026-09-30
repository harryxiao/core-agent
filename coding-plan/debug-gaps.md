# 调试前缺口清单（Debug-Readiness Gaps）

> **定位**：回答「是否具备开始调试条件 + 还有哪些任务未完成」的单一事实源。不属于 spec/interface 契约，不参与门禁；随 Phase 推进更新。
> **基线**：`feat/phase0-base` @ `60d9724` + 本轮 entry 接线（未提交）。生成日期 2026-10-01。

---

## 0. 结论

**核心回路已具备真机调试条件**：`core-agent run --prompt ...` 走真装配（LiteLLMProvider → DefaultLoop → judgment 三决策点 → 可逆副作用 + 崩溃恢复/时间旅行），四门禁全绿（490 tests）。

**唯一尚未做过的真机动作**是「活 LLM 端点冒烟」——这是调试第一步（见 §3），不是缺口。

剩余缺口三类：① 已 DEFERRED 的 Phase 12 MCP；② 本轮接线后暴露的「进程内 / 无状态」限制；③ 按「抽象不锁选型」立场 deferred 的真实外部后端。

---

## 1. 现状基线（已验证）

| 维度 | 状态 |
|---|---|
| 门禁 | ruff check ✓ / ruff format ✓(259 文件) / pyright 0 error / pytest 491 passed |
| 运行时依赖 | litellm（唯一第三方运行时依赖）已装 |
| Phase | 0–11、13–16 ✅；12 ⏸ DEFERRED |
| 里程碑 | M0–M10 名义完成 |
| CLI 命令面 | 19 命令：18 已接真实后端，`mcp *` 未接（Phase 12） |

---

## 2. 缺口清单

### 2.1 Phase 12 MCP（唯一 DEFERRED Phase）— 阻塞级

- **范围**：transport 生产实现（stdio/http）、client 安装分流、消费侧安全接线。
- **阻塞原因**：mcp SDK 离线不可装 + 「litellm-only 依赖红线」须 ADR 裁决。
- **现状**：`MCPClient`/`MCPServer` 骨架在，`build_transport` 返回 FakeTransport；CLI `mcp serve/list/add/remove` 未接（entry 落 stub）。
- **重开路径**：ADR 评估 mcp SDK 依赖定位 → 落 0033 ADDED delta。
- **参考**：`coding-plan/phase-12.md`；归档 `doc/openspec/changes/archive/2026-09-29-0033-mcp-install-security-DEFERRED/`。

### 2.2 CLI 命令面：本轮接线后的「无状态 / 进程内」限制 — 中

这些命令已接到真实后端，但后端是进程内对象，CLI 每次新进程 → 结果恒空 / 恒失败：

| 命令 | 现象 | 根因 | 关闭动作 |
|---|---|---|---|
| `plugin list` / `plugin uninstall` | ✅ 已修：list 可见、uninstall 可清理 | install 落 SkillLibrary/ToolProvider，list/uninstall 读 `PluginInstaller._assets`；Phase 16 install 路径未调 `register` → 双注册表脱节 | 已修：`_plugin_install` 补 `register(item, StubPlugin)` 落账本 |
| `sessions` | 恒「无活跃会话」 | 无常驻 serve host，`HarnessHost` 每进程新建 | 建 serve 常驻进程 + 会话持久化 |
| `probe` | 恒 alive（exit 0） | `LifecycleController` 默认 probe_fn 恒 alive，无真探活目标 | 接 serve 进程探活 |
| `release rollback` / `upgrade` | 恒失败（无历史 / 版本不存在） | `ReleaseManager` 每进程新建，无持久化版本登记 | 版本登记持久化 / 接真实制品仓库 |
| `config set` | 运行时生效但不写回 yaml | `apply_change` 是内存变更 | 契约「写回 + revalidate」仍待确认（`cli-contract-baseline.md` §14） |
| `skill search` | 恒空 | 市场 skillhub client 未接，仅本地库 | 接 SkillHubClient（外部市场 deferred） |

> 残留（未修，与 `install_tools` 路径同源）：`uninstall` 仅清账本（`_assets`）+ 卸载 `PluginRegistry` 桩，**不回退** SkillLibrary/ToolProvider 的真实注册。进程内态 + 无常驻 host，CLI 层面无感；真可逆需给 `PluginInstaller` 加对称 `uninstaller` 钩子。

### 2.3 真实外部后端未接（「抽象不锁选型」立场）— 低（不挡核心回路调试）

抽象 + 可注入 fake 已落地，真后端待接（约 20 处「未接」标记）：

| 模块 | 待接后端 |
|---|---|
| git | subprocess / gitpython / dulwich 适配器 |
| im | Telegram / Discord / 飞书 / 微信 SDK |
| mcp transport | 真实 stdio / http（同 §2.1） |
| ui | TTS 语音、Tauri 桌面壳 sidecar |
| observability | OTel 导出 |
| ci_cd | 门禁执行器（ruff/pyright/pytest）、制品仓库发布通道 |
| plugin_registry / plugins | 多源 resolver（git / market / mcp） |
| skillhub | 技能市场下载 |
| pet / beast | loop 由宿主注入、通知通道、git 写回、真实工具执行、神兽 NL 提取 |

### 2.4 杂项 — 无阻塞

- `coding-plan/phase-3-prompt.md` 未跟踪（一次性 prompt 残留，与计划无关，可删或 `git add`）。

---

## 3. 建议的第一次真机调试（非缺口，是待执行动作）

绿测试全用 `_FakeLLM`，真实 LLM 调用未对活端点冒烟。第一步：

1. 写真 `config.yaml`：`llm.provider=litellm` + 可达 `endpoint` + `api_key: ${VAR}`（环境变量喂真 key）；
2. `core-agent run --prompt "..."` 走一遍，验证 planner 解析 / 工具调用 / trace 事件在真模型下成立。

---

## 4. 关闭顺序建议

1. **真机冒烟**（§3）→ 确认核心闭环；
2. ~~§2.2「plugin 双注册表脱节」~~ ✅ 已修（`register` 落账本，见上）；
3. **§2.1 Phase 12 MCP 重开**（先 ADR）；
4. **§2.2 其余 + §2.3**——随「serve 常驻进程 + 持久化」一并落地。
