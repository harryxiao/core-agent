# core-agent 契约速查表（Contracts Summary）

> 从 `openspec/specs/*/spec.md`（28 个规格）与 `03-interfaces/*.md`（26 个接口）提取。
> 用途：跨模块快速检索「能力 / 关键契约 / 接口类与方法 / 错误码」。
> 来源只读，本表为唯一产物，不修改任何 core-agent 源文件。

## 总览

| 模块 | 规格 | 接口 | 定位一句话 | 主要错误码 |
|---|---|---|---|---|
| ci-cd | ✅ | ✅ | 交付流水线质量门禁 + 制品发布 | ARTIFACT_NOT_FOUND, CHANNEL_UNREACHABLE, GATE_FAILED |
| cli-ops | ✅ | ✅ | CLI 运维命令集（六组）+ 启动参数三层映射（flag > env > yaml > 默认） | UNKNOWN_COMMAND, INVALID_MAP_TO |
| composition | ✅ | ✅ | 唯一静态层：profile/bundle/patch 组合分发 | — |
| configuration | ✅ | ✅ | config.yaml 单一配置收口 | — |
| constraints | ✅ | ✅ | 输入输出校验 / 容错 / 上下文压缩中间件 | CIRCUIT_OPEN, OUTPUT_PARSE_FAILED, RETRY_EXHAUSTED, ROLLBACK_FAILED |
| context | ✅ | ✅ | 动态上下文构建 + 信息地图 + 自动压实 | BUDGET_EXCEEDED, COMPACTION_LOSSY, MAP_STALE |
| core-profile | ✅ | ✅ | 两级 Core.md 灵魂文件（宪法+人格） | PROFILE_MISSING, SECTION_INVALID |
| deployment | ✅ | ✅ | 自托管/BYOC 部署 + Harness Host 常驻 | — |
| distributed | ✅ | ✅ | A2A 分布式协作 + AgentCard 发现 | A2A_AUTH_FAILED, A2A_CARD_INVALID, A2A_PEER_UNREACHABLE, A2A_PROTOCOL_UNSUPPORTED, A2A_SCOPE_DENIED, A2A_TASK_FAILED |
| durability | ✅ | ✅ | 检查点 / 崩溃恢复 / 时间旅行 | CHECKPOINT_CORRUPT, CHECKPOINT_NOT_FOUND, RESTORE_DEGRADED, RETENTION_QUOTA_EXCEEDED |
| evolution | ✅ | ✅ | 进化引擎结晶闭环（诊断→提案→验证→评测） | — |
| git | ✅ | ❌ | 版本控制 + .git/工作区保护 | — |
| im | ✅ | ✅ | IM 网关多平台统一接入 | IM_CONFIRM_DENIED, IM_CONFIRM_TIMEOUT, IM_NOT_WHITELISTED, IM_PLATFORM_DISCONNECTED, IM_PLATFORM_UNSUPPORTED, IM_SEND_FAILED |
| judgment | ✅ | ✅ | 决策模型接入（choice/score/noul 三原语 + JEV + 置信度回退 + 决策审计） | JUDGMENT_PROVIDER_UNREACHABLE, JUDGMENT_SCHEMA_MISMATCH, JUDGMENT_LOW_CONFIDENCE, JUDGMENT_TIMEOUT, JUDGMENT_INVALID_PRIMITIVE |
| llm-provider | ✅ | ✅ | 三方 LLM 归一化（LiteLLM 默认，可替换） | LLM_ERROR, LLM_TIMEOUT, LLM_RATE_LIMITED, LLM_AUTH, LLM_NETWORK, LLM_UNKNOWN_PROVIDER |
| loop | ✅ | ✅ | 核心执行循环（观察→推理→行动→记忆） | — |
| mcp | ✅ | ✅ | MCP 集成（client + server 双向） | MCP_CONNECT_FAILED, MCP_PROTOCOL_MISMATCH, MCP_TOOL_NOT_FOUND, PERMISSION_DENIED, REMOTE_IRREVERSIBLE, REMOTE_TIMEOUT |
| memory | ✅ | ✅ | 记忆系统光谱 L0-L4 | — |
| observability | ✅ | ✅ | 全链路日志 + 指标 + 链路追踪 | EXPORT_FAILED, TELEMETRY_DEGRADED |
| orchestration | ✅ | ✅ | 任务状态机 / 子任务拆解 / 多 Agent 协同 | DEADLOOP_DETECTED, INVALID_TRANSITION, NO_AGENT_MATCH, PROGRESS_NOT_MET, SUBTASK_VERIFY_FAILED, WAVE_FANOUT_LIMIT |
| permission | ✅ | ✅ | 分级权限 + 人工审批 + 沙箱隔离 | APPROVAL_EXPIRED, APPROVAL_REQUIRED, APPROVAL_TIMEOUT, PERMISSION_DENIED, SANDBOX_UNAVAILABLE |
| pet-mode | ✅ | ✅ | 后台宠物模式（自治循环 + 多宠物 + 人格 + 受限探索 + 通知） | PET_ALREADY_ACTIVE, PET_NOT_ACTIVE, PET_BACKOFF, PET_YIELDING, PET_PREFERENCE_WRITE_FAILED |
| plugin-registry | ✅ | ✅ | 插件注册表 + 依赖解析 + 隔离 | COEFFECT_MISSING, GENERATION_CONFLICT, INVALID_SCHEMA, NOT_ACTIVE, UNDO_FAILED |
| rag | ✅ | ✅ | 本地向量库 + 检索增强生成 | EMBEDDING_FAILED, INDEX_CORRUPT, REBUILD_FAILED |
| skillhub | ✅ | ✅ | 技能市场（发现/路由/签名/审核） | PUBLISH_REJECTED, SIGNATURE_INVALID, SKILL_NOT_ACTIVE, SOURCE_NOT_FOUND, SOURCE_UNHEALTHY |
| skills | ✅ | ✅ | 原子技能库 + 版本灰度/A/B + 路由 | INVALID_SKILL_SCHEMA, NO_SKILL_MATCH, PRECONDITION_FAILED |
| tool-use | ✅ | ✅ | 工具 schema/参数校验 + coeffect 副作用契约 | COEFFECT_MISSING, GATE_DENIED, INVALID_ARGS, INVALID_TOOL_SCHEMA, IRREVERSIBLE_BLOCKED, TIMEOUT, UNDO_FAILED |
| ui | ✅ | ✅ | 三模入口（CLI/Web/Desktop）统一后端 API | — |

> 注：`git` 规格无对应接口文件（纯规格层）。

---

## 逐模块契约明细

### 1. ci-cd — 交付流水线

- **能力**：质量门禁（lint/typecheck/test/build 四道）+ 制品发布。
- **契约**：四道门禁全通过才交付；任一失败即阻断交付；制品版本化发布且可回滚。
- **接口**：`CICDPipeline`、`ArtifactPublisher`；数据类型 `Gate`/`PipelineRun`/`Artifact`。
- **方法**：`run()`、`gate()`、`publish()`、`rollback()`。
- **错误码**：`ARTIFACT_NOT_FOUND`、`CHANNEL_UNREACHABLE`、`GATE_FAILED`。

### 2. composition — 组合与分发层

- **能力**：静态组合代数（永不进化），经 profile（命名组合）/ bundle（分发格式）/ patch.yml（用户覆盖）三要素组合分发。
- **契约**：profile 按名选用；bundle 跨部署复用、校验失败/循环依赖被拦截；patch 覆盖冲突兜底；层叠解析顺序确定。
- **接口**：`CompositionEngine(Plugin)`、`ProfileResolver`、`BundlePackager`、`BundleDistributor`；数据类型 `Profile`/`Bundle`/`PatchSpec`/`ResolvedSet`。
- **方法**：`resolve()`、`pack()`、`unpack()`、`publish()`、`fetch()`。

### 3. configuration — 配置管理

- **能力**：config.yaml 单一收口，env 覆盖 yaml，密钥走 keychain。
- **契约**：LLM 配置必选（缺失阻断启动）；功能开关缺省关闭模块不初始化；IM 可选、凭证经 keychain；日志不泄露密钥、yaml 拒绝明文密钥；schema 校验通过才生效、半写状态回滚。
- **接口**：`ConfigManager`；数据类型 `AppConfig`/`LLMConfig`/`IMConfig`/`ValidationResult`。
- **方法**：`load()`、`validate_schema()`、`resolve_secret()`、`is_enabled()`、`apply_change()`。

### 4. constraints — 约束与中间件

- **能力**：输入输出校验、容错（熔断/重试/回滚）、上下文压缩中间件。
- **契约**：输入校验失败拒绝执行；输出解析失败不执行副作用；熔断器打开短路；失败触发回滚；压缩清理冗余上下文。
- **接口**：`Middleware(Protocol)`、`Validator`、`CircuitBreaker`、`RetryPolicy`、`Fallback`、`Rollback`。
- **方法**：`before()`、`after()`、`validate_input()`、`parse_output()`、`record_result()`、`state()`、`should_retry()`、`backoff()`、`on_failure()`。
- **错误码**：`CIRCUIT_OPEN`、`OUTPUT_PARSE_FAILED`、`RETRY_EXHAUSTED`、`ROLLBACK_FAILED`。

### 5. context — 上下文工程

- **能力**：动态上下文构建、信息地图（二级索引）、上下文自动压实、宪法约束注入、项目信息注入。
- **契约**：按需加载 + 预算控制，超预算裁剪保留关键；地图定位按需取详情、失效重建、重建失败二阶兜底；压实不丢关键信息；宪法分区注入；项目信息未命中降级。
- **接口**：`DynamicAssembler`、`InfoMap`、`Compactor`、`BudgetManager`；数据类型 `ContextPack`/`Pointer`/`Compaction`。
- **方法**：`build()`、`fetch_detail()`、`index()`、`lookup()`、`rebuild_if_stale()`、`should_compact()`、`compact()`、`persist()`、`enforce()`。
- **错误码**：`BUDGET_EXCEEDED`、`COMPACTION_LOSSY`、`MAP_STALE`。

### 6. core-profile — 灵魂文件

- **能力**：全局级/项目级两级 Core.md，宪法分区 + 人格分区双语义。
- **契约**：项目级按 cwd 向上查找、覆盖全局级；宪法分区注入 coeffect、人格分区落 L0；文件缺失静默降级、格式非法告警跳过；宪法命令式可判定、人格结构化且篇幅受控；与 CLAUDE.md 分工。
- **接口**：`CoreProfileEngine`、`GlobalProfileLoader`、`ProjectProfileLoader`、`SectionParser`、`Merger`、`Validator`；数据类型 `CoreProfile`/`AssembledProfile`/`Section`。
- **方法**：`load_global()`、`load_project()`、`assemble()`、`find_upwards()`、`parse()`、`merge()`、`validate()`。
- **错误码**：`PROFILE_MISSING`、`SECTION_INVALID`。

### 7. deployment — 部署与托管

- **能力**：自托管、可选云托管 BYOC、发布升级回滚、健康检查、Harness Host 常驻。
- **契约**：常驻 Host 多客户端接入统一端点；客户端断线清理、连接超时回收；健康探活与恢复；升级可回滚。
- **接口**：`HarnessHost`、`ReleaseManager`、`LifecycleController`、`CloudAdapter`；数据类型 `RuntimeEnvironment`/`RuntimeConfig`/`DeployTarget`/`ReleaseInfo`/`HealthStatus`。
- **方法**：`configure()`、`assemble()`、`bootstrap()`、`adapt()`、`parity_check()`、`publish()`、`upgrade()`、`rollback()`、`start()`、`stop()`、`restart()`、`probe()`、`serve()`、`accept()`、`sessions()`。

### 8. distributed — 分布式协作（A2A）

- **能力**：A2A 双向互调、AgentCard 发现与签名、协议绑定、安全鉴权、多设备拓扑、P2P 直连、连接管理。
- **契约**：委派外部 Agent + 对外暴露能力；卡片签名验证；默认 JSON-RPC 绑定可换；双向认证 + 最小权限；控制面/执行面分离；打洞直连优先；心跳保活、断线重连、调用超时、资源释放、委派重试幂等；A2A 与 MCP 互补（Server 内部经 MCP 调工具）。
- **接口**：`A2AClient`、`A2AServer`、`AgentCard`。
- **方法**：`read_card()`、`send_message()`、`subscribe()`、`expose()`、`on_message()`、`report()`。
- **错误码**：`A2A_AUTH_FAILED`、`A2A_CARD_INVALID`、`A2A_PEER_UNREACHABLE`、`A2A_PROTOCOL_UNSUPPORTED`、`A2A_SCOPE_DENIED`、`A2A_TASK_FAILED`。

### 9. durability — 持久性

- **能力**：检查点/快照、崩溃恢复、时间旅行回滚、生命周期保留。
- **契约**：显式创建检查点带元数据寻址；崩溃后自动恢复且幂等；检查点损坏降级；回滚到历史检查点并与副作用级回滚协同；保留策略自动清理、关键检查点 pin 保护。
- **接口**：`CheckpointManager`、`CrashRecovery`、`TimeTravel`、`RetentionManager`；数据类型 `Checkpoint`/`Snapshot`/`RestoreHandle`/`RetentionPolicy`。
- **方法**：`create_checkpoint()`、`list_checkpoints()`、`get_snapshot()`、`restore()`、`resume()`、`rollback()`、`apply()`、`pin()`、`unpin()`。
- **错误码**：`CHECKPOINT_CORRUPT`、`CHECKPOINT_NOT_FOUND`、`RESTORE_DEGRADED`、`RETENTION_QUOTA_EXCEEDED`。

### 10. evolution — 进化引擎

- **能力**：结晶闭环（经验采集→结晶→溶解→诊断→提案→验证门→留出评测）。
- **契约**：采集行动结果对、无结果证据不采集；生成技能候选待人工确认；退化检测溶解回收；对比诊断归因到插件、无插件级归因则人工介入；模块级提案过验证门才发布；留出集通过则发布、退化回滚、并发评测资源上限；基准集注册 + 批量评测 + 基线对比判定退化；任务完成度/正确性/轨迹质量三维评测。
- **接口**：`EvolutionEngine(Plugin)`、`Diagnoser`、`Proposer`、`Validator`、`Evaluator`、`EvolutionTrigger`；数据类型 `DiagnosisReport`/`GenerationCandidate`/`GateReport`/`EvalReport`。
- **方法**：`diagnose()`、`propose()`、`validate()`、`evaluate()`、`run_cycle()`、`maybe_run()`。

### 11. git — 版本控制（无接口）

- **能力**：版本控制核心操作、`.git` 与工作区保护、凭据安全、与 permission 协作、远程可靠性。
- **契约**：提交/分支/合并；保护 `.git` 元数据、失败不损坏工作区；凭据不落盘明文；高危操作走审批；远程超时、认证失败、断线重试、连接释放。

### 12. im — IM 网关

- **能力**：多平台统一接入、消息驱动会话、分平台接入、身份白名单、安全透传、会话隔离容错。
- **契约**：新增平台零侵入；发消息即会话、多轮上下文保持、重复消息幂等；官方通道接入、个人号拒绝；白名单放行、非白名单拒绝；高危操作确认 + 审计落盘；多用户隔离、断线重连退避。
- **接口**：`IMGateway(Plugin)`、`IMProvider(Protocol)`、`Message`。
- **方法**：`register()`、`on_message()`、`reply()`、`approve()`、`start()`、`send()`、`identity()`。
- **错误码**：`IM_CONFIRM_DENIED`、`IM_CONFIRM_TIMEOUT`、`IM_NOT_WHITELISTED`、`IM_PLATFORM_DISCONNECTED`、`IM_PLATFORM_UNSUPPORTED`、`IM_SEND_FAILED`。

### 13. llm-provider — LLM 归一化

- **能力**：统一 `LLMProvider` 抽象，LiteLLM 默认实现，依赖注入可替换，错误归一化，调用审计，可靠性，异步接口。
- **契约**：任意三方模型配置 API Key/URL 即接入、调用方零改动；底层异常归一；调用留痕；失败自动重试、超时控制、服务降级、连接复用、流式断流处理；异步入口 + 同步薄壳等价 + 真并发。
- **接口**：`LLMProvider(ABC)`、`LiteLLMProvider`、`LLMProviderRegistry`、`LLMError` 层级；数据类型 `Message`/`LLMRequest`/`TokenUsage`/`LLMResponse`/`Embedding`/`LLMChunk`。
- **方法**：`completion()`、`stream()`、`embedding()`、`acompletion()`、`astream()`、`aembedding()`、`register()`、`resolve()`、`default()`。
- **错误码**：`LLM_ERROR`、`LLM_TIMEOUT`、`LLM_RATE_LIMITED`、`LLM_AUTH`、`LLM_NETWORK`、`LLM_UNKNOWN_PROVIDER`。

### 14. loop — 核心执行循环

- **能力**：单轮循环闭环（观察→推理→行动→记忆）、横切中间件插入、错误与预算控制、异步流式执行。
- **契约**：停止条件触发退出、单轮回滚；中间件按序执行、被拒短路；循环次数超限、token 预算超限；异步入口 + 流式事件 + 同步薄壳等价。
- **接口**：`DefaultLoop(Plugin)`、`LoopPlugin(Protocol)`；数据类型 `LoopResult`/`LoopEvent`/`LoopContext`/`Action`。
- **方法**：`run()`、`arun()`、`astream()`、`done()`。

### 15. mcp — MCP 集成

- **能力**：连接管理、工具/资源发现、调用转发与错误隔离、Server 模式、白名单暴露、安全透传、会话隔离、多流复用。
- **契约**：注册连接、断线重连、心跳保活、关闭释放资源；动态映射工具、能力冲突处理；透明转发、MCP 异常隔离；stdio 本地挂载 + Streamable HTTP 远程挂载；默认最小暴露、白名单显式开放；高危确认、越权拒绝；多客户端隔离、单连接故障隔离；单连接多会话复用、会话与连接解耦。
- **接口**：`MCPClient(Plugin)`、`MCPServer(Plugin)`、`MCPEndpoint`、`MCPToolAdapter`。
- **方法**：`connect()`、`list_tools()`、`list_resources()`、`list_prompts()`、`call_tool()`、`read_resource()`、`get_prompt()`、`adapt()`、`serve()`、`initialize()`。
- **错误码**：`MCP_CONNECT_FAILED`、`MCP_PROTOCOL_MISMATCH`、`MCP_TOOL_NOT_FOUND`、`PERMISSION_DENIED`、`REMOTE_IRREVERSIBLE`、`REMOTE_TIMEOUT`、`MCP_UNAVAILABLE`、`TOOL_NAME_CONFLICT`。

### 16. memory — 记忆系统

- **能力**：L0-L4 分层记忆、温度分层检索、结晶/溶解、压实、人格注入。
- **契约**：分层写入 + 跨层检索；热数据即时返回、冷数据按需加载、检索失败降级；无行动不写入；索引最小化、压实失败降级、并发压实一致；人格分区写入 L0。
- **接口**：`MemoryStore(Plugin)`、`Crystallizer`、`MemoryBackend(Protocol)`；数据类型 `MemoryEntry`/`Layer`/`IndexEntry`。
- **方法**：`read()`、`write()`、`migrate()`、`index()`、`audit()`、`crystallize()`、`dissolve()`、`get()`、`put()`、`search()`、`list_index()`、`delete()`。

### 17. observability — 可观测性

- **能力**：全链路日志、指标监控、链路追踪、遥测缓冲导出、指标导出协议、告警。
- **契约**：记录模型与工具调用、敏感信息脱敏；指标聚合快照；单任务全链路回溯、遥测故障不阻塞主循环；缓冲溢出兜底、导出重试与背压；OTel 导出 + Prometheus 拉取、导出失败不阻塞；阈值触发、分级告警、告警风暴抑制。
- **接口**：`Tracer`、`TraceLogger`、`MetricsCollector`、`Exporter(Protocol)`、`TraceEvent`。
- **方法**：`log_model_io()`、`log_tool_call()`、`log_effect()`、`inc()`、`gauge()`、`snapshot()`、`start_trace()`、`end_trace()`、`replay()`、`emit()`。
- **错误码**：`EXPORT_FAILED`、`TELEMETRY_DEGRADED`。

### 18. orchestration — 任务规划编排

- **能力**：任务状态机、子任务拆解、多 Agent 协同、断点续跑、并行扇出、目标监控、优先级调度、异步执行单元。
- **契约**：合法状态转移、非法转移拒绝、死循环检测；拆解拓扑执行、子任务校验通过才推进；能力匹配交接、无匹配 Agent 处理；挂起/恢复/取消；波次划分并行扇出、fan-in 汇总推进、资源上限、fan-out 幂等派发；成功标准 + 进度追踪、未达标重试/重规划；优先级排序、同优先级稳定、缺省处理；复用异步接口、扇出真并发非阻塞、契约空白闭合。
- **接口**：`StateMachine`、`SubtaskDecomposer`、`MultiAgentRouter`；数据类型 `TaskState`/`Subtask`/`Plan`/`VerifyResult`/`TaskHandoff`。
- **方法**：`transition()`、`state()`、`decompose()`、`verify()`、`match()`、`handoff()`。
- **错误码**：`DEADLOOP_DETECTED`、`INVALID_TRANSITION`、`NO_AGENT_MATCH`、`PROGRESS_NOT_MET`、`SUBTASK_VERIFY_FAILED`、`WAVE_FANOUT_LIMIT`。

### 19. permission — 权限审批

- **能力**：分级权限、人工审批流、沙箱隔离、沙箱颗粒度、审批动作协议。
- **契约**：只读放行、高危默认拦截、无法归类处理；审批通过放行、超时拒绝、可追溯；沙箱内执行与销毁、沙箱不可用降级、销毁回收资源；三域隔离、网络出站白名单、资源配额超限、文件系统受控访问；批准/拒绝/编辑重提/分级路由。
- **接口**：`PolicyEngine`、`ApprovalWorkflow`、`SandboxManager`；数据类型 `RiskLevel`/`Decision`/`ApprovalRequest`/`ApprovalResult`/`SandboxResult`。
- **方法**：`classify()`、`authorize()`、`create()`、`ask()`、`archive()`、`run()`、`destroy()`。
- **错误码**：`APPROVAL_EXPIRED`、`APPROVAL_REQUIRED`、`APPROVAL_TIMEOUT`、`PERMISSION_DENIED`、`SANDBOX_UNAVAILABLE`、`QUOTA_EXCEEDED`。

### 20. plugin-registry — 插件注册表

- **能力**：插件注册与生命周期、依赖解析、隔离与安全。
- **契约**：注册并校验、卸载干净、并发热插拔原子性、注册超时；依赖满足、循环依赖检测；能力边界限制、插件崩溃隔离。
- **接口**：`Plugin(Protocol)`、`EffectTracker`、`CoeffectResolver`；数据类型 `Effect`/`Bundle`/`Profile`/`Patch`。
- **方法**：`load()`、`unload()`、`check()`、`record()`、`rollback()`、`replay()`、`audit()`、`resolve()`、`register()`、`compose()`、`activate()`、`apply()`、`undo()`。
- **错误码**：`COEFFECT_MISSING`、`GENERATION_CONFLICT`、`INVALID_SCHEMA`、`NOT_ACTIVE`、`UNDO_FAILED`。

### 21. rag — RAG

- **能力**：本地向量库（sqlite-vec）、文档摄取分块、本地 Embedding、语义检索、生成融合。
- **契约**：嵌入式零服务存储；文档导入建索引、源变更增量更新、摄取/重建失败降级；本地推理无外部依赖、可经 llm-provider 切远端模型；top-k 相似度检索；检索上下文注入生成、无结果降级；与 CodeBase Engine 职责边界（文档/代码各归其位）。

### 22. skillhub — 技能市场

- **能力**：技能发现、多源路由健康回退、签名校验可信下载、发布审核流。
- **契约**：搜索市场技能、按源列目录；源不可达回退、源不存在报错；签名校验失败拒绝、下载默认 draft；发布进审核、通过才发布、驳回处理。
- **接口**：`SkillHubClient`、`SkillPublisher`、`TrustVerifier`；数据类型 `MarketSkill`/`MarketIndex`/`SourceHealth`。
- **方法**：`search()`、`download()`、`list()`、`route()`、`health()`、`put()`、`get()`、`locate()`、`publish()`、`review()`、`verify()`。
- **供给侧契约已兑现**（change 0105／ADR-0098）：CLI `skill publish` / `skill review` 已接线，目录 / 制品库 /
  版本提升均落盘（`$CORE_STATE_DIR/skillhub-{index,artifacts,versions}.json`）⇒ 发布 → 索引 → search/install
  闭环**跨进程**成立。**仍未接**：远端市场 fetcher（网络 + 凭据，凭证半）；消费侧缺省 fetcher 用**本地**市场制品库。
- **错误码**：`PUBLISH_REJECTED`、`SIGNATURE_INVALID`、`SKILL_NOT_ACTIVE`、`SOURCE_NOT_FOUND`、`SOURCE_UNHEALTHY`。

### 23. skills — 技能封装

- **能力**：原子技能库、版本管理灰度/A/B、技能路由。
- **契约**：注册校验、前置条件检查；灰度发布、A/B 中 B 退化自动回退；路由命中 Top-K、未命中沉淀。
- **接口**：`SkillLibrary`、`VersionManager`、`SkillRouter`、`SkillCrystallizer`；数据类型 `Skill`/`ABResult`/`SkillMatch`。
- **方法**：`register()`、`lookup()`、`list_by_domain()`、`check_preconditions()`、`promote()`、`ab_test()`、`select()`、`match()`、`crystallize()`、`dissolve()`。
- **错误码**：`INVALID_SKILL_SCHEMA`、`NO_SKILL_MATCH`、`PRECONDITION_FAILED`。

### 24. tool-use — 工具使用

- **能力**：工具定义注册、参数校验、coeffect 副作用契约、撤销与时间旅行回滚、超时与资源上限、异步调用。
- **契约**：schema 合法注册、非法拒绝；参数缺失拒绝；副作用声明校验、声明与行为不符告警；写类工具可撤销、时间旅行回滚；执行超时、资源上限；异步入口 + 同步薄壳等价 + 真并发。
- **接口**：`ToolProvider`、`SafetyGate`；数据类型 `ToolDef`/`ToolResult`/`ToolError`/`EffectId`/`GateDecision`。
- **方法**：`active_tools()`、`invoke()`、`ainvoke()`、`confirm()`。
- **错误码**：`COEFFECT_MISSING`、`GATE_DENIED`、`INVALID_ARGS`、`INVALID_TOOL_SCHEMA`、`IRREVERSIBLE_BLOCKED`、`TIMEOUT`、`UNDO_FAILED`。

### 25. ui — UI 界面（三模入口）

- **能力**：三模统一内核（CLI/Web/Desktop）、统一后端 API（FastAPI，HTTP+SSE）、LLM 可配置、多模态输入、实时语音输出、Web Client 分离。
- **契约**：三模复用同一内核与 LLM 配置，统一后端 API，CLI 也不绕过；LLM API Key 只配置一次、密钥安全存储；CLI 流式输出 + 折叠块；Web SSE 断线重连；Web/桌面体验一致；图像输入理解、语音转写、模态缺失降级；流式 TTS 播报、用户打断（barge-in）、语音上下文引用；Web 前端纯静态独立托管、前后端解耦升级、发布不要求后端重启。
- **接口**：`UIAPILayer`、`CLIBridge`、`WebBridge`、`DesktopBridge`。
- **方法**：`create_session()`、`run_loop()`、`get_memory()`、`compact()`、`list_tools()`、`invoke_tool()`、`get_llm_config()`、`set_llm_config()`、`connect()`、`serve()`、`start_sidecar()`。

### 26. pet-mode — 宠物模式（后台自治）

- **能力**：后台自治循环（任务派发→周期触发→偏好读写→反馈/惊喜→让行退避）、多宠物管理、pet.md 人格约束行为、宠物角色库、受限探索工具集、安全边界、主动异步通知、日常随机微任务。
- **契约**：三入口（`/pet` 斜杠、`pet` CLI argv、WebUI 自然语言）统一收口 `PetSession` 生命周期，避免第二真源；主循环 busy 时让行（复用 orchestration `SUSPENDED`）不抢锁；异常退避 `BACKOFF` 故障隔离不残留半运行态；每次唤醒复用 `Loop.run()` 同步薄壳逐次执行不常驻；偏好以 `MemoryEntry.source="user"` 落 L2 facts 不新造记忆层；侵入性微任务可配置关闭。
- **接口**：`PetSession`、`PetActivator`、`PetTask`；数据类型 `PetSessionState`/`PetTaskKind`。
- **方法**：`start()`、`wake()`、`suspend()`、`resume()`、`backoff()`、`terminate()`、`dispatch()`、`observe()`、`prefer()`、`report()`、`surprise()`、`activate_from_slash()`、`activate_from_cli()`、`activate_from_nl()`。
- **错误码**：`PET_ALREADY_ACTIVE`、`PET_NOT_ACTIVE`、`PET_BACKOFF`、`PET_YIELDING`、`PET_PREFERENCE_WRITE_FAILED`。
- **依赖**：`loop-interface`（`Loop.run`）、`ui-interface`（`UIAPILayer.list_tools/run_loop`）、`im-interface`（`IMGateway.on_message`）、`cli-ops-interface`（`CommandGroup`）、`memory-interface`（`MemoryEntry.source`）、`orchestration-interface`（`SUSPENDED`）。
- **需求**：R7 架构分层 / R8 多宠物 / R9 人格 / R10 角色库 / R11 探索工具集 / R12 安全边界 / R13 通知 / R14 微任务。
- **里程碑**：无独立里程碑，随 M5。

### 27. cli-ops — CLI 运维命令面

- **能力**：统一 CLI 命令集（六组：生命周期/状态/资产/连接/安全/网关）+ 启动参数映射（单一真源 `ConfigSpec` 驱动 CLI flag / env / config.yaml 三层一一对应）。
- **契约**：六组命令统一入口 `dispatch()` 路由；`--foo.bar=value ↔ config.foo.bar ↔ CORE_AGENT_FOO_BAR` 一一对应无第二真源；优先级链 CLI flag > env > config.yaml > 默认值。
- **接口**：`CommandGroup`、`CLICommandDispatcher`、`ParamMapper`。
- **方法**：`dispatch()`、`lifecycle()`、`status()`、`asset()`、`connection()`、`security()`、`gateway()`、`resolve()`、`generate_cli()`、`generate_env()`、`generate_yaml_schema()`。
- **错误码**：`UNKNOWN_COMMAND`、`INVALID_MAP_TO`。
- **依赖**：`configuration-interface`（`ConfigSpec`）、`plugin-registry-interface`（插件来源/安装生命周期）、`mcp-interface`（mcp 安装/移除生命周期）。
- **需求**：运维命令集 / 启动参数映射。
- **里程碑**：无独立里程碑（CLI 命令面契约随 Phase 2.5 回填）。

### 28. judgment — 决策模型接入（JEV System One）

- **能力**：choice（选项路由）/ score（评分筛选）/ noul（布尔判断）三类决策原语统一入口；经 JEV/TypeSafe `POST /v1/systemone` 结构化决策；置信度低于阈值回退主 LLM；每次决策轨迹落 observability。
- **契约**：三原语统一走 `DecisionRouter.decide()` 不散落生成式 prompt；答案按原语分形（noul→noul / choice→choice+probabilities+confidence / score→score+legend+probabilities+confidence）；confidence < 阈值 → 主 LLM 回退 + `fallback=True` + 轨迹标注；JEV 不可达/超时亦回退；未配置 judgment 段 → 决策能力关闭、主 LLM 兜底。
- **接口**：`DecisionRouter`、`JEVProvider`、`Compactor`、`Guardrail`；数据类型 `DecisionPrimitive`/`DecisionRequest`/`DecisionResult`/`DecisionTrace`。
- **方法**：`choose()`、`decide()`、`query()`、`score()`、`check()`。
- **错误码**：`JUDGMENT_PROVIDER_UNREACHABLE`、`JUDGMENT_SCHEMA_MISMATCH`、`JUDGMENT_LOW_CONFIDENCE`、`JUDGMENT_TIMEOUT`、`JUDGMENT_INVALID_PRIMITIVE`。
- **依赖**：`observability-interface`（决策轨迹落盘）、`configuration-interface`（`ConfigSpec`）、`llm-provider-interface`（主 LLM 回退兜底）。
- **需求**：决策原语路由 / JEV 提供方接入 / 置信度回退 / 决策审计。
- **里程碑**：M8 决策模型接入。
