# 设计 — WebUI 设置页（Svelte SPA + Tauri 壳 + sidecar 拉起）（change 0100）

## 1. 不新开架构决定：落地 ADR-0014 / ADR-0015

栈（Svelte SPA / Tauri 壳 / 复用同一构建产物）**已由规格与 ADR 定死**（`ui/spec.md:91/105`、
ADR-0014 / ADR-0015）。本项只做落地，**不重议选型**。

## 2. 静态挂载：可选产物 + 不遮蔽端点

`build_app` 末尾按 `frontend/dist/index.html` 是否存在分流：

| 产物 | 行为 |
|---|---|
| 存在 | `app.mount("/", StaticFiles(directory=dist, html=True))` |
| 缺失 | 不挂载 ⇒ 纯 API 模式（后端可独立验收） |

**为何按「存在与否」而非硬依赖**：本仓后端一直是可独立运行的（`tests/test_serve.py` 的 `build_app(api)`
不带任何前端产物），`serve` 不该因**没跑过 npm** 而启动失败。这也让 CI 只需 Python 侧四门。

**为何挂 `/` 不遮蔽端点**：Starlette 的 `Mount` 在路由表中按注册顺序参与匹配，显式路由
（`/session`、`/llm-config`…）**先注册**、`Mount("/")` **最后注册** ⇒ 既有端点优先命中。
测试锁死该事实（`test_static_mount_does_not_shadow_endpoints`），防将来有人把 `mount` 提到最前。

## 3. SPA 结构（`frontend/`）

```
frontend/
├── package.json          # svelte + vite + @sveltejs/vite-plugin-svelte（无其他运行时依赖）
├── vite.config.js        # base: "./"（相对路径 ⇒ 桌面壳 file:// 与 Web 同产物可用）
├── index.html
└── src/
    ├── main.js
    ├── App.svelte        # 两页签：会话 / 设置（无路由库，一个 $state 足够）
    ├── lib/api.js        # fetch 封装：GET/PUT /llm-config、POST /session、POST /run(SSE)
    └── views/
        ├── Chat.svelte       # 建会话 → 发消息 → 读 SSE 增量渲染
        └── Settings.svelte   # LLM 配置表单（含 0098/0099 的窗口与预算旋钮）
```

**三个口径**：

- **`base: "./"`**：产物用相对路径引用资源 ⇒ 同一 `dist/` 既能被 FastAPI 挂在 `/`，也能被 Tauri 以
  `file://` 加载（规格「Web 与桌面 100% 一致」的**物理前提**；绝对路径 `/assets/...` 在 `file://` 下必 404）。
- **设置页只收 `${VAR}` 引用**：前端在提交前校验 `^\$\{.+\}$`，明文**不发请求**（后端也拒 —— 两层，
  前端这层只是**少一次无谓往返**，不是安全边界）；`context_window` 为 `0` ⇒ 显示「未配置」。
- **生效值回显**：设置页展示 `GET /llm-config` 回传的 `token_budget`（**派生后的预算**，见 ADR-0092 §⑤），
  用户改 `context_window`/`output_reserve` 保存后能立刻看到预算随之变化。

## 4. sidecar 拉起（`DesktopBridge`，账本 C8 代码半）

`_default_start` 由「直接 raise」改为**参数化 spawn**：

```
python -m core.entry serve --host 127.0.0.1 --port <port>
```

- **不经 shell**（`subprocess.Popen([...])` 列表形式）—— 避免 shell 解释与注入面（同 `0090`
  `SubprocessGitBackend` / `0091` `SubprocessGateExecutor` 口径）。
- **`sys.executable` 而非字面量 `python`**：sidecar 必须与被拉起方**同解释器**（venv/uv 环境下
  `python` 未必是同一个）。
- **注入缝**（`start_impl` / `spawn`）已存在 ⇒ 离线验证用**假可执行体脚本**断言 argv 逐项、不经 shell、
  返回值/失败处理；**不真起 uvicorn**（那会让单测挂住）。
- **失败不静默**：spawn 抛 `OSError`（可执行体不存在）⇒ 归一为 `UiError(UI_SIDECAR_FAILED)` 并以非零退出码
  报告，不假装成功。

## 5. 为何不做 TTS / 多模态前端

账本 C7（TTS）与多模态上传**与「LLM 配置能生效」无因果**，且多模态依赖模型能力探测（`ui/spec.md`
「模态能力缺失降级」）—— 混入会让本项从「补入口」膨胀成「补一条产品线」。各自另案。

## 6. 与 0098 / 0099 的边界

0098 给「可配」→ 0099 给「改了立即生效且不丢」→ **0100 给「点得着的界面」**。三者顺序不可换；
本项**零改动** 0098/0099 的配置与热更新语义，只在**最外层**加界面与静态挂载。
