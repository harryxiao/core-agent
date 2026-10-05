# 0091 — ci_cd 门禁执行器（stdlib subprocess，零三方依赖）（Phase 20 C3）

## 为什么

账本 `coding-plan/phase-20.md` §1 C3 / §4.2：`executor` 注入面（`pipeline.py:40-41`）与四道门禁命令基准
`GATE_COMMANDS`（ruff / pyright / pytest / uv build，`pipeline.py:21-26`）**均已就位**，但生产**缺省**执行器
`build_gate_executor` 对**任何**门禁都直接抛「离线未接」（`pipeline.py:29-34`）—— 即「交付流水线」在生产
**恒不可用**。与 Phase 19 反复记的「实现已落地、缺生产触达点」同型。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/ci_cd/pipeline.py` | **新增 `SubprocessGateExecutor`**：stdlib `subprocess` 执行 `GATE_COMMANDS`，退出码 / 工具缺失 / 超时归一为 `GateResult(passed=False, reason=…)`（不抛裸异常）；`build_gate_executor(...)` 由「无条件抛离线未接」改为返回该执行器 |
| `src/core/ci_cd/__init__.py` | 导出 `SubprocessGateExecutor` |
| `doc/openspec/specs/ci-cd/spec.md` | MODIFIED「交付流水线」：补生产缺省执行器口径 + 2 场景 |
| `doc/03-interfaces/ci-cd-interface.md` | §2 补生产执行器；§4 `GATE_FAILED` 行补注 |
| `doc/02-modules/ci-cd.md` | §3.1 门禁实现落到实现 |
| `doc/01-architecture/adr.md` | ADR-0086 + 映射表行 |
| `tests/test_ci_cd_subprocess.py` | 新：真实 subprocess 跑注入命令（通过 / 失败 / 工具缺失 / 超时 / 未知门禁） |

## 决策

- **stdlib `subprocess` 执行既有 `GATE_COMMANDS`**：门禁命令是 Phase -1 已固化基线，本变更**不另起命令表**
  （单一真源不动），只补「怎么跑」；零第三方依赖（ADR-0044），`shlex.split` + **不用 shell**（无注入面）。
- **失败归一为 `GateResult(passed=False)` 而非抛异常**：门禁「跑不起来」（工具缺失 / 超时）与「跑失败」（非零退出）
  对上都是**该门禁未通过**，交给 `CICDPipeline` 按既有「门禁失败阻断」路径处理（规格场景不变）；执行器
  **不向调用方抛裸异常**（对齐 CLAUDE.md「结构化错误码，不向模型抛裸异常」）。
- **`reason` 取**有界**输出尾部**（上限 2 000 字符）：规格明文「返回失败门禁与**原因**」，一个「退出码 1」对使用
  者无信息量；此处与 change `0090` git「不回显 stderr」**有意不同** —— 门禁输出是**本地工具自身**的诊断文本
  （ruff / pyright / pytest 的失败摘要，无凭据面），而 git stderr 可能含带凭据的远程地址。
- **`build_gate_executor(...)` 改为工厂**（`commands` / `cwd` / `timeout` 可注入）：与 `git` 的 `build_backend()`
  同形（`build_*` = 工厂），并给出**可离线验证**的注入缝（测试注入 `sys.executable -c …` 即真实 subprocess，
  不依赖 PATH 上是否装了 ruff/pyright）。
- **未知门禁类型仍抛 `GATE_FAILED`**：`commands` 表覆盖不到即配置/调用错误（非「门禁未通过」），保持既有语义
  （与 `CICDPipeline.gate` 的未知 kind 判据同口径）。

## 明确不做（**偏离 phase-20 §4.1/§4.2 原记，理由如下**）

- **不做组合根装配 / 不做 `ci gate` CLI 入口**：`ci_cd` 在 `src/` 内**零调用方**（`grep` 全 0），其消费者是
  **尚未存在**的交付编排；且本仓四门命令的**可执行体不在 PATH**（ruff 在 `~/.cache/uv/binaries-*`、pyright 在
  其它 venv、pytest 在 `.venv/bin`）⇒ 此刻上 CLI 会给出一个**在本仓必然失败**的门面（`GATE_COMMANDS` 的
  命令基准 / PATH 假设本身需要一次决策）。故 C3 的「代码半」以**执行器实现 + 测试**收口，装配与 CLI
  并入消费者出现时的 change（与 `0090` 对 git 的判定同理）。
- **不做真实制品仓库通道**（`publisher._default_channel` 保持抛 `CHANNEL_UNREACHABLE`）：属**凭证半**（网络 + 仓库凭据），
  归 Phase 19 §5。
