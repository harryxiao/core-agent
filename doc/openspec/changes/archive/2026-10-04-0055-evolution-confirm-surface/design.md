# Design — evolution-confirm-surface

## 决策 1：稳定候选身份用 UUID，不用 `(generation, target_plugin)` 组合

`Proposer._generation` 是进程内自增（每次装配从 0 起），故 `(generation, target_plugin)` 在
**跨进程**并不唯一（两次 `evolve run` 各产出一个 `generation=1` 的同目标候选）。用 UUID（取
前 12 位十六进制，CLI 可手输且碰撞概率可忽略）作为 `candidate_id`，构造即固化、不可变。

代价：不可读。收益：唯一性不依赖任何进程内状态 —— 这正是 A4 的症状根因。**已否决**
「用 `id(obj)` 的十六进制」：那只是把不稳定的键换成不稳定的字面量。

## 决策 2：门禁/评测报告**随候选**落盘，而非单独落盘

`crystallize` 需要 `GateReport`（`passed`）与 `EvalReport`（`verdict == "publish"`，
且 `held_out_score` 用作开窗基线）。二者原本以 `id(candidate)` 为键存于引擎私有字典。

落盘形状取「一条记录 = 候选 + 门禁 + 评测」的**整体**：

```json
{"pending": [{"candidate": {...}, "gate": {...} | null, "eval": {...} | null}, ...]}
```

理由：三者是**同一条待确认事项的三个面**，分开落盘会引入「候选在而报告缺」的半状态，
而 `crystallize` 对半状态只能 fail-closed 拒绝（正是要修的毛病）。整体落盘让「恢复即可用」
成为不变量。**已否决**「只落候选、评测重跑」：留出评测不可复现（基准集非确定注入）。

## 决策 3：`PendingQueue` 自持序列化，沿用 `core/persistence.py`

与 `ObservationRegistry`（`0051`／ADR-0054）同形：组件自持 `path` 与序列化形状，只把
「字节进字节出」交给 `core/persistence.py` 的两个纯函数（标准库 JSON）。`persistence.py`
不 import 任何能力包的中立性得以保持（红线）。

**未复用 `ObservationRegistry`**：二者状态形状与生命周期都不同（窗口 vs 队列），强行合并
只会造出一个「什么都装的容器」。相同的是**模式**，不是**数据**。

## 决策 4：`pending()` 只列 `status == "pending"`

`_pending` 原本只增不减，一条确认过的候选永远留在快照里（第二次 `confirm` 会静默重复放行）。
改为按 `status` 过滤后，「待确认队列」才名副其实；已确认/已拒绝的候选留在落盘记录中充当
**最小审计痕迹**（不额外建归档结构 —— 无消费者）。

## 决策 5：`reject` 是引擎方法，不是操作面自造

候选状态词表属 evolution 域（`models.py` 已注释 `pending | confirmed | rejected`）。让 CLI
直接改 `candidate.status` 会让域外认字面量 —— 与 permission 域「状态字面量不外泄」的同一原则。
故新增 `EvolutionEngine.reject(candidate, *, reason=None) -> GenerationCandidate`，落盘 + 写 L2 教训。

## 决策 6：审批单由**操作面**签发，不入引擎

`risk_level="high"` 的候选需要一张获批审批单。签发方（`ApprovalWorkflow.create` + `.approve`）
放在 CLI：**人**在操作面上确认，操作面即「人工」这一事实的来源；引擎只收单据做判定
（`confirm(candidate, approval=...)` 语义一字不动）。`core/im/gateway.py:14` 已有同形先例
（IM 通道侧构造 `ApprovalRequest`）。**已否决**「引擎内部自造审批单」：那等于把 HITL 门
自己给自己盖章，闸门立刻失效。

票据参数：`op="evolution.publish"`、`target=candidate.target_plugin`（必须与候选一致，
否则 `confirm` 按既有语义抛 `CONFIRM_REQUIRED`）、`impact_summary` 取候选 `delta.issue`、
`rollback_plan` 指向 `dissolve`、`trace_id="evolution"`（与既有 L2 教训条目同源）。

## 决策 7：CLI 面向 `pending` 队列而非 `generation`

`evolve confirm <candidate-id>` 先 `engine.find(id)`，未命中打印「候选不在待确认队列」
并返回退出码 1（对齐 `_evolve` 既有 stderr + 非零退出约定）。确认动作是 `confirm` 后
**立即** `crystallize`（两步在语义上是一次「放行发布」；分开成两条命令只会让人漏掉第二步，
而漏掉第二步正是本变更要修的病）。

---

## 接受的风险

- **归档不落盘**：`ApprovalWorkflow._archive` 仍进程内 —— CLI 一次进程内签发并立刻消费，
  不留悬空；但**跨进程**无法复查「当时是谁批的」。已记入后续（permission 域的审批归档持久化）。
- **队列无回收**：`evolution-pending.json` 随确认次数单调增长（每条记录很小）。当前无消费者，
  不预先造清理策略。
- **`candidate_id` 手输**：CLI 接受完整 12 位 id；不做前缀匹配（避免歧义匹配的隐性错误）。
