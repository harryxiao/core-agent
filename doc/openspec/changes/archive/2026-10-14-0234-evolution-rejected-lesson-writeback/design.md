# Design — evolution-rejected-lesson-writeback（0234）

> 评审收口：L3 **短指针**（不同文）；issue **有界**（400 字符）。

## D1 分层写回表（rejected 分支）

| 层 | id | 内容 | tags |
|---|---|---|---|
| L2 | `evolution.gate_rejected.<candidate_id>` | 完整教训：target + **有界** issue + review + 各门 bool | `["evolution","gate_rejected"]` |
| L3 | `evolution.gate_rejected.l3.<candidate_id>` | **短指针**：`ref=<L2 id>; target=…; review=…`（无 issue 全文） | `["evolution","gate_rejected","l3"]` |

- id 错开：`FileBackend` 以 id 为键；L3 加 `.l3` 后缀。与 `dissolve` / 人工 `reject` 前缀并行。
- **为何 L3 不同文**：L3 偏技能/程序知识面；同文双写会把负样本全文当「技能料」检索。
  指针兑现「写回 L2/L3」，详情仍在 L2。

常量（`engine` 模块级，不 import diagnoser）：

```python
_MAX_ISSUE_CHARS = 400  # 与 diagnoser._MAX_NOTE_CHARS 同口径字面量
```

## D2 方法签名与调用点

```python
def _write_rejected_lesson(
    self, candidate: GenerationCandidate, gate: GateReport
) -> None:
    """未过门教训：L2 全文（issue 有界）+ L3 短指针；memory 未注入则跳过。"""
    if self._memory is None:
        return
    issue = str(candidate.delta.get("issue", ""))[:_MAX_ISSUE_CHARS]
    gates = {k: bool(v) for k, v in gate.test_results.items()}
    l2_id = f"evolution.gate_rejected.{candidate.candidate_id}"
    l2_body = redact_secrets(
        f"rejected[{candidate.candidate_id}] {candidate.target_plugin}: "
        f"issue={issue} review={gate.review} gates={gates}"
    )
    l3_body = redact_secrets(
        f"ref={l2_id}; target={candidate.target_plugin}; review={gate.review}"
    )
    self._memory.put(MemoryEntry(
        id=l2_id, layer="L2", content=l2_body,
        tags=["evolution", "gate_rejected"], source="evolution", trace_id="evolution",
    ))
    self._memory.put(MemoryEntry(
        id=f"evolution.gate_rejected.l3.{candidate.candidate_id}",
        layer="L3", content=l3_body,
        tags=["evolution", "gate_rejected", "l3"],
        source="evolution", trace_id="evolution",
    ))
```

调用点：`run_cycle` rejected 分支，`pending.record` 之后、`return … rejected` 之前。

## D3 边界

- 不动 `_crystallize_*` / `dissolve` / `reject`；freeze/rollback/pending 不写。
- `redact_secrets` 从 `core.memory` 导入。

## D4 测试表

1. L2：id/层正确；content 含 target、截断后 issue、review；超长 issue 被截到 400。
2. L3：`.l3` id 并存；content 含 `ref=` 指向 L2 id；**不等于** L2 全文；**不含** issue= 长文。
3. `memory=None`：零写、不抛。
4. 与人工 `reject` 条目并存。
5. 其余分支无新增 `gate_rejected*`。
