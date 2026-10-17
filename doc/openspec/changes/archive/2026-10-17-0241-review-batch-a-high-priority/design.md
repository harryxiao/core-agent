# Design 0241: 记忆与进化高危面收口

## 背景

`change 0177/0181` 引入写入侧重要度闸门与派生来源豁免面；`change 0179` 引入轨迹/行动序列
双条目；`change 0155` 起关键事实抽取在 store 侧无条件脱敏。本轮 review 发现三处**规格已
要求、实现未闭合**的缺口，均属缺陷修复而非新行为。

## 决策

### D1 评测器捕获打分异常 ⇒ `freeze`

`Evaluator.evaluate` 在调用 `_held_out_score` 处包 `try/except Exception`，异常时返回
`self._frozen(baseline=baseline)`。理由：

- **语义**：执行器异常意味着**无法产出留出分**，与「无打分器 / 无样本 / 无执行器」同类；
  规格 evolution「留出评测」已声明评测器据此判 `freeze`，`BenchmarkScorer` 的 docstring
  也写明「异常冒泡给评测器」。
- **闭环**：`run_cycle` 已在 `evaluate` 之后 `_pending.record(...)` 并处理 `freeze` 分支；
  捕获后候选进台账、结局为 `frozen`，`EvolutionWorker.maybe_run` 的收尾（`_sample_observations` /
  `_completed.clear()`）得以执行。
- **不吞成通过/退化**：`freeze` 是 fail-closed 的第三态，SHALL NOT 被读作 rollback 或 publish。
- 只捕获 `Exception`（不捕获 `BaseException`）⇒ Ctrl-C / `SystemExit` 仍可中断。

不新增告警/日志：`frozen` 结局本身就是可观测面；在评测器里回显异常 message 有泄密风险，
本 change 不引入新的文本出口。

### D2 `episodic` 纳入评分豁免面

`_GATE_EXEMPT_SOURCES` 增 `"episodic"`。该来源由 `_consolidate_episodic` 从**已准入**的
L2 材料派生，属派生结论；被低分拒收/降层会销毁归纳结果。同步修正 `store.py:85-90` 注释：
豁免评分（写入面）与豁免遗忘（衰减面）不是同一组来源，`episodic` 是第三类（`forget` 只对
`kind=="episodic"` 走衰减，不看 source 集合），注释不得再声称「二集合恰好二分同一组来源」。

### D3 三处写回统一脱敏

判据统一用 `core.memory.redact_secrets`（行内替换、方向 over-redact、纯函数）：

| 写回点 | 位置 | 处理 |
|---|---|---|
| 会话摘要 | `store._commit_summary` | `content=redact_secrets(summary)`（store 侧无条件；注入摘要器不构成信任边界） |
| 循环轨迹 | `loop.default._remember` 的 `content="\n".join(lines)` | 整条内容写入前 `redact_secrets` |
| 溶解原因 | `engine.dissolve` | `content=redact_secrets(reason)` |
| 人工拒绝理由 | `engine.reject` | 落库前对拼接文本 `redact_secrets` |
| 技能内容 | `engine._crystallize_skill` | `description` / `preconditions` / `task_types` 脱敏；`instructions` 既有已脱敏；`param_schema` 不改写 |
| 架构候选 | `engine._crystallize_plugin` | 交付给 crystallizer 的 `issue` 脱敏 |

全部为**恒等变换**（未命中密钥形态时逐字不变），不改变结局与结构。

### 规格先行

- loop「执行循环」原写「轨迹条目的内容口径 SHALL 逐字不变」——与密钥红线冲突，改为
  「除密钥形态脱敏外逐字不变」，并新增 Scenario。**先改规格、后改代码**。
- memory「写入侧重要度闸门」豁免面补 `relation` / `episodic`（`relation` 代码早已豁免，
  规格文本遗漏）；「记忆压实」新增摘要落库前脱敏的句子与 Scenario。
- evolution 新增 Requirement「进化写回与技能内容的密钥形态脱敏」＋ 3 Scenario。
- evaluator 部分**规格中性**：evolution「留出评测」已要求异常冒泡给评测器判 freeze，
  本 change 只让实现对齐规格。

## 改动面

| 文件 | 改动 |
|---|---|
| `src/core/evolution/evaluator.py` | `evaluate` 捕获打分异常 ⇒ `_frozen`；docstring 同步 |
| `src/core/evolution/engine.py` | `dissolve` / `reject` / `_crystallize_skill` / `_crystallize_plugin` 脱敏 |
| `src/core/memory/store.py` | `_GATE_EXEMPT_SOURCES` 加 `episodic`；两处注释修正；`_commit_summary` 脱敏 |
| `src/core/loop/default.py` | 轨迹条目整条脱敏；docstring 同步 |
| 规格三份 | 见 `specs/` |

## 测试与反证

- **A1**：`score_fn` 抛 `RuntimeError` ⇒ `evaluate` 返回 `verdict=="freeze"` 且不抛出；
  `run_cycle`（经 gate 的候选）⇒ `outcome.status=="frozen"`，候选已入台账。
- **A2**：注入返回 0.1 的 scorer + episodic 抽取器 ⇒ 压实后 `source="episodic"` 条目仍在 L2、
  未被拒收/降层、无 `importance` 留痕。
- **A3**：摘要器返回含 `sk-...` 的文本 ⇒ 摘要条目无明文、含 `<redacted>`；轨迹终态回复含
  密钥形态 ⇒ `loop.<trace>` 无明文且结构保留；`dissolve` / `reject` 理由与技能字段含密钥形态
  ⇒ 落库无明文、其余正文不变。
- **反证**：还原各脱敏调用 / 摘掉 try-except / 摘掉 `episodic` ⇒ 对应用例红；复原后 `md5sum` 同。

## 局限

① 评测器只捕获 `Exception`，进程级中断（`KeyboardInterrupt`）仍直穿（刻意）；
② 脱敏为**行内替换**，不识别跨行拼接或编码变形后的密钥（既有判据边界，全仓同源）；
③ `episodic` 的遗忘面仍按 kind 走衰减，本 change 只修注释与评分豁免，不改遗忘策略。
