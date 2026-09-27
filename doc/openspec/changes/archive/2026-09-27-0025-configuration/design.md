# Design: configuration 配置管理 capability 的边界与单一收口

## Context

探索态实测：22 specs 无独立 configuration 能力，配置散落各处、无统一收口（来源：exploration_findings.md，2026-09-25）。用户提出三点需求：

1. 功能属性文件类配置（feature flag 开关，可选功能模块启用/禁用）；
2. LLM 配置为必选项（provider/model/endpoint/api_key）；
3. IM 模块账户/ID/密钥的接入信息配置。

现状缺口：

- `llm-provider`（0006）：design.md Open Question 第 2 条「模型配置并入 config.yaml 还是独立 llm.yaml」悬而未决；
- `im-gateway`（0005）：账户/凭证配置方式未统一；
- 全库无 schema 校验、无 feature flag 机制、无密钥分级（敏感密钥可能误入明文）。

现有 capability 语义边界：`llm-provider` 只描述模型调用（completion/stream/embedding），`im-gateway` 只描述消息收发，二者都不回答「配置从何而来、如何开关、如何保护密钥」，故需独立 `configuration` capability 作为横切能力（第 5 横切，见决策 1A）。

## Decisions

1. **独立横切 capability**（决策 1A）：configuration 作为第 5 个横切能力，与 durability 并列；只描述配置语义（源/开关/密钥/校验/生效），不改 llm-provider / im-gateway 的 Requirement 正文，仅以「配置语义挂载点」引用。
2. **config.yaml 单一收口**（决策 2A）：所有配置统一到 config.yaml，env 覆盖 + 默认值兜底；不引入 llm.yaml / im.yaml 等分裂文件，避免多配置源冲突。
3. **密钥 env/keychain 分级，不入 yaml 明文**（决策 3A）：敏感密钥（LLM api_key、IM secret 等）只在 env 或 keychain 存储，yaml 中以 `${VAR}` 引用；日志/报错对密钥脱敏。
4. **feature flag 机制**：`features` 段模块级开关，关闭的模块不加载、不初始化，实现功能裁剪。
5. **关闭 0006 Open Question**：0006-llm-provider design.md 第 2 条「模型配置并入 config.yaml 还是独立 llm.yaml」→ 已决：并入 config.yaml（见本 change 与 ADR-0034），保留其余 2 条 Open Question。

## config.yaml schema 草案

```yaml
llm:                        # 必选（决策 2A）
  provider: deepseek        # openai/anthropic/deepseek/...
  model: deepseek-chat
  endpoint: https://...     # 可选，覆盖默认
  api_key: ${OPENAI_API_KEY}  # 决策 3A：引用 env，不落明文

features:                   # 功能开关
  evolution: true
  rag: true
  mcp: true
  voice_output: false
  distributed: false

im:                         # IM 接入（可选，决策 3A）
  gateway: wecom
  corp_id: "..."
  secret: ${WECOM_SECRET}   # 引用 env/keychain
```

## Risks

- **密钥误入 yaml 明文**：通过 schema 校验 + `${VAR}` 引用规范 + 日志脱敏规避。
- **变更即生效与回滚复杂度**：schema 校验通过才写盘，失败回滚不留半写状态（对齐 ui spec 半写回滚）。
- **与现有 capability 语义重叠**：llm-provider / ui / im / git 的配置语义仅作挂载点引用，不重复定义，保持既有规格稳定。

## Open Questions

- 密钥 keychain 具体后端实现待工程落地选择。
- feature flag 动态热更新 vs 启动时加载待工程实现确定。
- config.yaml schema 的 JSON Schema / 校验器选型待实现收敛。
