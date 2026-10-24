# Design — 后台派生调用的推理档位透传（0320）

## 证据

| # | 观察 | 数值 / 来源 |
|---|---|---|
| E1 | `_llm_text` 只构造 `LLMRequest(messages=…, model=…)`，**不带** `reasoning_effort`、也不带 `max_tokens` | `src/core/runtime.py:812-821` |
| E2 | 前台 planner 调用**全部**带 `reasoning_effort=app.llm.reasoning_effort`（主 / 子 / 神兽 / 宠物 / 计划 / 校验） | `src/core/runtime.py:1189, 1397, 1446, 1744, 1870`；`loop/planner.py:680` |
| E3 | 用户配置 `llm.reasoning_effort: low`（`~/.core-agent/config.yaml`，密钥不读取、不回显） | 配置读取 |
| E4 | traces 中 `maintenance_failed` 59 次 vs `compaction` 10 次；超时行恒为 `{"step":"compaction_timeout","timeout_s":60.0}`，配对 `{"step":"memory_compact","error":"LLM_TIMEOUT: 调用超时（>60.0s）：glm-5.3"}`；`memory_compact` 步耗时 38–145s | `~/.core/state/traces.jsonl` |
| E5 | 同一段摘要 prompt（session `9d12d78a`）四组实测：现状 44.8s / 4988 completion tokens / 2525 字；仅 `max_tokens=2048` 26.0s / 2048 / **0 字**（`finish=length`）；仅 `reasoning_effort=low` 10.0s / 901 / 2008 字（`stop`）；两者 8.0s / 747 / 1635 字 | 直连用户端点实测（密钥仅内存解析，不落盘不回显） |
| E6 | 后台 provider 超时缺省 60s、`loop.compact_timeout` 缺省 60s；轮内压实阻塞等待 | `configuration/spec.md`；`loop/default.py:1385-1413` |
| E7 | `StdlibLLMProvider` 只在 `request.reasoning_effort is not None` 时写入请求体 | `llm_provider/stdlib_provider.py:254-255` |

## 决策

### D1 后台接缝透传配置档位（修复）

`_llm_text` 构造请求时加 `reasoning_effort=app.llm.reasoning_effort`：

- **同源同值**：`llm.reasoning_effort` 是 `llm` 级配置，语义上覆盖全部模型调用；前台已全部
  下发，后台漏发属**配置泄漏**，不是新策略。
- **例外为零**：后台派生的全部消费者（摘要 / 关键事实 / 关系 / 情景归纳 / SOP / 沉淀候选 /
  进化 review 与 patch author）共用同一接缝，一处修复即全量生效。
- **被拒**：在 `StdlibLLMProvider` 内按「后台 provider」身份自动补默认档位 —— 把策略藏进
  实现层，且会让「用户未配置」与「用户配置 low」不可区分。

### D2 不新增 `max_tokens` 缺省（以证伪为依据）

E5 第二行：仅加 `max_tokens=2048` 时思考占满整个预算，26s 后正文为空、`finish=length`。
`MemoryStore._summarize_session` 对空摘要只留痕并跳过派生抽取 ⇒ 记忆**永远不固化**，且每轮
重试。**被拒**：① 后台固定 `max_tokens=2048`（饿死正文）；② 复用 `loop.output_reserve=8192`
（本用户默认档位下实测 4988 tokens 已接近，仍会撞 60s 超时；且对 patch author 等长输出面
语义不明）。

### D3 未配置不下发（逐字不变）

`app.llm.reasoning_effort` 为 `None` ⇒ 请求字段保持 `None`；provider 不写请求体（E7）⇒ 与引入
前逐字一致。端点不支持该字段的风险面不变：既然前台已在用户显式配置时下发，后台沿用同一
口径，不新增端点兼容性风险。

## 规格映射

- `configuration` **ADDED** ×1「后台派生调用的推理档位透传」：透传 SHALL、未配置 SHALL NOT
  下发、零新配置键、不改超时/重试语义；Scenario ×2（透传 / 未配置不下发）。

## 测试与反证

- 正证（`tests/test_background_reasoning_effort.py`，经真实 `build_runtime` + 打桩
  `StdlibLLMProvider.acompletion` 捕获请求）：
  1. 配置 `llm.reasoning_effort: low`，经 `MemoryStore.compact(session_id=…)` 触发摘要与关键
     事实两次后台调用 ⇒ **每个**捕获请求的 `reasoning_effort == "low"`；
  2. 未配置该键 ⇒ 每个请求 `reasoning_effort is None`（零变化）。
- 反证（`cp` → `/tmp` 改坏 → 复原 → `md5sum`）：
  1. 删掉 `_llm_text` 的 `reasoning_effort` 实参 ⇒ 用例 1 红；
  2. 改成硬编码 `"high"`（无视配置）⇒ 用例 1 红；
  3. 未配置时回落 `"low"` ⇒ 用例 2 红。

## 局限

- **未配置档位的用户仍可能超时**：本 change 只修配置泄漏，不发明后台专用默认档位；若模型
  端点默认档位很高，需用户显式配置（或另立 change 讨论后台默认，须带配置键与决策记录）。
- 端点是否真正采纳低档位无法在配置期校验；只有实测延迟 / 超时反馈能证伪。
- 压实仍是轮内阻塞路径：修复后单次摘要 + 关键事实约 2×10s（实测单次 10s），不再撞 60s 墙，
  但仍会占用本轮时间。
- 60s 超时后的协作式截止行为不变（已完成会话的写回保留、未提交摘要不落库）。
