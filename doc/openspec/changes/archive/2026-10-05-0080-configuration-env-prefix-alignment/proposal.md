# 0080 — configuration env 前缀口径订正（规格/文档 → 实现）

## 为什么

账本 **E24**：feature flag 的 env 前缀**实现为复数** —— `src/core/configuration/manager.py:169`
`_FEATURE_ENV_PREFIX = "CORE_FEATURES_"`（与 yaml 段名 `features` 同源）；而**规格**
（`configuration/spec.md`「功能开关（feature flag）」）、**接口**
（`03-interfaces/configuration-interface.md` §2.2）、**模块**（`02-modules/configuration.md` §3.3）
字面写**单数** `CORE_FEATURE_<模块>`。`doc/00-product/user-guide.md` 与
`coding-plan/cli-contract-baseline.md` 则写**复数**。⇒ 同一口径三处不一致；照规格字面使用时
`CORE_FEATURE_BEAST=false` **静默无效**（既不裁剪、也不报错，同 E20① 的「未知键静默」取向）。

## 裁决（用户）

**改规格与文档向实现靠拢** —— 零代码变更、零对外破坏（与 E7/E8 裁决同型）：

- 现有实现与段名自洽（`features` 段 ↔ `CORE_FEATURES_` 前缀）；
- 改名是**对外可观测**的破坏性变更（既有部署 / CI 里的 env 会失效），收益仅为「与规格字面一致」——不值得。

## 变更

| 文件 | 动作 |
|---|---|
| `doc/openspec/specs/configuration/spec.md` | **MODIFIED**「功能开关（feature flag）」：env 面 `CORE_FEATURE_<模块>` → `CORE_FEATURES_<模块>`；新增场景「env 面以复数前缀生效」 |
| `doc/03-interfaces/configuration-interface.md` | §2.2 三通道行与实际口径同步；⚠️「待裁决」注记改为 ✅ 已订正（含历史说明） |
| `doc/02-modules/configuration.md` | §3.3 `CORE_FEATURE_*` → `CORE_FEATURES_*` |
| `doc/01-architecture/adr.md` | ADR-0069 正文与「登记后续」的 E24 项标注为已关闭（change `0080`） |
| `tests/test_feature_flag_faces.py` | docstring 引用的通道清单同步为复数（**无代码变更**） |

**顺带修复（同一条 Requirement，写 delta 时发现）**：change `0072` 的 delta 给该 Requirement 追加过一段
正文（「三条输入通道 SHALL **全部生效**…取值 SHALL **三面同口径**…SHALL NOT 经 `bool()` **静默强转**」），
但**归档合并时丢失** —— 现行 spec 只剩它带来的 4 个场景（「常见假值写法归一为关闭」「非法取值校验期拒绝」
「CLI 面覆盖 yaml 与环境」…），正文仍只有一段。本次 MODIFIED 的正是同一条 Requirement，故一并**补齐**该段
（逐字取自 `0072` delta 原文），使 E20②/E23 的口径在**正文层**可追溯，而不只靠场景名暗示。

## 不动

- **零代码**：`src/` 一行不改。
- **不做单数兼容别名**：静默接受 `CORE_FEATURE_*` 会造出**第二个真源**（同一开关两种写法、冲突时谁赢无定论），
  且掩盖笔误（与 E20①「保持开放」的取向一致：宁可静默忽略未知键，也不引入隐式别名）。
- 门控名单、三面取值集合、优先级链、组合根单一真源等一概不动。

## 验证

- `openspec validate 0080-configuration-env-prefix-alignment` 通过 + `openspec validate --all` 全绿；
- 四门（ruff check / ruff format --check / pyright / pytest）—— 无代码变更，期望与基线**逐位一致**（959 passed）。
