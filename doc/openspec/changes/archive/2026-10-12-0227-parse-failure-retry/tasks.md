## 1. Specification
- [ ] 1.1 spec delta `specs/loop/spec.md`：MODIFIED「推理动作解析与失败可见」——成因措辞条款扩到
  `{` 开头类（复用形态 4/5 判据 + finish_reason）＋ 新增回喂重试段（配置门 / 失败门 / 外发门 /
  恰一次 / nudge 约束 / 缺省关逐字不变）＋ ADDED 6 Scenario；既有 8 Scenario 逐字保留。
- [ ] 1.2 `openspec validate 2026-10-12-0227-parse-failure-retry` 全绿。

## 2. Tests（先红）
- [ ] 2.1 `tests/test_loop_output_protocol.py` 增 3 用例：`{` 开头未闭合载荷按 finish_reason
  区分成因（length⇒截断 / 无信号⇒未闭合）；`{` 开头闭合对象后仍有正文 ⇒ EMBEDDED 措辞；
  皆不命中 ⇒ 通用文案逐字。
- [ ] 2.2 新 `tests/test_parse_retry.py`：`_complete` 路径 —— ①失败门命中 ⇒ 恰两次模型调用、
  nudge 追加、第二次可解析 ⇒ 正常动作；②第二次仍失败 ⇒ reply 为第二次失败文案（恰两次）；
  ③缺省关 ⇒ 恰一次调用逐字；④astream 路径已外发 reply 增量 ⇒ 不重试（恰一次）；
  ⑤astream 缓冲路径（`{` 开头退化）⇒ 重试且对外只有第二次的动作；⑥nudge 不含原始退化文本。
- [ ] 2.3 配置面（并入 2.2 或独立）：三面声明（yaml/env/CLI）、缺省 False、非法值阻断
  （`_loop_errors`）、访问器归一化。
- [ ] 2.4 提词三处：`_RETRY_NUDGE` 常量 → `tests/test_prompt_pinning.py` 逐字副本 →
  `prompts.md` ⑮ 行 ＋ `test_prompt_mirror.py` 落点表 ①~⑮ ＋ 覆盖断言扩展。

## 3. Implementation
- [ ] 3.1 `planner.py`：`_RETRY_NUDGE`/`_retryable`/`_retry_nudge`/`_first_brace_reply`；
  `_parse` 的 `{`-first 失败分支接 `_first_brace_reply`；`_complete` 拆两 attempts；
  `astream` 拆 `_astream_once`（nudge/allow_retry）；构造参 `parse_retry`。
- [ ] 3.2 `manager.py`：`loop.parse_retry` ConfigSpec ＋ 访问器 ＋ `_loop_errors` bool 校验。
- [ ] 3.3 `runtime.py`：`parse_retry` 算一次注入四个 planner。
- [ ] 3.4 `doc/03-interfaces/prompts.md`：⑮ 行（注意 planner.py 行号变化 ⇒ §1 落点列
  planner 各行同步）。

## 4. Verification
- [ ] 4.1 四门禁直连二进制全绿（ruff check / ruff format --check / pyright 0-0-0 / pytest -q）。
- [ ] 4.2 `openspec validate --all` 全绿。
- [ ] 4.3 反证：摘 `_retryable` 判据中的前缀条件 ⇒ 重试门测试红；摘 `_first_brace_reply`
  接线 ⇒ 成因区分测试红；摘 `parse_retry` 缺省（改 True）⇒ 缺省关测试红。复原 ⇒ md5 同。
- [ ] 4.4 手工归档 ＋ 台账回填（E164 / ADR-0217 / §140 / 测试基线 2542→2560±）＋
  `known-risk.md`/`test-cases.md`/`retrospective.md` ＋ 单次提交。
