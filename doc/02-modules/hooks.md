# 模块设计：钩子（Hooks）

> 对应规格：`doc/openspec/specs/hooks/spec.md` ｜ 决策：`doc/01-architecture/adr.md` ADR-0155
> 设计稿：`doc/openspec/changes/archive/2026-10-07-0164-hooks-architecture/design.md`
> 定位：**横切扩展点**，让操作者在**不改内核代码**的前提下，对内核生命周期事件挂载「观察」或「否决」。
> **状态：已实现**（change `0269` / ADR-0259 / 台账 E205；契约来源 ADR-0155）。

---

## 1. 模块定位

内核已有若干横切接缝（`middlewares` / `action_observers` / `turn_observer` / `trace_observer` /
`cold_path` / `Approver`），但它们**全部由组合根代码注入** —— 部署方要挂一个策略就得改 Python 代码、
重打包。钩子把这条路径**声明化**：`config.yaml` 里写清楚「在什么事件上跑什么命令」，内核负责
投递事件、解释退出码、按失败策略处置。

**边界**（三条，避免与邻居混淆）：

| 邻居 | 区别 |
|---|---|
| `plugin-registry` | 插件是**可逆、可装载、有 generation** 的能力单元，进注册表、参与 coeffect 解析；钩子是**外部进程或组合根回调**，不进注册表、**不可逆** |
| `constraints`（中间件） | 既有 `middlewares` 是**动作前链**本体；钩子是**同层消费者** —— 它**用**接缝，不取代它们 |
| 事件总线 | **不建**（ADR-0155 决策①）：单一消费者场景下总线是净开销，且会成第二个分发中心（违 P1） |

---

## 2. 事件面

| 事件 | 时机 | 可否决 | 载荷（**值先脱敏**） |
|---|---|---|---|
| `session.start` | 会话建立 | 否 | `session_id` / `mode` / `ts` |
| `session.end` | 会话收尾 | 否 | `session_id` / `mode` / `reason` / `ts` |
| `turn.before` | 一轮开始（context 装配前） | **是** | `session_id` / `trace_id` / `turn_index` / `input` |
| `turn.after` | 一轮收尾（成功失败都发） | 否 | `session_id` / `trace_id` / `ok` / `steps` |
| `tool.before` | 非终止动作执行前 | **是** | `tool_id` / `args_digest` / `decision` |
| `tool.after` | 非终止动作执行后 | 否 | `tool_id` / `ok` / `result_digest` / `duration_ms` |
| `memory.write` | 记忆落库（`MemoryStore.write`） | **否** | `layer` / `entry_id` / `kind` / `bytes` |

三条硬口径：① **终止动作不发** `tool.*`（与 `action_observers` 同）；② `tool.*` 只给**摘要**
（长度 + 哈希前缀），不给正文；③ `memory.write` **不可否决**（静默丢写入 = 进化轨迹断点）。

---

## 3. 接缝映射（复用既有，缺者新增）

| 事件 | 接缝 | 现状 |
|---|---|---|
| `tool.before` | `middlewares`（`loop/default.py`） | **既有**（`loop` 规格已收口） |
| `tool.after` | `action_observers` | **既有** |
| `turn.after` | `turn_after` 注入形参（轮尾、**封 trace 前**） | **已实现**（change 0269） |
| `turn.before` | `turn_before` 注入形参 | **已实现**（change 0269；返回 `False` ⇒ 本轮拒绝） |
| `session.start` / `session.end` | 组合根适配器 + `atexit` | **已实现**（change 0269；首轮幂等） |
| `memory.write` | `MemoryStore(write_observer=...)` | **已实现**（change 0269；同步、异常吞掉） |

---

## 4. 执行形态与协议

**外部命令**（默认形态）：argv 列表、**不经 shell**（承 ADR-0093 ④）；stdin 收**一个** JSON 信封
（`{"event": …, "payload": {…}, "ts": …}`）后即 EOF；`timeout_s` 缺省 5s、**硬上限 60s**；
stdout / stderr 各**截断**（4 KiB）且**不进**日志 / 记忆 / 对话。

**退出码**：`before` 类 `0`=放行、**非 0=阻断**（stderr 首行作拒绝理由进 trace，不进对话正文）；
`after` 类**仅留痕**。

**内置回调**：组合根注入的 `Callable[[HookEvent], bool]`，**同一失败语义**（抛错 ≡ 非 0 / 超时）。

---

## 5. 失败矩阵

| 情形 | `before` 类 | `after` 类 |
|---|---|---|
| 退出码非 0 | 阻断（默认） | 仅留痕 |
| 超时 | 按 `on_error`（默认 `block`） | 仅留痕 |
| 无法执行（`OSError`） | 按 `on_error`（默认 `block`） | 仅留痕 |
| 回调抛错 | 按 `on_error`（默认 `block`） | 仅留痕 |

`on_error` ∈ `block`（**缺省**，fail-closed）/ `allow`（放行并留痕 `hook_error`）/ `warn`（放行 + 可见告警）。

---

## 6. 声明面

```yaml
hooks:
  enabled: true          # 标量 ⇒ ConfigSpec 三面（--hooks-enabled / CORE_HOOKS_ENABLED）
  timeout_s: 5           # 标量 ⇒ 三面（硬上限 60）
  on_error: block        # 标量 ⇒ 三面
  entries:               # 清单 ⇒ 只落 config.yaml 结构化段（无 flag / env 形态）
    - event: tool.before
      command: ["/usr/local/bin/policy", "--strict"]
      timeout_s: 3
      on_error: block
      match: { tool_id: "code_run" }   # 可选收窄；缺省 = 该事件全量
```

优先级链（标量）＝ **CLI flag > env > `config.yaml` > 默认值**（`configuration/manager.py:1140`）。
`enabled` 缺省**关闭**。**清单不入三面**的理由：`ConfigSpec` 是键 → 标量的映射，列表不入
（与 `host_allowlist` 用逗号串、mcp 端点另存 `mcp.json` 同源的既有取舍）。

---

## 7. 安全边界

1. **环境白名单**：子进程以显式白名单（`PATH` / `HOME` / `LANG` / `TZ` …）启动，**不继承**父进程
   环境变量 —— 密钥只经 `CoeffectResolver` **引用**，绝不因继承进入钩子进程。
2. **载荷脱敏**：出进程边界前逐条脱敏（承 `core/memory/extract.py::scrub_key_fact` 思路），
   口令形态 → `<redacted>`，**绝不**出现 `${VAR}` 的解析结果。
3. **输出不回灌**：钩子 stdout / stderr 不进日志 / 记忆 / 对话。
4. **不可逆（显式例外）**：钩子副作用**不纳入** `EffectTracker` —— 系统对「一切副作用可逆」的
   **唯一**例外；规格**建议**默认只读，写型钩子由操作者自担。
5. **审计**：每次调用落 trace `kind="hook"`（`event` / 命令 **basename** / 退出码 / 时长 / `blocked_by`），
   **不留**完整 argv 与输出正文。

---

## 8. 实现落点（change 0269）

| 文件 | 职责 |
|---|---|
| `src/core/hooks/model.py` | 事件词表 / `HookEvent` / `HookEntry`（`match` 收窄）/ `digest` / `redact_payload` |
| `src/core/hooks/executor.py` | argv 子进程（白名单 env、超时、输出丢弃）+ 内置回调 → `HookOutcome` |
| `src/core/hooks/manager.py` | 按事件 + `match` 派发、`on_error` 处置、`kind="hook"` trace、`entries_from_config`、`session.*` 幂等与 `atexit` |
| `src/core/loop/default.py` | `turn_before` / `turn_after` 注入点；中间件与观察者可等待（同步实现逐字等价）；`current_trace_id`；`ActionResult.duration_ms` |
| `src/core/memory/store.py` | `write_observer`：落库后同步通知，异常吞掉 |
| `src/core/runtime.py` | `hooks.enabled` 才构造 `HookManager`；四个 loop（主 / `_agent_loop` / `_beast_loop` / pet）接同一组适配器；登记密钥明文 |
| `src/core/configuration/manager.py` | 三个标量 `ConfigSpec`；`hooks_entries()`；YAML 块序列 / flow 列表支持（round-trip） |

**装配顺序**：`constraints_chain.middleware` 在钩子中间件**之前** —— 约束先判（预算/熔断），
钩子只对**已通过约束**的动作再作否决；钩子返回 `False` 走既有「已拒绝」终止语义，
trace 载荷带 `blocked_by=<entry label>`。

**已知局限**（ADR-0259）：① 钩子是**同步阻塞**调用（`asyncio.to_thread` 仅把子进程搬离事件
循环，`timeout_s` 仍串行累加）；② `session.end` 依赖 `atexit`，被 `SIGKILL` 时不投递；
③ `memory.write` 观察者同步执行在写入路径上，慢钩子会拖慢落盘；④ 钩子副作用不可逆（契约
显式例外），不纳入 `EffectTracker`；⑤ 每事件按声明序**串行**执行，无并行 / 优先级。
