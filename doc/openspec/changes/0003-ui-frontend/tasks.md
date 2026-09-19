# Tasks

## 1. 后端 API 层（P1）
- [ ] 1.1 实现 FastAPI 服务，暴露 loop/session/memory/tool-use/mcp 接口
- [ ] 1.2 实现 SSE 流式输出（会话增量推送）
- [ ] 1.3 实现 LLM 配置读写（provider/endpoint/key/base URL，落 config.yaml + settings.local.json）

## 2. Web SPA（P2）
- [ ] 2.1 实现聊天页（消息列表 + 流式渲染 + 折叠块）
- [ ] 2.2 实现会话管理页（新建/切换/删除/归档）
- [ ] 2.3 实现设置页（LLM API 可视化配置 + 用量/Token 展示）

## 3. 桌面壳（P3）
- [ ] 3.1 实现 Tauri 壳（开窗口 + 挂载 SPA）
- [ ] 3.2 实现 sidecar 拉起 Python 后端并管理生命周期
- [ ] 3.3 打包 Windows / macOS / Linux 安装包（CI 矩阵）

## 4. Textual CLI（P4）
- [ ] 4.1 实现 Textual App 入口（直连内核 API）
- [ ] 4.2 实现折叠块 / 流式输出 / 多面板 / 焦点管理组件
- [ ] 4.3 实现行内 diff 高亮与 Token 用量条
