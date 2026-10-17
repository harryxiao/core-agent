# Change 0255 — 技能提炼的确定性质量门与字段上界（P1）

## Why

记忆写回卫生审计（change `0254` / ADR-0245）收口了 P0 的脱敏 / 有界 / 空值 / 陈旧问题，但
**进化侧的内容质量**仍有缺口：SOP 提炼达阈值即自动 `active` 发布，唯一的发布前质量门
（`SopGate`，0198）**缺省不启用**（仅在 JEV 配置时注入）—— 缺省部署下，模型产出的**单步、
超短或与既有技能完全重复**的文本会直接成为可路由技能；同时 `SkillLibrary.register()` 只校验
`skill_id` 非空与 `param_schema` 为 dict，**无任何字段上界**，模型 / 下载内容可不限量入库
（evolution 侧另有一份 `validate_skill_content` 上界，两处口径各写各的）。

## What Changes

- **确定性发布门（缺省开启、零模型调用）**（`src/core/skills/sop.py`）：
  - 非空（既有）；正文 ≥ 10 字符、≤ 4000 字符；
  - 至少 **2 个步骤行**（行首 `1.` / `1)` / `1、` / `-` / `*` / `•` 后接非空内容）；
  - 与技能库中**任一**技能 `instructions` 逐字相同（strip 后）⇒ 视为重复，不入库。
  - 未过 ⇒ 不入库 + 清组 + 留痕（**只报组键，绝不回显正文**），与既有质量门失败路径同构。
  - 注入的判定质量门（`SopGate`）语义不变：在确定性门**之后**执行，未过同样清组留痕，
    判定异常 / 缺答案仍 **fail-open**。
- **技能库字段上界**（`src/core/skills/library.py`、`models.py`）：
  - `register()` 校验 `instructions` ≤ 4000、`description` ≤ 400、`task_types` ≤ 16 项
    （每项 ≤ 80）、`preconditions` ≤ 8 项（每项 ≤ 200）、`skill_id` ≤ 120；越界 ⇒
    `INVALID_SKILL_SCHEMA`，**不新增 / 不覆盖**。
  - 上界常量在 `skills.models` **单一定义**，`evolution.content` 改为引用同一组常量
    （消除两套口径漂移；evolution 已依赖 skills，方向不变）。
- **测试基线变更（有意）**：既有 SOP 用例中返回**单步**文本的桩改为两步（质量语义升级）。

## 影响面

- 规格：`skills` 「原子技能库」**MODIFIED**（字段上界 + 1 scen）、「SOP 提炼」**MODIFIED**
  （确定性门 + 重复拦截 + 2 scen；既有 10 场景名全部保留）。
- 代码：`src/core/skills/{models,library,sop}.py`、`src/core/evolution/content.py`。
- 测试：新增 `tests/test_skill_extraction_quality.py`；`tests/test_skills.py` /
  `tests/test_skill_retirement.py` 的单步桩改为两步。
- 缺省行为：**有意变更** —— 缺省发布路径多了确定性门（单步 / 超短 / 重复不再入库）；
  满足条件的多步 SOP 发布路径逐字不变；不新增配置键、不新增模型调用。

## 不做

- 不做**语义**去重（embedding 相似度 / 模糊匹配）—— 只拦**逐字相同**，阈值化相似度需新依赖
  与新判定面，另行提案。
- 不改 JEV 判定门的注入条件与 fail-open 语义。
- 不改 evolution 的提案 / 验证 / 留出评测链路；只把其内容上界常量改为同源。
