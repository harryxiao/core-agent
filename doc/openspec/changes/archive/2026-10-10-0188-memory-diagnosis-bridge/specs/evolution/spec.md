# evolution Specification Delta — 记忆面 → 诊断面桥（change 0188）

## MODIFIED Requirements

### Requirement: 对比诊断
系统 SHALL 把缺陷定位到单个插件级别，作为进化闭环的起点；SHALL 接受**可选的目标先验**
（来自课程）作为**并列裁决**输入。

- **先验并入分数、不取代证据**：每条失败证据计 1.0；先验按注入权重（< 1.0）并入同一分数表
  ⇒ 证据恒优先，先验的**唯一**效果是解并列。
- **无先验时行为不变**：仍按「唯一最高分归因，并列则转人工」判定。
- **显式目标不经竞争**：人/宿主显式指定的目标 SHALL 直接作为本轮目标（见「冷路径驱动」），
  不参与本条的分数竞争。
- **已沉淀失败摘要 SHALL 可用时并入报告**：诊断器 SHALL 接受**可选**的失败摘要查询接缝
  （依赖倒置注入的可调用体，**非** import），对**每条失败 trace** 以 `loop.failure.<trace_id>`
  取回已沉淀的 L2 失败摘要并并入 `DiagnosisReport.failure_notes`。该并入 SHALL **有界**
  （单条截断、总数封顶）且 SHALL NOT 改变 `target_plugin` / `confidence` / `evidence` / `issue`
  的判定 —— 桥只**增补**证据面。缺省**未接线** ⇒ 报告 `failure_notes` 恒空、诊断与既往
  **逐字一致**；查询**抛错** ⇒ **降级**（该 trace 无摘要），诊断不中断。

#### Scenario: 归因到插件
- **GIVEN** 一批任务 trace 含失败证据
- **WHEN** Diagnoser 运行诊断
- **THEN** 输出 DiagnosisReport，归因到 target_plugin（None 表示系统级）

#### Scenario: 无插件级归因则人工介入
- **GIVEN** 诊断无法归因到单一插件
- **WHEN** target_plugin 为 None
- **THEN** 转人工处理，不进入提案阶段

#### Scenario: 先验解并列
- **GIVEN** 两个插件各有 1 条失败证据（分数并列），且先验指向其中 A
- **WHEN** 诊断
- **THEN** 归因到 A（无先验时该情形仍转人工）

#### Scenario: 已沉淀失败摘要并入诊断报告
- **GIVEN** 一条失败 trace，其 `loop.failure.<trace_id>` 已沉淀在 L2，且诊断器已接上失败摘要查询接缝
- **WHEN** Diagnoser 运行诊断
- **THEN** 报告 `failure_notes` 含该摘要（有界），而归因（`target_plugin` / `confidence`）
  与未接线时**一致**；**未接线**或查询抛错时该字段为空、诊断照常产出
