# Design — 0297 动作 JSON 后的纯 JSON 注释对象

## 1. 事故形态与现有判据

trace `fc82601b…` 的原始产出（节选）：

```json
{"tool_id": "tools.code_run", "args": {"script": "cd ~/work/core-agent && git status --short | wc -l; …"}},
{"integrated_analysis": ["change 目录 2026-10-19-0296-foreground-liveness 不存在", "git 工作区有大量未提交修改", …]}
```

`_parse` 走 `{` 分支：

1. `_leading_object` 解出首对象与结束下标 `end`；
2. `text[end:]` 是 `,\n{"integrated_analysis": …}`，`_has_word` 命中 `integrated_analysis`
   ⇒ 不走「首对象 + 退化残渣」；
3. `json.loads(text)` 因 `Extra data` 失败；
4. `_recover_truncated_tool_json` 因首对象已完整 ⇒ `None`；
5. `_first_brace_reply` → `_embedded_action_payload`：首对象含 `tool_id` 且余部含词元
   ⇒ 形态 5 文案，失败。

问题不在「动作之后还有字符」，而在**余部的性质**：退化残渣 vs 正文 vs 结构化注释。
0229/ADR-0219 已把前两者用 `_has_word` 二分；本 change 补第三类。

## 2. 判据：纯 JSON 注释值序列

新增确定性函数（名字以实现为准，语义如下）：

```python
def _only_json_annotations(text: str) -> bool:
    """余部是否恰为一个或多个完整 JSON 值，且无动作/终态语义。"""
```

逐条规则：

1. 跳过空白；值之间允许一个可选 `,`（模型常用 JSONL/数组混写），逗号后仍只允许空白；
2. 每个值用 `json.JSONDecoder().raw_decode` 从当前位置解析，必须完整推进；
3. 顶层为对象时：`obj.get("tool_id")` 为真 ⇒ False（第二个动作）；
   `"reply" in obj` ⇒ False（第二个终态，无法判定意图）；
4. 至少解析出一个值；序列结束后只允许空白与至多一个收尾 ```` ``` ````；
5. 任何解析失败 / 尾随词元 ⇒ False。

对象、数组、字符串、数字、布尔、`null` 都算注释值。嵌套对象里的 `tool_id` / `reply`
不参与判定（只看顶层），避免把分析数据里的字段误当动作。

## 3. 接入点

在 `_parse` 的 `{` 分支、`json.loads` 之前：

```python
leading = _leading_object(text)
if leading is not None:
    obj, end = leading
    rest = text[end:]
    if not _has_word(rest):
        return self._from_dict(obj)          # 既有：退化残渣
    if obj.get("tool_id") and _only_json_annotations(rest):
        return self._from_dict(obj)          # 新增：动作 + 注释
```

其余路径逐字不变：

- 首个对象是 `{"reply": …}` + 注释 ⇒ **不**命中（仅动作享受此容错），仍走失败路径；
- 首个对象 + 第二动作 / `reply` 对象 / 正文 ⇒ `_only_json_annotations` 为 False，
  落回 `json.loads` 失败 → `_first_brace_reply` → 形态 5，文案与 `raw_output` 不变；
- 非 `{` 开头（正文 + 尾部动作 + 注释）**不在本 change 范围**：仍按形态 5 失败。
  原因：该形态需要同时重写 `_trailing_json_object` 的「只认最后一个对象」语义，
  爆炸半径大；现场事故是 `{` 开头，先修确定路径。

## 4. 提示词硬化

- `_SYSTEM_PROMPT` ②：在「其后不得再有任何字符」后补一句：不得追加第二段 JSON
  （包括 `integrated_analysis` 一类分析对象）；需要说明时选择①自然语言回复。
- `_RETRY_NUDGE`：同样补「或附带分析 JSON」。
- 仅改措辞，不改变请求形状之外的行为；提示词文本同步到 `doc/03-interfaces/prompts.md`。

## 5. 被拒方案

- **把余部直接拼进 `reply`**：动作轮的 `reply` 由工具结果后的下一轮生成；拼进去会污染
  转录/记忆，且注释并非用户可读终态。
- **接受第二动作（取第一个）**：模型明确写了两个动作，静默丢弃第二个会让模型看到的
  世界与它的意图不一致；宁可可见失败。
- **接受 `reply` 对象作为终态并执行首个动作**：同一轮既执行又回复，破坏「动作轮 /
  回复轮」二分。
- **用启发式识别 `integrated_analysis` 等键名**：键名无限、不可枚举；应按**结构**判定。
- **默认开启 `loop.parse_retry`**：多一次模型调用，且无法保证模型第二次不重复；本
  change 的确定性恢复已覆盖现场形态。

## 6. 局限（登记 known-risk E233）

1. 只覆盖 `{` 开头的「动作 + 注释」；正文 + 尾部动作 + 注释仍失败（见 §3）。
2. 注释值被**丢弃**，不进入任何持久面；若模型把关键结论只写在注释里，用户看不到。
3. 判定只看顶层 `tool_id` / `reply`；注释对象嵌套动作字段时会被当作数据接受。
4. 可选逗号/无逗号均接受，理论上 `{action}{"x":1}` 这类非标准拼接也会被接受；
   首个动作已完整，风险限于「模型本意是两个值」的极少数情形。
