# Design: 可选 Web 依赖的测试守卫规范

## Context

Web（serve）能力依赖 fastapi/starlette 等可选依赖。pytest 的 `importorskip` 机制可在缺依赖时抛 `Skipped` 优雅跳过，但前提是：**守卫必须在任何可选依赖的模块级导入之前执行**。`tests/test_serve.py` 违反了这一顺序（starlette 裸导入先于守卫），在精简环境（仅装核心依赖）里产生 collection error，连锁中断全部测试。

## Goals / Non-Goals

- Goals：缺可选 web 依赖时 `test_serve.py` 优雅 skip，不影响其他测试；有依赖时行为不变
- Non-Goals：不改 web 功能代码、不改依赖声明、不引入新的测试工具

## Decisions

### 决策 1：守卫前置 + 延迟导入

```python
import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from starlette import status  # noqa: E402
```

理由：
- `importorskip("fastapi.testclient")` 同时覆盖 fastapi 与其传递依赖 starlette 的存在性检查（starlette 缺失时该导入同样失败触发 skip）
- `# noqa: E402` 保留 lint 合规；Ruff 的 E402 规则与 importorskip 延迟导入惯例冲突，属可接受的定向豁免

### 决策 2：固化为 spec 而非仅修文件

将守卫顺序写入 `ui/spec.md` 的 Requirement，防止后续回归（新增可选依赖导入时再次裸置于守卫之前）。

## Risks / Trade-offs

- 延迟导入略降可读性（`# noqa: E402` 显式标注缓解）
- 若未来守卫目标包名变更（如 fastapi 拆分），需同步更新守卫调用

## Migration Plan

1. 调整 `tests/test_serve.py` 导入顺序（已完成）
2. 追加 `ui/spec.md` Requirement（本次 change）
3. 全量门禁回归：lint + test + build 全绿
