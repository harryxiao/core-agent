# design — 0091 ci_cd 门禁执行器（stdlib subprocess）

## 决策

### ① 执行器形态：`SubprocessGateExecutor`（可调用对象，工厂 `build_gate_executor`）

`CICDPipeline` 的注入面类型是 `Callable[[Gate], GateResult]`（`pipeline.py:40`），故执行器实现 `__call__(gate)`，
**既**能被缺省装配，**也**能原样注入（替换零改动）。工厂 `build_gate_executor(*, commands=None, cwd=None,
timeout=600.0)` 与 `git` 的 `build_backend()` 同形（`build_*` = 工厂）。

**为什么不改注入面为 `GateExecutor` Protocol**：既有类型别名（`Callable`）已被 `CICDPipeline` 与测试使用，
改 Protocol 是**无收益的抽象升级**（单一实现，YAGNI）；保留 `Callable` 即保留既有接缝。

### ② 命令解析：`shlex.split` + **不用 shell**

`GATE_COMMANDS` 的值是**我们自己**的常量命令串，非用户输入；但仍不以 `shell=True` 执行 —— 既免注入面，
也免去「哪层 shell / 引号语义」的平台差异。`cwd` 缺省 `None`（**继承调用进程 cwd**），可显式注入。

### ③ 失败归一到 `GateResult`，不抛

| 情形 | 结果 |
|---|---|
| 退出码 0 | `GateResult(passed=True)` |
| 退出码非零 | `GateResult(passed=False, reason="退出码 N：<输出尾部>")` |
| `FileNotFoundError`（工具未装 / 不在 PATH） | `GateResult(passed=False, reason="找不到可执行文件：<程序名>")` |
| `subprocess.TimeoutExpired` | `GateResult(passed=False, reason="门禁 <kind> 超过超时阈值 …")` |
| 未知门禁类型（`commands` 表未覆盖） | **抛** `CiCdError(GATE_FAILED)` |

前三行是「门禁未通过」，交 `CICDPipeline` 既有阻断路径；末行是**调用/配置错误**（不是门禁结果），
与 `CICDPipeline.gate` 对未知 kind 的判据同口径。

### ④ `reason` 含**有界**输出尾部（≤2 000 字符）

规格明文「返回失败门禁与**原因**」。此处**有意**与 `0090`（git 不回显 stderr）不同：门禁输出是**本地工具自身**
的诊断文本，无凭据面；git 的 stderr 可能含 `https://user:token@host`。以字符上限约束体积，避免把整份 pytest
输出塞进 `reason`（它会进异常文本 / 日志）。

### ⑤ 超时缺省 600s

四道门禁里 `pytest` 是全量套件（本仓 ~30s），600s 给足余量同时**杜绝无限挂起**（对齐规格 R5 对远程的取向：
宁可失败也不挂死）。可注入，便于测试用极小值验证超时路径。

### ⑥ 不动 `GATE_COMMANDS`

命令基准是 Phase -1 固化基线（`test_ci_cd.py::test_gate_commands_four_kinds` 逐条断言其形状），
本变更**只补「怎么跑」**。**已知接受项**：本仓四门的可执行体不在 PATH（ruff/pyright/pytest 分处不同 bin 目录），
故缺省执行器在本仓会按「工具缺失」如实判**未通过** —— 这是**正确**行为（执行器如实报告），
命令基准 / PATH 假设的调整是**另一次决策**（见 proposal「明确不做」）。

## 影响面

- **`CICDPipeline`**：`executor` 注入面与调用点不变；仅缺省值由「抛离线未接的函数」变为「工厂产出的可执行器」。
- **既有测试**：`tests/test_ci_cd.py` **零改动**（全部显式注入 executor 或断言错误码）。
- **无 Runtime / CLI / 工具面改动**（见 proposal「明确不做」）。
