# Design 0239: post-turn 跨 loop 取消传播 ＋ benchmark 桩适配 0236

## 背景与根因

见 proposal。取证链（组一）：traceback `asyncio.run → scheduler.run → _fan_out → _run_subtask
→ collect_result → DefaultLoop.astream(:446) → _await_post_turn(:656) → _run(:646) →
asyncio.to_thread → CancelledError`；`git log 0e93e95..HEAD -- default.py/protocol.py` 唯一
并行改动 = **7357a11**（轮末收尾后台化）；三测试共同形态 = **DefaultLoop 实例跨两次
`asyncio.run` 复用**（第一次遗留 post-turn task 于 loop A，loop A 关闭清理将其 cancel，
第二次在新 loop B 上 `await` 已取消 task ⇒ 重放 CancelledError）。

## 决策

- **D1 分野判据 = `task.cancelled()`**。`await task` 抛 `CancelledError` 有两种来源：
  (a) task 自身被取消（宿主 loop 关闭清理）——**吞**，放行新一轮（后台收尾尽力而为语义，
  与 0231/0238 的「呈现层/收尾层瞬时失败不得杀死主流程」同哲学）；
  (b) 当前协程被取消（用户打断 Ctrl+B、上层 gather 级联取消）——**传播**（取消语义必须
  保真，吞掉会让打断失效）。`task.cancelled()` 恰好区分两者：task 内部取消完成时为 True；
  外部取消当前协程时 task 仍正常运行（False）。
- **D2 不动 `_schedule_post_turn` 挂出时机**。更早的清扫（如 astream 入口判 loop 归属丢弃
  残留）也可行，但引入 loop 身份比较的额外耦合；`await` 处分野已覆盖实测形态且最小。
- **D3 组二修桩不修门**。0236 空壳 fail-closed 是**有意规格**（`require_skill_content`
  与 writer 同开同关）；测试桩对「技能内容蒸馏」请求回 `"PASS"` 是 0212 时代桩的视野盲区。
  桩按 `_PROMPT_HEAD` 特征子串「技能内容蒸馏器」分派 ⇒ `_SKILL_CONTENT_JSON`（合法
  SkillContent：`task_types` 非空 + `instructions` 非空 + `param_schema` dict）。
- **D4 缺陷修复 ⇒ 无条件生效、不设配置门**（判例 0206/0210/0228/0238）。

## 改动面

| 文件 | 改动 |
|---|---|
| `src/core/loop/default.py` | `_await_post_turn`：`except asyncio.CancelledError` ＋ `task.cancelled()` 分野（吞旧/传播新） |
| `tests/test_benchmark_runner.py` | `_SKILL_CONTENT_JSON` 常量；桩 `acompletion` 按 prompt 分派 |

## 反证（实测）

- **A**：还原 `_await_post_turn`（摘 except 分支）⇒ **3 红**（history_persistence /
  longtask_e2e / orchestration 的 CancelledError）。
- **B**：摘桩分派（content 恒 `_REPLY`）⇒ **2 红**（benchmark 两用例 `eval=None`）。
- 同时摘 A+B ⇒ **5 红**；复原 ⇒ 两文件 `md5sum` 逐字节同（`0bcdb5a7…` / `cd6c4f3d…`）⇒ 63 passed。
- 承重锚 = **既有五测试本身**（红 → 绿即锚定），未新增用例。

## 局限

① 「当前协程被取消」与「旧 task 恰好同时被取消」的极窄窗口会把 (b) 误判为 (a)（吞掉一次
打断；后果限于本轮多推进一步，无数据面影响）。
② 未清扫跨 loop 残留 task 本体（D2）——引用在下次 `_await_post_turn` 的 finally 中释放。
③ 桩分派按 prompt 特征子串，`_PROMPT_HEAD` 措辞变更需同步桩（镜像漂移风险同 0225 类）。
④ 0233 的 spec delta 归档欠账（MODIFIED 漏抄 scenario「TUI 思考折叠回显」致 validate 红）
不在本 change 范围。
