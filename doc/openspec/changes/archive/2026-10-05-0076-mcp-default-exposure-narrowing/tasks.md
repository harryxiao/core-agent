# tasks — MCP 默认暴露面收窄（change 0076）

## 1. 测试先行（红）
- [x] 1.1 `tests/test_mcp_default_exposure.py` 新建：默认面 = 纯本地只读（`file_read` + 未声明 coeffect 的 `list`）；
      `web_fetch`（`network:outbound`）与 `delegate`（`agent:delegate`）**不在**默认面
- [x] 1.2 白名单仍可开放跨边界工具；默认面外的工具被调用 → `PERMISSION_DENIED`
- [x] 1.3 `tests/test_phase13.py` 增：真实 `tools.delegate` **声明** `agent:delegate`，且未被默认面暴露
- [x] 1.4 红证：实现前 `test_mcp_default_exposure.py` **3 failed / 1 passed** —— 默认面含
      `core.tools.delegate` 与 `core.tools.web_fetch`（且调 delegate 落到 `COEFFECT_MISSING` 而非
      `PERMISSION_DENIED`，证明其穿过暴露面）；先绿的 1 例是白名单路径（本就与默认面无关）

## 2. 实现（绿）
- [x] 2.1 `src/core/mcp/server.py`：`_is_readonly` → `_is_default_exposed`（`coeffects ⊆ {"filesystem:read"}`，
      空集通过）+ 模块常量 `_DEFAULT_EXPOSED_COEFFECTS`
- [x] 2.2 `src/core/runtime.py`：`tools.delegate` 补 `coeffects=["agent:delegate"]` + resolver 注册该 coeffect
- [x] 2.3 绿证：全量 pytest **940 passed**（基线 936）；四门全绿（ruff check / ruff format / pyright 0 error）

## 3. 规格
- [x] 3.1 `mcp` spec delta：MODIFIED「工具暴露与白名单」—— 写实「默认最小暴露」判据 + 新场景「默认面排除跨边界工具」
- [x] 3.2 `openspec validate 0076-mcp-default-exposure-narrowing` 通过

## 4. 文档
- [x] 4.1 `doc/03-interfaces/mcp-interface.md` §6：默认暴露面判据（只读且无跨边界 coeffect）
- [x] 4.2 `doc/02-modules/mcp.md` §4：暴露面行 / 错误表补一行
- [x] 4.3 `doc/01-architecture/adr.md`：ADR-0073 + 变更追踪行
- [x] 4.4 `doc/07-mcp-server/mcp-server.md` §9 P2 行同步
- [x] 4.5 `doc/04-testing/test-cases.md`：TC-MCP-12

## 5. 收口
- [x] 5.1 `coding-plan/phase-19.md`：§1 表 B7 行、§0 结论、§4 B7 段（→ 已关闭块）、§9 第 5 项、§4 表头计数
- [x] 5.2 `coding-plan/README.md`：行 49 / 82 同步
- [x] 5.3 手动归档（合并 delta + 移动目录）+ `openspec validate --all` 全绿
- [x] 5.4 记忆更新 + 提交
