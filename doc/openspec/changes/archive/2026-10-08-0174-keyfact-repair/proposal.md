# Proposal: keyfact-repair（失效关键事实的运维修复）

> change `0174` / 台账 **E111** / ADR-0165。承 change `0173`（ADR-0164）：判据已修，但**已写坏的条目留在库里**。

## §1 Why —— 判据修好了，写坏的数据还在，且仍在污染检索

生产 `~/.core/state/memory.jsonl`（169 行：L2 157 / L4 12；keyfact **24** 条）里，**16 条**是 change `0173`
修复前判据的产物，形态为：

```json
{"id": "keyfact.榴莲", "content": "榴莲: <redacted>",
 "tags": ["key_fact", "entity:榴莲", "ref:round1:热带水果有哪些", "session:b19cd0e6…"],
 "reuse_count": 36, "layer": "L2"}
```

三个要点（逐条取证）：

1. **条目已不含任何可用信息** —— 取值被抹成 `<redacted>`，`ref` 标签是模型自造的出处说明
   （`ref:round1:热带水果有哪些` / `ref:会话事件` / `ref:证据链第1条` / `ref:分析结论` 等）。
2. **污染是持续的** —— `keyfact.榴莲` 的 `reuse_count` 已是 **36**：这条废事实被检索命中并注入上下文 36 次。
3. **材料仍在，且能救回来** —— 两个来源会话的 episodic 原文已归档到 L4（`_all_entries()` 经
   `backend.search("")` 读**全层**），`build_runtime()` 已注入 `extract_with(_llm_text)` ⇒ CLI 侧可直接重抽。

### 前置实证（本 change 的 dry-run，**只读、未写入**）

跑法：装配 `build_runtime`，取生产抽取器，对两个会话的材料（同条目、同 400 字符窗口）重抽，**不落库**。
`memory.jsonl` 前后 sha256 一致（`d7c45c34140fd8ef`）⇒ 未写入。

| 会话 | 当年抽出的实体（取值全被抹） | 重抽结果 |
|---|---|---|
| `b19cd0e6…`（热带水果 / 东南亚产地） | 山竹, 榴莲, 泰国, 缅甸, 菠萝蜜, 菲律宾, 越南, 马来西亚 | **8 条明文**：泰国=「东南亚水果王国，产榴莲、山竹…为全球最大榴莲、山竹出口国之一」；越南=「全球最大火龙果出口国…」；榴莲=「被称为"水果之王"，气味浓烈」；另有 印度尼西亚 / 菲律宾 / 马来西亚 / 缅甸 / 柬埔寨 |
| `8e01a4b9…`（TUI 表格显示问题定位） | 问题现象, 表格显示问题根因, 渲染组件, Textual 依赖版本, 控件是否支持表格, round 5 执行结果, round 6 执行结果, 处理要求 | **8 条明文**：表格显示不出的根因=「流式渲染的"按行固化"分段策略，而不是 Markdown 组件本身」；Textual版本=`8.2.8`；repl.py中导入Markdown控件的行号=`198行`；问题处理要求=「只分析原因，不用改代码」；另有 REPL渲染组件 / 内置表格渲染（基于 DataTable）/ 创建行号 471/484 / 会话轮次失败情况 |

三点确认：① **「当年既抽到这些实体名 ⇒ 材料窗口够用」的推理成立** —— 同材料重跑即得明文；② 修复后的判据下
**无一 `ref` 标签**落地（`ref` 全空）⇒ 不会再产生假引用；③ `round N 执行结果` 这类垃圾实体消失。

### 为什么「重抽」必须配套「清理」

重抽产出的**实体名与当年不同**（`表格显示不出的根因` vs `表格显示问题根因`、`Textual版本` vs `Textual 依赖版本`）
⇒ slug 不重合 ⇒ **旧条目不会被覆盖**，若不清理，`<redacted>` 死条目继续留在库里污染检索。

### 为什么是「删除」而不是「迁 L4 归档」

本仓既有清理口径是 `forget()` 的**迁 L4、不真删**（可逆）。本 change **不沿用**，因为实测它**止不了血**：

- `read()` 检索的是 `backend.search()` —— **无层过滤**，L4 条目同样进候选；
- 层权重只是**加性**项 `_W_LAYER × priority`（L4 `0.2` vs L2 `0.6`，差 `0.08`），而 `reuse_count`／
  `importance` 是**乘性**调制（`recency_decay × (1 + log1p(reuse_count)) × (1 + importance)`）——
  `榴莲` 那条 `reuse_count=36` 的乘性放大足以盖过层权重的加性差距。

即：归档**不改变「会被检索命中」这一事实**。故本 change 采取**删除 + 备份文件**（可逆性由备份承担，见 design §D3）。

## §2 改什么

1. **memory 侧**：`MemoryStore.repair_stale_key_facts(*, dry_run=False) -> RepairReport`
   —— 识别失效条目 → 按会话取**全层**材料 → 重抽 → 备份 → 落新 → 删旧（**排除本次新写入的 id**）；
   三处 fail-closed（抽取器未注入 / 抽取失败 / 备份写入失败 ⇒ 均不删）；幂等；`dry_run` 只读。
2. **CLI 侧**：`memory repair-keyfacts [--dry-run]` —— 装配运行时 → 调上述方法 → 打印报表。

## §3 待裁（已裁）

| # | 问题 | 裁决 | 依据 |
|---|---|---|---|
| 1 | 清理范围：只删「仍呈失效形态者」，还是删该会话**全部旧** keyfact？ | **清该会话全部旧 keyfact** | 实体名不保证重合（实证），只删失效者会残留死条目 |
| 2 | 旧条目去向：迁 L4 归档（本仓先例）还是删除？ | **删除 + 落备份文件** | 实测归档止不了血（§1 末）；备份文件承担可逆性 |
| 3 | CLI 形态与缺省行为 | `memory repair-keyfacts`；缺省**执行**、`--dry-run` 只报告；备份落 `$CORE_STATE_DIR/` | 与 `memory maintain` / `evolve implement --dry-run` 既有口径一致（我自定，见 design §D5） |

## §4 不做

1. **不清理无 `session:` 出处的失效条目** —— 无会话即无材料 ⇒ 不可重抽；**不删**（存疑即留），报告标明不可修复。
2. **不改 change `0173` 的判据 / prompt / 窗口** —— 抽取侧零变更。
3. **不改 `forget()` 口径** —— 遗忘仍是迁 L4；本 change 只对「失效 keyfact」这一特定面做删除。
4. **不引入自动/定时触发** —— 只在显式运维命令下发生（不挂进维护节拍、不随启动自跑）。
5. **不做跨会话全量重抽** —— 只处理**确实产出了失效条目**的会话。
6. **不做实体名映射迁移** —— 不试图把 `表格显示问题根因` 的值搬到 `表格显示不出的根因`。

## §5 切出

- **「自动修复」**：若将来希望在内存维护节拍里自动跑修复，须独立 change（涉节拍是否携带 LLM 调用、成本与
  失败语义）⇒ 本 change 只提供**显式**入口。
- **「备份文件的保留策略」**：本 change 只落不删；轮转/清理策略另议（记入台账）。

## §6 Impact

- **规格**：`memory` **ADDED** Requirements「失效关键事实的运维修复」（+7 Scenario，落在既有 `memory` 能力内 ⇒
  capability 数不变）；`cli-ops` **MODIFIED**「运维命令集」（+1 Scenario，既有 9 条逐字保留）。
- **代码**：`src/core/memory/store.py`（`RepairReport` + `repair_stale_key_facts` + 删除辅助）、
  `src/core/memory/__init__.py`（导出 `RepairReport`）、`src/core/entry.py`（子命令 + 分派 + 报表打印）。
- **测试**：新建 `tests/test_memory_keyfact_repair.py`（约 10 用例，含红态证据）。
- **文档**：ADR-0165 + 变更追踪行；`doc/02-modules/memory.md`；`doc/03-interfaces/memory-interface.md`；
  `doc/04-testing/test-cases.md` §87；`coding-plan/known-risk.md` §1 E111 + §3 ADR-0165 局限行。
- **基线**：pytest **2003**（记增量）。
- **风险**：**中低** —— 动作含**删除**，但有三处 fail-closed（抽取器未注入 / 抽取失败 / 备份失败均不删）、
  备份文件、`--dry-run`，且目标条目**信息为零**（取值已抹）⇒ 最坏情形是「没修好」，而非「修坏了」。
