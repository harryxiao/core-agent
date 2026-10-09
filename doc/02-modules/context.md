# 模块设计：上下文工程（Context Engineering）

> 对应规格：`doc/openspec/specs/context/spec.md` ｜ 接口：`doc/03-interfaces/context-interface.md`
> 定位：**L2 记忆之上 / L3 输入侧**，解决长任务下信息过载、关键信息丢失的核心痛点。

---

## 1. 模块定位

上下文窗口是稀缺资源。全量塞入会让关键信息被淹没、token 爆表；什么都不塞又会遗忘关键约束。

本模块做**按需加载、信息地图、自动压实**三件事，保证"每次只把当前任务最需要的上下文装进窗口"。

---

## 2. 内部组成

```
ContextBuilder（L3 输入侧）
├── DynamicAssembler 动态上下文构建：按任务阶段按需加载
├── InfoMap          信息地图：轻量目录索引，按需跳转取细节
├── Compactor        上下文自动压实：多轮关键信息摘要沉淀
└── BudgetManager    token 预算：控制注入上界
```

---

## 3. 关键设计

### 3.1 动态上下文构建

- 根据当前任务阶段，**按需加载**对应领域文档、历史经验、规范要求，而非一次性全量塞入。
- 加载来源：MemoryStore 检索（L2 事实 / L3 技能）+ InfoMap 跳转 + 宪章/coeffect。
- 装配结果经 BudgetManager 控制 token 上界（可配置）。
- 调用方会话标识（`build(session_id=…)`）透传至 L2 事实检索 ⇒ 事实召回同样按会话隔离
  （change `0114`／ADR-0107）；缺省空串 ⇒ 不过滤，语义与既往逐字一致。
- 构造参数 `exclude_source_prefixes` / `allow_source_prefixes` 透传至同一次检索（排除面 + 其
  **例外面**，change `0117`／ADR-0110）；`with_allow_source_prefixes(*prefixes)` 派生**新**装配器
  （排除面逐字继承、放行面替换）—— 主 loop 与神兽共用一份配置，派生而非原地改（封存红线）。

### 3.2 信息地图机制

- 把千页级业务文档转化为**轻量化目录索引**（章节/要点/位置指针），不把全文塞入窗口。
- 模型按需跳转获取细节：先用地图定位，再 fetch 对应片段。
- 地图更新策略：文档变更时增量重建（hash 比对）。

### 3.3 上下文自动压实

- 对多轮对话的关键信息自动摘要沉淀：已完成子任务的结论、关键决策、未决事项。
- 沉淀产物写回 MemoryStore（L2 事实 / L3 技能），避免重复传递冗余内容。
- 压实触发时机：轮数阈值 / token 接近上限 / 子任务切换时。
- 产物按**本轮会话**归属（`persist(session_id=…)`），条目 id 带会话键（缺省 `default`）
  ⇒ 跨会话不再同名覆盖（change `0114`／ADR-0107）。

### 3.4 三层窗口比例分配（change `0178`／ADR-0169）

- **策略纯函数**：`core.context.plan_window(history_turns, history_budget, *, tiered) -> WindowPlan`
  —— 只依赖 stdlib、**零 I/O、零模型调用**，把会话历史回灌的分层策略收敛为确定性配额。
- **份额**：短 `0.5` / 中 `0.3` / 长 `0.2`，为**模块常量**（不新增配置键，与 `_ROUND_THRESHOLD` /
  `MAX_SUMMARY_CHARS` 同纪律）；`history_budget = token_budget // 2`（沿用既有 `_load_history` 口径）。
- **配额**：`short_turns` / `mid_turns` / `short_tokens`（短层 token 上界）/ `mid_chars`（中层摘要字符上界）；
  clamp —— 轮数或预算非正 ⇒ **全零**（关闭回灌）；非分层 ⇒ 「短层 = 全部 `history_turns` + 全部预算、中层零」，
  与既有双重上界**逐字等价**；分层时 `short ≥ 1`、`short + mid ≤ history_turns`、配额随总量**单调不减**。
- **LLM 压缩不在此层新开调用点**：本模块只**分配**，摘要由记忆的压实通道统一产出（`summarize_slice`）。

---

## 4. 与记忆/约束的分工

| 层 | 职责 |
|---|---|
| MemoryStore（L2） | 存储与检索事实/技能 |
| ContextBuilder | 决定"这一轮装什么"（按需 + 预算） |
| Constraints.Compressor | 执行期清理无效信息 |
| Compactor（本模块） | 跨轮摘要沉淀（写回记忆） |

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| token 超预算 | 裁剪低相关度内容，优先保留宪章/未决事项/验收标准 |
| 地图索引失效 | 触发重建，期间降级为全文检索 |
| 压实产物质量差 | 校验关键信息不丢失，否则不替换原文 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/context-interface.md`
- 规格：`doc/openspec/specs/context/spec.md`
- 测试：`doc/04-testing/test-cases.md`（CTX 系列）
