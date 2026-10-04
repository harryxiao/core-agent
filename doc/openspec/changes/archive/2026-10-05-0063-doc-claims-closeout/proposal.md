# 文档承诺订正与已知语义登记（doc-claims-closeout）

## Why

账本三条**文档层**项，性质都是「文档写的与事实不一致」，且**规格本身不背这个锅**——偏差全在
模块文档 / 接口文档层：

1. **A6 观察窗口按 target 覆盖**：`ObservationRegistry.open` 对同一 target **覆盖**旧窗口
   （基线重置、旧样本丢弃，`observation.py:53-57`）。这是**有意语义**（判「当前那次发布是否回归」），
   但接口文档从未写明，读者会当成「历史样本丢失」的缺陷。
2. **E13 `Validator.parse_output` 零生产调用方**：规格「输入输出校验」要求「调用后把自由文本解析为
   结构化指令，解析失败绝不带病执行」——但接口文档只有一句「仍无生产调用方（planner 自解析）**」，没写
   清**为什么**，读者会读成「实现未用 = 遗漏」。**一手核实**：该 Requirement 的生产实现是
   `LLMPlanner._parse`——**动作感知**解析，失败即产出终止 Action（工具不执行）并把失败原因回灌下一轮，
   正是规格场景的「不执行，请求模型修正」。`Validator.parse_output` **无动作语义**（判不了
   `tool_id`/`reply` 契约），接进 planner 反而**降级**——即「不该用」而非「没用上」。
3. **E19 durability「持久化故障降级」未实现**：`doc/02-modules/durability.md:74` 承诺
   「降级为内存环形缓冲 + 异步重试落盘」，而 `CheckpointStore._persist` **直接抛出**。**用户裁决**：
   订正文档承认现状（**不**实现该降级路径——静默降级会掩盖磁盘满）。

三条都**无代码缺陷**（A6 有意、E13 有意、E19 现状更安全），缺的是把事实写进文档。

## What Changes

- `doc/03-interfaces/evolution-interface.md` §3.1：新增「重发布即重开窗」一行，登记为**有意语义**
  （判当前发布是否回归；跨版本混池会使基线失义），并指明历史留痕的承载处（`dissolve` 教训条目 + 遥测）。
- `doc/03-interfaces/constraints-interface.md` §2：把「仍无生产调用方」的**一句断言**扩为**判定**
  ——规格该 Requirement 的生产实现是动作感知的 `LLMPlanner._parse`（含追踪号 `TC-CONS-05`）；
  `parse_output` 有意保留为中间件契约的输出侧 API，不接线。
- `doc/02-modules/constraints.md`：§3.1「输出校验」与 §5「输出解析失败」两行指向生产实现（planner），
  写明本模块 `parse_output` 有意不接线。
- `doc/04-testing/test-cases.md`：补 `TC-CONS-05`（规格「输出解析失败不执行」→ 用例可达），
  指向 `tests/test_phase13.py::test_llm_planner_parse_failure_error_code` /
  `::test_planner_native_tool_call_bad_arguments`。
- `doc/02-modules/durability.md` §5：把「降级为内存环形缓冲 + 异步重试落盘」改为**实际策略**
  ——持久化故障不静默降级（直接抛结构化错误，由上层断点续跑承接；检查点在波次/轮次边界，不在主循环热路径）。

## 规格中性（`.openspec.yaml: schema: spec-driven + skip_specs: true`）

三处订正**均不改规格行为**：

- **A6 / E13**：规格（evolution 观察窗口、constraints「输入输出校验」）、源码、测试三者**本就一致**，
  本变更只补**接口文档的解释**与**追踪号**。
- **E19**：**规格里从来没有**「环形缓冲 + 异步重试」这条——已逐字核对
  `doc/openspec/specs/durability/spec.md`（只有「崩溃恢复 / 原子提交 / 检查点损坏降级」），
  过度承诺仅存在于 `doc/02-modules/durability.md`。故**无规格可订正**，改的是模块文档。

## 明确不做

- **不实现 E19 的环形缓冲 + 异步重试**：用户裁决「订正文档承认现状」。静默降级会**掩盖**磁盘满
  （把「写失败」伪装成「已持久化」），与「已持久化结果不丢失」的规格精神相悖；检查点不在主循环热路径，
  失败向上传播由断点续跑承接即可。
- **不把 planner 的输出解析下沉到 `Validator`**：`parse_output` 无动作语义，下沉即**降级**（见 Why 2）。
- **不为 E13 改 `loop`/`constraints` 源码或规格**：现状即正确形态。
- **不为「重发布覆盖」新增历史留痕存储**：用户已按「维持现状 + 文档标注」关闭（A6），
  审计需求未出现前不预造存储（CLAUDE.md §2）。
- **零 `src/`、零 `tests/` 改动**（纯文档；追踪行只登记**既有**测试）。
