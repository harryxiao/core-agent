# Tasks — 退化 JSON 的控制字符修复（change 0322）

## 1. 规格

- [x] 1.1 写 `specs/loop/spec.md` delta：MODIFIED「推理动作解析与失败可见」+ 2 条 Scenario
- [x] 1.2 `openspec validate 2026-10-24-0322-json-control-char-repair` 通过

## 2. 测试先行

- [x] 2.1 `tests/test_degenerate_json_repair.py` 增加事故原文复刻（裸换行，红）
- [x] 2.2 合法 JSON 含 `\n` / `\t` 转义零影响

## 3. 实现

- [x] 3.1 `planner.py`：`_repair_string_fragment` 增加控制字符转义支（`< 0x20`）
- [x] 3.2 既有边界不变：只插入转义、不补结构、采纳门槛沿用 0321

## 4. 验证

- [x] 4.1 新用例全绿；原先红用例转绿
- [x] 4.2 全量 `uv run pytest`
- [x] 4.3 `uv run ruff check .`、`uv run pyright` 全绿（ruff format 仅检查改动文件）
- [x] 4.4 反证：回退控制字符支 ⇒ 事故用例红；`cp` 复原后 `md5sum` 一致

## 5. 台账

- [x] 5.1 `adr.md`：ADR-0312 + 变更追踪行
- [x] 5.2 `known-risk.md`：E258 行
- [x] 5.3 `test-cases.md`：§235 用例与反证记录
- [x] 5.4 `doc/02-modules/loop.md` 解析协议描述订正

## 6. 归档

- [x] 6.1 `openspec validate --all` 全绿
- [x] 6.2 `openspec archive 2026-10-24-0322-json-control-char-repair -y`
- [ ] 6.3 仅暂存本 change 文件并提交（`fix(loop): 修复退化 JSON 的裸控制字符`）
