# Tasks 0237: 运行环境感知的 shell 方言

## 1. Specification
- [x] 1.1 delta ADDED loop「运行环境事实」：系统提示可注入 OS/默认壳/路径约定；未注入逐字不变；
      场景：注入后可见 / 未注入无块。
- [x] 1.2 delta MODIFIED tool-use「内置原子工具」：`code_run` 支持 python/bash/powershell；
      平台缺省；缺解释器 fail-closed、不静默改方言；场景覆盖 Win 缺省 PS、*nix 缺省 bash、
      缺 bash/缺 PS。
- [x] 1.3 delta ADDED ui「code_run 活动标题按方言命名」（PowerShell/Bash/Python 分设场景）。
- [x] 1.4 `openspec validate` 本 change 全绿。

## 2. Tests（先红）
- [x] 2.1 `EnvironmentSnapshot` / 探测：平台映射表（可用 monkeypatch `platform.system` +
      which 替身）；不依赖本机真实壳。
- [x] 2.2 planner：注入 snapshot ⇒ 系统提示含「运行环境」与 os/default_shell；`env_snapshot=None`
      ⇒ 无该块（与既有提示逐字兼容锚点）。
- [x] 2.3 `code_run` powershell：捕获 argv 含 `-Command`；无 pwsh/powershell ⇒ 结构化错误。
- [x] 2.4 缺省 type：Win snapshot ⇒ powershell；Darwin/Linux ⇒ bash。
- [x] 2.5 `type=bash` 且无 bash ⇒ 结构化错误，不回落 powershell。
- [x] 2.6 `type=python` 回归（仍 `sys.executable -c`）。
- [x] 2.7 TUI：`args.type=powershell` ⇒ 标题友好名 PowerShell；`bash` ⇒ Bash。

## 3. Implementation
- [x] 3.1 新增探测/快照模块（建议 `src/core/tools/env_shell.py` 或 `loop/env_facts.py`），
      纯函数 + 可注入 which。
- [x] 3.2 `planner.py`：可选注入 snapshot；装配「运行环境」块（D2 位置）。
- [x] 3.3 `builtin.code_run`：schema 扩 enum；handler 按 D3 解析默认与 argv；缺壳结构化错。
- [x] 3.4 工具 description 同步三方言与平台默认。
- [x] 3.5 TUI `repl`（或后继）按 type 映射友好名。
- [x] 3.6 `runtime` 组合根：生产路径注入真实探测快照到 planner（测试路径可关）。

## 4. Gates & Archive
- [x] 4.1 相关单测绿；ruff/pyright 触及文件绿。
- [x] 4.2 `openspec validate` 本 change 全绿；归档；提交
      `feat(tools): 运行环境感知的 code_run 方言（change 0237）`。
