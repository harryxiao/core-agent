# 模块设计：CI/CD 交付流水线（CI-CD）

> 对应规格：`doc/openspec/specs/ci-cd/spec.md` ｜ 接口：`doc/03-interfaces/ci-cd-interface.md`
> 定位：**"记忆即光谱"闭环的工程闸门**，lint/typecheck/test/build 四道质量门禁阻断不合格交付，制品发布提供版本化制品与发布通道。

---

## 1. 模块定位

交付流水线是"记忆即光谱"闭环的**工程闸门**：任何交付提交都必须先通过质量门禁，不合格交付被阻断，合格交付打包为版本化制品进入发布通道。

本模块覆盖两个能力——**质量门禁**（CICDPipeline）与**制品发布**（ArtifactPublisher），是交付可信度与可回滚性的最后一道防线。

---

## 2. 内部组成

```
CI-CD（工程闸门）
├── CICDPipeline      质量门禁：顺序执行 lint/typecheck/test/build
├── Gate              门禁实体：gate_id / kind（lint|typecheck|test|build）/ blocking
├── PipelineRun       流水线执行结果：run_id / commit_ref / gates / status
├── ArtifactPublisher 制品发布：publish / rollback
└── Artifact          版本化制品：artifact_id / version / commit_ref / channel
```

---

## 3. 关键设计

### 3.1 四道质量门禁

- 门禁分 lint / typecheck / test / build 四类，lint/typecheck/test 为阻断级（blocking）。
- 门禁实现引用 development-toolchain（0025-configuration 工具链：ruff / pyright / pytest / 构建），不重复造轮子。
- **生产缺省执行器已落地**（change 0091／ADR-0086）：`SubprocessGateExecutor` 以 stdlib `subprocess` 直跑
  `GATE_COMMANDS`（不经 shell，零第三方依赖）；非零退出 / 工具缺失 / 超时一律归一为「该门禁未通过」+ 有界原因，
  不抛裸异常。命令基准 `GATE_COMMANDS` 不动（单一真源）；`commands` / `cwd` / `timeout` 可注入。
- **装配待消费者**：`ci_cd` 在 `src/` 内零调用方，其消费者（交付编排）未出现，故不加组合根字段 / `ci gate` CLI
  入口（另：本仓四门可执行体不在 PATH ⇒ 命令基准 / PATH 假设本身待一次决策）。

### 3.2 顺序执行与阻断

- 一次交付提交经 CICDPipeline 顺序执行四道门禁；全部通过交付放行，任一失败阻断交付并返回失败门禁与原因。
- 每道门禁带 `blocking` 标记，决定失败时是阻断还是仅告警（build 视工程阶段）。

### 3.3 版本化制品与回滚

- 门禁通过的交付打包为带版本号制品（artifact_id / version / commit_ref / channel），进入发布通道，可追溯来源提交。
- 制品可回滚到指定历史版本；版本不存在或通道不可达时返回对应错误码。

---

## 4. 交付闸门闭环

```
交付提交 ──run──► PipelineRun（顺序执行 lint/typecheck/test/build）
四道门禁全通过 ──► 交付放行；任一失败 ──► 阻断并返回失败门禁与原因
放行交付 ──publish──► Artifact（版本号 + 来源提交 + 发布通道）
Artifact ──rollback──► 回滚到指定历史版本
```

- 门禁通过是制品发布的唯一入口，制品发布永远以「已放行的 PipelineRun」为输入，保证上架的交付已通过全部闸门。
- 版本化 + 来源提交引用使每次发布可追溯、可回滚，闭环可审计。

---

## 5. 错误处理

| 错误码 | 行为 |
|---|---|
| `GATE_FAILED` | 门禁失败，阻断交付，返回失败门禁与原因 |
| `ARTIFACT_NOT_FOUND` | 制品版本不存在，回滚失败 |
| `CHANNEL_UNREACHABLE` | 发布通道不可达，发布失败 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/ci-cd-interface.md`
- 规格：`doc/openspec/specs/ci-cd/spec.md`
- 门禁实现：`development-toolchain`（0025-configuration 工具链：ruff / pyright / pytest / 构建）
- 交付编排：`doc/02-modules/orchestration.md`
