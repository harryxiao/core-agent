# 0224 — 文档摘要落盘前无条件脱敏（PA-03）

## Why

`rag ingest --summarize` 把文档**全文**交给一次模型调用产摘要，产物经 `entry._doc_summary_note`
落成 canonical **结论笔记**（长期可检索）。两条路径都**无**脱敏：

1. **写入侧**：`notes` 包**无** `redact_secrets`（`memory` 侧有），`_doc_summary_note` 把模型输出
   原样写进正文；
2. **提示侧**：`_DOC_SUMMARY_PROMPT` 只要求「总结核心结论」，未禁止把密钥写进摘要。

⇒ 文档若含密钥形态子串（`sk-…` / `AKIA…` / `…password=…`），明文可能经摘要进入**长期可检索**的
结论笔记 —— 与红线「密钥只引用不读取、绝不进日志/记忆」冲突。PA-03 裁决 **B + C**（与 `memory`
同构的两道防线）。

## What Changes

- **B（承重）**：`entry._doc_summary_note` 落盘前**无条件**对摘要正文执行
  `core.memory.redact_secrets`（与 `memory` 抽取/情境链同口径：命中密钥形态的子串 → `<redacted>`，
  保留工具名与其余结构）。**信任边界在写入侧**，不依赖提示词自律。
- **C（纵深）**：`_DOC_SUMMARY_PROMPT` 补一句「不得输出密钥等敏感值」的措辞（实现细节，不升规格）。

## Impact

- capability：`notes` —— **MODIFIED**「文档摘要笔记（notes.rag）」：Requirement 正文增一段
  「落盘前无条件脱敏」，ADDED 1 Scenario（既有 4 Scenario **逐字保留**）。
- `rag` 规格**不动**：其「把文档**全文**交给一次模型调用」为既有承诺，本 change **不改**送模型的
  材料（只脱敏**产物**）⇒ 无 delta。
- 向后兼容：不含密钥形态的摘要在 `redact_secrets` 下**逐字不变**（`redact_secrets` 只替换命中
  子串）⇒ 既有测试与幂等覆盖语义零回归。
- 提词镜像：`prompts.md` ⑭ 同步更新（`test_prompt_mirror` 逐行核对会拦漂移）。
