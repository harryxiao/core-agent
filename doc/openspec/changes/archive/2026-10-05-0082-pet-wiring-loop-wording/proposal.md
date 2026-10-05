# 0082 — pet「Runtime Wiring」loop 措辞订正（规格向实现靠拢）

## 为什么（账本 E29，**change `0081` 自报**）

`pet-mode` 规格「Pet Session Runtime Wiring」把唤醒依赖写成**主 loop**：

| 位置 | 现行规格字面 | 实现（change `0081` 起） |
|---|---|---|
| Requirement | 「…注入真实依赖：唤醒用的**主 loop**、记忆后端、受限探索工具集、安全边界与通知器」 | 组合根装配**宠物专属 loop**（受限 `ToolProvider` + 安全中间件） |
| Scenario THEN | 「唤醒复用运行系统的**主 loop**（非 echo 兜底 loop）执行自治任务」 | 唤醒经**专属 loop**（非 echo 兜底） |

**成因**：`0081` 的用户裁决是「**专属 loop 真强制**」——共享主 loop 时受限工具集与安全边界
**都不在路径上**（R11/R12 无生产落点）。裁决落地后规格原字面即成陈迹。

**旁证：这不是本仓常规，而是措辞孤例。** `beast-mode` 规格**明文**写「神兽以独立 `LoopPlugin` 实例运行」；
`_agent_loop` / `_beast_loop` 亦均为专属 loop ⇒ 「真实 loop」在本仓本就**不**等于「主 loop」。

## 裁决

**规格向实现靠拢**（同 `0080` 先例，用户裁决）：`0081` 的专属 loop 已由用户明确裁定，
故订正规格字面，**零代码变更**。

## 变更

| 文件 | 动作 |
|---|---|
| `doc/openspec/specs/pet-mode/spec.md` | **MODIFIED**「Pet Session Runtime Wiring」：Requirement 的「主 loop」→「组合根装配的真实 loop（可为专属 loop，非 echo 兜底）」+ 追加一段口径说明（专属 loop 才承载 R11/R12；对比 `beast-mode` 明文独立实例）+ Scenario THEN 同步 |

## 明确不做

- **不改代码**：专属 loop 是 `0081` 的用户裁决，回退共享主 loop 会**撤销** R11/R12 的强制路径。
- **不改 `beast-mode` 规格**：其「独立 `LoopPlugin` 实例」字面**已与实现一致**（本次仅作对照引用）。
- **不改历史 ADR / archive**：`0081` 的 proposal/design/ADR-0077 忠实记录了裁决时的规格状态。
- **不加新场景**：既有「生产激活的宠物唤醒走真实 loop」场景订正措辞即足，行为面由
  TC-PET-03（工具面 = 白名单 / 专属 loop）与 TC-PET-04（越界阻断）锁住。
