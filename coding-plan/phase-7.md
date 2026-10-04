# Phase 7 — 交付流水线、三模入口与 IM 网关（ci-cd / ui / im / git）

> 里程碑：**M5 可发布产品**
> 位置：接入层（ui/im）+ 交付层（ci-cd）+ 工具横切（git）
> 上游：Phase 0（底座）+ Phase 1（能力）+ Phase 2（横切中间件）+ Phase 4（orchestration/distributed/deployment）

---

## 1. 范围与定位

本 Phase 交付 **4 个能力，让 core-agent 达到「完整产品形态可发布」**：

| Capability | 职责一句话 | 分层 |
|---|---|---|
| ci-cd | 质量门禁（lint/typecheck/test/build 四道）+ 制品发布 | 交付层 |
| ui | 三模统一内核（CLI/Web/Desktop）+ 统一后端 API | 接入层 |
| im | 多平台 IM 统一接入 + 消息驱动会话 | 接入层 |
| git | 版本控制核心操作 + 安全与可靠性 | 工具横切 |

**里程碑口径（M5）**：完整产品形态可发布 —— 分发 + 三入口 + CI/CD 全链路。

---

## 2. 契约红线（contracts_summary 原文）

**ci-cd（§1）**：
- 能力：质量门禁四道（lint/typecheck/test/build）+ 制品发布
- 契约：四道门禁全通过才交付；任一失败即阻断；制品版本化发布且可回滚
- 接口：`CICDPipeline`、`ArtifactPublisher`；数据类型 `Gate`/`PipelineRun`/`Artifact`
- 方法：`run()`、`gate()`、`publish()`、`rollback()`
- 错误码：`ARTIFACT_NOT_FOUND`、`CHANNEL_UNREACHABLE`、`GATE_FAILED`

**ui（§25，三模入口）**：
- 能力：三模统一内核（CLI/Web/Desktop）、统一后端 API（FastAPI，HTTP+SSE）、LLM 可配置、多模态输入、实时语音输出、Web Client 分离
- 契约：三模复用同一内核与 LLM 配置、统一后端 API，CLI 也不绕过；LLM API Key 只配置一次、密钥安全存储；CLI 流式输出 + 折叠块；Web SSE 断线重连；Web/桌面体验一致；图像输入理解、语音转写、模态缺失降级；流式 TTS 播报、用户打断（barge-in）、语音上下文引用；Web 前端纯静态独立托管、前后端解耦升级、发布不要求后端重启
- 接口：`UIAPILayer`、`CLIBridge`、`WebBridge`、`DesktopBridge`
- 方法：`create_session()`、`run_loop()`、`get_memory()`、`compact()`、`list_tools()`、`invoke_tool()`、`get_llm_config()`、`set_llm_config()`、`connect()`、`serve()`、`start_sidecar()`
- 错误码：**无**（需首步补齐）
- 命令面边界：运维命令面（status/doctor/logs/install/mcp/auth/gateway）**不并入 ui**，复用 cli-ops（M4 横切能力）；`CLIBridge` 只承载交互会话面（无子命令进 `run_loop()`）。

**im（§12）**：
- 能力：多平台统一接入、消息驱动会话、分平台接入、身份白名单、安全透传、会话隔离容错
- 契约：新增平台零侵入；发消息即会话、多轮上下文保持、重复消息幂等；官方通道接入、个人号拒绝；白名单放行、非白名单拒绝；高危操作确认 + 审计落盘；多用户隔离、断线重连退避
- 接口：`IMGateway(Plugin)`、`IMProvider(Protocol)`、`Message`
- 方法：`register()`、`on_message()`、`reply()`、`approve()`、`start()`、`send()`、`identity()`
- 错误码：`IM_CONFIRM_DENIED`、`IM_CONFIRM_TIMEOUT`、`IM_NOT_WHITELISTED`、`IM_PLATFORM_DISCONNECTED`、`IM_PLATFORM_UNSUPPORTED`、`IM_SEND_FAILED`

**git（§11，无接口）**：
- 能力：版本控制核心操作、`.git` 与工作区保护、凭据安全、与 permission 协作、远程可靠性
- 契约：提交/分支/合并；保护 `.git` 元数据、失败不损坏工作区；凭据不落盘明文；高危操作走审批；远程超时、认证失败、断线重试、连接释放
- 接口：**无**（需首步补契约）

---

## 3. 验收口径（M5 里程碑）

- 分发链路（composition/distributed/deployment）已可用，见 Phase 6
- 三入口（CLI/Web/Desktop）复用同一内核，均可跑通 loop
- CI/CD 四道门禁 + 制品发布闭环
- IM 至少一个平台（如 Telegram/钉钉/企业微信）端到端跑通会话
- git 安全操作（含凭据保护 + 高危审批）可用

---

## 4. 首步任务

**首步补 2 个契约缺口 + 3 项对齐**：

1. **补 git 契约（git@119 无接口）**——走 openspec_sop：补 `GitClient` 接口（建议方法：`commit()`/`branch()`/`merge()`/`status()`/`diff()`/`checkout()`/`stash()`/`push()`/`pull()`）+ 错误码（建议：`GIT_AUTH_FAILED`、`GIT_REMOTE_TIMEOUT`、`GIT_WORKTREE_DIRTY`、`GIT_CONFLICT`），再编码。禁止直接 import 具体 git 库到上层，经接口隔离。
2. **补 ui 错误码（ui@222 无错误码）**——建议：`UI_LLM_KEY_UNSET`、`UI_SESSION_NOT_FOUND`、`UI_MODALITY_MISSING`、`UI_BARGEIN`，走 openspec_sop 补契约再编码。
3. **对齐 ci-cd 门禁命令**：ci-cd 四道门禁（lint/typecheck/test/build）必须与 Phase -1 已固化的门禁基线命令一致（复用 `verify_sop`/门禁脚本），不得另起一套。
4. **核对 im ↔ distributed A2A 边界**：im 是「消息驱动会话入口」（人→agent），distributed 是「A2A 双向互调」（agent↔agent）；确认两者不重叠、im 的 `Message` 与 distributed 卡片协议可互转。
5. **对齐 ui CLI 入口 ↔ cli-ops 运维命令面**：ui 的 `CLIBridge` 只承载交互会话面（`core-agent` 无子命令进会话）；运维命令面（status/doctor/logs/install/mcp/auth/gateway）复用 cli-ops（M4，横切能力，不并入 ui），CLI 入口不得另起命令解析（与 ci-cd 门禁「不得另起一套」同一原则）。

**启动前核对**（按顺序执行）：
1. 读 contracts_summary §1（ci-cd）+ §11（git）+ §12（im）+ §25（ui）原文。
2. 补 git 接口契约（先补 `doc/03-interfaces/git-interface.md`，当前缺失）+ ui 错误码契约，validate 通过后再编码。

---

## 5. 依赖与顺序

- ci-cd 依赖：Phase -1 门禁基线（复用）+ 全部模块（制品）
- ui 依赖：Phase 3（loop/context/skills）+ Phase 1（llm-provider）+ Phase 2（memory）
- im 依赖：Phase 2（permission 审批）+ Phase 4（distributed 边界）
- git 依赖：Phase 2（permission 高危审批）
- 建议顺序：git 契约补齐 → ci-cd 门禁对齐 → ui 三模内核 → im 接入

---

## 6. 里程碑验收清单

- [x] git 接口契约补齐，安全操作（凭据不落盘 + 高危审批）可用
- [x] ui 三模（CLI/Web/Desktop）复用同一内核跑通 loop（抽象层）
- [x] 统一后端 API + LLM Key 单次配置 + 安全存储（抽象层落地；FastAPI HTTP/SSE 传输 ✅ 已由 Phase 9 落地：`src/core/ui/fastapi_serve.py`）
- [x] im 白名单/高危确认/消息幂等/断线隔离（抽象层 + FakeProvider 测试跑通；真实平台 SDK 未接）
- [x] ci-cd 四道门禁 + 制品发布闭环，任一门禁失败阻断交付
- [x] 三入口 + CI/CD 全链路冒烟通过（M5；真实后端 deferred，抽象层门禁全绿）

---

## 7. 测试要点

- [x] ci-cd：四道门禁全通过才交付；任一失败阻断；制品回滚测试；错误码 3 覆盖
- [x] ui：三模复用同一内核测试；SSE 流式事件；barge-in 打断；模态缺失降级；LLM Key 只存引用（断线重连/前端托管 deferred）
- [x] im：消息幂等；白名单放行/拒绝；高危操作确认；断线隔离；6 错误码覆盖（退避重连 deferred）
- [x] git：`.git` 保护；凭据不落盘（SecretRef 引用）；高危操作走审批；远程超时/认证失败/工作区脏/冲突 4 错误码（断线重试/连接释放 deferred）

---

## 8. 提交规范

- **一个 Phase 一个 commit**：ci-cd + ui + im + git 四模块 + 门禁全绿后单次提交。
- commit message 形如：`feat(phase7): ci-cd/ui/im/git 交付流水线与三模入口（M5）`
- 提交后更新 `README.md` §2 总览表 Phase 7 行状态列为「完成」。
