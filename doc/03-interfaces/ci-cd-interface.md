# 接口设计：CI/CD 交付流水线（CI-CD Interface）

> 规格：`openspec/specs/ci-cd/spec.md` ｜ 门禁引用：`development-toolchain`（0025-configuration 工具链）

---

## 1. 实体模型

```python
@dataclass
class Gate:
    """门禁：一道质量校验，归属 lint/typecheck/test/build 四类之一。"""
    gate_id: str                    # 门禁标识
    kind: str                       # "lint" | "typecheck" | "test" | "build"
    blocking: bool                  # 是否阻断级（lint/typecheck/test 阻断，build 视工程阶段）

@dataclass
class PipelineRun:
    """一次交付流水线执行：顺序执行四道门禁的结果。"""
    run_id: str
    commit_ref: str                 # 交付提交引用
    gates: list[Gate]               # 顺序门禁
    status: str                     # "passed" | "blocked" | "running"

@dataclass
class Artifact:
    """版本化制品：门禁通过后的可追溯、可回滚交付物。"""
    artifact_id: str
    version: str                    # 带版本号
    commit_ref: str                 # 来源提交
    channel: str                    # 发布通道
```

---

## 2. CICDPipeline 接口（质量门禁）

```python
class CICDPipeline:
    def run(self, commit_ref: str) -> PipelineRun:
        """顺序执行 lint/typecheck/test/build 四道门禁；全部通过交付放行，任一失败阻断交付并返回失败门禁与原因。"""

    def gate(self, kind: str) -> Gate:
        """取回指定门禁；门禁实现引用 development-toolchain（ruff/pyright/pytest/构建）。"""
```

**生产缺省门禁执行器**（`src/core/ci_cd/pipeline.py::SubprocessGateExecutor`，经 `build_gate_executor()` 工厂产出）：
以 stdlib `subprocess` 直跑 `GATE_COMMANDS`（`shlex.split`，**不经 shell**），类型满足 `Callable[[Gate], GateResult]`
⇒ 缺省装配与注入替换**同一接缝**。构造参数 `commands` / `cwd` / `timeout`（缺省 600s）可注入。

| 情形 | 结果 |
|---|---|
| 退出码 0 | `GateResult(passed=True)` |
| 退出码非零 | `GateResult(passed=False, reason="退出码 N：<有界输出尾部>")` |
| 找不到可执行文件 | `GateResult(passed=False, reason="找不到可执行文件：<程序名>")` |
| 超过超时阈值 | `GateResult(passed=False, reason="门禁 <kind> 超过超时阈值 …")` |
| 未知门禁类型 | 抛 `CiCdError(GATE_FAILED)`（调用/配置错误，非门禁结果） |

---

## 3. ArtifactPublisher 接口（制品发布）

```python
class ArtifactPublisher:
    def publish(self, run: PipelineRun) -> Artifact:
        """门禁通过的交付打包为带版本号制品，进入发布通道。"""

    def rollback(self, version: str) -> Artifact:
        """回滚到指定历史版本。"""
```

---

## 4. 错误码

| 错误码 | 含义 |
|---|---|
| `GATE_FAILED` | 门禁失败（阻断交付，返回失败门禁与原因）；执行器侧另用于**未知门禁类型**（配置/调用错误） |
| `ARTIFACT_NOT_FOUND` | 制品版本不存在 |
| `CHANNEL_UNREACHABLE` | 发布通道不可达 |

---

## 5. 关联

- 规格：`openspec/specs/ci-cd/spec.md`
- 挂载：`development-toolchain`（0025-configuration 工具链：ruff/pyright/pytest/构建，门禁实现引用）、`02-modules/orchestration.md`（交付编排）
