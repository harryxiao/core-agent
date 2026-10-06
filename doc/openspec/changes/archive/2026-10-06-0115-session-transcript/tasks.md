# tasks — 对话转录落盘与会话历史回灌（change 0115 / phase-28 E49）

## 1. 规格（先行）
- [x] 1.1 `specs/memory/spec.md`：MODIFIED「分层记忆模型」——L4「原始会话」校正为「归档层」
      （消 canonical `:9` 与同文档 `:119/:131/:181` 及实现的**自相矛盾**）
- [x] 1.2 `specs/memory/spec.md`：ADDED「对话转录持久化（非记忆层级）」——按轮追加单文件 + 按会话读取 +
      **明写非 L0–L4 条目 / 不进 `MemoryStore.read` / 不参与温度分层·排名·`reuse_count`·压实·固化·遗忘**（5 场景）
- [x] 1.3 `specs/loop/spec.md`：MODIFIED「执行循环」——载入 `LoopContext.history`（双重上界）、
      请求次序「系统提示 → 历史 → 本轮消息」、历史 token 计入记账、收尾追加本轮 (user, reply) 且**合成终止不写**（+5 场景）
- [x] 1.4 `specs/configuration/spec.md`：MODIFIED「循环预算配置」——新增 `loop.history_turns`（缺省 `20`，三面可配，受校验）（+1 场景）
- [x] 1.5 `specs/ui/spec.md`：ADDED「会话转录的读取面」——`GET /session/{id}/messages` + 枚举附**派生** `title`/`updated_at`（4 场景）
- [x] 1.6 `specs/ui/spec.md`：MODIFIED「会话注册表持久化与跨入口共享」——创建互斥限定为**进程内**，跨进程据实列为已知局限
- [x] 1.7 `openspec validate 0115-session-transcript` 通过

## 2. 测试（先写，红）
- [x] 2.1 新 `tests/test_transcript.py` §存储：append→read 往返 + 跨实例（同 `tmp_path`）可见
- [x] 2.2 同文件：按会话过滤 + **反例守门**（B 读不到 A）
- [x] 2.3 同文件：`tail` 边界（`turns=0` / 大于总数 / token 切片截断 / 尾部未答 user 行保留）
- [x] 2.4 同文件：坏行跳过 / 缺文件降级；`summaries()` 的 title 截断、`updated_at`、**排除 `session_id == ""`**
- [x] 2.5 新 `tests/test_transcript_memory_boundary.py`：**反例守门** —— 转录不进 `MemoryStore.read` 结果（钉住「非记忆层级」）
- [x] 2.6 新 `tests/test_history_replay.py`：第二轮 `_build_request` 序列 = `[system, 历史 user, 历史 assistant, 本轮 user]`
- [x] 2.7 同文件：**四处 accessor 不被打破**（`_task_text`/`_echo`/`planner._task` 只见本轮；`_action_steps` 仍取 `messages[1:]`）
- [x] 2.8 同文件：历史 token 计入 `token_used`（spy）；`history_turns=0` ⇒ 零回灌；无 transcript ⇒ 逐字一致；`session_id==""` ⇒ 零回灌
- [x] 2.9 新 `tests/test_history_persistence.py`：一轮成功 ⇒ store 有 (user, reply) 两条
- [x] 2.10 同文件：**预算耗尽轮不落盘合成串**；`remember` 抛错 ⇒ 转录仍落（独立 try/except）；
      `perceive` 已落 user 行 + 后续抛错 ⇒ 该 user 行仍在
- [x] 2.11 `tests/test_serve.py` 增：`GET /session/{id}/messages` 正常 / 未登记 404；`GET /sessions` 富化后仍含
      `session_id`/`mode` 且**顶层形状不变**（空表 `{"sessions": []}` 逐字相等）
- [x] 2.12 `tests/test_session_registry.py` 增：多线程并发 `create` 不丢会话（进程内）
- [x] 2.13 `tests/test_loop_budget_config.py` 增：`loop.history_turns` 三面解析 + 非法值被拒；`loop_limits()` 仍返 2 元组

## 3. 实现
- [x] 3.1 新 `src/core/memory/transcript.py`：`TranscriptStore`（`append` 用 `os.open(O_APPEND)` + 单次 `os.write` 整行；
      `read` / `tail(session_id, turns, *, max_tokens)` / `summaries()`；`path=None` ⇒ 纯内存；坏行 `continue`）
- [x] 3.2 `src/core/loop/protocol.py`：`LoopContext` 增 `history: list[Any]`；对齐 `:111` `perceive` 签名漂移
- [x] 3.3 `src/core/loop/default.py`：`__init__` 增 `transcript` / `history_turns`；`perceive` 先载历史再落 user 行；
      收尾在 `:285` **之前**落 reply（门控 `limit_reason`）；两处各自 try/except 降级
- [x] 3.4 `src/core/loop/planner.py`：`_build_request` 插入 `_to_messages(ctx.history)`
- [x] 3.5 `src/core/configuration/manager.py`：ConfigSpec `loop.history_turns` + `history_turns()` 访问器 + 校验
- [x] 3.6 `src/core/ui/api.py`：`transcript` 注入 + `list_sessions` 富化 + `session_messages()` +
      `apply_llm_config(history_turns=)` 并同步 `_llm_patch` / `set_llm_config`
- [x] 3.7 `src/core/ui/fastapi_serve.py`：注册 `GET /session/{session_id}/messages`；「10 端点」→ 11
- [x] 3.8 `src/core/ui/sessions.py`：`create` 加 `RLock`；docstring 并发声明据实收窄
- [x] 3.9 `src/core/runtime.py`：读 `history_turns()` + 构造 `TranscriptStore`（`messages.jsonl`）**只注入主 loop**；`Runtime` 加字段
- [x] 3.10 `src/core/entry.py`：`_build_ui` 从 runtime 取 `transcript` 传给 `UIAPILayer`

## 4. 四门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`（须 0/0/0）
- [x] 4.4 `.venv/bin/pytest -q`（基线 1415 passed）

## 5. 端到端（离线，不触网）
- [x] 5.1 临时 `CORE_STATE_DIR` 起 `serve`：建 A/B 两会话 → A 发两轮 ⇒ `GET /session/A/messages` 4 条、
      `GET /sessions` 中 A 有 `title` 而 B 无
- [x] 5.2 切 B 发一轮 ⇒ B 的 prompt 不含 A 的历史、B 的转录独立
- [x] 5.3 跨进程：CLI 建会话 ⇒ `serve` 的 `GET /sessions` 可见、`GET /session/<cli-id>/messages` 可读
- [x] 5.4 兼容回归：`session_id == ""` 路径与未注入 transcript 的调用逐字不变

## 6. 文档 / ADR
- [x] 6.1 `doc/01-architecture/adr.md`：ADR 正文（8 条决策 + 已知局限）+ 变更追踪表行
- [x] 6.2 `doc/03-interfaces/{memory,loop,ui}-interface.md`（转录读写面 / `LoopContext.history` / 新端点 / 10→11）
- [x] 6.3 `doc/02-modules/{memory,loop}.md`；`doc/04-testing/test-cases.md` 增 TC 行

## 7. 归档 / 台账 / 提交
- [x] 7.1 delta 合进 4 个 canonical spec（**逐文件对齐排版惯例**）+ 校正 canonical `memory/spec.md:4` Purpose 的同一处措辞
- [x] 7.2 勾 tasks → `shutil.move` 进 `archive/2026-10-06-0115-session-transcript/`
- [x] 7.3 `openspec validate --all` ⇒ 30 passed / 0 failed
- [x] 7.4 `coding-plan/phase-28.md` 登记 **E49** + 判据订正段（含 L4 措辞背离旧账）+ `coding-plan/README.md` 三处
- [x] 7.5 记忆：`coding-plan-leftover-walkthrough.md` + `MEMORY.md`
- [x] 7.6 单提交 `feat(memory,loop,ui,configuration): 对话转录落盘与会话历史回灌（change 0115）`
