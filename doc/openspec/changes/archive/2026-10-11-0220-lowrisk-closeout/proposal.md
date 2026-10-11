# Proposal 0220 — 提词收紧轮低风险收口（strip_fence 兜底 / 镜像门禁 / ⑧ 微调，规格中性）

## Why（缺口）

2026-10-11 提词收紧轮（提交 `1f93b88`）落地 10 条提词 ＋ 2 处代码后，`coding-plan/Pending-Arbitration.md`
登记了 7 项待裁决（`PA-01`~`PA-07`）。其中**三项为低风险收口**，本轮一并做掉：

- **PA-04**：`evolution.author.strip_fence` 的正则只匹配「**整体**被围栏包裹」；模型输出「说明 ＋
  围栏」时说明文字会被原样写进 `.py` ⇒ 语法错误、白耗一轮进化。
- **PA-05**：`doc/03-interfaces/prompts.md` 自称「现状快照（镜像）」，但 `tests/test_prompt_pinning.py`
  只钉「常量 ↔ 逐字副本」两处，**不读镜像** ⇒ 第三处（镜像）漏改无声、评审依据失真。
- **PA-06**：`memory/episodic.py` ⑧ 的「教训」段易写成「下次小心」类空话，而该段会被 loop 的
  「既往失败教训」块**直接注入规划器** ⇒ 空话直灌推理面。

## What Changes

1. **PA-04（`evolution`，代码）**：`strip_fence` 增兜底 —— 整体匹配失败时取**最后一个**围栏块
   （同 `loop/planner._trailing_json_object` 的「只认尾部」思路）。新增 `_FENCE_ANY` ＋ 4 条测试。
2. **PA-05（测试，零 `src/`）**：新增 `tests/test_prompt_mirror.py` —— 逐条取模块常量，断言其
   **每一非空行**都出现在 `prompts.md`（⑤⑥ 先去 `.format()` 转义取渲染形态）。14 用例。
3. **PA-06（`memory`，提词）**：`episodic._PROMPT_HEAD` 教训段加「须写成**可复用的判据**，
   而非「下次小心」这类空话」；同步 pin 逐字副本 ＋ `prompts.md` 镜像。

**规格中性判定**：PA-04 是 author 适配器的**解析兜底**（`evolution/spec.md` 无 `strip_fence` 条，
grep 无「围栏」）；PA-05 是**测试**（零 `src/`）；PA-06 是 **prompt 措辞**（模块私有实现细节）。
三者皆无 spec delta ⇒ `.openspec.yaml` `skip_specs: true`（沿 `0156`/`0189`/`0195`/`0199`/`0215`/`0219`）。

## 显式不做

- **PA-01 / PA-02 / PA-03 不在本 change**：各自独立走 change（`PA-01` 尤其须新 ADR 承接旧测试语义）。
- **PA-07（本轮 change/ADR/台账登记）单列**：它是把已提交的 `1f93b88` 挂上 change 号，不与本 change 混。
- **⑦ 重要度提词微调不做**：牵动 `W_IMPORTANCE` 权重分布，须先有真实样本分布观测。
