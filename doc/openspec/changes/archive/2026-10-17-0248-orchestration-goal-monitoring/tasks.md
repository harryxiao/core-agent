# Tasks — 目标监控（change 0248）

## 1. 模型与拆解

- [x] 1.1 `models.py` 新增 `DecomposeResult` 并从 `core.orchestration` 导出
- [x] 1.2 `Planner` 协议接受 `list[Subtask] | DecomposeResult`
- [x] 1.3 `decompose`：显式非空优先 / 否则取生成标准；`Plan.success_criteria` 落定
- [x] 1.4 `_DECOMPOSE_SYSTEM` 顶层加 `success_criteria`（2-5 条、可客观判定）
- [x] 1.5 `_parse`：标准解析（strip/去重/限 5）+ `depends_on` strip + 重复 id 首项保留
- [x] 1.6 `_fallback` 无标准

## 2. 任务级判定

- [x] 2.1 `_judge` / `_fail_closed` 提为模块级私有函数（两判定器共用）
- [x] 2.2 新增 `LLMTaskVerifier`（Goal + 标准 + outcomes 摘要；有界、脱敏；单次重试）
- [x] 2.3 `__init__` 导出 `LLMTaskVerifier`

## 3. 调度器

- [x] 3.1 `SuccessChecker` 三参签名；`_success_met` 改 async、接收 outcomes
- [x] 3.2 异常 / 非法返回 fail-closed；未达标接 0246 恢复回路
- [x] 3.3 `ProgressTracker` 增 `started` / `failed` 与 `progress()`；`start`/`record` 清 failed
- [x] 3.4 `_run_subtask` 派发前 `start`；`_guarded_subtask` 失败时 `fail`

## 4. 组合根与 prompt

- [x] 4.1 `runtime.py` 注入 `LLMTaskVerifier`
- [x] 4.2 `tests/test_prompt_pinning.py` 逐字副本同步
- [x] 4.3 `doc/03-interfaces/prompts.md` ② 正文与 ③ 落点行号同步

## 5. 规格与测试

- [x] 5.1 `orchestration` R6 MODIFIED（+3 Scenario）
- [x] 5.2 既有 planner 用例改取 `DecomposeResult.subtasks`；既有 checker 桩改三参
- [x] 5.3 新增：标准解析/去重/限条；显式标准覆盖；fallback 无标准；空白依赖与重复 id；
      runtime 注入；未达标重拆/耗尽 FAILED；判定器异常 fail-closed；三态计数
- [x] 5.4 四门禁 + `openspec validate --all` + 归档
- [x] 5.5 ADR-0236 / 台账 E183 / 测试节 §159 / 接口与模块文档
