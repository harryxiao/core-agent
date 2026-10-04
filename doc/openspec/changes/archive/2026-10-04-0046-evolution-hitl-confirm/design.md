# Design: 架构级候选强制人工审批（evolution HITL confirm gate）

## 决策 1：`risk_level` 是候选的**固化物**，由提案阶段按 `kind` 判定

```python
# evolution/models.py
GenerationCandidate:
    risk_level: Literal["low", "high"] = "low"   # 架构级=high（kind="plugin"）；技能库级=low

# evolution/proposer.py
risk_level="high" if self._kind == "plugin" else "low"
```

- 风险域是**提案时的事实**（这条候选动不动架构代码），不是确认时的调用参数——由调用方传
  `risk_level` 等于把门禁交给被门禁的一方。默认 `"low"` 保证既有构造调用零改动。
- 判据就是 `kind`（`plugin` = 架构级）。**不采纳**「让调用方显式声明风险」（同一候选的
  风险域会随调用方而变，规格要求的是确定性判定）。

## 决策 2：审批判定谓词落在 permission 域（`is_approved`），域外不认状态字面量

```python
# permission/approval.py
def is_approved(ticket: ApprovalTicket) -> bool:
    """审批单是否经人工批准（含 result 复核）。供域外做 HITL 门判定。"""

# permission/__init__.py 导出；evolution 侧：
from core.permission import ApprovalTicket, is_approved
```

- 审批单的**状态词表属 permission**（`_STATUS_APPROVED = "approved"` 是模块私有）。若 evolution
  自己写 `ticket.status == "approved"`，等于把一个域的私有词表复制到另一个域——今天改一处、明天
  漏一处。谓词函数把这个知识留在原域，域外只问「批了吗」。
- **不采纳**「engine 注入 `ApprovalWorkflow` 实例再 `workflow.is_approved(ticket)`」：该判定是
  **审批单的纯函数**（只读 `status`/`result`，与 workflow 的归档状态无关），为它注入一个有状态
  对象是无谓的依赖；**不采纳**「evolution 自定义 `Callable[[Any], bool]` 接缝」：把一个三行谓词
  藏进闭包会让「谁在判定」不可见（此处不存在需要替换的实现）。
- 方向：evolution（L4）→ permission（横切底层）是**下层依赖**，与既有
  `im/gateway.py → core.permission` 同向（`test_architecture` 无禁止项）。

## 决策 3：`confirm(candidate, *, approval=None)` —— `high` 三重校验，`low` 行为不变

```python
def confirm(self, candidate, *, approval: ApprovalTicket | None = None) -> None:
    if candidate.risk_level == "high":
        if approval is None or not is_approved(approval):
            raise EvolutionError(CONFIRM_REQUIRED, f"架构级候选未获人工审批（{candidate.target_plugin}）")
        if approval.request.target != candidate.target_plugin:
            raise EvolutionError(CONFIRM_REQUIRED, "审批单目标与候选不符（不得跨候选复用审批）")
    candidate.status = "confirmed"
```

- 三重校验：**有单 + 已批准 + 目标一致**。目标一致性挡住「拿一张别的插件的批准单解锁本候选」
  ——没有它，门禁只是仪式。
- 失败**抛结构化错误**（不返回布尔）：`confirm` 的语义是「确认」这个动作，静默失败会让调用方
  以为候选已放行；抛错则候选保持 `pending`，`crystallize` 的既有 `CANDIDATE_PENDING` 守卫兜底。
- `low` 分支忽略 `approval`：技能库级候选**仍须人工显式调用 `confirm`**（不引入自动结晶）。
- **不采纳**「engine 内建 `ApprovalWorkflow` 并自动建单/等待」：单据生命周期（TTL、ask 超时
  fail-closed、UI/IM 交互）属 permission 与交互端；engine 只做**门禁校验**，不做人的事。

## 决策 4：不新增可追溯字段

审批单据自身携带 `request.target` / `request.trace_id`，且 `ApprovalWorkflow._resolve` 会把单据
归档（`list_archived`）——追溯链已经完整。**不采纳**「在候选上再存 `approval_id`」：同一事实两处
存储就会两处漂移。

## 已知缺口（如实记录，不扩大范围）

- **进程内信任边界**：单据由 permission 域构造（状态只经 `_resolve` 迁移），但同进程代码理论上可
  自造 `ApprovalTicket(status="approved")`；与既有 `approver` / `ApprovalChannel` 的信任面一致
  （进程边界外不可信结构不在本变更范围）。
- **无审批单的持久化/重放**：重启后候选队列与审批归档都不落盘（进化引擎本身无持久化）。
- **`risk_level` 只有两档**：不做多级风险（`RiskLevel` 三档属 tool 权限面，与候选风险域不同轴）。
