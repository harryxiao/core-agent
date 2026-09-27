# Phase 1 契约基线核对 — §13 / §16 / §24 逐条签名对照表

> 只读核对产物（M1「能力可调」启动前最后一环），作为 claude code 实现清单。
> **状态（2026-09-26）**：§13/§16/§24 三处契约不一致点已由 Phase 1 实现收敛（五红线对抗 39/39 PASS），本对照表归档为历史记录，不再作为开放实现清单。
> 源三件套：
> - 速查表：`contracts_summary.md`（§13 / §16 / §24）
> - 行为契约：`doc/openspec/specs/llm-provider/spec.md`（7 Requirement）、`tool-use/spec.md`（6）、`memory/spec.md`（6）
> - 签名契约：`doc/openspec/03-interfaces/*.md`
> 生成：2026-09-26（GA 只读核对，未改任何源码）

---

## 0. 实现拓扑与门禁总纲

- **拓扑序**：`llm-provider` → `tool-use` → `memory`（llm 无依赖先建；tool-use 复用错误归一化与异步约定；memory 复用 plugin/错误/异步约定）。
- **M1 门禁专属锚点**（Phase 1 完成后按 `verify_sop` 对抗探测，勿只信 claude code 自测）：
  1. **架构测试禁反向依赖**：memory/tool-use 不得被 llm-provider 反向 import；只允许单向依赖。
  2. **异步等价**：`a*` 入口与同步 `*` 薄壳结果一致、非阻塞、真并发。
  3. **错误归一化**：底层供应商/tool 异常不得泄漏原始结构，统一为领域异常。
  4. **撤销回滚**：写类工具逆序撤销、时间旅行回滚到检查点。
  5. **memory 分层**：写入落对应层 + L1 索引最小；跨层检索按热度路由。

---

## 1. §13 llm-provider — LLM 归一化（7 Requirement）

| # | Requirement（SHALL） | 场景 | 接口签名（interface.md） | 速查表 §13 | 门禁锚点 |
|---|---|---|---|---|---|
| 1 | LLMProvider 抽象接口（completion/stream/embedding 三入口 + 统一请求/响应模型，内核只依赖接口） | 统一接口调用 | `LLMProvider(ABC)`：`completion()` `stream()` `embedding()` `acompletion()` `astream()` `aembedding()`；数据模型 `Message`/`LLMRequest`/`TokenUsage`/`LLMResponse`/`Embedding`/`LLMChunk` | ✅ 方法 9 条 | 内核 loop 只 import 接口，不感知供应商 |
| 2 | LiteLLM 默认实现与配置归一化（任意三方 API Key/URL 自动路由） | 任意三方模型接入 | `LiteLLMProvider`（委托 litellm，API Key/URL 配置即路由） | ✅ 能力行 | 无 litellm 硬编码泄漏到内核 |
| 3 | 依赖注入可替换（替换 LiteLLM/自研，调用方零改动） | 替换底层实现 | `LLMProviderRegistry`：`register()` `resolve()` `default()` | ✅ 方法行 | 换 Provider 不改内核/调用方 |
| 4 | 错误归一化（超时/限流/鉴权/网络 → 领域异常） | 底层异常归一 | `LLMError` 层级：基类 + `Timeout`/`RateLimited`/`Auth`/`Network`/`UnknownProvider` | ⚠️ 速查表 §13 无错误码行；总览表记「—」 | 上层只处理一类语义 |
| 5 | 模型调用审计（标注 provider/model/结果，复用 observability） | 调用留痕 | 横切（无专属签名，实现在 `completion`/`stream` 内） | ✅ 能力/契约行 | 每次调用可审计 |
| 6 | 模型调用可靠性（retry 指数退避 / timeout / degrade 切换备用 / keep-alive 连接复用 / 流式断流可恢复） | 可靠性行为 | 横切（无专属签名，内嵌在调用路径） | ✅ 契约行 | 断流/超时可恢复，不拖垮 loop |
| 7 | 异步调用接口（异步为主、同步薄壳、真并发） | 异步非阻塞 / 薄壳等价 / 真并发 | `acompletion()` `astream()` `aembedding()` + 同步薄壳 | ✅ 方法行 | 异步等价 + 真并发 |

**§13 契约不一致点**：速查表 §13 明细「无错误码行」且总览表错误码列记「—」，但 interface.md 已定义 `LLMError` 六类层级 → **速查表遗漏**（见 §4）。

---

## 2. §24 tool-use — 工具使用（6 Requirement）

| # | Requirement（SHALL） | 场景 | 接口签名（interface.md） | 速查表 §24 | 门禁锚点 |
|---|---|---|---|---|---|
| 1 | 工具定义与注册（schema 定义 + 启动校验，非法拒绝） | schema 合法注册 / schema 非法拒绝 | `ToolProvider.active_tools()`（+注册入口）；数据类型 `ToolDef`/`ToolResult`/`ToolError` | ✅ 能力/契约行 | ⚠️ 非法拒绝返回码三方冲突（见 §4） |
| 2 | 参数校验（缺参/错型直接拒绝） | 参数缺失拒绝 | `invoke()` 调用前按 schema 校验 | ✅ 契约行 | 返回 `INVALID_ARGS` |
| 3 | coeffect 副作用契约（read-only/write/secret/external，权限引擎校验） | 副作用校验 / 声明与行为不符告警 | `SafetyGate` + 数据类型 `EffectId`/`GateDecision` | ✅ 能力行；错误码 `COEFFECT_MISSING`/`GATE_DENIED` | 声明与行为不符必须告警 |
| 4 | 撤销与时间旅行回滚（写类工具撤销函数 + 时间旅行） | 写类工具撤销 / 时间旅行回滚 | 写类工具注册撤销函数；错误码 `IRREVERSIBLE_BLOCKED`/`UNDO_FAILED` | ✅ 契约行 | 逆序撤销、状态恢复到检查点 |
| 5 | 超时与资源上限（异常不拖垮主循环） | 执行超时 / 资源上限 | `invoke()` 执行路径内置超时/资源限制；错误码 `TIMEOUT` | ✅ 契约行 | 超时/超限不拖垮 loop |
| 6 | 异步调用（异步为主、同步薄壳、真并发） | 异步非阻塞 / 薄壳等价 / 真并发 | `ainvoke()` + 同步薄壳 | ✅ 方法行 | 异步等价 + 真并发 |

**§24 契约不一致点**：spec.md L19「schema 非法拒绝 → 返回 `INVALID_TOOL_SCHEMA`」，但 interface.md §5 错误码表与速查表 §24 均只有 `INVALID_ARGS`，且 plugin-registry 用 `INVALID_SCHEMA` → **三名字并存**（见 §4）。

---

## 3. §16 memory — 分层记忆（6 Requirement）

| # | Requirement（SHALL） | 场景 | 接口签名（interface.md） | 速查表 §16 | 门禁锚点 |
|---|---|---|---|---|---|
| 1 | 分层记忆模型（L0-L4，层间轻量索引） | 分层写入 / L1 索引命中路由 | `MemoryStore(Plugin)`：`read()` `write()` `migrate()` `index()`；数据类型 `Layer`/`IndexEntry` | ✅ 能力/契约行；方法行 | 写入落对应层 + L1 索引最小 |
| 2 | 温度分层检索（热/温/冷三档） | 热数据即时返回 / 冷数据按需加载 / 检索失败降级 | `MemoryStore.search()` `get()` | ✅ 契约行 | 热区无磁盘 IO、冷区异步加载、失败降级不阻断 |
| 3 | 无行动不记忆（只沉淀行动与结果，拒绝空想） | 无行动不写入 | `write()` 前置校验（无行动结果证据则拒绝） | ✅ 契约行 | 未经验证主张写入被拒 |
| 4 | 记忆压实（合并重复、归档过期、L1 索引最小） | 索引最小化 / 压实失败降级 | `Crystallizer.crystallize()` + `list_index()` `delete()` `audit()` | ✅ 能力/方法行 | 压实失败保留原始条目、下次重试 |
| 5 | 并发压实一致性（加锁/事务） | 并发压实一致 | 加锁/事务（`MemoryStore` 内） | ✅ 契约行 | 并发压实不丢条目 |
| 6 | Core Profile 人格注入（人格分区写 L0） | 人格分区写入 L0 | `MemoryBackend(Protocol)` 人格分区写 L0 | ✅ 能力/契约行 | 人格写入 L0 分区 |

**§16 契约不一致点**：速查表 §16 数据类型仅 `MemoryEntry`，缺 `Layer`/`IndexEntry` → **速查表遗漏**（minor，见 §4）。

---

## 4. 契约不一致点（实现前需 claude code 确认/拍板）

| # | 冲突 | 证据 | 建议 |
|---|---|---|---|
| 1 | **tool-use 错误码三方命名冲突** | spec.md L19：`INVALID_TOOL_SCHEMA`；tool-use interface §5 错误码表 & 速查表 §24：`INVALID_ARGS`；plugin-registry：`INVALID_SCHEMA` | 统一为 `INVALID_TOOL_SCHEMA`（语义最准），同步改 interface.md + 速查表；`INVALID_ARGS` 保留给参数校验（错型/缺参） |
| 2 | **llm-provider 错误码速查表遗漏** | interface.md §5 已定义 `LLMError` 六类层级（Timeout/RateLimited/Auth/Network/UnknownProvider+基类），但速查表 §13 无错误码行、总览表记「—」 | 在速查表 §13 补错误码行 + 总览表改「—」为「LLMError 六类层级」 |
| 3 | **速查表数据类型遗漏（minor）** | §13 缺 `Embedding`/`LLMChunk`；§16 缺 `Layer`/`IndexEntry`；§24 缺 `EffectId`/`GateDecision` | 补全速查表数据类型行（以 interface.md 为准） |

> 以上 3 处不阻塞编码（interface.md 与 spec.md 已一致定义了行为与签名），但需在 M1 完成前由 claude code 回填速查表/错误码命名，避免后续 Phase 引用错名。

---

## 5. Phase 1 验收锚点（完成后按 verify_sop 独立探测）

- **必须运行 + 工具证据**：四件套门禁（pytest / pyright / ruff / format）+ 独立对抗脚本，不以 claude code 自测为证据。
- **对抗探测清单**：
  1. 反向依赖：`import` 图断言 memory/tool-use 不被 llm-provider 反向引用。
  2. 异步等价：`acompletion`/`ainvoke`/`a*` 与同步薄壳同输入同输出；真并发（并发调用不串行阻塞）。
  3. 错误归一化：构造 litellm 超时/限流/鉴权 → 断言抛出 `LLMError` 子类，非供应商原始异常；tool 超时 → `TIMEOUT`。
  4. 撤销回滚：写类工具执行后触发回滚 → 状态恢复到检查点；不可逆工具 → `IRREVERSIBLE_BLOCKED`。
  5. memory 分层：写入 L0/L2/L4 → 落对层；L1 索引最小；冷数据异步加载、失败降级不阻断主流程。
  6. 错误码命名：验证 §4 冲突 #1 已拍板收敛（单一 `INVALID_TOOL_SCHEMA` 或等效）。
- **一个 Phase 一个 commit**；M1 完成后回填 `roadmap` §3 进度。
