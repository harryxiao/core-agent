# Tasks — 上下文淘汰的情景检查点（0310）

## 1. 规格与红灯

- [x] 1.1 写 `specs/context/spec.md`、`specs/memory/spec.md`、`specs/configuration/spec.md`
      delta（本目录）
- [x] 1.2 新增 `tests/test_context_checkpoint.py`：淘汰回写、只写新增区间、无新增零写入、
      工件聚合、脱敏有界、开关/无窗口零写入、失败降级、转录工件列往返
- [x] 1.3 新增 `tests/test_memory_checkpoint_watermark.py`：`-1`、取最大、跨层跨状态单调、
      只认本会话、坏标签跳过
- [x] 1.4 配置三面与归一用例（缺省开启、yaml/env/CLI、非法值归一、直接构造缺省关）
- [x] 1.5 跑新用例确认全红（`evicted_prefix` / `checkpoint_watermark` /
      `context_checkpoint` 构造参 / 配置键缺失）——21 红 + 收集期 `ImportError`

## 2. 实现

- [x] 2.1 `src/core/memory/transcript.py`：
      - `append(..., artifacts=())` 可选工件列（非空才写键）
      - `evicted_prefix(session_id, *, short_turns, mid_turns, short_tokens) -> (int, rows)`
      - `CHECKPOINT_TAG` / `CHECKPOINT_ID_PREFIX`（中立字面量，避免循环 import）
- [x] 2.2 `src/core/context/checkpoint.py`：纯函数摘要与工件聚合
      （`MAX_CHECKPOINT_CHARS=800` / `MAX_CHECKPOINT_LINE_CHARS=120` /
      `MAX_CHECKPOINT_ARTIFACTS=16` / `MAX_ROW_ARTIFACTS=8` / `MAX_ARTIFACT_CHARS=200`），
      导出到 `core.context`
- [x] 2.3 `src/core/memory/protocol.py` + `store.py`：`checkpoint_watermark(session_id)`
      （pyright 0 errors ⇒ 既有测试桩无需增补）
- [x] 2.4 `src/core/loop/default.py`：
      - 构造参 `context_checkpoint: bool = False`
      - `perceive` 写点 `_checkpoint_evicted`
      - assistant 转录行登记本轮工件（`_round_artifacts`，`file_write`/`file_patch` 的 `path`）
- [x] 2.5 `ConfigManager`：ConfigSpec `memory.context_checkpoint`（缺省 `True` 三面）+
      `context_checkpoint_enabled()`（非法值归一开）
- [x] 2.6 `runtime.py`：主 loop 注入 `context_checkpoint=config.context_checkpoint_enabled()`
      （子 Agent / 神兽 / 宠物 loop 不接，与 `transcript` 同一注入面）
- [x] 2.7 新用例转绿（43 passed）；全量 `uv run pytest` **3556 passed**

## 3. 门禁与反证

- [x] 3.1 `uv run ruff check`、`uv run ruff format --check`、`uv run pyright`（0 errors）
- [x] 3.2 反证（`cp` 到 `/tmp` + `md5sum` 复原），逐条至少一红（6/6）：
      - 去掉 `perceive` 写点 ⇒ 8 红；
      - 去掉水位增量（每次写全前缀）⇒ 1 红；
      - 去掉脱敏 ⇒ 1 红；
      - 去掉 `artifact:` 标签 ⇒ 1 红；
      - 水位过滤 `status=="active"` ⇒ 1 红；
      - 去掉开关门控 ⇒ 1 红
- [x] 3.3 `openspec validate 0310-context-checkpoint` 通过；`openspec validate --all`

## 4. 文档

- [x] 4.1 `doc/02-modules/memory.md`：转录工件列 + 检查点水位小节（§3.2.2 / §3.2.3）
- [x] 4.2 `doc/03-interfaces/memory-interface.md`：`TranscriptStore.append` / `evicted_prefix` /
      `checkpoint_watermark`；检查点条目形状
- [x] 4.3 `doc/03-interfaces/configuration-interface.md`：`memory.context_checkpoint` 行（§2.24）
- [x] 4.4 `doc/01-architecture/adr.md`：ADR-0300（淘汰检查点：确定性摘要 + 水位增量 + 工件列；
      被拒：LLM 摘要 / 转录 seq 列 / 全前缀回写）
- [x] 4.5 `coding-plan/known-risk.md`：E246 行（§1）+ ADR-0300 已知局限（§3）
- [x] 4.6 `doc/04-testing/test-cases.md`：§223（TC-CTXCP-01~13）
- [ ] 4.7 归档（用户确认后）+ 提交 + 推送
