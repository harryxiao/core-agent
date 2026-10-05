# design — 0095 auto-approve 全放行 + 只读判定子串修复

## 决策

### ① 为什么必须改两处（gate + guard），只改一处不够

确认门有**两条**独立的 confirm 来源：

| 来源 | 位置 | auto-approve 缺失时的后果 |
|---|---|---|
| `PermissionModeGate.authorize` 返回 `approval_required` → `guard._to_gate` 翻成 `confirm` | `policy.py:101` → `guard.py:75-80` | 出站网络 / 不可归类动作（HIGH_RISK）仍走审批 |
| `PermissionGuard.confirm` 的 `_is_write and not reversible` 分支 | `guard.py:57-58` | 不可逆写（`code_run` 等）仍走审批 —— **与权限档无关** |

故 B1（gate 顶部短路）与 B2（guard 分支感知模式）**缺一不可**。

### ② B1 顶部短路的形状与位置

在 `PermissionModeGate.authorize` 的**最前面**（read-only / high-risk-block 判定**之前**）：

```python
if self.mode is PermissionMode.AUTO_APPROVE:
    return Decision(True, f"auto-approve 模式全放行: {op}")
```

- 放最前是为了**不调用** `classify`（省一次判定），且语义上 auto-approve 压根不关心风险等级；
- 返回的 `Decision` 与 `PolicyEngine.authorize` 对非高危的返回**同形状**（`allowed=True, approval_required=False`）⇒ `_to_gate` 落 `auto`；
- read-only / high-risk-block **逐字不变**（仍在原位置）；interactive 仍回落 `PolicyEngine.authorize`。

### ③ B2 guard 感知模式的形状

```python
self._mode = self._gate.mode            # __init__ 末尾（PermissionModeGate.mode 是公开属性）
...
if self._is_write(coeffects) and not reversible and self._mode is not PermissionMode.AUTO_APPROVE:
    return GateDecision("confirm", ...)
```

- 记属性而非每次读 `self._gate.mode`：模式在构造后不变（无 setter），两者等价；记下来可读性更好。
- **不改 guardrail 分支**（在其**之前**判定）：guardrail 与权限档正交，auto-approve 也须被 guardrail 拦。
- `loop/default.py` 侧同源生效 —— `_allow` 调的就是注入的同一个 `PermissionGuard`，无需改动。

### ④ B3 只读词表：删 `"ls"` + 字面量豁免（顺序敏感）

```python
_READ_TOKENS = ("read", "get", "list", "search", "query", "cat", "view", "show", "stat")
_DELEGATE_COEFFECT = "agent:delegate"   # 字面量精确豁免，SHALL NOT 放宽为 "agent:" 前缀
```

`classify` 内插入点：**两个 HIGH_RISK 判定之后、`_WRITE_TOKENS` 扫描之前**：

```python
if _DELEGATE_COEFFECT in coeffect:      # list 元素等值匹配
    return RiskLevel.READ
```

- **为何在两段 HIGH_RISK 之后**：`classify("delete", ...)` 之类风险信号优先；委托工具无风险 coeffect，不受影响。
- **为何不用 `startswith("agent:")`**：change `0076` 引入 `agent:delegate` 是**具名委托能力的契约**，不是命名空间；前缀豁免会让将来任何 `agent:*` coeffect 静默变只读（安全面收窄的隐性风险）。
- **为何用 `in`（等值）而非子串**：与本次修复的根因（子串误判）保持同一口径 —— 豁免本身也不得靠子串。
- 删 `"ls"`：`"ls"` 是唯一出现在命名空间前缀（`"tools."`）里的短词元；`cat`/`get`/`set` 等虽短，但不在任何工具 id 前缀中（`tools.` 只含 `l`+`s`）。**备份判断**：即便将来出现含这些子串的 id，其归属也应由显式 coeffect/词元决定 —— 本次只删证据确凿的 `"ls"`。

### ⑤ `safety_gate.py` 不改（分歧登记）

`core/tools/safety_gate.py::SafetyGate` 是 `ToolProvider` 的**缺省** `confirm_gate`，`runtime.py` 生产装配注入的是 `PermissionGuard` ⇒ `SafetyGate` 只在「未注入」的测试/裸 `ToolProvider` 路径上出现。给它加权限档：① 需给它注入 mode（新注入面）；② 与 `PermissionGuard` 职责重复（两份模式语义真源）；③ 会破 `tests/test_tool_use.py` 既有断言。**不做**，分歧写进 ADR-0090「明确不做」。

### ⑥ 有意行为变化（更正确，非回归）

| 档 | 工具 | 改前 | 改后 |
|---|---|---|---|
| `high-risk-block` | `code_run` | 走审批（因误判 READ → 非高危） | **无条件阻断**（正解：它是高危） |
| `read-only` | `code_run` | confirm（同上） | `PERMISSION_DENIED`（正解） |
| 任意档 | `tools.<未知>` | READ（误判放行） | HIGH_RISK，deny-by-default |

以上无既有测试断言（已核 `tests/test_permission.py` / `test_phase13.py` / `test_tool_use.py`）。

## 影响面

- `PermissionModeGate.authorize`：**唯一对外行为变化**是 AUTO_APPROVE 档（其余三档逐字不变）。
- `PermissionGuard`：新增 `self._mode` 属性（纯加法）；confirm 行为仅在 AUTO_APPROVE 档变化。
- `PolicyEngine.classify`：`"ls"` 移出词表 + 一条新规则 ⇒ 仅 `tools.*` 类 id 与 `agent:delegate` 变化。
- 既有测试：仅 `tests/test_permission.py::test_permission_mode_auto_approve_low_risk` 需改写（其断言正是被修正的语义）；其余全绿。
- 规格：`permission` 两条 Requirement MODIFIED（含原有场景保留作锚点）。
