# Tasks · 0141 账目校准（skip_specs，纯文档）

## 1. 规格（先行）

- [x] 1.1 **无 delta**（本 change **零行为变更**：不改 spec、不改 `src/`、不改 `tests/`
      ⇒ 无规格可先行）：写 `.openspec.yaml`（`schema: spec-driven` + `skip_specs: true`）
- [x] 1.2 `openspec validate 0141-ledger-calibration` 通过

## 2. 证据复核（先行 · 实测坐实，禁凭记忆）

- [x] 2.1 **E86**：`grep -rn "reconnect|retry|Last-Event-ID" frontend/src/ src/core/ui/` ⇒ **零命中**；
      `frontend/src/lib/api.js:55-63` 用 `fetch` + `ReadableStream` 读 POST SSE（**非** `EventSource`
      ⇒ 无浏览器原生自动重连）⇒ 假绿成立
- [x] 2.2 **E82**：`ui/spec.md` 全文无「pet/beast 专有 HTTP 端点」要求；宠物入口
      `src/core/ui/api.py:231/237`、神兽入口 `:263/276`（change `0137` 接线，**复用 `/run` 消息路径**）
      ⇒ 「Web 面缺失」不成立
- [x] 2.3 **E87**：`doc/10-codebase-engine/integration-plan.md:11` 与
      `codebase-engine-evaluation.md:71` **自述**「走 MCP 接入 / 复用 `mcp` capability /
      **不新增** `codebase` capability」⇒ 「有文档无实现」为形态误读
- [x] 2.4 **E71**：`doc/openspec/specs/memory/spec.md:26-29`（跨层检索）与 `:49-52`（检索失败降级）
      **并存**；正文 SHALL（`:31-37`）只要求「热/冷两档」⇒ `src/core/memory/store.py:110-115`
      的「全库扫描 + `_hot`」＝常驻降级态（合法）⇒ 非代码违约
- [x] 2.5 **E84-b**：`grep` 确认 deployment 侧无 bundle 内容哈希 SHALL（口径 SHALL 属 composition）
      ⇒ 记已知取舍；真口径接线由 change `0143` 承担

## 3. 台账订正（纯文档）

- [x] 3.1 `coding-plan/phase-9.md:114`：**取消勾选**「Web 断线重连」+ 就地注记实测口径（E86）
- [x] 3.2 `coding-plan/phase-34.md` §1 `E71` 行：证据栏补**定性订正**条文（非代码违约）
- [x] 3.3 `coding-plan/phase-34.md` §2 `E82` / `E87` 行：证据栏补**证伪**条文，复核栏标证伪
- [x] 3.4 `coding-plan/phase-34.md` §2 `E84` 行：证据栏补 **E84 拆二**（a ⇒ `0143`；b ⇒ 取舍）
- [x] 3.5 `coding-plan/phase-34.md` §2 `E86` 行：证据栏补**已落地（change `0141`）**
- [x] 3.6 `coding-plan/phase-34.md` §4：增列取舍条目（E84-b 退化哈希、E71 一阶索引路由未落）
- [x] 3.7 `coding-plan/phase-34.md` §5：增列证伪条文（E82、E87）+ 订正条文（E71）
- [x] 3.8 `coding-plan/phase-34.md` §0：补「事后订正」一句（2 条证伪 / 1 条定性订正）

## 4. 交叉引用（文档）

- [x] 4.1 `doc/04-testing/test-cases.md`：§57（TC-LEDGER，无新增用例；纯文档校准之交叉引用）
- [x] 4.2 `coding-plan/README.md`：三处索引行推进到 `0126`~`0141`（ADR 列表不变 —— 本 change 无 ADR）
- [x] 4.3 `coding-plan/phase-34.md` §9：`0141` 行 ⇒ **✅ 已落地（2026-10-07）**，ADR 栏 `—`

## 5. 门禁（直连二进制，禁 `uv run`）

- [x] 5.1 `.venv/bin/ruff check src tests` —— 绿
- [x] 5.2 `.venv/bin/ruff format --check src tests` —— 绿
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` —— 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` —— **1674 passed**（与 `0140` 收口逐字相同；纯文档 ⇒ 基线不动）
- [x] 5.5 `openspec validate --all` —— **31 passed / 0 failed**（归档后回落 30 / 0）

## 6. 收口

- [x] 6.1 手工归档至 `archive/2026-10-07-0141-ledger-calibration/`
- [x] 6.2 台账回填：`coding-plan/phase-34.md`（§0/§1/§2/§4/§5/§9）；`coding-plan/README.md` 3 处索引行
- [x] 6.3 记忆更新：`MEMORY.md` + `coding-plan-leftover-walkthrough.md`
- [x] 6.4 单次提交（`docs(ledger): 账目校准（change 0141）`）
