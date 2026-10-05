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

**分级判定契约（change `0095`）**：`classify` 按**语义词元**判定，不对标识串做**任意子串**匹配 ——
`_READ_TOKENS` / `_WRITE_TOKENS` / `_HIGH_RISK_TOKENS` 的命中均以完整词元语义为准；命名空间前缀
（如 `tools.`）偶然含只读词子串（如 `"ls"`）**不构成**只读判定（否则所有 `tools.*` 会误判为 READ，
deny-by-default 兜底失效）。判定顺序：高危词元 → 高危 coeffect 前缀（`secret:` / `network:` / `external`）
→ **字面量委托豁免** `agent:delegate`（list 元素**等值**匹配，判 READ）→ 写词元 → 只读词元 → 兜底 HIGH_RISK。
该豁免 SHALL NOT 放宽为 `agent:` 前缀（其余 `agent:*` 仍按高危及后续规则处理）。

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

def is_approved(ticket: ApprovalTicket) -> bool:
    """审批单是否经人工批准（status 与 result 双重复核）。

    状态词表属本模块——供域外（如 evolution 的 HITL confirm 门）判定「批了吗」，
    不必依赖 ``"approved"`` 字面量。
    """

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

### 3.1 ApprovalChannel（交互审批通道）

```python
class ApprovalChannel:
    """交互审批通道：confirm 门 → UI 终端 y/n（问一次、拿布尔）。

    与 ApprovalWorkflow 的单据生命周期互补，供 loop / ToolProvider 在异步
    执行流内直接 await；未接交互端（handler=None）时 fail-closed 拒绝。
    """

    handler: Callable[[str, dict, str], Awaitable[bool]] | None

    async def ask(self, tool_id: str, args: dict, reason: str) -> bool: ...
```

---

## 4. SandboxManager 接口

```python
class SandboxManager:
    def run(self, cmd: str | list[str], *, env: dict, budget: ResourceBudget) -> SandboxResult:
        """在独立沙箱中执行命令/代码，执行完自动销毁（一次性执行）。"""

    def spawn(self, cmd: list[str], env: dict | None = None,
              budget: ResourceBudget | None = None) -> subprocess.Popen[str]:
        """以资源配额（POSIX rlimit）拉起**常驻**子进程，返回可交互句柄。

        与 run 互补：run 跑完即返回结果，无法承载需要持续 stdin/stdout 的长连接
        （如本地 stdio MCP 服务端）。句柄归调用方持有并负责终止；拉起失败降级
        `SANDBOX_UNAVAILABLE`。仅施加 rlimit —— 可移植的 fs jail 需 OS 设施（namespaces/bwrap）。
        """

    def create(self, kind: str = "local-subprocess") -> SandboxHandle: ...
    def destroy(self, handle: SandboxHandle) -> None: ...

@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    destroyed: bool             # 是否已自动销毁
```

### 4.1 出站白名单策略与配置（change `0071`，账本 B5）

```python
class SandboxPolicy:
    def __init__(self, host_allowlist: list[str] | None = None,
                 fs_allowlist: dict[str, str] | None = None) -> None: ...
    def check_outbound(self, host: str) -> None:
        """host 不在白名单即抛 `AccessControlError(PERMISSION_DENIED)`（fail-closed 全拒）。"""
    def check_fs(self, path: str, mode: str = "r") -> None: ...
```

- **构造面**可注入；**配置面**（change `0071` 起）：`permission.sandbox.host_allowlist`
  —— 逗号分隔的**裸主机名**标量，经 `ConfigSpec` 单一真源解析（CLI flag / env / config.yaml 三面，
  优先级链一致），组合根 `build_runtime` 取值后注入，`MCPClient` 与 `SandboxManager` **共用同一实例**。
- **缺省空 = 全拒出站**（fail-closed，安全默认）；条目须为**裸主机名** —— `check_outbound` 的
  实参是 `urlparse(url).hostname`（**不含 scheme / 端口 / 路径**），带这些的条目不匹配，
  故**校验期即拒绝**（不静默忽略），详见 `03-interfaces/configuration-interface.md` §2.6。
- **生产调用点**：`core/mcp/transport.py` 的 `build_http_transport`（http / streamable-http 出站）。

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

## 6. 权限模式门（PermissionModeGate）

```python
class PermissionMode(str, Enum):
    READ_ONLY = "read-only"            # 只读：拒 DATA_EDIT / HIGH_RISK
    INTERACTIVE = "interactive"        # 交互：高危走审批（缺省）
    AUTO_APPROVE = "auto-approve"      # 无人值守全放行（高危 / 不可逆写 / 出站网络 / 不可归类）
    HIGH_RISK_BLOCK = "high-risk-block"  # 高危无条件阻断

    @classmethod
    def from_config(cls, value: str | None) -> "PermissionMode": ...

class PermissionModeGate:
    def __init__(self, mode: PermissionMode = PermissionMode.INTERACTIVE) -> None: ...
    def classify(self, op, target, coeffect) -> RiskLevel: ...
    def authorize(self, op, target, coeffect) -> Decision:
        """按 mode 前置判定；AUTO_APPROVE 顶部短路全放行；read-only / high-risk-block
        抛 PERMISSION_DENIED；其余委托 PolicyEngine。"""
```

映射 `config.permission.mode` + CLI `--permission-mode`。

**AUTO_APPROVE 语义（change `0095`，全放行）**：`authorize` **最前**短路返回
`Decision(True, ...)`，不调用 `classify` —— 对一切可由权限层决定的操作放行（含高危、不可逆写、出站网络、
无法归类），不返回 `approval_required`、不抛 `PERMISSION_DENIED`。**必须顶部短路而非只改 `PermissionGuard`**：
`PolicyEngine.authorize` 对 HIGH_RISK 返回 `approval_required=True`，`guard._to_gate` 会翻成 `confirm`
⇒ 出站网络 / 不可归类动作仍走审批（名实不符）。全放行**仅覆盖权限层**，SHALL NOT 越过与之正交的 guardrail
拦截（`PermissionGuard` 的 guardrail 分支保留在不可逆写分支**之前**）；read-only 与 high-risk-block 两档逐字不变。

---

## 7. 关联

- 模块：`02-modules/permission.md`
- 规格：`openspec/specs/permission/spec.md`
