# 0095 — auto-approve 全放行 + 只读判定子串误判修复

## 为什么

真机活 LLM 冒烟暴露：**`auto-approve` 权限档名实不符** —— 与 `interactive` 的判定**逐行相同**，不可逆工具在非交互入口下**全被 fail-closed 拒绝**。两个原因叠加：

1. `PermissionModeGate.authorize`（`src/core/permission/policy.py:86`）只在 read-only / high-risk-block 两档改变判定，其余**回落 `PolicyEngine.authorize`** ⇒ auto-approve 与 interactive 无差异；
2. `PermissionGuard.confirm`（`src/core/permission/guard.py:57-58`）的 `if self._is_write(coeffects) and not reversible: return confirm` **完全不看权限档** ⇒ 不可逆写一律进 confirm；而 `DefaultLoop._allow`（`loop/default.py`）在**无 approver** 时 fail-closed，`approver` 只有 `interactive=True` 才装配（`entry.py:_build_ui`）⇒ `run` / `serve` / `--app` 三入口**跑不了任何不可逆工具**（名不符实：标称 auto-approve 却什么都批不过）。

**顺带真 bug（同类根因：子串匹配）**：`PolicyEngine.classify`（`policy.py:47-60`）的只读词表含 `"ls"`（`policy.py:41`），而工具 id 命名空间前缀 `"tools."` **含子串 `"ls"`** ⇒ **所有 `tools.*` 一律被判 READ**（含 `tools.file_write`！），deny-by-default 的高危兜底对其失效 —— 这是「按子串而非按词元」的直接后果。

顺带记录：`tools.delegate` 在 change `0076` 已补声明 coeffect `agent:delegate`（用于 MCP 默认暴露面判据），但**分级层不认识它**；若只删 `"ls"` 而不补规则，`tools.delegate` 会由「靠 `"ls"` 混进 READ」变为 HIGH_RISK，**破坏上一轮真机实测行为**（委托在默认档下须可放行）。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/permission/policy.py` | `PermissionModeGate.authorize` 增 AUTO_APPROVE **顶部短路**；`PolicyEngine` 删 `_READ_TOKENS` 的 `"ls"`、增字面量 `agent:delegate` 只读规则 |
| `src/core/permission/guard.py` | `PermissionGuard` 记 `self._mode`；不可逆写分支加 `and self._mode is not AUTO_APPROVE` |
| `doc/openspec/specs/permission/spec.md` | MODIFIED「权限模式」+「分级权限体系」 |
| `doc/03-interfaces/permission-interface.md` | §2（分级契约：字面量 vs 子串）、§6（AUTO_APPROVE 全放行） |
| `doc/02-modules/permission.md` | §3.1 补「模式覆盖」段 |
| `doc/01-architecture/adr.md` | ADR-0090 + 映射表行 |
| `doc/04-testing/test-cases.md` | TC-PERM-08 / TC-PERM-09 |
| `tests/test_permission.py` | 改 1 例（auto-approve 语义）+ 增 4 例（classify） |
| `tests/test_permission_auto_approve.py` | 新：端到端 7 例（无 approver 放行 / guardrail 仍拦 / 两拒绝档仍拒 / loop 正向回归） |

## 决策

- **auto-approve = 全放行**（用户裁决）：无人值守档不询问、不阻断；read-only 与 high-risk-block 仍是两个拒绝档，interactive 语义不变。**必须在 `authorize` 顶部短路**（不能只改 guard）：`PolicyEngine.authorize` 对 HIGH_RISK 返回 `approval_required=True`，`guard._to_gate` 会翻成 `confirm` ⇒ 出站网络 / 不可归类动作仍走审批 = 名实不符的另一半。
- **不改 `PolicyEngine`**：它是**模式无关**的风险引擎，「模式语义归 gate」是现架构的既有分层（`PermissionModeGate` 注释即如此），改引擎会把模式耦合进分级。
- **guardrail 保留拦截**：`PermissionGuard` 的 guardrail 分支与权限档**正交**（缺省装配 `guardrail=None`）⇒ 无人值守缺省即成立、且不牺牲 JEV 红线。**否决**「顶部早期 `return auto`」的激进写法（会把 guardrail 一起绕过）。
- **删 `"ls"` + 字面量 `agent:delegate`**（用户裁决）：`"ls"` 从 `_READ_TOKENS` 移除（`cat` 等保留 —— 它们不在任何命名空间前缀里）；新增模块常量 `_DELEGATE_COEFFECT = "agent:delegate"`，在**两个 HIGH_RISK 判定之后、WRITE 扫描之前**以 `in coeffect`（list 元素**等值**匹配）判 READ —— 放 HIGH_RISK 之后保证风险信号优先，等值匹配保证**不放宽为 `agent:` 前缀**（将来 `agent:*` 仍 HIGH_RISK）。
- **`safety_gate.py` 不改行为**：它是模式无关的 `ToolProvider` 缺省门，运行时不用它（runtime 注入 `PermissionGuard`）；为它加 mode 会破坏既有用例且职责重复。

## 逐工具净结果（confirm 门）

| 工具 | 改前 | 改后 | 说明 |
|---|---|---|---|
| `file_read` / `file_write` / `file_patch` / `web_fetch` | 不变 | 不变 | 词表与 coeffect 未触及 |
| `code_run` | 靠 `"ls"` 混进 READ | HIGH_RISK | **confirm 净结果不变**（改前靠写 coeffect、改后靠 HIGH_RISK，均 confirm）；有意变化：`high-risk-block` 下由「走审批」变「无条件阻断」、`read-only` 下由 confirm 变 `PERMISSION_DENIED`（均**更正确**，无测试破） |
| `tools.delegate` | 靠 `"ls"` 混进 READ | READ（新字面量规则） | **保持上一轮真机实测不变**（不依赖 change A） |
| `tools.whatever`（未登记 id） | READ（误判） | HIGH_RISK | 修好为 deny-by-default |

## 明确不做

- 不给 `SafetyGate` 加权限档（运行时不用它，职责重复；分歧见 ADR-0090）。
- 不改 `PolicyEngine.authorize`（模式无关引擎，语义归 gate）。
- 不做「auto-approve 顶部 return」（绕过 guardrail）。
- 不改 `_WRITE_TOKENS` / `_HIGH_RISK_TOKENS` 其余词元（无证据支持，避免顺带重构）。
