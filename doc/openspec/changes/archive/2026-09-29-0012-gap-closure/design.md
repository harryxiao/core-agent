# Design

## Context

审计报告 §4.2 识别的 P1~P4 缺口均为"概念层已有、工程层缺失"：permission 沙箱仅概念层、evolution 评测未工程化、permission 审批未展开、ui 多模态缺失。本 change 以 delta spec 补齐四条 Requirement，本 design 固化各缺口落地决策，作为 spec 与审计报告 §6 修复项的映射依据。

## Decisions

- **沙箱执行颗粒度（P1）**：沙箱按执行域（终端/浏览器/文件系统）三域隔离，域间数据流经显式通道；网络出站白名单拦截、资源配额（CPU/内存/磁盘）超限终止回收返回 QUOTA_EXCEEDED、文件系统按授权清单粒度授予只读/读写。
- **审批动作分级（P3）**：人工审批细化为 approve/reject/edit-plan 三动作；edit-plan 提交修订后形成新审批单、原单标记 superseded；按风险等级路由，高危二次确认。
- **评测基建（P2）**：提供基准集 + 评测运行器 + 指标对比基线；候选通过验证门后在留出集批量评测，与基线对比判定 publish/rollback，指标差异归档供诊断归因。
- **多模态输入（P4）**：图像与语音统一接入，转写/理解后并入上下文；模型不具备某模态能力时明确提示并给替代建议，不静默丢弃。
- **规格追踪**：四缺口各对应 delta 一条 Requirement，Scenario 逐一对齐审计 §6 修复方向，使缺口可验收。

## Risks / Trade-offs

- **逐字一致**：delta 的 Requirement 正文与当前 spec 逐字一致，否则 validate 校验脱节。
- **无代码变更**：本 change 仅补规格与设计文档（Affected code = 无），工程实现落地依赖后续任务；design 只固化契约，不引入实现假设。

## Open Questions

- 沙箱三域（终端/浏览器/文件系统）底层实现选型（容器 vs VM vs 进程级）未定，待实现期明确。
- 评测基准的数据集格式与指标口径（与 evolution-interface.md 的 metric 结构对齐）待实现期细化。
