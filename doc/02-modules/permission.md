# 模块设计：权限与审批管控（Permission & Approval Gate）

> 对应规格：`doc/openspec/specs/permission/spec.md` ｜ 接口：`doc/03-interfaces/permission-interface.md`
> 定位：**横切边界层**，是智能体安全落地的核心，解决裸模型无约束执行的失控风险。

---

## 1. 模块定位

权限与审批管控是 L0 确认门（Confirmation Gate）之上的**策略层**：它不决定"怎么做"，而决定"**能不能做、需不需要人点头**"。

它把上一层的可逆效应追踪（EffectTracker）与 coeffect 注入（CoeffectResolver）**升级为三级权限体系 + 人工审批流 + 沙箱隔离**，是所有写操作的强制前置检查点。

**设计原则**：默认拒绝（deny-by-default）。凡未显式授权的操作一律拦截，高危操作必须有人工审批。

---

## 2. 内部组成

```
PermissionGate（横切）
├── PolicyEngine       分级权限判定：read / data-edit / high-risk
├── ApprovalWorkflow   人工审批流：发起 → 待审 → 批准/拒绝 → 归档
├── SandboxManager     沙箱隔离：独立环境执行，执行完自动销毁
├── RiskClassifier     风险分级：操作属性 → 风险等级（默认 high-risk）
└── AuditTrail         审批与权限决策的审计日志
```

---

## 3. 关键设计

### 3.1 分级权限体系（三级）

| 等级 | 说明 | 默认行为 |
|---|---|---|
| `read` | 只读查询：读文件/查状态/只读 API | 放行（受 coeffect 约束） |
| `data-edit` | 数据编辑：写文件/改配置/DB 写 | 放行 + 可逆效应记录 |
| `high-risk` | 高危操作：删文件/杀进程/大额交易/系统级写入 | **默认拦截**，强制人工审批 |

- 分类依据：操作类型 × 作用对象 × 影响面（爆炸半径）。
- 分级结果进入每个 effect 的 `risk_level` 字段，供 EffectTracker 与审计复用。

### 3.2 人工审批流

```
[拦截] high-risk 操作
   └─► ApprovalWorkflow.create(request)   # 生成审批单（含操作摘要、影响面、回滚预案）
         └─► ask_user（等待人工批准/拒绝）
               ├─ 批准 ─► 放行执行（仍记录可逆效应）
               └─ 拒绝/超时 ─► 阻断执行 + 写审计
```

- 审批单带 TTL，超时默认拒绝（fail-closed）。
- 审批结果与请求一起归档，可回溯"谁在何时批准了什么"。

### 3.3 沙箱隔离机制

- 所有代码执行、Shell 执行默认在**独立沙箱环境**运行（子进程 + 受限文件系统/网络 + 资源配额）。
- 执行完成后**自动销毁**沙箱，不留残留，避免污染宿主系统。
- 沙箱类型可插拔：`local-subprocess` / `container`（v0.5+），统一由 SandboxManager 调度。

---

## 4. 与既有机制的衔接

| 既有机制 | 本模块的增强 |
|---|---|
| CoeffectResolver（L0） | 权限等级作为必需 coeffect 注入，缺失即拒绝 |
| EffectTracker（L0） | 不可逆/高危效应进入特殊审计区，审批单关联 trace_id |
| 确认门（loop） | loop 的 ask_user 门由本模块的 ApprovalWorkflow 接管 |

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 未授权操作 | 拦截，返回 `PERMISSION_DENIED`（含所需等级） |
| 高危操作未经审批 | 拦截，返回 `APPROVAL_REQUIRED`，创建审批单 |
| 审批超时 | fail-closed 拒绝，写审计 |
| 沙箱启动失败 | 阻断执行，返回 `SANDBOX_UNAVAILABLE`，不降级到宿主直跑 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/permission-interface.md`
- 规格：`doc/openspec/specs/permission/spec.md`
- 测试：`doc/04-testing/test-cases.md`（PERM 系列）
