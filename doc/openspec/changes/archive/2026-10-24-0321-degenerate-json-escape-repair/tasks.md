# Tasks — 退化 JSON 的转义与内引号修复（change 0321）

## 1. 规格

- [x] 1.1 写 `specs/loop/spec.md` delta：MODIFIED「推理动作解析与失败可见」+ 3 条 Scenario
- [x] 1.2 `openspec validate 2026-10-24-0321-degenerate-json-escape-repair` 通过

## 2. 测试先行

- [x] 2.1 新增 `tests/test_degenerate_json_repair.py`：事故原文复刻（红）
- [x] 2.2 未闭合 + 非法转义仍失败（既有语义守卫）
- [x] 2.3 修复后无 `tool_id` / `reply` 不采纳（通用文案）
- [x] 2.4 合法 JSON 含转义引号 / 反斜杠解码逐字不变

## 3. 实现

- [x] 3.1 `planner.py` 新增 `_repair_degenerate_json_literals()`（字符串感知单遍扫描）
- [x] 3.2 `_parse` 在既有恢复链之后、失败动作之前调用；采纳门槛按 D3
- [x] 3.3 不补括号 / 不补缺失引号 / 不删改已有字符

## 4. 验证

- [x] 4.1 新用例全绿；原先红用例转绿
- [x] 4.2 全量 `uv run pytest`
- [x] 4.3 `uv run ruff check .`、`uv run ruff format --check .`、`uv run pyright` 全绿
- [x] 4.4 反证 3/3（删除修复调用 / 关内引号修复 / 去掉门槛），`cp` 复原后 `md5sum` 一致

## 5. 台账

- [x] 5.1 `adr.md`：ADR-0311 + 变更追踪行
- [x] 5.2 `known-risk.md`：§3 E257 行
- [x] 5.3 `test-cases.md`：§234 用例与反证记录
- [x] 5.4 `doc/02-modules/` 相应模块文档订正（如有解析协议描述）

## 6. 归档

- [x] 6.1 `openspec validate --all` 全绿
- [x] 6.2 `openspec archive 2026-10-24-0321-degenerate-json-escape-repair -y`
- [ ] 6.3 仅暂存本 change 文件并提交（`fix(loop): 修复退化 JSON 的转义与内引号`）
