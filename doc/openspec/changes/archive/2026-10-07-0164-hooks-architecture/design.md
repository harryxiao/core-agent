# 0164 · hooks 架构设计（设计稿）

> **本 change 不写实现代码。** 本文是**契约**：事件面、接缝映射、命令协议、失败处置、安全边界。
> 实现另立 change（见 §9「实现待办（下一个 change 的输入）」）。
> 规格落点为新建 capability `hooks`：`doc/openspec/specs/hooks/spec.md`。

---

## 1. 定位与边界

钩子是**操作者**（部署方 / 团队）在**不修改内核代码**的前提下，对内核生命周期事件挂载
「**观察**」或「**否决**」动作的**声明式扩展点**。

- **不是**插件（`plugin-registry`）：插件是**可逆、可装载、有 generation** 的能力单元；钩子是**外部进程或
  组合根回调**，不进插件注册表、不参与 coeffect 解析、**不可逆**。
- **不是**中间件本体（`constraints`）：既有 `middlewares` 是**动作前链**、由组合根**代码注入**；
  钩子是**声明式**的同层消费者 —— 它**消费**既有接缝，不取代它们。
- **不是**事件总线：本设计明示**不建**通用总线（P1「无特权核心」；先复用接缝，多播需求出现再议）。

## 2. 事件面（7 个事件，稳定 JSON 载荷）

| 事件 | 时机 | 可否决 | 载荷（稳定字段；**值**一律先脱敏） |
|---|---|---|---|
| `session.start` | 会话建立 | 否 | `session_id` / `mode` / `ts` |
| `session.end` | 会话收尾（进程退出或显式结束） | 否 | `session_id` / `mode` / `reason` / `ts` |
| `turn.before` | 一轮开始（输入已定、context 装配前） | **是**（阻断本轮） | `session_id` / `trace_id` / `turn_index` / `input`（脱敏后） |
| `turn.after` | 一轮收尾（**成功与失败都发**） | 否 | `session_id` / `trace_id` / `ok` / `steps`（动作与结果序列摘要） |
| `tool.before` | 动作执行前（**非终止**动作） | **是** | `tool_id` / `args_digest` / `decision`（`allow` \| `confirm`） |
| `tool.after` | 动作执行后（**非终止**动作） | 否 | `tool_id` / `ok` / `result_digest` / `duration_ms` |
| `memory.write` | 记忆落库（**单一写入咽喉** `MemoryStore.write`） | **否**（仅观察） | `layer` / `entry_id` / `kind` / `bytes` |

**契约要点**：

1. **终止动作不发钩子**（空 `tool_id`，即本轮回复）—— 与既有 `action_observers` 同口径
   （`loop/default.py:735`：`action.is_terminal` 直接返回）。
2. `*_digest` 是**摘要**（长度 + 哈希前缀），**不是**正文：参数/结果正文只对 `turn.before.input`
   开放（脱敏后），其余面只给摘要 —— 减少外部进程接触面。
3. `memory.write` **不可否决**：记忆是进化轨迹的载体（P5「记忆先行」），静默丢一次写入等于
   轨迹断点 ⇒ 只允许观察。写入失败仍由 store 自身的 fail-closed 与 `EffectTracker` 处理。
4. 载荷**逐条脱敏**后出进程边界：口令形态的值一律替换为 `<redacted>`（承 `core/memory/extract.py`
   的 `scrub_key_fact` 思路），**绝不**出现 `${VAR}` 的**解析结果**。

## 3. 接缝映射（**复用既有，不新建总线**）

| 事件 | 接缝 | 现状 | 实现落点 |
|---|---|---|---|
| `tool.before` | `middlewares`（动作前链，返回 `None` 即短路） | **既有**（`loop/default.py:723-733`，规格已收） | 组合根追加一个钩子中间件（**排在最外层**，先于 constraints） |
| `tool.after` | `action_observers`（结果侧观察者，仅通知） | **既有**（`loop/default.py:735-741`） | 组合根追加一个观察者 |
| `turn.after` | `turn_observer`（每轮收尾；成功失败都提交） | **既有**（`loop/default.py:380-385`） | 组合根在既有 `loop_turn` 闭包内**多播**到钩子 |
| `turn.before` | —— | **待新增** | loop 增一个与 `turn_observer` **对称**的注入形参（可否决），**不改** `middlewares`（那是**动作**面，不是轮面） |
| `session.start` / `session.end` | —— | **待新增** | 落**组合根**（会话生命周期是组合根职责；UI 层不持钩子） |
| `memory.write` | —— | **待新增** | `MemoryStore` 增一个**观察者** DI 形参（与既有 `summarizer` / `key_fact_extractor` **同构**），**不**在 store 内读配置 |

**裁决**：**不**引入事件总线。理由：① 现存的接缝已覆盖 3/7 个事件，且**规格已收口**；② 总线的收益
（多播、解耦）在**单一扩展消费者**（钩子执行器）的场景下是**净开销**（多一层间接、多一处生命周期）；
③ P1 要求核心无特权 —— 总线会成为「第二个分发中心」。若将来出现**多个**独立消费者，先改 ADR-0155，
再考虑引入。

## 4. 形态（两种，同一契约）

### 4.1 外部命令钩子（默认形态）

- **argv 列表、不经 shell**（承 ADR-0093 ④ sidecar 口径）：`command: ["/usr/local/bin/policy", "--strict"]`。
  **禁止**字符串形式（避免 shell 注入）。
- **单事件 stdin**：进程启动后，stdin 收**一个** JSON 对象（信封：`{"event": …, "payload": {…}, "ts": …}`），
  stdin 随即关闭（EOF）⇒ 钩子无需长驻、无需协议握手。
- **退出码语义**：
  - `before` 类（`tool.before` / `turn.before`）：`0` = **放行**；**非 0 = 阻断**（stderr 首行作为
    拒绝理由进 trace，**不**进对话正文）。
  - `after` 类（`session.*` / `turn.after` / `tool.after` / `memory.write`）：退出码**仅留痕**，
    不改变本轮结局。
- **超时**：`timeout_s`（逐条可配，缺省 5s，**硬上限 60s** —— 配置超上限按上限截断并 `warn`）。
- **输出**：stdout / stderr 各**有界截断**（4 KiB），**不进日志 / 记忆 / 对话**，只进 trace 的
  digest + 退出码 + 时长。

### 4.2 内置回调钩子（代码注入）

- 与既有接缝**同构**的函数注入（`Callable[[HookEvent], bool]`），只在**组合根**装配 ——
  供内部消费者（如团队自建的策略）使用，不经子进程、无序列化开销。
- **同一失败语义**（§5）：内置回调抛错 ≡ 外部命令非 0 / 超时。

## 5. 失败处置（fail-closed 默认）

| 场景 | `before` 类 | `after` 类 |
|---|---|---|
| 退出码非 0 | **阻断**（默认） | 仅留痕 |
| 超时 | 按 `on_error`（默认 **`block`**） | 仅留痕 |
| 无法执行（`OSError`，命令不存在 / 不可执行） | 按 `on_error`（默认 **`block`**） | 仅留痕 |
| 回调抛错 | 按 `on_error`（默认 **`block`**） | 仅留痕 |

- `on_error` ∈ `block`（默认）/ `allow` / `warn`：
  - `block`：**fail-closed** —— 阻断本轮 / 该动作（诊断的默认姿态与 permission 的 fail-closed 一致）。
  - `allow`：放行但留痕 `hook_error`（**显式**选择「钩子坏了不挡路」）。
  - `warn`：放行、留痕、并在时间线/日志给一次**可见**告警。
- **after 类恒不改变结局**（与既有观察者链同语义：观察者抛错降级为遥测）。

## 6. 声明面（`config.yaml` + ConfigSpec 单一真源）

```yaml
hooks:
  enabled: true          # 标量 ⇒ ConfigSpec 三面
  timeout_s: 5           # 标量 ⇒ ConfigSpec 三面（硬上限 60）
  on_error: block        # 标量 ⇒ ConfigSpec 三面
  entries:               # 清单 ⇒ 只落 config.yaml 结构化段（见下）
    - event: tool.before
      command: ["/usr/local/bin/policy", "--strict"]
      timeout_s: 3
      on_error: block
      match: { tool_id: "code_run" }   # 可选收窄（缺省 = 该事件全量）
```

- **标量三面**（`hooks.enabled` / `hooks.timeout_s` / `hooks.on_error`）经
  `configuration/manager.py` 的 **`_CONFIG_SPECS`** 声明 ⇒ 自动获得 `--hooks-enabled` /
  `--hooks.timeout-s` / `--hooks.on-error` 与 `CORE_HOOKS_*` 环境变量，优先级链
  **CLI flag > env > config.yaml > 默认值**（`manager.py:1140`）。
- **清单只落 yaml**：`ConfigSpec` 是**键 → 标量**的映射，**列表不入**（与
  `permission.sandbox.host_allowlist` 用逗号串、`mcp` 端点另存 `mcp.json` 同源的取舍）
  ⇒ `hooks.entries` 是**结构化段**，只从 `config.yaml` 读，**不**提供 flag / env 形态。
- **缺省关闭**：`hooks.enabled` 缺省 `false`（与模块级 feature flag「未显式开启不加载」一致）。

## 7. 安全边界（红线）

1. **子进程环境白名单**：显式列举（`PATH` / `HOME` / `LANG` / `TZ` …），**不继承**父进程
   环境变量 —— 密钥只经 `CoeffectResolver` **引用**，**绝不**因继承而进入钩子进程。
2. **载荷脱敏**：出进程边界的每一条载荷先逐条脱敏（§2.4）。
3. **输出不回灌**：钩子的 stdout / stderr **不进**日志 / 记忆 / 对话（只有 trace 摘要）。
4. **不可逆边界（显式例外）**：钩子副作用**不纳入** `EffectTracker`（外部命令不可撤销）⇒
   规格**明示**此例外，并**建议**钩子默认只读；写操作型钩子由操作者自担（文档与 ADR 写明）。
5. **审计留痕**：每次调用落 trace，`kind="hook"`，字段 `event` / `command`（**basename**）/
   `exit` / `duration_ms` / `blocked_by`（可否决类被拒时记钩子标识）；**不留**命令的完整 argv
   （可能含路径敏感信息）与任何输出正文。

## 8. 与既有裁决的关系

- **承** `loop` 规格「横切中间件插入」：`tool.before` / `tool.after` **即**该二接缝的消费者，
  **不新增** loop 内的横切机制。
- **承** ADR-0093 ④：argv 列表、不经 shell —— 与 sidecar 拉起的同一条口径。
- **承** ADR-0147（`scrub_key_fact`）：脱敏思路复用，**不**另写一套。
- **例外于** P2「一切副作用可逆」：钩子副作用不可逆 ⇒ 在 ADR-0155 与规格里**显式**记为唯一例外。

## 9. 实现待办（下一个 change 的输入）

1. 新包 `src/core/hooks/`：事件模型（`HookEvent` / 载荷脱敏）+ 执行器（argv 子进程 + 内置回调、
   超时、有界输出、白名单环境）+ 注册表（按事件与 `match` 收窄）+ 与配置面接线。
2. `loop` 侧：`turn.before` 注入形参（与 `turn_observer` 对称，可否决）。
3. `memory` 侧：`MemoryStore` 增写入观察者 DI 形参（与 `summarizer` / `key_fact_extractor` 同构）。
4. 组合根 `runtime.py`：装配 `session.start` / `session.end` 与既有三接缝的多播。
5. 配置面：`_CONFIG_SPECS` 增三个标量 spec + `hooks.entries` 结构化段解析（fail-closed 校验）。
6. 测试面：脱敏红线（哨兵值不入载荷）、before 阻断、after 只留痕、超时按 `on_error`、
   环境白名单（密钥不入子进程）、配置三层优先级。
7. 文档面：`doc/03-interfaces/hooks-interface.md`（若实现暴露对外契约）+ `test-cases.md` 追踪号。

---

## 已知局限（写进 ADR-0155）

1. **未实现** —— 本 change 只出契约（E101 挂账至实现 change）。
2. **清单不入三面** —— `hooks.entries` 只有 yaml 形态（ConfigSpec 是标量映射的既有取舍）。
3. **无优先级 / 多播语义** —— 同事件多钩子按**声明序**执行，**任一** before 钩子阻断即终局
   （不设权重、不做「否决覆盖」）。
4. **载荷脱敏 ⇒ 检查不了密钥本身** —— 钩子看不到密钥形态的原始值（若某策略需要，属另一件事，
   须走 permission 面而非钩子面）。
5. **不可逆** —— 钩子副作用不入 `EffectTracker`（唯一显式例外）。
6. **不覆盖 Web / Desktop** —— 声明面属配置面，跨端一致另议。
