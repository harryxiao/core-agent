# Proposal 0215 — 提示词文本 pin（测试，规格中性）

## Why（缺口）

控制面/数据面的提词**措辞**是模块私有常量（实现细节），而**全仓 `tests/` 对 9 条核心
prompt 头的引用数为零** —— 唯一的内容锚是 `tests/test_memory.py` 的 `build_prompt`
（`现有摘要` 槽 / 首尾保留 / 有界性）。后果：**任一条 prompt 头措辞被改（或误删一个约束句），
模型行为静默改变、无任何测试拦截**。对「抽取器只说 JSON 数组」「绝不输出密钥明文」
「谓词必须归入闭表白名单」这类**承重措辞**，漂移即**能力退化或安全面收窄**。

| prompt 头 | 落点 | 承重措辞（漂移即退化） |
|---|---|---|
| 关键事实抽取 | `memory/extract.py:_PROMPT_HEAD` | 只输出 JSON 数组 / 密钥一律 `<redacted>` / `ref` 只认 `coeffect:` |
| 实体关系抽取 | `memory/extract.py:_RELATION_PROMPT_HEAD` | 谓词**必须**归入闭表白名单 / 不归入不输出 |
| 会话摘要 | `memory/summarize.py:_PROMPT_HEAD` | 保留结论·决策·未决 / 只输出摘要不复述过程 |
| 重要度评分 | `memory/importance.py:_PROMPT_HEAD` | 只输出 0–1 数值 / 不解释 |
| SOP 提炼 | `skills/sop.py:_PROMPT_HEAD` | 只输出编号步骤清单 / 不复述轨迹 |
| 技能迭代 | `skills/iteration.py:_PROMPT_HEAD` | 针对失败给更稳健步骤 / 不复述原文 |
| 主推理规划 | `loop/planner.py:_SYSTEM_PROMPT` | 二选一输出格式 / 工具 JSON **单独成块**且不用围栏 |
| 任务拆解 | `orchestration/planner.py:_DECOMPOSE_SYSTEM` | 2–6 子任务 DAG / 只输出 JSON / 不伪造依赖 |
| 验收判定 | `orchestration/planner.py:_VERIFY_SYSTEM` | 只输出 JSON / 未达标准判 false |

## What Changes

**零 `src/` 改动**，新增 `tests/test_prompt_pinning.py`（12 个用例）＋ ADR-0205。

**两类锚**：

1. **逐字头（9 条）**：把每条 prompt 头常量**独立副本**逐字比较 —— 任一字符改动即红。
   头 = prompt 的**身份句**（首句「你是……器。」）＋ 该条独有的**承重措辞**（JSON 形状 /
   脱敏规则 / 引用规则 / 步骤清单约束 / 块内不得混写）。
2. **结构不变量（3 条）**：经各 `build_*` 渲染函数验证**槽位序**（头恒在首位、条目行 `- ` 前缀）、
   **模板占位符解析**（`{max}` / `{predicates}` 在渲染产物中**消失且取值正确**、谓词白名单全量出现）、
   **节选有界**（超长正文在任何 builder 里都被截到当条上界，prompt 不爆炸）。

**规格中性判定**：pin 的是**实现细节**（模块私有常量），是**既有行为的回归护栏**而非新行为；
把 prompt 措辞升进规格即**过约束**（措辞非对外契约，规格约束的是「抽取/归纳**发生**及其产物形状」）。
沿 `0156` / `0189` / `0195` / `0199` 先例 ⇒ 无 spec delta，`.openspec.yaml` `skip_specs: true`。

**反证（门禁非空过的证明）**：逐条**临时改一字符**并确认对应用例转红，复原后 `diff -q` 逐字节同。
