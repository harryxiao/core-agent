# Design — 基准会话隔离与 CJK token 估算（change 0245）

## D1 基准会话：`ephemeral_sessions`

**问题**：会话过滤只作用于 `read`；压实是**写**路径——`_summarize_sessions` 对
`session_id="bench"` 的条目照常跑摘要、派生抽取与提升，而三类派生条目 `session_id=""`
（全局层）⇒ 污染用户检索面。

**方案**：`MemoryStore.__init__(..., ephemeral_sessions: tuple[str, ...] = ())`，内部规范化
为 `frozenset`（空串丢弃）。`_summarize_sessions` 对命中的 `sid`：

- 会话级摘要与原条目归档**照常**（保持 L2 有界、条目迁 L4，不新增增长面）；
- **跳过** `_deliver_promotion`（canonical 笔记）与 `_extract_key_facts` /
  `_extract_relations` / `_consolidate_episodic`（全局层派生）。

**为何不用 `maintenance_interval=0`**：基准 loop 与 `general` 兜底子 Agent **共用同一实例**
（`general_agent.loop`），关维护会连带关闭普通子任务的维护节拍；新建独立 loop 则复制装配
且只挡住「维护」一条路径，读面（skills/SOP/notes）仍会写入。会话级标记更小、更准、可单测。

**为何不新增配置键**：`bench` 是执行面内部约定，不是用户旋钮；组合根只在
`features.evolution_benchmark_runner` 开启时传入 ⇒ 与执行面同开同关。

**缺省零行为改变**：空元组 ⇒ 成员判断恒假 ⇒ 压实逐字不变。

## D2 CJK 感知的 token 估计

**方案**：新增中性模块 `core/tokens.py`：

```python
def estimate_tokens(text: str) -> int:
    cjk = sum(1 for ch in text if _is_cjk(ch))
    return max(1, cjk + (len(text) - cjk) // 4)
```

`_is_cjk` 覆盖 CJK 统一表意文字（含扩展 A）、CJK 标点、全角形式、假名与谚文。
**CJK 按 1 token/字符**是保守上界（主流 tokenizer 中文约 0.6–1.0 token/字符），宁高勿低
（低估会让预算失真，高估只是更早裁剪）。

`context.budget.estimate_tokens` 改为从 `core.tokens` 导入（`core.context.__init__` 的再导出
面不变）；`memory._truncate` 改用同一函数（memory 不能 import context —— ADR-0045；
`core.persistence` 已是「中性模块被能力包共用」的先例）。`_TOKEN_DIVISOR` 常量随之删除。

**效果**：`estimate_tokens("") == 1`、纯 ASCII 与旧口径逐字相同（`len//4`）；纯中文由
`n//4` 变为 `n`。混合文本按字符集分档累加。

## D3 三层窗口字符换算 4 → 2

`plan_window` 的 `mid_chars = int(budget * 0.3) * _CHARS_PER_TOKEN` 是「token 预算 → 摘要
字符上界」的换算。按 D2 口径，4 字符/token 对中文高估 4 倍 ⇒ 中文中层摘要可超出预算。
取 **2 字符/token**（review 建议的中日韩混合中间值）：纯中文仍偏松（1 字符/token 才严格），
纯英文偏紧但只是更短的摘要——两者都往「有界」方向收。份额常量不变（规格只钉份额）。

## 局限

1. 基准执行仍注入 skills / SOP / notes（`_loop_hooks` 的 `on_turn` 会写 canonical 笔记与
   技能反馈）——读面与学习信号隔离是独立议题，本 change 只收口**记忆压实派生**。
2. `_score_importance` 仍对基准会话条目打分（会话内写 important，非全局）；省调用未做。
3. `ephemeral_sessions` 是构造期集合：运行期新增的合成会话若不登记仍会派生（当前只有
   `bench` 一个用例）。
4. token 估计是**字符集粗估**：不区分代码/数字密集文本，也不与供应商 tokenizer 对齐；
   CJK 按 1 token/字符偏保守。
5. `_CHARS_PER_TOKEN=2` 是混合口径折中：纯中文摘要仍可能有 ≤2 倍预算误差，纯英文摘要
   比旧行为短一半。
