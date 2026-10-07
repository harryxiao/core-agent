# Change: 可选 Web 依赖的测试守卫规范（importorskip 前置）

## Why

`tests/test_serve.py` 顶部存在 `from starlette import status` 裸导入，位于 `pytest.importorskip("fastapi.testclient")` 守卫**之前**。在未安装 web 可选依赖（fastapi/starlette）的环境里，导入在守卫生效前即抛 `ModuleNotFoundError`，导致 pytest **collection error**，中断整个测试会话而非优雅 skip。这与「可选能力测试必须在缺依赖环境优雅跳过」的意图相悖。

## What Changes

- `tests/test_serve.py`：将 `pytest.importorskip("fastapi.testclient")` 前置为文件首个导入动作，starlette 导入移至守卫之后（`# noqa: E402`）
- `ui/spec.md` 追加一条 Requirement：Web 可选依赖测试的 importorskip 守卫规范——所有可选依赖模块级导入 MUST 位于 `importorskip` 守卫之后；缺依赖时整文件 SHALL 优雅 skip（零 collection error）

## Impact

- **Affected specs**：`ui`（追加 1 条 Requirement）
- **Affected docs**：无
- **Affected code**：`tests/test_serve.py`（导入顺序调整，测试逻辑零改动）
- **Dependencies**：无
