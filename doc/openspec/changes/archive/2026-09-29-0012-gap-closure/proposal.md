# Change: 缺口闭合补全（沙箱颗粒度 / 评测基建 / 审批分级 / 多模态输入）

## Why

全量走查审计报告 §4.2 识别 4 条 P 级缺口，均属"概念层已有、工程层缺失"：
- **P1 沙箱执行颗粒度**：permission/spec.md 的沙箱隔离仅概念层（"独立沙箱执行+销毁"），未展开执行域隔离与网络/资源约束，无法对齐 Devin/Manus 云端 VM（browser+terminal+FS 全隔离）与 Claude Code bash 沙箱的工程化规格。
- **P2 评测/eval 平台**：evolution/spec.md 的留出评测未工程化，验证门缺可落地评测基建，无法对齐 OpenAI Agents eval / LangSmith eval。
- **P3 HITL 审批颗粒度**：permission/spec.md 的"人工审批流"未展开 approve/reject/edit-plan 分级与路由，审批流交互协议缺失，未对齐 Claude Code permission 规则与 OpenAI HITL 粒度。
- **P4 多模态/语音**：ui/spec.md 完全缺失多模态输入，未对齐 OpenAI Agents voice / Manus/Claude Code 图像输入。

## What Changes

- **permission**：追加「沙箱执行颗粒度」（P1）与「审批动作分级协议」（P3）两条 Requirement。
- **evolution**：追加「评测基建」（P2）一条 Requirement。
- **ui**：追加「多模态输入」（P4）一条 Requirement。
- 各当前 spec 的 Purpose 段同步纳入新内容（双向改动）。

## Impact

- **Affected specs**：`permission`（+2 Requirement）、`evolution`（+1）、`ui`（+1）
- **Affected docs**：无（spec 补全；审计报告 §6 已列修复方向）
- **Affected code**：无
- **Dependencies**：对齐设计全面性评估报告 §4.2 缺口表；与 audit 报告 §6 修复项一致
