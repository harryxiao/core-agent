# 0142 · core-profile 题词模板产出物（账本 E85）

> 账本：`coding-plan/phase-34.md` §2 **E85**（core-profile「题词规范 / 题词模板」doc-only，**无骨架文件、无专门测试**）
> 规格面：`core-profile/spec.md` **MODIFIED「题词模板」**（+1 Scenario）
> ADR：**0134**

## Why

`core-profile/spec.md`「题词模板」SHALL「提供 Core.md 题词模板（骨架）」，并以两 Scenario 定格
「全局级模板产出」「项目级模板产出」。但实现侧**没有任何模板产出物**（全仓 `find` 未命中模板文件、
无对应测试）⇒ 规格这条 SHALL 处于**不可验证、不可使用**状态：用户拿到 `Core.md` 的**唯一依据**
是题词规范（纯文字），且看不出分区标题必须逐字写成什么样。

这条 SHALL 的隐患不小 —— 分区标题是**运行时解析器**的判据（`profile.py:16-19`
`_SECTION_HEADERS`，未知标题落 `unknown`、空分区一并 ⇒ `SECTION_INVALID` 告警并**跳过该分区**）：
用户若凭直觉写「## 宪法」或「## 人格设定」，整段预设会被**静默跳过**（规格「格式非法告警跳过」
允许跳过 ⇒ 用户往往察觉不到）。所以模板不能只是「一份看起来像样的示例」，而须**与解析器逐字对齐**。

## What

**规格先行**：把「提供模板」从**无形合约**落为**具体产出物 + 可断判据**（MODIFIED「题词模板」）：

1. **产出物具名**：仓库内 `templates/Core.global.md`（落向 `~/.core/Core.md`）与
   `templates/Core.project.md`（落向 `<project>/Core.md`）—— 两份**可直接复制**的骨架。
2. **逐字对齐解析器**：分区标题 SHALL 与 `_SECTION_HEADERS` 一致（`## 宪法与全局规则` /
   `## 人格` / `## 项目信息`）；新增 Scenario「骨架复制即被解析器接受」把这一点钉住
   （原文喂 `SectionParser` + `Validator` ⇒ 分区 kind 正确且**无 `SECTION_INVALID`**）。
3. **注入说明注释**（规格原文已要求）：各分区用 HTML 注释注明落向的运行时通道
   （`constitution:v1` coeffect / L0 记忆层 / ContextEngine 上下文）。注释形式是**有意的** ——
   解析器 `_is_content` 会跳过 `<!--` 与 `>` 开头的行，故说明不进注入内容。

**实现**：新增两个骨架文件 + `tests/test_core_profile_templates.py`（**无运行时代码变更** ——
模板是静态产物，测试即门禁）。

## 影响

- **零运行时影响**：不改 `src/`、不改既有 spec 条文语义（只在「题词模板」Requirement 上**追加**
  产出物与可断判据，两条既有 Scenario **逐字保留**）。
- **新目录** `templates/`（仓库根）：纯静态产物，不参与打包之外的任何运行时路径。
- **用户面收益**：复制骨架即得**可被解析**的两级 `Core.md`，不再有「标题写错 ⇒ 整段静默跳过」的坑。
- **红线不动**：不触 `exclude_source_prefixes=("beast.",)`、不触 `CoeffectResolver`「密钥只引用不读取」。

## 验证

- 新增 `tests/test_core_profile_templates.py`：① 两骨架存在；② 全局骨架含两分区标题、**不含**
  `## 项目信息`；③ 全局骨架原文解析 ⇒ `["constitution", "personality"]` 且 **零告警**；
  ④ 项目骨架原文解析 ⇒ `["project_info"]` 且 **零告警**；⑤ 分区注入说明注释含运行时通道关键字
  （`constitution:v1` / `L0` / `ContextEngine`）；⑥ 篇幅受控（各 ≤ 50 行，题词规范口径）。
- `.venv/bin/ruff check src tests` / `ruff format --check src tests` 全绿；`pyright` **0/0/0**。
- `.venv/bin/pytest -q` ⇒ **1680 passed**（1674 → 1680，+6）。
- `openspec validate --all` ⇒ 31 passed / 0 failed（归档后 30 / 0）。

## 风险与已知局限

- **骨架占位行是「内容行」**：解析器要求分区非空（空分区 ⇒ `SECTION_INVALID`），故骨架的示例/占位
  行（`- 必须：<…>`）**计入**注入内容 —— 用户复制后须改写或删除占位行；上游用「建议不超过 50 行」
  的篇幅约束兜底（注释已就地说明）。
- **不提供 CLI scaffold**：`core-agent profile init` 会改写文件（可逆副作用、覆盖语义）并触碰
  CLI 动词基线（30 动词 + 14 flag 的逐条 diff 断言），而本账只要求「提供模板骨架」⇒ YAGNI，
  取**静态产物**即可满足规格（若将来要 CLI 落盘，另立账）。
- **不新增 wiki/文档站入口**：模板的发现路径是仓库 `templates/` 目录本身与 `test-cases.md` §58 的
  交叉引用，不在本账补用户手册章节。
