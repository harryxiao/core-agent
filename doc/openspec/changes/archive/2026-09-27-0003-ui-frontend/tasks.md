# Tasks

> 注：本 Phase 按项目「不锁选型」立场，ui 仅落**可注入抽象**（三模复用同一 UIAPILayer 内核，无真实 FastAPI/SPA/Tauri/Textual）。
> 下方标注「真实后端未接」的项 = 抽象（统一 API + 注入 seam）已落地，真实前端/传输留待后续。

## 1. 后端 API 层（P1）
- [ ] 1.1 实现 FastAPI 服务，暴露 loop/session/memory/tool-use/mcp 接口—— 真实后端未接：UIAPILayer 会话/循环/记忆/工具/LLM 配置 API 已落地，真实 FastAPI 服务未接（WebBridge.serve 经注入 serve_impl）
- [ ] 1.2 实现 SSE 流式输出（会话增量推送）—— 真实后端未接：run_loop 异步流式 + LoopEvent→SSE 事件映射已落地，真实 HTTP/SSE 线协议未接
- [x] 1.3 LLM 配置读写（set/get_llm_config，key 只存 ${VAR} 引用拒绝明文）；落 config.yaml/settings.local.json 持久化 deferred

## 2. Web SPA（P2）
- [ ] 2.1 实现聊天页（消息列表 + 流式渲染 + 折叠块）—— 真实后端未接：WebBridge 注入 seam 已落地，真实 SPA 前端未接
- [ ] 2.2 实现会话管理页（新建/切换/删除/归档）—— 真实后端未接：SPA 前端未接
- [ ] 2.3 实现设置页（LLM API 可视化配置 + 用量/Token 展示）—— 真实后端未接：SPA 前端未接

## 3. 桌面壳（P3）
- [ ] 3.1 实现 Tauri 壳（开窗口 + 挂载 SPA）—— 真实后端未接：DesktopBridge.start_sidecar 注入 seam 已落地，真实 Tauri 壳未接
- [ ] 3.2 实现 sidecar 拉起 Python 后端并管理生命周期—— 真实后端未接：start_impl 注入 seam 已落地
- [ ] 3.3 打包 Windows / macOS / Linux 安装包（CI 矩阵）—— 真实后端未接

## 4. Textual CLI（P4）
- [ ] 4.1 实现 Textual App 入口（直连内核 API）—— 真实后端未接：CLIBridge.connect 复用同一 UIAPILayer（不另起命令解析），真实 Textual 前端未接
- [ ] 4.2 实现折叠块 / 流式输出 / 多面板 / 焦点管理组件—— 真实后端未接：Textual 前端未接
- [ ] 4.3 实现行内 diff 高亮与 Token 用量条—— 真实后端未接：Textual 前端未接
