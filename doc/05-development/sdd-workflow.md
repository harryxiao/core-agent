# SDD 工作流与 OpenSpec 约定（SDD Workflow）

> 本文说明如何使用 **[Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec)** 进行规格驱动开发，
> 以及本仓库 `doc/openspec/` 目录与官方约定的对应关系。

---

## 1. OpenSpec 核心概念

| 概念 | 位置 | 说明 |
|---|---|---|
| **spec** | `openspec/specs/<capability>/spec.md` | 某能力"应该做什么"，含 Requirements + Scenarios |
| **change** | `openspec/changes/<id>/` | 一次变更提案，含 proposal/tasks/design/spec deltas |
| **delta** | change 下的 `specs/<capability>/spec.md` | 对现有规格的增量（ADDED/MODIFIED/REMOVED） |

---

## 2. 规格格式（spec.md）

```markdown
# <Capability> Specification

## Purpose
（一句话说明本能力解决什么问题）

## Requirements

### Requirement: <名称>
系统 SHALL <可验证的行为>。

#### Scenario: <场景名>
- **GIVEN** <前置状态>
- **WHEN** <触发动作>
- **THEN** <可验证结果>
```

**规则**：
- 每条 Requirement 至少 1 个 Scenario；Scenario 用 `GIVEN/WHEN/THEN` 描述。
- 用 **SHALL** 表达规范性要求（对应 RFC 2119）。
- Scenario 必须**可验证**——能直接映射为测试用例。

---

## 3. 变更格式（change）

```
openspec/changes/0001-bootstrap-core/
├── proposal.md      # 为什么做、做什么、影响范围
├── tasks.md         # 实施清单（勾选式）
├── design.md        # 技术方案与取舍（可选，复杂变更必写）
└── specs/
    └── <capability>/
        └── spec.md  # delta：## ADDED / ## MODIFIED / ## REMOVED
```

Delta 示例：

```markdown
# Plugin Registry Spec Delta

## ADDED Requirements
### Requirement: 插件可逆注册
系统 SHALL ...

## MODIFIED Requirements
### Requirement: （对现有需求行的修改）

## REMOVED Requirements
### Requirement: （被删除的需求）
```

---

## 4. 常用命令

```bash
openspec init --tools none  # 初始化：生成 config.yaml + specs/ + changes/ 骨架
openspec list               # 列出活动 change
openspec validate           # 校验规格与 change 格式
openspec show <change>      # 查看变更详情
openspec archive <change>   # 归档：把 delta 合并进 specs/，change 移入 archive/
openspec instructions apply # 输出应用变更的执行指令
```

---

## 5. 本仓库约定

- 规格唯一事实来源放在 `doc/openspec/specs/`；若启用 CLI，`openspec/` 目录与其同步。
- 变更编号：`NNNN-<kebab-case>` 递增。
- 每个 change 完成并验收后 `archive`，delta 并入 specs。

---

## 6. 关联

- 官方文档：OpenSpec `docs/writing-specs.md`、`docs/changes.md`
- 开发指南：`doc/05-development/development-guide.md`
- 首个变更：`doc/openspec/changes/0001-bootstrap-core/`
