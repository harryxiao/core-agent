# 0088 — pet 控制面 `/pet [cmd]`（用户诉求①）

## 为什么

用户诉求：**在 WebUI / CLI / app 前台随时输入 `/pet [cmd]`** —— 查看宠物状态、让它**停止工作**、
**换一件活**、**睡觉**；配合 `0086`（工作中随时上报惊喜）与 `0087`（干完无任务自睡）构成完整交互模型。

今天宠物**只能被激活与驱动**（`gather|info|explore|walk|list|stop|run`），**没有控制面**：想让它睡觉 /
换活 / 看结构化状态，无处下手 —— 内核虽有 `suspend()` / `resume()` / `dispatch()`，但**没有任何宿主面调用它们**。

## 用户裁决

- **全量 ①②+③**、跨进程**仅同进程**；本变更 = **① 控制面**（②= `0086`、③= `0087` 已闭）。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/pet/core/control.py` | **新增 `PetControl` 门面**：verb → 会话操作（`status` / `sleep` / `wake` / `assign` / `stop`）+ 会话寻址（单宠物默认 / 多宠物须显式 / 未知 ⇒ `PET_NOT_FOUND`）；结构化 `status` **不外泄偏好与任务正文** |
| `src/core/pet/core/errors.py` | 新增错误码 `PET_NOT_FOUND` |
| `src/core/pet/core/__init__.py` | 导出 `PetControl` |
| `src/core/ui/api.py` | `UIAPILayer` 收 `pet_control` 注入面 + `pet_command(verb, *, session_id=None, goal=None)` 控制面（WebUI/app 前台 `/pet [cmd]` 的落点） |
| `src/core/entry.py` | `_pet` 增控制动词 `status` / `sleep` / `wake` / `assign`（复用同一 `PetControl`）；`_build_ui` 注入 `pet_control` |
| `doc/openspec/specs/pet-mode/spec.md` | ADDED「Pet Control Surface」（寻址 / 动词 / 状态 / 拒绝 / 同进程 + 5 场景） |
| `doc/03-interfaces/pet-mode-interface.md` | 增 §5 控制面契约 + `PET_NOT_FOUND` |
| `doc/02-modules/pet.md` | §3 增控制面小节 |
| `doc/01-architecture/adr.md` | ADR-0083 + 映射表行 |
| `doc/04-testing/test-cases.md` | TC-PET-08 |
| `doc/03-interfaces/ui-interface.md` | `pet_command` + `pet_control` 注入面 |

## 明确不做

- **不做跨进程控制**（用户裁决仅同进程）：`pets.json` 是快照，改盘不驱动 live 会话 —— 已在规格写明作用域。
- **不新增 `PetSession` 方法**：`sleep`/`wake`/`assign` 复用既有 `suspend()`/`resume()`/`dispatch()`；
  `status` 由 `snapshot()` 过滤而来（不读私有、不新造 API）。
- **不新增内核调度**：控制面只是把既有会话操作**收口成一个 verb 面**，不改生命周期语义。
- **不启用 `nonsense_comment` 等侵入面**：控制面只做控制，不扩任务类型。
