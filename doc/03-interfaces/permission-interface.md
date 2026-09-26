# 接口设计：权限与审批（Permission & Approval Interface）

> 模块：`02-modules/permission.md` ｜ 规格：`openspec/specs/permission/spec.md`

---

## 1. 风险等级枚举

```python
class RiskLevel(str, Enum):
    READ = "read"            # 只读查询
    DATA_EDIT = "data-edit"  # 数据编辑
    HIGH_RISK = "high-risk"  # 高危操作
```

---

## 2. PolicyEngine 接口

```python
class PolicyEngine:
    def classify(self, op: str, target: str, coeffect: list[str]) -> RiskLevel:
        """判定操作风险等级；无法归类时默认 HIGH_RISK（deny-by-default）。"""

    def authorize(self, op: str, target: str, risk: RiskLevel) -> Decision:
        """授权判定；read/data-edit 走 coeffect 校验，high-risk 要求审批单。"""

@dataclass
class Decision:
    allowed: bool
    reason: str                 # 拒绝原因
    approval_required: bool     # 是否需要人工审批
```

---

## 3. ApprovalWorkflow 接口

```python
class ApprovalWorkflow:
    def create(self, request: ApprovalRequest) -> ApprovalTicket:
        """创建审批单；高危操作执行前必须持有 approved 单据。"""

    def ask(self, ticket: ApprovalTicket) -> ApprovalResult:
        """向人工发起审批（经 loop 的 ask_user 门）；超时默认 fail-closed。"""

    def archive(self, ticket: ApprovalTicket) -> None:
        """审批归档，可回溯'谁在何时批准了什么'。"""

@dataclass
class ApprovalRequest:
    op: str
    target: str
    impact_summary: str         # 影响面摘要
    rollback_plan: str          # 回滚预案
    trace_id: str
    ttl_seconds: float = 300.0  # 超时默认拒绝

@dataclass
class ApprovalResult:
    approved: bool
    approver: str | None
    note: str | None
```

---

## 4. SandboxManager 接口

```python
class SandboxManager:
    def run(self, cmd: str | list[str], *, env: dict, budget: ResourceBudget) -> SandboxResult:
        """在独立沙箱中执行命令/代码，执行完自动销毁。"""

    def create(self, kind: str = "local-subprocess") -> SandboxHandle: ...
    def destroy(self, handle: SandboxHandle) -> None: ...

@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    destroyed: bool             # 是否已自动销毁
```

---

## 5. 错误码

| 错误码 | 含义 |
|---|---|
| `PERMISSION_DENIED` | 未授权操作（含所需风险等级） |
| `APPROVAL_REQUIRED` | 高危操作需人工审批 |
| `APPROVAL_TIMEOUT` | 审批超时，fail-closed |
| `SANDBOX_UNAVAILABLE` | 沙箱不可用（不降级直跑） |
| `APPROVAL_EXPIRED` | 审批单已过期 |
| `QUOTA_EXCEEDED` | 资源配额超限 |

---

## 6. 关联

- 模块：`02-modules/permission.md`
- 规格：`openspec/specs/permission/spec.md`
