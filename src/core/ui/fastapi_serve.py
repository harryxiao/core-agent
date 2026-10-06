"""FastAPI/uvicorn 适配器（ui 接入层边界依赖）。

把 UIAPILayer 方法暴露为 REST + SSE 端点，供 `WebBridge.serve()` 使用。
按 ADR-0040 MAL 隔离：fastapi/uvicorn 仅此文件持有且函数内懒 import，
上层（web_bridge / UIAPILayer）不依赖具体 Web 框架。

对应接口：doc/03-interfaces/ui-interface.md §1.2（12 端点）。
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

from core.configuration.models import LLMConfig
from core.tools import ToolDef

from .api import UIAPILayer
from .errors import UiError, UiErrorCode
from .models import Event

# UiErrorCode → HTTP 状态码（结构化错误映射，不向客户端抛裸异常）。
_STATUS: dict[UiErrorCode, int] = {
    UiErrorCode.UI_SESSION_NOT_FOUND: 404,
    UiErrorCode.UI_MODALITY_MISSING: 400,
    UiErrorCode.UI_LLM_CONFIG_INVALID: 400,
    UiErrorCode.UI_LLM_KEY_UNSET: 500,
    UiErrorCode.UI_BARGEIN: 501,
    UiErrorCode.UI_SIDECAR_FAILED: 500,
}

# SPA 构建产物目录（change 0100）。**存在与否**决定是否挂载：不硬依赖前端产物，
# 后端可独立验收（没跑过 npm 也能 `serve`）。
_DIST_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def _opt_int(value: Any) -> int | None:
    """可空整数解析：缺省 / 空串 ⇒ ``None``；无法解析 ⇒ ``UI_LLM_CONFIG_INVALID``（不 500）。"""
    if value is None or value == "":
        return None
    try:
        return int(cast("int | str", value))
    except (TypeError, ValueError) as exc:
        raise UiError(UiErrorCode.UI_LLM_CONFIG_INVALID, f"非法数值字段：{value!r}") from exc


def serve(api: UIAPILayer, host: str, port: int) -> None:
    """启动真实 HTTP + SSE 服务（阻塞；懒 import uvicorn）。"""
    import uvicorn  # noqa: PLC0415 — 接入层边界依赖，MAL 懒 import

    uvicorn.run(build_app(api), host=host, port=port)


def build_app(api: UIAPILayer) -> Any:  # noqa: C901, PLR0915 — 12 端点注册，复杂度/语句数固有
    """构建 FastAPI 应用（懒 import fastapi），暴露 12 端点。"""
    from fastapi import FastAPI, Request  # noqa: PLC0415 — MAL 懒 import
    from fastapi.responses import (  # noqa: PLC0415 — MAL 懒 import
        JSONResponse,
        StreamingResponse,
    )

    def _ui_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        err = cast(UiError, exc)
        return JSONResponse(
            status_code=_STATUS.get(err.code, 500),
            content={"error": err.code.value, "message": err.message},
        )

    def create_session(body: dict[str, Any]) -> dict[str, str]:
        return {"session_id": api.create_session(str(body.get("mode", "cli")))}

    def list_sessions() -> dict[str, object]:
        return {"sessions": api.list_sessions()}

    def session_messages(session_id: str) -> dict[str, object]:
        return {"session_id": session_id, "messages": api.session_messages(session_id)}

    async def run(body: dict[str, Any]) -> StreamingResponse:
        session_id = str(body.get("session_id", ""))
        user_input = str(body.get("user_input", ""))

        async def stream() -> AsyncIterator[str]:
            try:
                async for event in api.run_loop(
                    session_id, user_input, modalities=body.get("modalities")
                ):
                    yield _sse_frame(event)
            except UiError as err:
                yield _sse_frame(
                    Event(
                        type="error",
                        payload={"code": err.code.value, "message": err.message},
                    )
                )

        return StreamingResponse(stream(), media_type="text/event-stream")

    async def run_task(body: dict[str, Any]) -> StreamingResponse:
        """编排任务入口（change 0122）：SSE 流式外发 `task.*` 进度事件（与 CLI `/task` 同事件面）。

        `run_task` 为异步生成器 ⇒ 会话校验 / 编排器缺失在**首帧**才抛出，故与 `run` 同型地
        在 `stream()` 内捕获 `UiError` 并转成**错误帧**（不裸抛、不静默成功）。
        """
        session_id = str(body.get("session_id", ""))
        goal = str(body.get("goal", ""))

        async def stream() -> AsyncIterator[str]:
            try:
                async for event in api.run_task(session_id, goal):
                    yield _sse_frame(event)
            except UiError as err:
                yield _sse_frame(
                    Event(
                        type="error",
                        payload={"code": err.code.value, "message": err.message},
                    )
                )

        return StreamingResponse(stream(), media_type="text/event-stream")

    def barge_in() -> dict[str, str]:
        api.barge_in()
        return {"ok": "true"}

    def get_memory(session_id: str) -> dict[str, object]:
        return api.get_memory(session_id)

    def compact(body: dict[str, Any]) -> dict[str, str]:
        api.compact(str(body.get("session_id", "")))
        return {"ok": "true"}

    def list_tools() -> dict[str, object]:
        return {"tools": [_tool_to_dict(t) for t in api.list_tools()]}

    def invoke_tool(body: dict[str, Any]) -> dict[str, object]:
        args = cast(dict[str, Any], body.get("args") or {})
        result = api.invoke_tool(str(body.get("tool_id", "")), args)
        return {
            "ok": result.ok,
            "data": result.data,
            "error": (
                {
                    "code": result.error.code,
                    "message": result.error.message,
                    "details": result.error.details,
                }
                if result.error is not None
                else None
            ),
            "effect_id": result.effect_id,
        }

    def get_llm_config() -> dict[str, object]:
        cfg = api.get_llm_config()
        limits = api.get_loop_limits()
        return {
            "provider": cfg.provider,
            "model": cfg.model,
            "endpoint": cfg.endpoint,
            "api_key_ref": cfg.api_key_ref,
            "reasoning_effort": cfg.reasoning_effort or "",
            "embedding_model": cfg.embedding_model,
            "context_window": cfg.context_window,
            # 回显**生效值**（派生后的预算），非旋钮原文（change 0099）
            "max_rounds": limits[0] if limits else None,
            "token_budget": limits[1] if limits else None,
        }

    def set_llm_config(body: dict[str, Any]) -> dict[str, object]:
        # 用户保存 ⇒ apply_llm_config（落盘 + 热生效），非启动期 hydrate 的 set_llm_config
        api.apply_llm_config(
            LLMConfig(
                provider=str(body.get("provider", "")),
                model=str(body.get("model", "")),
                endpoint=str(body.get("endpoint", "")),
                api_key_ref=str(body.get("api_key_ref", "")),
                reasoning_effort=str(body["reasoning_effort"])
                if body.get("reasoning_effort")
                else None,
                embedding_model=str(body.get("embedding_model", "")),
                context_window=_opt_int(body.get("context_window")) or 0,
            ),
            output_reserve=_opt_int(body.get("output_reserve")),
            max_rounds=_opt_int(body.get("max_rounds")),
            history_turns=_opt_int(body.get("history_turns")),
        )
        return {"ok": "true"}

    app = FastAPI(title="core-agent")
    app.add_exception_handler(UiError, _ui_error_handler)
    app.add_api_route("/session", create_session, methods=["POST"])
    app.add_api_route("/sessions", list_sessions, methods=["GET"])
    # 3 段路径：与 `/session`(POST) / `/session/compact`(POST) 段数或方法不同，无遮蔽
    app.add_api_route("/session/{session_id}/messages", session_messages, methods=["GET"])
    app.add_api_route("/run", run, methods=["POST"])
    app.add_api_route("/task", run_task, methods=["POST"])  # 编排任务（change 0122）
    app.add_api_route("/barge-in", barge_in, methods=["POST"])
    app.add_api_route("/memory", get_memory, methods=["GET"])
    app.add_api_route("/session/compact", compact, methods=["POST"])
    app.add_api_route("/tools", list_tools, methods=["GET"])
    app.add_api_route("/tools/invoke", invoke_tool, methods=["POST"])
    app.add_api_route("/llm-config", get_llm_config, methods=["GET"])
    app.add_api_route("/llm-config", set_llm_config, methods=["PUT"])

    # SPA 挂在**最后**（change 0100）：Starlette 按注册顺序匹配 ⇒ 显式路由先注册，
    # `Mount("/")` 不遮蔽既有 REST/SSE 端点；缺产物则不挂载（纯 API 模式）。
    if (_DIST_DIR / "index.html").is_file():
        from fastapi.staticfiles import StaticFiles  # noqa: PLC0415 — MAL 懒 import

        app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True))

    return app


def _sse_frame(event: Event) -> str:
    """Event → SSE data 帧（`data: {json}\n\n`）。"""
    data = json.dumps(
        {"type": event.type, "payload": event.payload},
        ensure_ascii=False,
        default=_json_default,
    )
    return f"data: {data}\n\n"


def _json_default(obj: Any) -> Any:
    """JSON 序列化兜底：dataclass → dict，其余 → str（loop 产物非 JSON 原生）。"""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return str(obj)


def _tool_to_dict(tool: ToolDef) -> dict[str, object]:
    return {
        "tool_id": tool.tool_id,
        "description": tool.description,
        "schema": tool.schema,
        "coeffects": tool.coeffects,
        "reversible": tool.reversible,
        "timeout_s": tool.timeout_s,
        "max_output": tool.max_output,
    }
