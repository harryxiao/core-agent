# Phase 1 — 能力可调（llm-provider / tool-use / memory）

> 里程碑：**M1 能力可调**
> 位置：分层图 L4 能力层（LLM 归一化 / 工具使用 / 记忆系统）
> 上游：Phase 0（M0 底座：plugin-registry / configuration / observability）

---

## 1. 范围与定位

本 Phase 交付 3 个能力，是 agent「能说、能做事、能记住」的第一层实现：

| Capability | 职责一句话 | 分层 |
|---|---|---|
| llm-provider | 统一 `LLMProvider` 抽象，任意三方模型零改动接入 | L4 能力层 |
| tool-use | 工具注册/参数校验/coeffect 副作用契约/撤销回滚 | L4 能力层 |
| memory | L0-L4 五层记忆 + 温度分层检索 + 结晶/溶解/压实 | L4 能力层 |

**定位原则**：三个模块全部挂载在 Phase 0 底座上——llm-provider 通过 plugin-registry 注册 provider，API Key/URL 从 configuration 读取；tool-use 通过 plugin-registry 的 `CoeffectResolver` 校验副作用声明；memory 的 `MemoryStore` 实现 `Plugin` 协议，写入留痕走 observability。

---

## 2. 里程碑验收（M1）

以下清单全部勾选才算 M1 完成：

- [ ] 真实 LLM 调用打通：配置 API Key + URL 后即可调用任意三方模型，调用方零改动
- [ ] 错误归一化：底层异常统一归一到 `LLMError` 层级，不向调用方泄漏三方原始异常
- [ ] 异步入口 + 同步薄壳等价：`acompletion`/`astream`/`aembedding` 与同步版结果等价，且真并发
- [ ] 可靠性：失败自动重试、超时控制、服务降级、连接复用、流式断流处理
- [ ] 工具 invoke 可用：`active_tools()` 列出、`invoke()`/`ainvoke()` 执行、`confirm()` 审批
- [ ] 参数校验：非法 schema 拒绝注册，参数缺失拒绝调用并报 `INVALID_ARGS`
- [ ] 副作用契约：coeffect 声明校验 + 声明/行为不符告警；写类工具可撤销、时间旅行回滚
- [ ] 五层记忆读写：L0-L4 分层写入 + 跨层检索，热数据即时返回、冷数据按需加载
- [ ] 结晶/溶解/压实：`crystallize()`/`dissolve()`/`migrate()` 全链路，压实失败降级、并发压实一致

---

## 3. 依赖与前置

- **上游**：Phase 0 全部四个模块（plugin-registry / configuration / observability / core-profile）。
- 外部依赖：
  - llm-provider：`litellm`（默认实现），provider 抽象为 ABC 可替换
  - memory：存储后端走 `MemoryBackend(Protocol)`，默认内置实现即可，不强制三方向量库

---

## 4. 首步任务

无（三个 capability 的 spec/interface 均已齐全，无契约缺补、无重命名）。

**启动前核对**：以 `contracts_summary.md` 第 13 / 16 / 24 章为契约基线，与 `specs/` 下对应 spec.md + `03-interfaces/` 下对应 interface 逐一比对后再开工。

---

## 5. 实现顺序（模块级拓扑序）

### 5.1 llm-provider（最先，依赖 plugin-registry + configuration）

- 核心类/接口：`LLMProvider(ABC)`、`LiteLLMProvider`、`LLMProviderRegistry`、`LLMError` 层级
- 数据类型：`Message` / `LLMRequest` / `TokenUsage` / `LLMResponse`
- 关键方法：`completion()`、`stream()`、`embedding()`、`acompletion()`、`astream()`、`aembedding()`、`register()`、`resolve()`、`default()`
- 验收重点：API Key/URL 从 configuration 读（不硬编码）、调用留痕（走 observability）、错误归一化、重试/超时/降级/连接复用/断流

### 5.2 tool-use（依赖 plugin-registry 的 `CoeffectResolver`）

- 核心类/接口：`ToolProvider`、`SafetyGate`
- 数据类型：`ToolDef` / `ToolResult` / `ToolError`
- 关键方法：`active_tools()`、`invoke()`、`ainvoke()`、`confirm()`
- 错误码：`COEFFECT_MISSING`、`GATE_DENIED`、`INVALID_ARGS`、`IRREVERSIBLE_BLOCKED`、`TIMEOUT`、`UNDO_FAILED`
- 验收重点：schema 合法注册、参数缺失拒绝、副作用声明校验、写类工具撤销/回滚、超时与资源上限、异步真并发

### 5.3 memory（依赖 plugin-registry + llm-provider 的 `embedding()`）

- 核心类/接口：`MemoryStore(Plugin)`、`Crystallizer`、`MemoryBackend(Protocol)`、`MemoryEntry`
- 关键方法：`read()`、`write()`、`migrate()`、`index()`、`audit()`、`crystallize()`、`dissolve()`、`get()`、`put()`、`search()`、`list_index()`、`delete()`
- 验收重点：分层写入 + 跨层检索、温度分层（热即时/冷按需）、检索失败降级、无行动不写入、索引最小化、压实失败降级、并发压实一致、人格分区写入 L0

---

## 6. 契约对齐

以 `contracts_summary.md` 为唯一契约基线（本 Phase 对应第 13/16/24 章）：

| Capability | contracts_summary.md 章节 | 关键方法签名（实现必须覆盖） |
|---|---|---|
| llm-provider | §13 | `completion()`, `stream()`, `embedding()`, `acompletion()`, `astream()`, `aembedding()`, `register()`, `resolve()`, `default()` |
| memory | §16 | `read()`, `write()`, `migrate()`, `index()`, `audit()`, `crystallize()`, `dissolve()`, `get()`, `put()`, `search()`, `list_index()`, `delete()` |
| tool-use | §24 | `active_tools()`, `invoke()`, `ainvoke()`, `confirm()` |

**契约红线**（违反即返工）：
1. 三方异常不得向调用方泄漏，必须归一到 `LLMError` 层级。
2. 参数缺失必须拒绝调用（`INVALID_ARGS`），不得带缺省继续执行。
3. 写类工具无 `undo` 实现不得执行（`IRREVERSIBLE_BLOCKED`）。
4. memory 无行动不写入（被动读取不得产生写）。
5. 异步与同步结果必须等价，不得「假并发」（异步内串行阻塞）。

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

- [ ] 架构测试：三模块不得反向依赖 Phase 3+ 的 loop/skills/orchestration
- [ ] 异步等价测试：`acompletion` 与 `completion` 对同一请求结果一致；并发压测证明真并发（耗时 < 串行）
- [ ] 错误归一化测试：模拟底层三方异常，断言抛出的均为 `LLMError` 子类
- [ ] 撤销回滚测试：执行写类工具后 `undo`，断言副作用被完全回滚
- [ ] memory 分层测试：热数据即时返回、冷数据按需加载、检索失败降级

---

## 8. 提交规范

- **一个 Phase 一个 commit**：3 模块 + 门禁全绿后单次提交。
- commit message 形如：`feat(phase1): llm-provider/tool-use/memory 能力可调（M1）`
- 提交后更新 `README.md` §2 总览表 Phase 1 行状态列为「完成」。
