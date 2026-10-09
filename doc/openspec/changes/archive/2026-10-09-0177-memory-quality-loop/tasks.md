# Tasks: 记忆系统质量闭环

测试先行：每个实现任务先写/改测试（标注对应 Scenario），后实现；完成一组跑一次
`openspec validate` + pytest 全量，绿了才进下一层。

## Layer A — keyfact 抽取上限自适应

- [x] A1. 测试：追加到既有 `tests/test_memory_key_facts.py`（本仓测试**扁平**在 `tests/`，无
  `tests/unit/`）—— 断言 `cap()` 边界：`cap(小会话) == KEY_FACTS_MIN`、`cap(长会话) == KEY_FACTS_MAX`、
  线性区单调递增（对应 delta Scenario「上限随会话长度自适应」）
- [x] A2. 测试：`cap(n) >= 8`（现状死值）恒成立 —— 零收紧回归锚点
  （Scenario「自适应上限不低于既有死值」）
- [x] A3. 实现：`MAX_KEY_FACTS_PER_COMPACT` 死值改为 `cap(n_episodic)` 函数
  （`KEY_FACTS_RATIO=0.25, MIN=8, MAX=16`）。实现面：`_plan_key_facts` 增 `cap` 形参
  （现硬读常量于 `store.py:128`），调用点 `_extract_key_facts` 传 `cap(len(entries))`；
  `extract.py` 两处 `max_facts: int = MAX_KEY_FACTS_PER_COMPACT` 默认值与 `KEY_FACTS_MIN`
  口径对齐；`core/memory/__init__.py` 公开导出同步
- [x] A4. 既有 keyfact 测试全量回归（归并/脱敏/幂等语义不动）
- [x] A5. 复核 `tests/test_memory_key_facts.py` **5 处**以常量为期望值的断言
  （`:260/:266/:357/:366/:367`）——**复核结论（已核实，零改动）**：5 处均经 `_store()` 只写
  **1 条** L2 episodic ⇒ `cap(1) == KEY_FACTS_MIN == 8 == 既有死值`，判据在自适应上限下**仍恰好成立**，
  无需改引 `cap(n)`（A1 已另加 `cap` 表驱动断言覆盖边界）
- [x] A6. 同步 delta 中两条既有 Scenario 的措辞（「条数与长度有界」「同批同 slug 归并」）——
  原以固定常量 `MAX_KEY_FACTS_PER_COMPACT` 为界，改引 `cap(n)`（**已完成**，勿再回退）

## Layer B — 检索命中强化衰减

- [x] B1. 测试：`reuse_count=0` 的 L2 episodic 条目遗忘评分与改动前**逐字一致**
  —— 零回归锚点（Scenario「未复用条目衰减不变」）
- [x] B2. 测试：同时间戳、同 importance 下，`reuse_count=3` 的条目遗忘评分
  **高于** `reuse_count=0` 的条目，且不会被同一阈值归档
  （Scenario「复用延缓新鲜度衰减」）
- [x] B3. 测试：`ts<=0` 豁免、semantic/L0/L3 不受遗忘影响的既有断言不回归
- [x] B4. 实现：遗忘评分 freshness 项改为
  `freshness ** (1 / (1 + log1p(reuse_count)))`；只动遗忘评分，不动检索排序公式

## Layer C — importance 写入侧闸门

- [x] C1. 测试：未注入 scorer（缺省 UNWIRED）⇒ `write()` 行为与现状**逐字一致**
  （不评分、不拒收、不降层）—— 零回归锚点（Scenario「未注入评分器时写入不变」）
- [x] C2. 测试：注入 scorer 返回 0.1（< FLOOR）⇒ 条目被拒收：不落库、`audit()` 无变化、
  无效应记录、`warnings.warn` 留痕（Scenario「低分条目拒收」）
- [x] C3. 测试：scorer 返回 0.3（FLOOR ≤ 分 < AMBIT）⇒ 条目落至 **L4**，效应可撤销——
  回滚后**按原意向层恢复**（实现为「先按意向层 `write`（条目自身 trace）再
  `migrate(意向层→L4, trace_id=f"gate.<id>")`」**两步双 trace**，见 design D2；
  **不得同 trace** —— 逆序撤销会先迁回再删除）（Scenario「中间分降层写入」）
- [x] C4. 测试：scorer 返回 0.8 ⇒ 正常写 L2 且条目 `importance` 被写为分值，
  该写回可撤销（Scenario「高分正常入库并写回分值」）
- [x] C5. 测试：scorer 抛错 ⇒ 降级放行（不拒收、不降层），`warnings.warn` 留痕，
  写入主流程不中断（Scenario「评分器抛错降级放行」）
- [x] C6. 实现：`MemoryStore` 增 `importance_scorer` 构造形参（UNWIRED 缺省）+
  写入路径闸门（`IMPORTANCE_FLOOR=0.2`、`IMPORTANCE_AMBIT=0.4`），评分写回走
  `EffectTracker.record`
- [x] C7. 检查 memory 域无任何 LLM/rag import（ADR-0045 红线，grep 验证）

## 收尾

- [x] D1. 台账 + 文档：`doc/01-architecture/adr.md` **ADR-0168**（记忆质量闭环：闸门依赖注入 /
  衰减调制落点 `_decay_score` / 降层两步可撤销 / 自适应上限实现面 / 局限）+ 变更追踪行；
  `coding-plan/known-risk.md` §1 新行 **E114**、§3 ADR-0168 局限行；`doc/04-testing/test-cases.md`
  新增 TC 节；`doc/02-modules/memory.md` 与 `doc/03-interfaces/memory-interface.md` 补段
- [x] D2. `openspec validate` 全绿 + pytest 全量无回归
- [x] D3. commit：`feat(memory): memory quality loop — importance write gate, reuse-reinforced decay, adaptive keyfact cap（change 0177 / ADR-0168 / 台账 E114）`
- [x] D4. 归档 change：本环境（symlink + WSL）`openspec archive` 恒失败 ⇒ **手工归档**——delta
  合入 canonical（合并脚本须断言既有 Scenario 标题全存活）后 `mv` 至 `changes/archive/`
