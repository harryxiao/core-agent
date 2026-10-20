# Tasks — 0296 前台轮不被后台收尾与压实拖死

## 1. 规格与测试先行

- [x] 1.1 写 spec delta：loop（收尾/维护线程、轮内压实上限）、memory（压实 deadline +
  single-flight）、configuration（三键）、cli-ops（`--timeout`）
- [x] 1.2 新增 `tests/test_loop_foreground_liveness.py`：慢收尾不堵下一轮、收尾后台串行、
  `arun` 有界等待、截止后维护步骤跳过
- [x] 1.3 新增 `tests/test_memory_compaction_deadline.py`：截止前零调用、调用间停止、
  single-flight 跳过、截止后不提交摘要
- [x] 1.4 扩展配置/接线测试：三键三面与缺省、非法值阻断、后台 provider 注入、
  `loop.compact_timeout` 注入四个 loop
- [x] 1.5 扩展 CLI 测试：`memory maintain --timeout` 传截止时间、缺省值、非法值拒绝
- [x] 1.6 确认新增用例先红（实现前）

## 2. loop 实现

- [x] 2.1 删除 `_astream_events` 轮首 `_await_post_turn`；仍运行 ⇒ `post_turn_overlap` 留痕
- [x] 2.2 `_schedule_post_turn` 后台串行链（`asyncio.shield(previous)`、跨事件循环/已结束放行、
  完成后清理引用）
- [x] 2.3 `_await_post_turn(timeout=...)` 有界；`arun` 超时留痕 `post_turn_timeout` 并返回
- [x] 2.4 `_maintain` 总截止：每步前检查，截止记 `maintenance_failed{error: deadline_exceeded}`；
  `compact(deadline=...)`
- [x] 2.5 `_compact_bounded` 计算 deadline 传入 `_compact`；`_COMPACT_TIMEOUT_SECONDS` 60s

## 3. memory 实现

- [x] 3.1 `MemoryStore` 注入 `clock`；`compact(..., deadline=None)`
- [x] 3.2 `_summarize_sessions` / `_score_importance` 调用前检查截止
- [x] 3.3 single-flight 非阻塞锁 + 告警（只报「已在运行」）
- [x] 3.4 `memory/protocol.py` 的 `compact` 签名同步

## 4. 配置 / 运行时 / CLI

- [x] 4.1 `LLMConfig` 增加 `background_timeout` / `background_max_retries`；ConfigSpec 两条 + 校验
- [x] 4.2 `loop.compact_timeout` ConfigSpec + `_loop_errors` + 访问器
- [x] 4.3 runtime 构造后台 provider；`_llm_text` 改用之；四个 `DefaultLoop` 注入 compact_timeout
- [x] 4.4 `memory maintain --timeout`（缺省 120）、截止传参、截止提示

## 5. skills 并发

- [x] 5.1 `SkillLibrary` 增 `RLock`，覆盖注册 / 查询 / 列表 / 启停 / 删除 / 持久化 / 索引

## 6. 门禁与文档

- [x] 6.1 `uv run ruff check src tests` / `ruff format --check src tests` / `uv run pyright`
- [x] 6.2 `uv run pytest -q`（基线 3325 ⇒ **3367 passed**）
- [x] 6.3 反证 4/4（`cp` 到 `/tmp` + `md5sum` 复原；含技能库锁）：恢复轮首等待 ⇒ 解耦用例红；
  去掉 deadline 检查 ⇒ 调用间停止用例红；后台 provider 改回主 provider ⇒ 重试上限用例红
- [x] 6.4 `cd doc/openspec && openspec validate --all`
- [x] 6.5 ADR-0286 / known-risk E232 / test-cases §209 / 接口文档
- [ ] 6.6 归档 / 提交（**待用户确认**）
