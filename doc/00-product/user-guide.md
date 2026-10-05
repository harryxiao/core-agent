# core-agent 用户指南（M6 可启动产品）

> 本文是面向最终用户的启动指南，覆盖**安装 / 主 Agent 配置 / Pet 配置 / help 清单 / 启动入口 / LLM 配置**六节。
> 文中命令与输出均为实测结果（`python -m core` 等价于已安装的 `core-agent` 命令）。

---

## 1. 安装

要求 Python 3.11+。本仓库用 `uv` 管理依赖：

```bash
uv sync                      # 安装运行时依赖 + 建 .venv
pip install -e .             # 等价：可编辑安装，注册 core-agent 命令
```

安装后 `core-agent` 命令可用，`python -m core` 等价。核心运行时零第三方依赖（LLM 归一化 stdlib 手写 OpenAI 兼容）；接入层边界依赖 `fastapi`/`uvicorn`/`textual`。

验证：

```bash
core-agent --version
# core-agent 0.1.0
```

---

## 2. 主 Agent 配置

配置收口于 `config.yaml`（默认相对 cwd 读 `config.yaml`，可用全局 `--config PATH` 指定）。优先级链：

```
CLI flag  >  env var  >  config.yaml  >  默认值
```

最小可启动 `config.yaml`：

```yaml
llm:
  provider: openai
  model: gpt-4o
  endpoint: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}      # 只存 ${VAR} 引用，拒绝明文
features:
  voice_output: false
```

- `llm.provider` / `llm.model` / `llm.endpoint` 必选非空；`llm.api_key` 必须是 `${VAR}` 引用（明文直接拒绝启动）。
- `features.*` 为 feature flag：**门控名单内模块缺省装配**（未声明即开，change `0067` 口径），显式关闭写 `features.<模块>: false`；另有 env `CORE_FEATURES_<NAME>`、CLI `--feature <NAME>[=false]` 两条通道。取值 `true/false`·`yes/no`·`on/off`·`1/0`（大小写不敏感），其余取值**阻断启动**。
- 覆盖层：`--llm.provider` / `--llm.model` / `--llm.endpoint` / `--llm.api-key`（CLI），`CORE_LLM_PROVIDER` 等（env）。

单键读取（遵循同一优先级链 **CLI > env > config.yaml > 默认值**，change `0078`）：

```bash
core-agent config get permission.mode
# interactive
```

---

## 3. Pet 配置

宠物模式（后台自治会话）由 `pet.*` 两项控制，纳入 ConfigSpec 单一真源：

| 配置键 | CLI flag | env var | 默认值 |
|---|---|---|---|
| `pet.enabled` | `--pet-enabled` | `CORE_PET_ENABLED` | `false` |
| `pet.persons_dir` | `--pet-dir` | `CORE_PET_DIR` | `persons` |

`config.yaml` 示例：

```yaml
pet:
  enabled: true
  persons_dir: ./pets
```

- 未启用时 `core-agent pet ...` 输出 `宠物模式未启用（pet.enabled=false，可用 --pet-enabled 或 CORE_PET_ENABLED 开启）`。
- `pet.persons_dir` 指向多宠物 persona 目录，每只宠物一个 `<name>.md` 文件：

```markdown
name: 小橘
species: 猫
traits: 慵懒、敏锐
preferences: 晒太阳
---
慵懒但敏锐，喜欢在主人工作时安静陪伴。
```

---

## 4. help 清单

三级帮助：`core-agent -h`（顶层 + 全局 flag）→ `core-agent <command> -h`（子命令参数）→ `core-agent <command> <sub> -h`（子子命令参数）。

顶层命令面（19 子命令，无子命令则进 REPL）：

```
serve  app  start  stop  restart  probe  status  doctor  sessions
config  mcp  plugin  skill  session  run  release  pet  summon  recall
```

全局 flag（`core-agent -h` 可见全量）：`--profile` `--cwd` `--config` `--feature` `--verbose` `--quiet` `--log-level` `--llm.provider` `--llm.model` `--llm.endpoint` `--llm.api-key` `--im.gateway` `--im.corp-id` `--im.secret` `--permission-mode` `--pet-enabled` `--pet-dir` `--version` `-h/--help`。

命令面权威基线：`coding-plan/cli-contract-baseline.md`（32 动词 + 14 全局 flag）。

---

## 5. 启动入口

三种入口：

```bash
# CLI / TUI：无子命令进入交互会话（Textual REPL，多轮上下文 + barge-in 打断）
core-agent

# Web：HTTP + SSE 打开单 SPA（默认 127.0.0.1:8000）
core-agent serve --host 127.0.0.1 --port 8000

# Desktop：Tauri 壳 + sidecar（M6 范围外，未落地）
core-agent app
```

运行一轮任务：

```bash
core-agent run --prompt "总结当前目录"
core-agent session create     # 返回 32 位 session_id
```

Pet 激活（三入口之一）：

```bash
core-agent pet gather --name 小橘
core-agent pet list
core-agent pet run --interval 60    # 前台常驻驱动：按间隔唤醒每只宠物（Ctrl-C 停止）
```

进化冷路径（强制跑一轮；`--goal` 指定本轮迭代目标）：

```bash
core-agent evolve run                        # 由课程选目标（失败强度定序，已处理目标降权）
core-agent evolve run --goal memory.retrieve # 显式指定目标（直接采用，仍须人工 confirm 才发布）
core-agent evolve pending                    # 待人工确认的候选
```

---

## 6. LLM 配置

LLM 归一化经 stdlib OpenAI 兼容 HTTP，配置项与主 Agent 配置同源（`config.yaml` 的 `llm` 段）。四键：

| 键 | 说明 |
|---|---|
| `llm.provider` | 提供方（如 `openai`） |
| `llm.model` | 模型名（如 `gpt-4o`） |
| `llm.endpoint` | API URL（如 `https://api.openai.com/v1`） |
| `llm.api_key` | `${VAR}` 引用（如 `${OPENAI_API_KEY}`，明文拒绝） |

可选增强（非必选）：

| 键 | 说明 |
|---|---|
| `llm.embedding_model` | 记忆检索向量化模型（如 `text-embedding-3-small`），复用 `endpoint` 与密钥引用。未设置或不可达时记忆检索回退词法相似，不影响启动。 |

覆盖层（CLI flag > env > yaml）：

```bash
core-agent --llm.endpoint https://your-gateway/v1 --llm.api-key '${MY_KEY}' run --prompt "hi"
```

密钥安全：`api_key` 只存 `${VAR}` 引用，运行时经 `CoeffectResolver` 从 env / keychain 解析，绝不写入日志或记忆。
