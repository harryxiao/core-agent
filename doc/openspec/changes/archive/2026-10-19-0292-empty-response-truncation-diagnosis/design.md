# 设计 — 0292 空响应的截断成因诊断

## D1. 空内容分支读取 `finish_reason`

**现状**（`src/core/loop/planner.py` `_parse`）：

```python
raw = content.strip()
if not raw:
    return Action(args={"reply": f"{_PARSE_FAILED}: 空响应"}, failed=True)
```

`finish_reason` 已经由两条路径传入：非流式取 `LLMResponse.finish_reason`，流式取最后一个
携带该字段的 `LLMChunk`（change 0170 / ADR-0161 起）。空内容时该信息被直接丢弃。

**改法**：

```python
if not raw:
    reply = f"{_PARSE_FAILED}: 空响应"
    if finish_reason == "length":
        reply += "（输出被截断；思考可能占用全部 max_tokens）"
    return Action(args={"reply": reply}, failed=True)
```

- 保留 `LLM_PLAN_PARSE_FAILED: 空响应` 作为前缀子串：既有日志检索、呈现层与测试的前缀
  匹配不受影响；新增的是括号内的成因。
- 只认 `finish_reason == "length"`（provider 的权威截断信号）。空串、`None`、`stop`
  等一律维持原文案，避免对第三方 provider 的缺失信号做猜测。
- 失败语义、`raw_output`（空内容本来就没有）、工具执行路径均不变。

## D2. 为什么不是「自动兜底」

自动降档重试（例如空内容 + `length` 时改用 `reasoning_effort=low` 再调一次）会改变
模型调用次数、延迟与成本，且需要新的重试策略与规格；本次只解决**可见性**。预算分配
（`output_reserve` / 思考额度）与自动重试另立 change 评估。

## D3. 被拒方案

- **把空内容一律归为「截断」**：`finish_reason=stop` 的空包也可能是端点异常，误报会掩盖
  真实原因；只在权威信号为 `length` 时改文案。
- **用 `completion_tokens == max_tokens` 推断**：planner 拿不到可靠的请求侧 `max_tokens`
  与用量对应关系（部分 provider 不报用量），且 `finish_reason` 已是协议内的权威信号。
- **在 planner 里自动调大 `max_tokens` 重试**：改变请求形状与成本，超出诊断范围。

## 局限

- 只改善提示，不阻止同类失败：GLM 系仍需显式 `llm.reasoning_effort: low`（或调大
  `loop.output_reserve`）才能让正文获得预算。
- provider 若在截断时不报 `finish_reason="length"`（缺失或 `stop`），仍显示旧文案
  「空响应」。
- 该文案只描述「本次产出为空且被截断」，不区分「思考耗尽」与「正文本身超长被截断」
  两种子因；后者由非空内容的既有截断提示覆盖。
