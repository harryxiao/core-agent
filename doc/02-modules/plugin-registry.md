# 模块设计：插件注册与组合基底（L0 Substrate / Plugin Registry）

> 对应规格：`doc/openspec/specs/plugin-registry/spec.md` ｜ 接口：`doc/03-interfaces/plugin-registry-interface.md`

---

## 1. 模块定位

L0 是 CORE 唯一"核心"，提供**组合代数**：注册、查找、组合、生命周期、可逆效应、coeffect 解析、热插拔。
它**不做任何业务**，只保证"任何插件都能被安全地装上、跑起来、卸下来"。

**无特权核心原则**：loop、模型、记忆、进化引擎都不是 L0，而是 L0 上的普通插件。

---

## 2. 内部组成

```
PluginRegistry（L0）
├── Registry          插件注册表：id → PluginDef（含版本、schema、coeffect 声明）
├── LifecycleManager  插件生命周期：load → active → suspend → unload（+版本切换）
├── EffectTracker     可逆效应追踪：undo 栈、时间旅行回滚、审计日志
├── CoeffectResolver  共效应解析：权限/宪章/配置注入，缺失拒绝
├── HMR               热插拔：运行中 load/unload，不中断主循环
└── EventBus          组合事件总线：跨层解耦（插件间不直接引用）
```

---

## 3. 关键设计

### 3.1 插件标识与版本（世代）

- 每个插件有全局唯一 `plugin_id`（命名空间：`tools.code_run`、`memory.store` …）。
- 版本采用**世代语义**：`gen0 → gen1 → …`，每次过验证门的进化产物提升一个世代。
- 同一 `plugin_id` 允许并存多世代，运行时指定 `active_generation`，回滚=切换世代。

### 3.2 可逆效应追踪（EffectTracker）

```
effect = {
  op: "file_write",
  target: "doc/x.md",
  undo: ( ) => 恢复原内容,       # 撤销闭包
  payload_meta: {...},
  reversible: true|false,
  coeffect: ["filesystem:write"],  # 执行前需解析注入
  trace_id: "loop-轮次-序号"
}
```

- 所有写操作必须 `record(effect)`；undo 栈按 trace_id 分组，支持**按轮回滚**或**全局回滚**。
- **回滚清账（change `0128` / ADR-0121）**：撤销**成功**的效应与**不可逆**效应随即出账 ⇒ 同一 trace
  **重复回滚不二次撤销**、账目**不无界增长**（tracker 为长驻单例）；撤销**失败**者**留账隔离**（仍在
  `audit` 可见，由 `undo_failed` 报告，绝不静默丢弃）；`clear(trace_id=None)` 提供只清账、不撤销的入口。
- 不可逆效应（`reversible: false`）必须提前通过确认门（ask_user），并进入特殊审计区。

### 3.3 Coeffect 解析

- 插件声明所需 coeffect：`["filesystem:read", "constitution:v1"]`。
- CoeffectResolver 从**环境**（配置文件、宪章、权限表）读取并注入；缺任一必需项 → 拒绝执行并记录原因。
- 密钥类 coeffect 只注入引用（路径/句柄），**值绝不进日志/记忆**。

### 3.4 热插拔（HMR）

- `load`：注册 schema + coeffect 声明 + 实例化，注册表立即可查。
- `unload`：先回滚该插件未确认的 undo 栈，再卸载；正在执行的调用等其完成（graceful）。
- 主循环通过 EventBus 订阅插件变更事件，无需感知实现细节。

---

## 4. 组合语义（Composition Algebra）

插件按三种方式组合，全部由 L0 提供：

| 组合方式 | 说明 | 示例 |
|---|---|---|
| **Bundle** | 能力集：把一组插件打包成一个可装配单元 | `bundle(core_tools)` |
| **Profile** | 配置集：指定 active 插件 + 世代 + coeffect 来源 | `profile("coding-agent")` |
| **Patch** | 进化补丁：一次世代化变更（含 delta + 验证结果） | `patch(gen42, diff, gate_report)` |

组合满足**可逆律**：`apply(p) 后 apply(p.undo) == 原状态`。这是可观测性与进化安全性的根基。

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 插件依赖的 coeffect 缺失 | 拒绝执行，返回 `COEFFECT_MISSING` 结构化错误 |
| 插件加载失败 | 不污染注册表，记录诊断信息（供 L4 诊断） |
| 卸载时 undo 回滚失败 | 进入 `QUARANTINE` 状态，人工介入，绝不静默继续 |
| 重复注册同一 id | 按世代并存，不覆盖 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/plugin-registry-interface.md`
- 规格：`doc/openspec/specs/plugin-registry/spec.md`
- 测试：`doc/04-testing/test-cases.md`（PLG 系列）
