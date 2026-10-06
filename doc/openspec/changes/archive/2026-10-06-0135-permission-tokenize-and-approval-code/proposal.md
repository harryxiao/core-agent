# proposal — permission 分级按词元 + 高危审批门错误码（change 0135 / 账本 E76）

## Why

`coding-plan/phase-34.md` 登记的 **E76**（规格漂移 · 接线收口）：两处**规格与接口文档早已立规、
代码未跟上**的背离（故属 conformance ⇒ `skip_specs`，非新规格）：

- **① 裸子串匹配违反「语义分词」**：`permission/spec.md`「分级权限体系」SHALL 按**语义分词**
  （工具 / 动作词的**完整词元**）判定，命名空间前缀或无关子串的偶然命中 SHALL NOT 影响等级；
  `03-interfaces/permission-interface.md` §2 亦以 change `0095` 立下同一契约。但
  `src/core/permission/policy.py:53,61,63` 的实现一直是 `tok in op_l`（**任意子串**）：
  - `tools.target`（词元 `target` 含子串 `get`）⇒ 今日判 `read`，应为 `HIGH_RISK`；
  - `tools.category_sync`（含子串 `cat`）⇒ 今日判 `read`，应为 `HIGH_RISK`；
  - **目标侧同病灶**：`classify("tools.whatever", "/var/log/target")` ⇒ 今日判 `read`。

  后果：命名空间前缀（`tools.*`）下的误放行让「无法归类 → deny-by-default HIGH_RISK」的**兜底形同失效**。

- **② `APPROVAL_REQUIRED` 是死码，且高危审批门用错了码**：`src/core/permission/errors.py:18` 定义
  `APPROVAL_REQUIRED`（错误码表口径：「高危操作**需人工审批**」），全 `src/` **零 raise**；而唯一的高危
  审批门 `src/core/git/client.py::_require_approval`（force-push）却抛 `PERMISSION_DENIED`
  （语义是「**无权**」）—— **事由张冠李戴**，且「高危须审批」这一规格 Scenario 在错误码面上无落点。

## What Changes

- **① `PolicyEngine.classify` 改为词元集合命中**（`src/core/permission/policy.py`）：
  新增 `_tokens(op, target)` —— 操作与目标一并按 `._:-/`（命名空间 / 路径 / snake / kebab / coeffect 式）
  切成**小写词元集合**；三张词元表由 `tuple` 转 `frozenset`，命中改为集合交（`tokens & _READ_TOKENS`）。
  **判定顺序逐字不变**：高危词元 → 高危 coeffect 前缀（`secret:` / `network:` / `external`）
  → 字面量委托豁免 `agent:delegate` → 写词元 → 只读词元 → 兜底 `HIGH_RISK`。
- **② `GitClient._require_approval` 改抛 `APPROVAL_REQUIRED`**（`src/core/git/client.py`）：
  「缺审批」≠「无权限」—— 未获批准即 fail-closed 阻断（**行为不变**：仍拒绝、仍不起后端调用），
  只是错误码归位。该码自此有**生产可达的 raise 落点**。

## 判据订正（一手复核，两条 —— 明示偏离 `phase-34.md` §6 的计划措辞）

| 计划原文 | 订正 | 依据 |
|---|---|---|
| 「`authorize` 的 `approval_required=True` 无审批时 `raise APPROVAL_REQUIRED`」 | **未采纳 raise 进 `authorize`**；raise 落在 `git._require_approval` | `PolicyEngine.authorize` 对 HIGH_RISK **返回** `Decision(approval_required=True)` 是 loop confirm 门的**契约**：`guard._to_gate` 据此翻成 `confirm` 走审批通道（`provider.py:111` / `loop/default.py:639` 据此 fail-closed）。改成抛异常会**打断审批流**，并使 `guard` 的 `approval_required` 分支成为**新死分支**——以消死码之名造新死码。同一错误的另一处 `git._require_approval` 才是该码的正确语义落点 |
| 测试例「`tools.list` **不**判 read」 | **反例改写**为 `tools.target` / `tools.category_sync` | 词元 `list` 本就是只读词 ⇒ 切词后 `tools.list` 判 `READ` 是**正确**结果（非缺陷）。真正的子串陷阱是「**词元非只读却含只读子串**」的标识 |

## Impact

- 受影响 capability：`permission`、`git`。
- **规格中性**：两条均为「实现回归既有契约」⇒ `.openspec.yaml` 置 `schema: spec-driven` + `skip_specs: true`
  （先例 `0110` / `0083`）；不新增 / 不修改任何 Requirement。
- 行为变化（**均朝 fail-closed**）：`tools.target` 一族由 `read` 收敛为 `HIGH_RISK`（多要一次审批）；
  自带内置工具（`tools.file_read` / `tools.file_write` / `tools.file_patch` / `tools.code_run` /
  `tools.web_fetch` / `tools.gate_run`）判定**逐字不变**（已逐一核对）；
  force-push 未批的**错误码**由 `PERMISSION_DENIED` 改为 `APPROVAL_REQUIRED`（阻断行为不变）。
- 不影响：`PermissionModeGate` 四档语义（read-only / high-risk-block 仍 `PERMISSION_DENIED`，
  interactive 仍返回 `Decision(approval_required=True)` 供审批通道）；
  `guard` / `provider` / `loop` 的 confirm-fail-closed 链；coeffect 面（`secret:` / `network:` /
  `external` / `agent:delegate`）逐字不变。
- **已知局限（明示）**：词元表是白名单 —— `tools.stats`（词元 `stats` ≠ `stat`）由「子串误判 READ」
  变为「**保守地**判 HIGH_RISK」。这是有意的 fail-closed 取舍（宁可多要一次审批，不放过一次误放行）。
