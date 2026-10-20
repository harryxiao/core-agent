# Tasks — 0297 动作 JSON 后的纯 JSON 注释对象

## 1. 规格与测试先行

- [x] 1.1 写 `specs/loop/spec.md` MODIFIED「推理动作解析与失败可见」
- [x] 1.2 新增 `tests/test_loop_output_protocol.py` 用例：
  动作 + `integrated_analysis` 对象执行；动作 + 注释数组执行；动作 + 第二动作失败；
  动作 + `reply` 对象失败；动作 + 注释 + 正文失败
- [x] 1.3 确认新增用例先红（实现前）

## 2. 解析实现

- [x] 2.1 新增 `_only_json_annotations(rest)`（严格完整值序列 + 顶层动作/终态字段排除）
- [x] 2.2 `_parse` 的 `{` 分支：首对象为动作且余部为纯注释 ⇒ 返回该动作
- [x] 2.3 其余分支（形态 3/4/5、`raw_output`、失败文案）零改动

## 3. 提示词

- [x] 3.1 `_SYSTEM_PROMPT` ② 补「不得追加第二段 JSON（含分析对象）」
- [x] 3.2 `_RETRY_NUDGE` 同步补一句
- [x] 3.3 `doc/03-interfaces/prompts.md` 同步

## 4. 门禁与文档

- [x] 4.1 `uv run ruff check src tests` / `ruff format --check src tests` / `uv run pyright`
- [x] 4.2 `uv run pytest -q`（基线 3367）
- [x] 4.3 反证（`cp` 到 `/tmp` + `md5sum` 复原）：去掉注释判据 ⇒ 新增执行用例红；
      放宽「第二动作」排除 ⇒ 第二动作用例红
- [x] 4.4 `cd doc/openspec && openspec validate --all`
- [x] 4.5 ADR-0287 / known-risk E233 / test-cases §210 / loop-interface
- [ ] 4.6 归档 / 提交（**待用户确认**；0296 亦待确认）
