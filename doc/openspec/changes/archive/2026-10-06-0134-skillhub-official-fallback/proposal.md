# 变更提案：skillhub 源不健康以官方源结果回退（change 0134 / phase-34 E80）

## 背景

`coding-plan/phase-34.md` §2 登记的 **E80**（规格漂移）。

规格 `skillhub/spec.md`「多源路由与健康回退」**一句话内自相矛盾**：

> 系统 SHALL 按 source 路由到对应市场源；源不健康时**回退官方源**，源不存在时拒绝路由。

而其 Scenario「源不可达回退」又写：

> **THEN** 标记源不健康并**回退官方源**，返回 `SOURCE_UNHEALTHY`

实现（`skillhub/index.py:134-140 _ensure_healthy`）与测试（`test_skillhub.py:41`）**都只选了后半句**：
探测失败即 `raise SOURCE_UNHEALTHY`，**没有任何回退动作**（异常信息里那句「（回退官方源）」
是**空头承诺**——异常文本描述了未发生的行为）。

于是「多源路由」在生产上退化为**单源**：任一非官方源抖动，`skill search --source S` 直接失败，
而不是回退到可用源取结果。

## 变更内容

**裁决（2026-10-06，用户）**：**回退成功即返回官方源的结果**；仅当**回退目标也失败**才抛
`SOURCE_UNHEALTHY`。

1. **实现**（`src/core/skillhub/index.py`）：
   - `_ensure_healthy(source) -> str`：改为返回**可用源名**——源健康则返回原源；不健康则
     **标记该源不健康**（写入 `self._health`，`health()` 可查）并**回退官方源**；官方源
     （= 回退目标）亦不可用时才抛 `SOURCE_UNHEALTHY`。
   - `list(source)` / `route(source)` 改用返回的**可用源**取结果（`route` 因此可能返回
     `official` 源对象 —— 这正是「回退」的语义）。
   - 源不存在仍抛 `SOURCE_NOT_FOUND`（**不**回退到未知源，逐字不变）。
   - 官方源自身不健康时**无回退目标** ⇒ 抛 `SOURCE_UNHEALTHY`（语义等价于旧行为）。
2. **规格**（`skillhub/spec.md`）：**MODIFIED**「多源路由与健康回退」——把矛盾句拆成
   「不健康 ⇒ SHALL 回退官方源**并以其结果响应**；回退目标**亦**不可用 ⇒ 返回
   `SOURCE_UNHEALTHY`；源不存在 ⇒ `SOURCE_NOT_FOUND`，SHALL NOT 回退到未知源」，
   + 3 Scenario（回退成功 / 回退目标亦不可用 / 官方源自身不可达）。

## 不做（明确排除）

- **不改 `健康探测` 的 `health()` 语义**：`health(source)` 仍是「探测并如实返回」，不做回退
  （它是**诊断面**而非取数面；回退只发生在 `list` / `route` 这类取数路径）。
- **不改 `download` / `locate`**：二者是**查找**而非路由（`locate` docstring 已立此口径），
  本就不经健康探测。
- **不引入重试 / 熔断**：单次回退，不做多次探测（重试语义另属 E79 的 git 面，与此无关）。

## 影响面

| 面 | 变化 |
|---|---|
| `MarketIndex.list` / `route` | 非官方源不健康 ⇒ 返回**官方源**结果（此前抛错） |
| `SOURCE_UNHEALTHY` | 收窄为「**无可用源**」：官方源自身不健康，或回退目标亦不健康 |
| `SOURCE_NOT_FOUND` | 逐字不变 |
| CLI `skill search --source S` | 非官方源抖动 ⇒ 回退官方源出结果（不再 `搜索失败`） |
| `health()` | 逐字不变（仍如实探测） |

## 验证

- 四门禁：`ruff check` / `ruff format --check` / `pyright` **0/0/0** / `pytest -q`（1629 → 1632）。
- `openspec validate --all`：active 期 31/0，归档后 30/0。
