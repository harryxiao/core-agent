# 0229 — 形态 5 判据收窄：退化残渣不构成「追加了正文」

## Why

**生产事故（2026-10-12 08:25，session `88a6a6b9…`，trace `6925d31f…`）**：子 Agent 在创建
OpenSpec change 提案时，交出了一个**完整、可执行**的动作 ——

```
{"tool_id": "tools.file_write", "args": {"path": "~/work/core-agent/doc/openspec/changes/2026-10-13-0229-memory-long-task-gaps/proposal.md", "content": "<1806 字符的完整 proposal>"}}
```

—— 只在**末尾**多出一个孤零零的 `}`。判据重放（当前代码）：

```
json.loads FAILED: Extra data: line 1 column 1996 (char 1995)
object ends at 1995 of 1996   trailing repr: '}'
_unclosed_action_payload: False
_embedded_action_payload: True   ⇒ 形态 5 ⇒ 整轮报废、零执行
```

**根因**：`_embedded_action_payload` 的判据是「存在已闭合的含非空 `tool_id` 对象 ＋ 其后有**任何
非空白字符**」—— 它把**一个多余 `}`** 与**一整段解释正文**当成同一件事。0227 又把这个判据接进了
`{` 开头分支的成因措辞（规格 453-456 行：「含**对象在前、正文在后**的形态」），于是本案的错误
提示「动作 JSON 之后仍跟有正文」**在事实层面是假的** —— 后面没有正文。

**代价**：一个**可恢复**的动作被丢弃 ⇒ 本轮以失败终止（`loop.parse_retry` 缺省关 ⇒ 无任何补救），
用户只看到一句不准确的提示 —— 即「可见失败」优于「静默零执行」的 0222 决定，在这里**用错了对象**。

## What Changes

收窄形态 5：判据中的「**正文**」限定为**含词元**（字母 / 数字 / CJK）的余部；其后**仅**为
**退化残渣**（不含词元：多余闭合符 / 围栏符 / 零散标点 / 空白）时 **SHALL NOT** 命中形态 5 ——
残渣不构成「追加了正文」的证据。

1. 新纯函数 `_has_word(text)`（`any(ch.isalnum() …)`）作为**唯一谓词**，两处**朝向相反**地复用：
   - `_trailing_json_object`：余部**无**词元 ⇒ 残渣可忽略、接受该对象（形态 3）；
   - `_embedded_action_payload`：余部**有**词元 ⇒ 才算夹带正文（形态 5）。
2. `_parse` 的 `{` 开头分支：**先**解码首个对象，余部仅残渣 ⇒ 按工具动作处理（形态 2 容残渣）；
   余部含词元 ⇒ 落到既有 `_first_brace_reply`（成因措辞逐字不变）。
3. 同步收窄 `_trailing_json_object` —— **必须**：否则「正文 + 动作 JSON + 残渣」在 `_embedded`
   不再命中后会**落回「整段当答复」**，重新引入 0222 修掉的**静默零执行**。既然残渣可为**纯
   标点**（`…}。`），该函数的「文本须以 `}` 收尾」前置门槛一并去掉，余部只按 `_has_word` 二分。

**无条件生效**（属缺陷修复，不设配置键；判例：0206 / 0210 / 0228）。不改 0222 对「JSON 在**真正文**
中间」的拒绝，也不改 `loop.parse_retry` 缺省。

## Impact

- **规格**：`loop` **MODIFIED**「推理动作解析与失败可见」（形态 2 加容残渣子句 ＋ 形态 3 的围栏收尾句
  扩为容残渣 ＋ 形态 5 加「正文须含词元」子句 ＋ ADDED 2 Scenario，**既有 16 Scenario 逐字保留**）
  ⇒ **6 → 6** req、**89 → 91** scen。
- **代码**：`src/core/loop/planner.py` 两个纯函数 ＋ 一处分支 ＋ 两处判据（约 30 行）。
- **接口**：`doc/03-interfaces/loop-interface.md` 的「原始产出可诊断」条目补一句残渣容差。
- **兼容**：残渣-only 的余部此前一律失败 ⇒ 现在执行（放宽）；含词元的余部行为**逐字不变**。

## Migration

无需迁移。既有配置、请求形状与含词元余部的失败语义均不变。
