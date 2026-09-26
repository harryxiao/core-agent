# Phase 0 — 底座与配置（plugin-registry / configuration / observability / core-profile）

> 里程碑：**M0 底座就绪**（roadmap §3）
> 位置：分层图 L0（core-profile 宪法分区）/ L5（plugin-registry / configuration / observability）
> 上游：无（首个 Phase，全系统地基）

---

## 1. 范围与定位

本 Phase 交付 4 个 capability，构成 core-agent 运行时底座，所有后续 Phase 的模块都建立在其上：

| Capability | 职责一句话 | 分层 |
|---|---|---|
| plugin-registry | 插件注册/卸载/生命周期 + effect 追踪 + coeffect 解析 | L5 底座 |
| configuration | config.yaml 单源 + env 覆盖 + keychain 密钥 | L5 底座 |
| observability | 日志/指标/链路追踪 + 遥测缓冲导出 + 告警 | L5 底座 |
| core-profile | 全局/项目两级 Core.md（宪法分区 + 人格分区） | L0 灵魂文件 |

**定位原则**：这四个模块是「纯机制、零业务」，不依赖任何 LLM/tool/memory 等能力层，只提供运行骨架。任何业务模块若要注册，必须走 plugin-registry 的 `Plugin` 协议。

---

## 2. 里程碑验收（M0）

以下清单全部勾选才算 M0 完成：

- [ ] 可注册/卸载一个最小 Plugin，卸载后无残留（进程内引用、定时器、文件句柄全部释放）
- [ ] 并发热插拔原子性：注册/卸载并发执行不产生半注册状态，`check()` 能探测到不一致
- [ ] 循环依赖检测生效：A→B→A 的依赖链被拒绝并报 `CIRCULAR_DEPENDENCY`
- [ ] config.yaml 单一收口生效；缺失 LLM 配置时**阻断启动**（拒绝进入主循环）
- [ ] 功能开关缺省关闭：未启用的模块完全不初始化（不 import 副作用、不注册）
- [ ] schema 校验通过才生效；非法配置半写状态可回滚（不残留坏配置）
- [ ] 遥测可观测：模型调用/工具调用/effect 三类事件可记录，敏感信息脱敏
- [ ] 单任务全链路可回溯（trace 起止 + replay），遥测故障不阻塞主循环
- [ ] 宪法 coeffect 注入链路打通：core-profile 宪法分区 → CoeffectResolver → 供上层模块取用

---

## 3. 依赖与前置

- **无上游 Phase**。本 Phase 是地基。
- 外部依赖约束（需在 `pyproject.toml` 声明，最小化引入）：
  - observability：`opentelemetry-api`（可选，导出走 Protocol 抽象，缺省 no-op 不阻塞）
  - 其余模块**零第三方运行时依赖**，仅标准库 + 类型标注

---

## 4. 首步任务

无（本 Phase 4 个 capability 的 spec/interface 均已齐全，无契约缺补、无重命名、无钩子解耦）。

**启动前核对**：以 `contracts_summary.md` 第 3 / 6 / 17 / 20 章为契约基线，与 `specs/` 下对应 spec.md + `03-interfaces/` 下对应 interface 逐一比对后再开工。

---

## 5. 实现顺序（模块级拓扑序）

严格按下述顺序实现，每完成一个模块立即过门禁（§7）再进下一个：

### 5.1 plugin-registry（最先，无内部依赖）

- 核心类/接口：
  - `Plugin(Protocol)`：插件统一协议（`activate()` / `apply()` / `undo()` 生命周期）
  - `CoeffectResolver`：coeffect 解析（供 core-profile 宪法注入使用）
  - `EffectTracker`：effect 追踪（`record()` / `rollback()` / `replay()` / `audit()`）
- 关键方法：`load()`、`unload()`、`check()`、`resolve()`、`register()`、`compose()`
- 错误码：`COEFFECT_MISSING`、`GENERATION_CONFLICT`、`INVALID_SCHEMA`、`NOT_ACTIVE`、`UNDO_FAILED`、`CIRCULAR_DEPENDENCY`
- 验收重点：卸载干净（无残留）、并发原子性、循环依赖检测、崩溃隔离（插件异常不拖垮宿主）

### 5.2 configuration（依赖 plugin-registry 的 `Plugin` 协议注册配置模块）

- 核心类/接口：`ConfigManager`
- 数据类型：`AppConfig` / `LLMConfig` / `IMConfig` / `ValidationResult`
- 关键方法：`load()`、`validate_schema()`、`resolve_secret()`、`is_enabled()`、`apply_change()`
- 验收重点：LLM 必选校验阻断启动、功能开关缺省关闭、密钥走 keychain（不落明文、日志脱敏）、schema 失败回滚

### 5.3 observability（依赖 plugin-registry 的 `EffectTracker` + configuration 的开关）

- 核心类/接口：`Tracer`、`TraceLogger`、`MetricsCollector`、`Exporter(Protocol)`、`TraceEvent`
- 关键方法：`log_model_io()`、`log_tool_call()`、`log_effect()`、`inc()`、`gauge()`、`snapshot()`、`start_trace()`、`end_trace()`、`replay()`、`emit()`
- 错误码：`EXPORT_FAILED`、`TELEMETRY_DEGRADED`
- 验收重点：脱敏、缓冲溢出兜底、导出重试与背压、OTel/Prometheus 协议、告警分级 + 风暴抑制、故障不阻塞主循环

### 5.4 core-profile（依赖 plugin-registry 的 `CoeffectResolver`）

- 核心类/接口：`CoreProfileEngine`、`GlobalProfileLoader`、`ProjectProfileLoader`、`SectionParser`、`Merger`、`Validator`
- 数据类型：`CoreProfile` / `AssembledProfile` / `Section`
- 关键方法：`load_global()`、`load_project()`、`assemble()`、`find_upwards()`、`parse()`、`merge()`、`validate()`
- 错误码：`PROFILE_MISSING`、`SECTION_INVALID`
- 验收重点：cwd 向上查找 + 项目覆盖全局、宪法分区注入 coeffect、人格分区落 L0、缺失静默降级、格式非法告警跳过

---

## 6. 契约对齐

以 `contracts_summary.md` 为唯一契约基线（本 Phase 对应第 3/6/17/20 章），逐条比对：

| Capability | contracts_summary.md 章节 | 关键方法签名（实现必须覆盖） |
|---|---|---|
| configuration | §3 | `load()`, `validate_schema()`, `resolve_secret()`, `is_enabled()`, `apply_change()` |
| core-profile | §6 | `load_global()`, `load_project()`, `assemble()`, `find_upwards()`, `parse()`, `merge()`, `validate()` |
| observability | §17 | `log_model_io()`, `log_tool_call()`, `log_effect()`, `inc()`, `gauge()`, `snapshot()`, `start_trace()`, `end_trace()`, `replay()`, `emit()` |
| plugin-registry | §20 | `load()`, `unload()`, `check()`, `record()`, `rollback()`, `replay()`, `audit()`, `resolve()`, `register()`, `compose()`, `activate()`, `apply()`, `undo()` |

**契约红线**（违反即返工）：
1. LLM 配置缺失必须阻断启动（不是警告）。
2. 功能开关缺省关闭，禁用模块零初始化。
3. 密钥绝不落明文，日志绝不泄露密钥。
4. 遥测故障绝不阻塞主循环（降级不中断）。

---

## 7. 门禁验收

全局四命令（见 `doc/05-development/development-standards.md`）全部通过：

```bash
ruff check src tests   # 格式（行宽 100、双引号）
ruff format --check
pyright                # 类型（strict，include=src）
pytest -q              # 单元 + 架构测试
```

本 Phase 专属校验（附加于全局门禁）：

- [ ] 架构测试：4 个模块不反向依赖能力层（llm-provider / tool-use / memory 等），可用 import-linter 或等价断言守住
- [ ] 插件崩溃隔离测试：注入一个抛异常插件，宿主进程与其余插件不受影响
- [ ] 并发注册/卸载压测：多线程热插拔 1000 次，无半注册状态、无残留
- [ ] 密钥脱敏测试：任何日志/遥测输出 grep 不到真实密钥
- [ ] 遥测降级测试：Exporter 挂掉时主循环照常推进

---

## 8. 提交规范

- **一个 Phase 一个 commit**：完成 4 模块 + 门禁全绿后单次提交。
- commit message 形如：`feat(phase0): plugin-registry/configuration/observability/core-profile 底座（M0）`
- 提交后回填 roadmap §3 的 M0 里程碑状态为「完成」，并同步更新 `README.md` Phase 0 行状态。
