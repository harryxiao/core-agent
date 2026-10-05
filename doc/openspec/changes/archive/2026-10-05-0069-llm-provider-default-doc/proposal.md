# 0069 订正 llm-provider 模块文档的「默认实现」措辞（账本 D6）

## Why

账本 D6：`doc/02-modules/llm-provider.md` 多处称「**LiteLLM 作默认实现**」，与事实不符 ——
默认实现是 `StdlibLLMProvider`（`src/core/llm_provider/stdlib_provider.py`；`__init__.py` 自述、
`runtime.py` 默认接线），且 `litellm` 已于 **ADR-0044** 被移除（核心运行时零三方依赖）。
规格 `doc/openspec/specs/llm-provider/spec.md:5` 与 Requirement「默认实现与配置归一化」也逐字写
「`StdlibLLMProvider`（OpenAI 兼容 stdlib）作默认实现」。

三类对齐：① 规格 = stdlib；② 实现 = stdlib；③ 模块文档 = LiteLLM ⇒ **唯一不一致在文档**，
属「文档过度承诺/陈旧」型（同 E17/E19），**订正文档承认现状**，零代码、零规格改动。

## What Changes

**① 主文件** `doc/02-modules/llm-provider.md`（D6 具名项），局部订正 5 处：
§1 定位 3 处、§2 架构图与实现说明 2 处、§3.2 小节标题与正文、§3.3 正文。

**② 全仓残留复查发现同一事实错误的其余「现行文档」**（一手 `grep -rn LiteLLM doc/`）：

| 文件 | 位置 | 订正 |
|---|---|---|
| `doc/00-product/requirements.md` | CORE-LLM-R2 / R3 | 需求文本早已由 ADR-0044 改成 stdlib，此处是**陈旧镜像** → 与规格逐字对齐 |
| `doc/README.md` | §1 文档清单 llm-provider 行 | `LiteLLM 默认实现` → `stdlib 默认实现` |
| `doc/04-testing/test-cases.md` | TC-LLM-03 | 「替换 LiteLLM」→「替换默认实现」 |
| `doc/03-interfaces/ui-interface.md` | §关联 | 「可替换 LiteLLM」→「可替换默认实现」 |

**不改（有意保留）**：`archive/` 下历史变更（当时的真实决策快照）；
`adr.md` 的 ADR-0021 / ADR-0032（历史决策记录，由 ADR-0044 supersede，不回溯改写）；
`adr.md` ADR-0044 正文（**故意**叙述替换前的 litellm 现状，是决策上下文）；
`00-product/design-completeness-eval.md`（横向对比分析稿，LiteLLM 作为对比产品出现）。

## 规格 delta

**规格中性**：无 spec 改动（规格早已写 stdlib），`.openspec.yaml` 声明 `skip_specs: true`。
