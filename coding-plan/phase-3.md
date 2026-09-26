# Phase 3 — 单 Agent 闭环（context / loop / skills / skillhub）

> 里程碑：**M2 单 Agent 闭环**（roadmap §3）
> 位置：分层图 L2.5 上下文 + L3 主轴（执行循环 / 技能封装 / 技能市场）
> 上游：Phase 0（底座）+ Phase 1（能力）+ Phase 2（横切中间件）

---

## 1. 范围与定位

本 Phase 交付 **4 个能力，跑通第一个端到端可运行的 agent**——loop 的「观察→推理→行动→记忆」单轮闭环：

| Capability | 职责一句话 | 分层 |
|---|---|---|
| context | 动态上下文构建 + 信息地图二级索引 + 自动压实 + 预算控制 | L2.5 |
| loop | 单轮循环闭环（观察→推理→行动→记忆），横切中间件插入 | L3 主轴 |
| skills | 原子技能库 + 版本管理灰度/A/B + 技能路由 + 超时资源上限 | L3 |
| skillhub | 技能发现/多源路由/签名校验下载/发布审核 | L3 |

**命名对齐（已拍板 D2）**：`src/core/substrate/` 是 `context` 历史命名，本 Phase **开工第一步**统一重命名为 `context`，一次性消除漂移（风险清单 #3）。

**额外承接 Phase 2.5 遗留（M3 / M4 代码）**：Phase 2.5 已完成 `0028/0029` 契约全量定稿（含 M3/M4 的 spec），本 Phase 承接其**代码实现**——`M3`（tool-use `install/uninstall/list` 三工具，AI 对话安装通道）+ `M4`（新增横切 cli-ops 命令面收口）。契约以 Phase 2.5 落定的 spec 为准，**本 Phase 不重复改 spec**。

---

## 2. 里程碑验收（M2 单 Agent 闭环）

**M2 标志**：loop「观察→推理→行动→记忆」端到端可跑。以下全部勾选才算 Phase 3 完成：

- [ ] context：按需加载 + 预算控制，超预算裁剪保留关键；地图定位按需取详情、失效重建、重建失败二阶兜底；压实不丢关键信息；宪法分区注入；项目信息未命中降级
- [ ] loop：停止条件触发退出、单轮回滚；中间件按序执行、被拒短路；循环次数超限、token 预算超限；异步入口 + 流式事件 + 同步薄壳等价
- [ ] skills：注册校验、前置条件检查；灰度发布、A/B 中 B 退化自动回退；路由命中 Top-K、未命中沉淀；执行超时中断、资源超限熔断
- [ ] skillhub：源不可达回退、源不存在报错；签名校验失败拒绝、下载默认 draft；发布进审核、通过才发布、驳回处理
- [ ] 端到端：一次真实任务从「观察」到「记忆写入」全程无断点，loop 能驱动 llm-provider + tool-use + memory + context 协同工作

---

## 3. 依赖与前置

- **上游**：Phase 0（plugin-registry / configuration / observability / core-profile）+ Phase 1（llm-provider / tool-use / memory）+ Phase 2（constraints / permission / durability / mcp）。
- 关键前置：
  - `loop` 的 `Plugin` 基类悬空问题（风险 #2）——依赖 Phase 0 plugin-registry 落地质量，loop 的 `DefaultLoop(Plugin)` 必须在 plugin-registry 上注册。
  - `context` 与 `memory` 的分层协作——热数据即时返回走 memory，冷数据按需加载走 context 的 InfoMap。
  - `skills` 与 `tool-use` 的边界——skill 是「可复用的原子能力包」，内部可能组合多个 tool；路由命中后交给 tool-use 执行。

---

## 4. 首步任务

无（四个 capability 的 spec/interface 均已齐全）。

**启动前核对**（按顺序执行）：
1. **重命名**：`src/core/substrate/` → `src/core/context/`，同步更新所有 import 与文档引用（风险 #3，已拍板 D2）。
2. 以 `contracts_summary.md` 第 5 / 14 / 22 / 23 章为契约基线，逐一对齐 specs/ 与 03-interfaces/ 后开工。
3. 确认 `loop/protocol.py` 骨架与 plugin-registry 的 Plugin 基类衔接方式（风险 #2，关键路径）。

---

## 5. 实现顺序（模块级拓扑序）

### 5.1 context（最先，依赖 memory + plugin-registry + configuration）

- 核心类/接口：`DynamicAssembler`、`InfoMap`、`Compactor`、`BudgetManager`
- 数据类型：`ContextPack` / `Pointer` / `Compaction`
- 关键方法：`build()`、`fetch_detail()`、`index()`、`lookup()`、`rebuild_if_stale()`、`should_compact()`、`compact()`、`persist()`、`enforce()`
- 错误码：`BUDGET_EXCEEDED`、`COMPACTION_LOSSY`、`MAP_STALE`
- 验收重点：超预算裁剪保留关键、地图失效重建 + 二阶兜底、压实不丢关键、宪法分区注入

### 5.2 loop（核心，依赖 context + llm-provider + tool-use + memory + constraints + permission）

- 核心类/接口：`DefaultLoop(Plugin)`、`LoopPlugin(Protocol)`
- 数据类型：`LoopResult` / `LoopEvent` / `LoopContext` / `Action`
- 关键方法：`run()`、`arun()`、`astream()`、`done()`
- 验收重点：单轮闭环、中间件按序执行 + 被拒短路、循环/预算超限、异步流式 + 同步薄壳等价
- **关键路径**：这是 M2 的验收主体，`run()` 必须把「观察→推理→行动→记忆」串成一条链路

### 5.3 skills（依赖 plugin-registry + tool-use + memory）

- 核心类/接口：`SkillLibrary`、`VersionManager`、`SkillRouter`、`SkillCrystallizer`
- 数据类型：`Skill` / `ABResult` / `SkillMatch`
- 关键方法：`register()`、`lookup()`、`list_by_domain()`、`check_preconditions()`、`promote()`、`ab_test()`、`select()`、`match()`、`crystallize()`、`dissolve()`
- 错误码：`INVALID_SKILL_SCHEMA`、`NO_SKILL_MATCH`、`PRECONDITION_FAILED`
- 验收重点：灰度/A-B 中 B 退化自动回退、路由未命中沉淀、超时中断 + 资源熔断

### 5.4 skillhub（依赖 skills + configuration + permission）

- 核心类/接口：`SkillHubClient`、`SkillPublisher`、`TrustVerifier`
- 数据类型：`MarketSkill` / `MarketIndex` / `SourceHealth`
- 关键方法：`search()`、`download()`、`list()`、`route()`、`health()`、`publish()`、`review()`、`verify()`
- 错误码：`PUBLISH_REJECTED`、`SIGNATURE_INVALID`、`SKILL_NOT_ACTIVE`、`SOURCE_NOT_FOUND`、`SOURCE_UNHEALTHY`
- 验收重点：签名校验失败拒绝下载、下载默认 draft、发布审核流、多源路由健康回退

### 5.5 M3 — tool-use 插件安装工具（承接 Phase 2.5，契约见 0028）

- 核心类/接口：`InstallTool`、`UninstallTool`、`ListTool`（注册进 tool-use 的 `active_tools()`）
- 关键方法：`install(source)`、`uninstall(name)`、`list(kind?)`
- 复用：Phase 2.5 M1 的 `InstallableAsset{kind}` + `PluginSource` 生命周期（`discover → verify → install → register`）
- 约束：经 SafetyGate + 权限审批流（危险操作走审批，与 Phase 2 permission 已交付链对接）
- 错误码：`INSTALL_FAILED`、`SOURCE_NOT_FOUND`、`SIGNATURE_INVALID`、`UNINSTALL_NOT_FOUND`
- 验收重点：AI 对话可驱动 install/uninstall/list 全链路；审批流拦高危；uninstall 走 deactivate→清理无残留

### 5.6 M4 — 新增横切 cli-ops 命令面收口（承接 Phase 2.5，契约见 0029）

- 命令集分组：生命周期 start/stop/restart/kill；状态 status/doctor/logs/version/help；资产 install/uninstall/list/info；连接 mcp add/remove/list；安全 auth/permission-mode；网关 gateway
- 参数映射：优先级链 `CLI flag > env > config.yaml > 默认值`（复用 Phase 2.5 M5 的 ConfigSpec 单一真源）
- 前置：M1/M2/M3 的资产命令 + M5 映射模型 + M6 权限开关均已就位
- 验收重点：命令分组全覆盖；`--foo.bar=value ↔ config.foo.bar ↔ CORE_AGENT_FOO_BAR` 三面一致；暴露面 core/advanced/hidden 分级正确

---

## 6. 契约对齐

以 `contracts_summary.md` 为唯一契约基线（本 Phase 对应第 5/14/22/23 章）：

| Capability | 章节 | 关键方法（实现必须覆盖） |
|---|---|---|
| context | §5 | `build()`, `fetch_detail()`, `index()`, `lookup()`, `rebuild_if_stale()`, `should_compact()`, `compact()`, `persist()`, `enforce()` |
| loop | §14 | `run()`, `arun()`, `astream()`, `done()` |
| skillhub | §22 | `search()`, `download()`, `list()`, `route()`, `health()`, `publish()`, `review()`, `verify()` |
| skills | §23 | `register()`, `lookup()`, `list_by_domain()`, `check_preconditions()`, `promote()`, `ab_test()`, `select()`, `match()`, `crystallize()`, `dissolve()` |

**契约红线**（违反即返工）：
1. loop 停止条件触发后必须退出，单轮失败必须回滚（不污染记忆与状态）。
2. 中间件被拒必须短路，不得继续执行后续链。
3. 压实不得丢失关键信息（`COMPACTION_LOSSY` 仅在显式降级时出现）。
4. 技能签名校验失败必须拒绝下载，不得落盘。
5. A/B 测试中 B 版本退化必须自动回退到稳定版。

---

## 7. 门禁验收

全局四命令（见 `doc/05-development/development-standards.md`）全部通过：

```bash
ruff check src tests
ruff format --check
pyright
pytest -q
```

本 Phase 专属校验（附加于全局门禁）：

- [ ] 架构测试：loop 不得反向依赖 skills/skillhub；context 不得反向依赖 loop
- [ ] 端到端冒烟：`run()` 一次真实任务跑通「观察→推理→行动→记忆」闭环
- [ ] 中间件短路测试：权限拒绝后 loop 立即停止，无后续副作用
- [ ] 预算控制测试：token/循环超限后 loop 退出并返回可诊断错误
- [ ] 压实测试：超长上下文压实后关键信息仍在
- [ ] 技能 A/B 测试：B 退化自动回退，路由结果不劣化
- [ ] 签名测试：篡改签名下载被拒，合法签名通过
- [ ] M3 安装工具测试：`install` 走 SafetyGate + 审批流；`list` 能列出已装资产；`uninstall` 走 deactivate→清理（契约见 Phase 2.5 0028）
- [ ] M4 cli-ops 测试：命令分组全覆盖；参数映射优先级链 `CLI > env > yml > 默认` 生效；暴露面 core/advanced/hidden 分级正确（契约见 Phase 2.5 0029）

---

## 8. 提交规范

- **一个 Phase 一个 commit**：4 模块 + M3/M4 承接 + 门禁全绿后单次提交。
- commit message 形如：`feat(phase3): context/loop/skills/skillhub 单 Agent 闭环（M2）+ M3/M4 安装通道与 cli-ops`
- 提交后回填 roadmap §3 的 M2 里程碑状态为「完成」，并同步更新 `README.md` Phase 3 行状态。
