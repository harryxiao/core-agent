# design — 0088 pet 控制面 `/pet [cmd]`

## 决策

### ① 单一门面 `PetControl`（CLI 与 `UIAPILayer` 复用同一实现）

控制动词会有**两个宿主面**：CLI `pet <verb>` 与 `UIAPILayer.pet_command`（WebUI/app 前台 `/pet [cmd]` 的落点）。
若各自实现 verb → 会话操作的分发，就是**两份真源**（同 `0079` / `0086` 反复回避的坑）。

故新增 `src/core/pet/core/control.py::PetControl`：**verb → 会话操作 + 会话寻址** 收口一处；
CLI 与 `UIAPILayer` 都只**调用它**。`PetControl` 是无状态门面（持 `PetManager`），构造廉价 ⇒ 组合根各处
就地 `PetControl(runtime.pet_manager)`，**不给 `Runtime` 数据类加字段**（其字段集被多测试隐式断言）。

### ② 寻址：单宠物默认、多宠物须显式、未知 ⇒ `PET_NOT_FOUND`

- 未指定 `session_id` 且**仅一只**宠物 ⇒ 默认作用于它（前台 `/pet sleep` 的常见形态，免记 id）。
- 未指定且**多只** ⇒ **拒绝并列出可选 id**（SHALL NOT 猜测 —— 赌错宠物是静默的错操作）。
- 指定但**未注册** ⇒ `PET_NOT_FOUND`（CLI 退出码 1）。**对照既有 `PetManager.stop()` 静默 no-op** ——
  那是「注入式批量驱动」的容错取向；控制面是**人显式操作**，静默成功会让人以为宠物睡了、其实没动。

### ③ 动词 `wake` = `resume()`（命名沿用用户前台语汇）

- `sleep` → `PetSession.suspend()`（让行/休眠）、`wake` → `PetSession.resume()`（清让行态）、
  `assign` → `dispatch()`（换活；`0087` 已保证 dispatch 自动唤醒）、`stop` → `PetManager.stop()`、
  `status` → 结构化状态。
- **命名陷阱（显式记录）**：控制面 `wake` 是**恢复让行**，与 `PetSession.wake()`（**执行一次任务**）**语义不同**。
  仍取 `wake` 的原因：① 用户前台语汇是 `sleep`/`wake` 成对（本变更服务用户诉求①）；② 二者作用面不同
  （控制动词 vs 会话内部方法），且接口文档并列写明以防误读。**已否决**改名为 `resume`
  （更精确但丢失用户语汇，且 `resume` 与「让行恢复」的对应不如 `wake` 直白）。

### ④ `status` 不外泄偏好与任务正文

`status` 由 `PetSession.snapshot()` **过滤**得出（`session_id` / `state` / `sleeping`=`yielding` /
`pending`=任务数 / `wake_count` / `fault`），**不含** `preferences` 与 `tasks` 正文 —— 控制面是**观测面**，
无须把主人偏好与任务文本投给任何前台客户端（对齐「密钥只引用不读取」的隐私取向，且避免新造
`PetSession` 公开 API：不读私有、复用既有 `snapshot`）。

### ⑤ 作用域 = 本进程已注册会话

`PetManager` 只在注册/启停时写 `pets.json`，`list()` 返回**本进程内存**；另一进程的 `pet run` 常驻驱动
**不重读**注册表 ⇒ **跨进程控制今天不通**。用户已裁决「**仅同进程**」：本变更的控制面同样只作用本进程，
并在规格写明作用域（**有意不做**跨进程，避免造出「改了盘却没驱到 live 会话」的假象）。

## 影响面

- **既有 `pet stop` 输出**：CLI `pet stop` 现在经 `PetControl`，未知 id ⇒ 退出码 1（此前静默 no-op + 恒打印成功）。
  无测试断言旧行为（已核实）。
- **`0086` / `0087`**：控制面 `wake`/`assign` 的语义由二者落定（`assign` 自动唤醒、`sleep` 后唤醒被拒）。
- **`0089+`（若将来做跨进程）**：本变更的 `PetControl` 是唯一要扩展的点。
