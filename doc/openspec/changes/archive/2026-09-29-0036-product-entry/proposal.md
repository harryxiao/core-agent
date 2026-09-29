# Change: Phase 9 产品化入口层——entry / serve / repl / pet.md / user-guide（M6 可启动产品）

## Why

core-agent 当前「库可导入但无法启动」：无 `[project.scripts]`、无 `__main__.py`、无 argparse `-h`；`WebBridge.serve()` 占位抛 `RuntimeError`；`CLIBridge.connect()` 仅 `return UIAPILayer` 无交互循环；pet.md 无加载、`pet.*` 不在 ConfigSpec。M6 里程碑要求补齐「可安装、可启动、可调试」的完整产品形态。

## What Changes

- **pet 配置**（configuration，ADDED）：pet.enabled / pet.persons_dir 纳入 ConfigSpec 单一真源，禁止绕过 ConfigSpec 另起解析。
- **entry**（ADDED）：console_scripts + `__main__.py` + argparse 全命令面（-h 三级帮助，与 cli-contract-baseline 32 动词 + 14 flag 逐条对齐）。
- **serve**（MODIFIED）：`WebBridge.serve()` 接真实 FastAPI/HTTP+SSE 后端（替换占位抛错），暴露 UIAPILayer 全部 9 方法端点。
- **repl**（MODIFIED）：`CLIBridge.connect()` 扩展为 Textual 交互循环（多轮上下文 + barge-in）。
- **pet.md**（ADDED）：多宠物 persona 文件加载（`<name>.md` 每只一个）。
- **user-guide**（ADDED）：用户指南六节落盘（安装/主 Agent 配置/Pet 配置/help 清单/启动入口/LLM 配置）。

## Impact

- **Affected specs**：`configuration/spec.md`（1 ADDED，扩展既有 capability）
- **Affected docs**：`03-interfaces/configuration-interface.md`（PetConfig 已在，无变更）；`00-product/requirements.md`；`coding-plan/phase-9.md`；`coding-plan/README.md`
- **Affected code**：`src/core/configuration/models.py` + `manager.py`（PetConfig + pet.* ConfigSpec）、`src/core/entry.py` + `__main__.py`（入口）、`src/core/ui/web_bridge.py`（serve）、`src/core/ui/cli_bridge.py`（repl）、`src/core/pet_core/`（pet.md 加载）——M6 阶段
- **Dependencies**：pyproject 补 `fastapi` + `uvicorn` + `textual`（接入层边界依赖，按 ADR-0040 MAL 四条隔离）
