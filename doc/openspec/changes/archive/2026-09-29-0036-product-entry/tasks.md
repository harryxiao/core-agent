# Tasks

## 1. spec 契约（P0）

- [x] 1.1 ADDED「宠物模式配置」pet.enabled / pet.persons_dir 纳入 ConfigSpec 单一真源

## 2. pet.* ConfigSpec 落地（M6，P1）

- [x] 2.1 models.py 新增 PetConfig（enabled / persons_dir）+ AppConfig.pet 字段
- [x] 2.2 manager.py `_CONFIG_SPECS` 补 pet.enabled / pet.persons_dir 两条 ConfigSpec
- [x] 2.3 PetSession 构造时经 resolve() 加载对应 pet.md 人格

## 3. entry（M6，P1）

- [x] 3.1 pyproject `[project.scripts] core-agent = "core.entry:main"` + fastapi/uvicorn/textual 依赖
- [x] 3.2 `src/core/__main__.py` + `entry.py`（argparse 全命令面 + -h 三级帮助）
- [x] 3.3 argparse 32 动词 + 14 flag 与 cli-contract-baseline.md 逐条对齐
- [x] 3.4 入口复用 cli-ops CommandGroup/ParamMapper，不另起命令解析

## 4. serve（M6，P1）

- [x] 4.1 `WebBridge.serve()` 接真实 FastAPI（懒 import），暴露 UIAPILayer 9 方法端点
- [x] 4.2 SSE 流式 run_loop + 断线重连

## 5. repl（M6，P1）

- [x] 5.1 `CLIBridge.connect()` 扩展为 Textual 交互循环（多轮上下文 + barge-in）
- [x] 5.2 运维命令面不并入 REPL（仍走 cli-ops）

## 6. pet.md + user-guide（M6，P1）

- [x] 6.1 多宠物 persona 文件加载 + pet 激活入口落到 `PetActivator.activate_from_cli`
- [x] 6.2 user-guide 六节落盘（安装/配置/help/启动/LLM）

## 实现说明

- **2.3**：persona 经 entry 层 `resolve("pet.persons_dir")` 读取目录 + `load_persona()` 解析后 DI 注入 `PetSession(persona=...)`，保持 pet_core 与 configuration 解耦（未在 PetSession 内直接调 resolve，避免为一行配置制造耦合）。
- **3.4**：argparse 命令面由 cli-contract-baseline.md 派生；全局 flag 复用 ConfigSpec 单一真源（`config_specs()` 驱动 `_add_config_flag`，与 ParamMapper 同源）；status/doctor 路由 `CLICommandDispatcher`（cli-ops dispatcher.py），未另起第二命令解析真源。
- **4.2**：断线重连属客户端侧（SSE 断开后由 Web SPA 重连），M6 范围仅服务端（无 SPA），服务端交付 SSE 流式 run_loop 已落地并经测试覆盖。
