# Change: 新增 configuration 横切能力（config.yaml 单一收口 + 功能开关 + 密钥分级）

## Why

当前 22 个 capability spec 中无独立的 configuration capability，配置语义散落于各模块：LLM 提供商配置为必选项、IM 模块账户/ID/密钥接入信息、功能开关（feature flag）均无单一权威收口，导致配置落点、密钥存放、开关机制三处语义空白。`changes/0006-llm-provider/design.md` 遗留 Open Question「模型配置并入 config.yaml 还是独立 llm.yaml」长期未决（来源：exploration_findings.md，2026-09-25）。此外，工程侧缺少 ruff/pyright/pre-commit/GitHub Actions CI 工具链（pyproject.toml 无 lint/typecheck 配置，.github/ 不存在，tests 仅 test_smoke.py），开发体验与 CI 校验空白。

## What Changes

- **新增 configuration 横切能力**：独立 capability（第 5 横切 = 第 23 spec），以 config.yaml 为单一收口（决策 2A），env 覆盖 + 默认值兜底，明确配置源与分层。
- **LLM 提供商配置（必选）**：provider/model/endpoint/api_key 统一入 config.yaml，缺失则阻断启动并报明确错误；关闭 0006 Open Question（模型配置并入 config.yaml，非独立 llm.yaml）。
- **功能开关（feature flag）**：模块级启用/禁用，关闭则不加载，覆盖 evolution/rag/mcp/voice_output/distributed 等模块。
- **IM 接入配置**：账户/ID/密钥接入信息；密钥经 env/keychain，不入 yaml 明文（决策 3A）。
- **密钥分级与安全**：敏感密钥不入 yaml 明文，日志/报错脱敏。
- **配置校验与生效**：schema 校验、变更即生效、失败回滚不留半写状态。
- **03-interfaces**：configuration 照 durability 先例只建单 spec.md，不单独建 03-interfaces/configuration-interface.md（配置语义已内嵌 spec）。
- **adr.md**：追加 ADR-0034（configuration 为独立横切能力 + 单一 config.yaml 收口 + 密钥 env/keychain 分级的决策）。
- **architecture-overview.md**：横切能力计数 4→5 及横切行/横切表/核心组件表/运行时视图/部署树共 6 处同步。
- **开发工具链落地**：ruff（lint+format）+ pyright（typecheck）+ pre-commit + GitHub Actions CI（lint/typecheck/test/openspec validate）配套落地。

## Impact

- **Affected specs**：`configuration`（新增，第 23 spec，单 spec.md）；配置语义为 `llm-provider`/`ui`/`im`/`git` 提供挂载点引用（仅语义引用，不修改既有 spec）
- **Affected docs**：`00-product/requirements.md`（+1.23 配置管理）、`01-architecture/architecture-overview.md`（横切计数 4→5 + ASCII 横切行 + 横切能力表 + 核心组件表 + 运行时视图 + 部署树，共 6 处）、`01-architecture/adr.md`（+ADR-0034）、`00-product/design-completeness-eval.md`（模块计数 22→23）、`changes/0006-llm-provider/design.md`（关闭 Open Question）
- **Affected code**：无（架构设计与设计文档落地；工程实现依赖后续任务）
- **Dependencies**：ADR 编号=当前最大+1（0034）；横切能力计数 4→5；specs 22→23 需同步 requirements.md 1.x 清单与 design-completeness-eval.md「N 模块」数字口径；不引入新框架

