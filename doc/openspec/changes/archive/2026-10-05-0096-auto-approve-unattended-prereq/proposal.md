# 0096 auto-approve 无人值守前置条件补记（change 0095 文档收口）

## Why

change `0095` 把 `auto-approve` 落地为**权限层全放行**并新增 ADR-0090。但 0095 的文档只写到
「**不越过正交红线**」这一**抽象**约束 —— 读者知道「还有别的东西可能拦」，却读不出**缺省状态下
有没有那条红线**、以及「哪些机制在缺省装配下会拦住无人值守」。这正是用户追问
「现在 auto approve 可以无人值守吗」时所暴露的**文档空洞**：可操作事实（缺省 `guardrail=None`、
缺省出站白名单 fail-closed、进化结晶门与权限档零耦合）散落在源码行号里，未落到接口/架构文档。

本 change 是**纯文档补记**，不改任何代码、不改规格。

## What Changes

- `doc/03-interfaces/permission-interface.md` §6（AUTO_APPROVE 段后）：新增「无人值守前置条件（change `0096`）」
  三行表 —— 逐机制列「缺省装配 / 无人值守下是否成立」，并给出结论句与「会停但不算要人批」的熔断说明。
- `doc/01-architecture/adr.md` ADR-0090：新增「已知边界（无人值守前置条件）」条，把 0095 的「正交红线」
  从不变量**落到缺省值**（配了 judgment 才有红线；缺省无）。
- **不**改 `doc/openspec/specs/permission/spec.md`：规格「权限模式」的 `auto-approve 与安全红线正交` 场景
  已覆盖该约束的**行为**（红线拦截 ⇒ 仍拒绝）；本 change 补的是**缺省装配事实**，属文档而非规格。

## Non-goals

- **不**改任何代码（`policy.py` / `guard.py` / `runtime.py` 一律不动）。
- **不**改规格（`skip_specs`）：无新行为条款，即无 delta。
- **不**动 `read-only` / `high-risk-block` / `interactive` 三档语义（0095 已冻结）。
- **不**改缺省装配本身（如「是否给 auto-approve 自动关掉 judgment」）—— 那是行为变更，非本轮议题。

## 风险

- 纯文档，**无运行时影响**；四门中 ruff / pyright / pytest 无新增面（无 `.py` 变更）。
- 唯一风险是**文档与源码脱锚**：表内行号（`runtime.py:258` / `engine.py:136`）随重构漂移 ——
  已在表内同时写明**判据**（「仅当配了 `judgment.provider` 才注入」），不单靠行号。
