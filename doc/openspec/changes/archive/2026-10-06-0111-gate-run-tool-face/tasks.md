# tasks — 质量门禁工具面（change 0111 / phase-27 切片 S1）

## 1. 规格（先行）
- [x] 1.1 `specs/tool-use/spec.md`：ADDED「质量门禁工具」——按门禁名触发 + 单一真源 `GATE_COMMANDS`
      + 执行器**注入**（工具层不依赖交付流水线层）+ 诚实 coeffect/不可逆走确认门 + 未知门禁 fail-closed（4 场景）
- [x] 1.2 `openspec validate 0111-gate-run-tool-face` 通过

## 2. 测试（先写，红）
- [x] 2.1 新 `tests/test_gate_run_tool.py`：工具定义契约 —— `tool_id == "tools.gate_run"`、
      `coeffects == ["process:spawn","filesystem:write"]`、`reversible is False`、schema `required == ["gate"]`、
      `enum == list(gates)`
- [x] 2.2 同文件：注入 fake runner（记录调用）⇒ 经 provider 调用返回结构化结果 `{gate, passed, reason}`
      （两向：通过 / 未通过含 reason）
- [x] 2.3 同文件：**确认门** —— 未批准 ⇒ `IRREVERSIBLE_BLOCKED`（runner **零调用**）；批准 ⇒ 执行
- [x] 2.4 同文件：**未知门禁 fail-closed** ⇒ `EXECUTION_FAILED` 且 runner **零调用**（enum 不被框住时的兜底）
- [x] 2.5 同文件：**真执行器 seam** —— `build_gate_executor(commands={…sys.executable…})` 注入，
      经 provider 走真 subprocess（通过 / 非零退出两例，不出网）
- [x] 2.6 新 `tests/test_gate_run_wiring.py`：`runtime.build_runtime` 后主工具面含 `tools.gate_run`，
      且其 schema 枚举与 `GATE_COMMANDS` 键**逐字一致**（单一真源）
- [x] 2.7 运行确认**红**（新增用例失败、既有用例全绿）

## 3. 实现
- [x] 3.1 `tools/builtin.py`：`gate_run(*, gates, run_gate)` —— 结构协议 `GateOutcome`（`passed`/`reason`）
      ＋ 处理器内白名单 fail-closed ＋ `asyncio.to_thread` 隔离阻塞 ＋ `timeout_s=660.0`
- [x] 3.2 `runtime.py`：`build_gate_executor()` + 门禁名→`Gate` 适配，注册进**主**工具面（`tools`）
- [x] 3.3 四门全绿（直连二进制，不用 `uv run`）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/tool-use-interface.md`：`tools.gate_run` 一行（§3 工具表）
- [x] 4.2 `doc/04-testing/test-cases.md`：TC-TOOL-xx
- [x] 4.3 `doc/01-architecture/adr.md`：ADR-0104 —— 门禁工具面（层级注入 / 单一真源 / 诚实 coeffect /
      **S2 改判**与两条判据订正留痕）

## 5. 收口
- [x] 5.1 手工归档（delta 合进 `doc/openspec/specs/tool-use/spec.md` + tick tasks + `shutil.move` 进
      `archive/2026-10-06-0111-gate-run-tool-face/`）
- [x] 5.2 `openspec validate --all` 全绿（30 passed / 0 failed；项数为 spec 文件数，不变）
- [x] 5.3 账本回填（`phase-27.md` §5.4 S1 勾选 + **S2 改判** + §3.2 订正；`README.md` §2 第 27 行状态列）
- [x] 5.4 记忆更新 + 提交（`feat(tool-use): …`，一个 Phase 一个 commit）
