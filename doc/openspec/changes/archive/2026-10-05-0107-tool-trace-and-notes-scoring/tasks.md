# tasks — 工具级 trace 接线 + notes 加权 + E31 裁决（change 0107）

## 1. 规格（先行）
- [x] 1.1 `specs/loop/spec.md`：MODIFIED「异步流式执行」——非终止动作完成后 SHALL 另行产出
      `kind="tool_call"` **工具调用遥测**（工具 id / 参数 / 成败 / 耗时，载荷有界）；SHALL NOT
      改变 `LoopEvent` 外发路径与既有消费语义；未注入 `tracer` 时不产出（+3 场景）
- [x] 1.2 `specs/evolution/spec.md`：MODIFIED「经验采集」——工具调用通道**须有生产方**；
      内部核心模块的 `plugin_id` = **归因对象身份**（SHALL NOT 蕴含注册表成员身份）；模块自身
      失败证据经 `module_id` 通道承载（+2 场景）
- [x] 1.3 `specs/notes/spec.md`：MODIFIED「canonical Markdown 真相层与可插拔后端」——`search`
      纯词法打分的**字段加权口径**（标题 3× / tags 2× / Search Queries 2× / 正文与 id 1×）（+1 场景）
- [x] 1.4 `openspec validate 0107-tool-trace-and-notes-scoring` 通过

## 2. 测试（先写，红）
- [x] 2.1 新 `tests/test_tool_trace.py`：注入真 `Tracer` 跑一轮含工具动作的 loop ⇒ 导出事件含
      `kind == "tool_call"` 且载荷为（工具 id / 参数 / `result.ok` / `latency_ms`）（**生产方接线**，E30）
- [x] 2.2 同文件：上述 trace 经 `_to_traces` ⇒ 产出 `task_type="tool_use"`、`plugin_id == 工具 id`
      的证据（**端到端**：skill 维度产线有输入）
- [x] 2.3 同文件：执行失败**仍**产遥测（`result.ok` 为假）；终止动作**不**产出 `tool_call`
      （与 `action_completed` 同判据）；未注入 tracer 不产出且本轮回复不变
- [x] 2.4 `tests/test_notes.py` 追加：标题精确命中排在**正文顺带命中**之前；tags / Search Queries
      权重高于正文（E32 加权）
- [x] 2.5 追加：加权不改过滤与返回结构（无命中仍空列表、既有用例全绿）
- [x] 2.6 运行确认**红**（新增用例失败、既有用例全绿）

## 3. 实现
- [x] 3.1 `loop/default.py`：ctor 建 `self._trace_logger = TraceLogger(tracer)`（tracer 缺省则 `None`）；
      `astream` 非终止动作分支在 `action_completed` 同点调用 `_log_tool_call(...)`；耗时抽成局部
      变量（`LoopEvent` 载荷逐字不变）
- [x] 3.2 `notes/backend.py`：`_score` 改分区加权（常量 + 字段表），docstring 同步
- [x] 3.3 `evolution/plugin_ids.py`：docstring 把「未纳入注册表」写成**裁决 + 重开条件**（不再是「欠账」）
- [x] 3.4 四门全绿（直连二进制，不用 `uv run`）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/observability-interface.md`：`tool_call` 事件的**生产方**口径
- [x] 4.2 `doc/03-interfaces/evolution-interface.md`：`plugin_id` = 归因对象身份（含 E31 裁决一句）
- [x] 4.3 `doc/02-modules/notes.md` §3.3：打分口径改「分区加权」
- [x] 4.4 `doc/01-architecture/adr.md`：ADR-0100（工具级 trace 生产方 + notes 加权 + 归因身份口径
      / E31 裁决）+ 末尾映射表行 + ADR-0099 已知局限②/⑤ 的「已由 ADR-0100 关闭」标注
- [x] 4.5 `doc/04-testing/test-cases.md`：TC-LOOP-09 / TC-EVO-09 / TC-OBS-08 / TC-NOTE-20

## 5. 收口
- [x] 5.1 手工归档（delta 合进 `doc/openspec/specs/{loop,evolution,notes}/spec.md` + tick tasks +
      `shutil.move` 进 `archive/2026-10-05-0107-tool-trace-and-notes-scoring/`）
- [x] 5.2 `openspec validate --all` 全绿（30 passed / 0 failed）
- [x] 5.3 账本回填（`phase-24.md` 验收勾选 + §0 现状列 + §6 收口；`phase-19.md` §5 **E30 关闭 /
      E31 改判** + §9 步 9 续报；`phase-21.md` §1.3/§1.4 转出账本同步 + 引用订正；`README.md` 第 24 行状态列）
- [x] 5.4 记忆更新 + 提交（`feat(...)`，一个 Phase 一个 commit）
