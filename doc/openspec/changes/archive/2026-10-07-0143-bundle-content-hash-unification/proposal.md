# 0143 · bundle 内容哈希双口径归一（账本 E84-a）

> 账本：`coding-plan/phase-34.md` §1 **E84**（拆二之 **a**：composition 真内容哈希接线）
> 规格面：`composition/spec.md` **MODIFIED「bundle 分发格式」**（+2 Scenario）
> ADR：**0135** ｜ 配对：`0141`（E84-b：deployment 侧退化哈希**无 spec SHALL** ⇒ 已记已知取舍）

## Why

同一概念「bundle 发布哈希」在仓内存在**两套口径**，且 **wired 的一方是退化口径**：

- **真口径（孤置）**：`composition/packager.py:18-21 content_hash` —— 由**制品内容**（`plugin_id@generation`
  有序拼接）派生，`BundlePackager.pack` / `unpack` 都按它校验（「bundle 携带哈希保证一致」的**唯一实现**）。
- **退化口径（wired）**：CLI `release publish` 走 `entry.py:1030-1032 _content_hash(version)`
  = `sha256(版本名)[:16]` —— 哈希取自**元信息**（版本名），与制品内容无关，自注「CLI 无真实制品内容」。

后果有两重：① 真口径 `content_hash` 全仓**零引用**（composition 零接线 ⇒ 「真口径孤置」）；
② 发布记录里的哈希**不承载内容语义** —— 内容不同、名字相同的两次发布哈希相同，名字不同、内容相同的
两次发布哈希不同（**与「保证跨部署一致」的语义正好相反**）。规格侧，`composition/spec.md`
「bundle 分发格式」只 SHALL「bundle 携带哈希 / 校验失败拒绝引入」，**未**把「哈希由制品内容派生」写成
SHALL ⇒ 退化口径在规格上**无据可依却是唯一在跑的路径**。

## What

**规格先行**：把内容哈希口径写成 SHALL（MODIFIED「bundle 分发格式」）：

1. **口径入规格**：bundle 哈希 SHALL 由**制品内容**（插件引用集合的规范形 `plugin_id@generation`
   有序拼接取 SHA-256）派生；**内容相同 ⇒ 哈希相同，内容不同 ⇒ 哈希不同**；SHALL NOT 以版本名 /
   清单文件名等**元信息**充当内容哈希。
2. **发布入口入规格**：CLI `release publish <bundle 制品清单>` 读制品清单（声明 `plugin_refs`）并经
   上述口径发布；清单缺失 / 不可读 / 非法 ⇒ 结构化拒绝（`BUNDLE_INVALID`）且**既有发布记录不变**，
   SHALL NOT 静默退化为元信息哈希。
3. **两条新 Scenario 钉住**：同内容异元信息 ⇒ 同哈希；清单缺失 ⇒ 不产假账。

**实现**（外科手术，两处）：

- `src/core/composition/packager.py`：新增 `BundlePackager.load_manifest(location)` —— 读清单 JSON
  （`plugin_refs` → `PluginRef`）→ 复用既有 `pack()` 得**真口径哈希**；格式问题抛 `CompositionError(BUNDLE_INVALID)`
  （沿用既有错误码「bundle 校验和 / 格式损坏」，**不新增错误码**）。
- `src/core/entry.py`：`_release` 的 publish 分支改走 `load_manifest`（`ReleaseInfo.hash = bundle.hash`），
  **删除** `_content_hash`（含随之无用的 `import hashlib`）；`except` 补 `CompositionError`。

**为何入参是「制品清单路径」而非「名字」**：发布必须交出**制品内容**，否则无从派生内容哈希；
沿用仓内既有约定 —— `plugin install <asset> --source local` 的 `_resolve_local` 即把位置参数当
**manifest JSON 路径**（`plugins/install.py:68-75`）。清单是 bundle 内容的载体，不是新发明的格式。

## 影响

- **行为变更**：`core-agent release publish` 的位置参数由「bundle 版本名」变为「bundle 制品清单路径」；
  清单不可读 ⇒ **拒绝发布**（退出码 1），不再「以版本名哈希照常发布」。
- **消「真口径孤置」**：`composition.packager.content_hash` 经 `pack()` 首次被 CLI 路径消费。
- **零新概念**：不新增错误码、不新增命令、不新增 flag（32 动词 + 14 flag 基线不变），不触
  `exclude_source_prefixes=("beast.",)` 与 `CoeffectResolver` 密钥红线。
- **与 0141 配对**：deployment 侧 `ReleaseInfo.hash` 不参与校验（`grep` 零消费）⇒ 本 change 只归一**口径与
  入参**，不给 deployment 引入新的校验语义（那属另账）。

## 验证

- `tests/test_composition.py`：`load_manifest` 同内容异清单名 ⇒ 同哈希；改 `generation` ⇒ 哈希变；
  缺失 / 非法 JSON / `plugin_refs` 非法 ⇒ `BUNDLE_INVALID`。
- `tests/test_entry.py`：`release publish <清单>` ⇒ 退出码 0 + 「已发布版本 <name>」；同内容两清单 ⇒
  `releases.json` 两条记录哈希**相同**；异内容 ⇒ 不同；清单缺失 ⇒ 退出码 1 + 落 `releases.json` 不变。
- `.venv/bin/ruff check src tests` / `ruff format --check src tests` 全绿；`pyright` **0/0/0**。
- `.venv/bin/pytest -q` ⇒ **1680 → 1693**（+13：composition 10 + entry 3）。
- `openspec validate --all` ⇒ 31 passed / 0 failed（归档后回落 30 / 0）。

## 风险与已知局限

- **CLI 契约变更**：`release publish` 位置参数语义变化 ⇒ 同步改 `coding-plan/cli-contract-baseline.md`
  §2 动词表（第 27 行动词行）与 `doc/03-interfaces/deployment-interface.md` §3。
- **清单 schema 仅覆盖 `plugin_refs` + 可选 `name`**：bundle 的 `version` / `deps`（循环依赖检测）不在本账
  清单面内 —— `pack()` 的版本仍为 `1.0.0`；如果将来要发布带依赖图 / 显式版本的 bundle，另立账。
- **deployment 侧哈希仍不被消费**（E84-b）：`ReleaseInfo.hash` 目前无任何读取方 ⇒ 本 change 保证「写进去的
  哈希是真口径」，**不保证**任何一处在校验它。
