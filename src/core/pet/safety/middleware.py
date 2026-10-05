"""pet-safety → loop 的 before 接缝：越界动作阻断 + 通知主人（change 0081 / 账本 E25）。

- **before 接缝**（`middlewares`）：越界 ⇒ 返回**终止 Action**（本轮终止）—— 与 loop 既有
  `decline()` 路径同构（`observe()` 见 `data["reply"]` 即 `ctx.finish()`），无需加 loop 语义；
  并**通知主人**。
- **会话状态不动**：「暂停」= 本轮终止，**非** `suspend()` —— 生产无 `resume()` 调用方，
  转让行态即**永久楔死**（用户裁决，已写进 pet-mode 规格）。

**工具面收窄（R11）**由组合根的**受限 ToolProvider** 完成（只注册白名单内真实工具，未注册 =
结构化拒绝，且宠物看不到越界工具）；本中间件是**边界（R12）**：即便工具已注册，动作仍可能越界
（写 / 不可逆 / 爆炸半径外）。两者职责不重叠，避免两处真源。

对应规格：`doc/openspec/specs/pet-mode/spec.md`「Pet Safety Bounds」；ADR-0077。
"""

from __future__ import annotations

from collections.abc import Callable

from core.loop.protocol import Action, LoopContext
from core.pet.core import SafetyLayer

# 半径判定取 target 的候选参数键（真实工具参数名各异；取首个命中的非空字符串）。
_TARGET_KEYS = ("path", "file", "url", "target")


def _target_of(args: dict[str, object]) -> str:
    for key in _TARGET_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def build_safety_middleware(
    bounds: SafetyLayer, *, notify: Callable[[str], None] | None = None
) -> Callable[[LoopContext, Action], Action | None]:
    """构造 before 中间件：越界动作短路本轮并通知主人（无通知器则静默阻断）。"""

    def middleware(ctx: LoopContext, action: Action) -> Action | None:
        if action.is_terminal:
            return action
        decision = bounds.check(action.tool_id, _target_of(action.args))
        if not decision.blocked:
            return action
        if notify is not None:
            notify(f"宠物越界被拦截：{decision.reason}（工具 {action.tool_id}）")
        return Action(args={"reply": f"已按安全边界阻断：{decision.reason}，本轮终止。"})

    return middleware
