/**
 * 主/子 Agent 视图模型（change 0294 / ADR-0284）。
 *
 * 纯函数、零 DOM/runes：数据全部来自既有 `task.*` 事件载荷（不建第二数据源，不接子
 * Agent 消息流）。`App` 持有状态，`TaskPanel` 与聊天区视图共用同一份模型。
 */

import { titleFromAction } from "./activity.js";

export const TAB_MAX_CHARS = 14;
export const REPLY_MAX_CHARS = 240;

/** 空状态：无在途任务、无快照、主视图。 */
export function initialTaskState() {
  return { tasks: [], lastTask: null, selected: null, notice: "", error: "" };
}

/** 子任务主题缩写：单行化 + 去空白 + 有界；空目标 ⇒ ""（调用方回退 `子任务 <id>`）。 */
export function abbreviateGoal(goal, max = TAB_MAX_CHARS) {
  const line = String(goal ?? "")
    .replace(/\s+/g, " ")
    .trim();
  if (!line) return "";
  return line.length > max ? `${line.slice(0, max - 1)}…` : line;
}

/** 子任务结果节选（有界；只呈现事件载荷里的 reply 字段）。 */
export function replyExcerpt(reply, max = REPLY_MAX_CHARS) {
  const text = String(reply ?? "").trim();
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** 里程碑事件 → 详情行（标题语法与 Chat/TUI 同源；载荷已白名单化）。 */
export function milestoneLine(ev) {
  const d = ev?.payload?.data ?? {};
  if (ev?.payload?.event === "action_started") {
    return titleFromAction(d.tool_id, d.args ?? {});
  }
  if (ev?.payload?.event === "action_completed") {
    return titleFromAction(d.tool_id, d.args ?? {}, {
      ok: Boolean(d.ok),
      ms: d.duration_ms,
    });
  }
  return `· 第 ${d.round} 步${d.failed ? "（失败）" : "完成"}`;
}

function findTask(state, taskId) {
  return (
    state.tasks.find((task) => task.taskId === taskId) ??
    (state.lastTask?.taskId === taskId ? state.lastTask : null)
  );
}

function replaceTask(state, taskId, fn) {
  const tasks = state.tasks.map((task) => (task.taskId === taskId ? fn(task) : task));
  const lastTask =
    state.lastTask?.taskId === taskId ? fn(state.lastTask) : state.lastTask;
  return { ...state, tasks, lastTask };
}

function upsertSubtask(task, payload) {
  const subtaskId = String(payload.subtask_id ?? "");
  const found = task.subtasks.some((st) => st.id === subtaskId);
  if (!found) {
    return {
      ...task,
      subtasks: [
        ...task.subtasks,
        {
          id: subtaskId,
          title: String(payload.goal ?? ""),
          acceptance: String(payload.acceptance ?? ""),
          status: "running",
          milestones: [],
          reason: "",
          reply: "",
          attempt: 1,
        },
      ],
    };
  }
  return {
    ...task,
    subtasks: task.subtasks.map((st) =>
      st.id === subtaskId
        ? {
            ...st,
            title: String(payload.goal ?? st.title ?? ""),
            acceptance: String(payload.acceptance ?? st.acceptance ?? ""),
            status: "running",
          }
        : st,
    ),
  };
}

function applyOutcome(subtask, outcome) {
  return {
    ...subtask,
    status: outcome.ok ? "done" : "failed",
    reason: String(outcome.reason ?? subtask.reason ?? ""),
    reply: replyExcerpt(outcome.reply ?? subtask.reply),
    attempt: Number(outcome.attempt ?? subtask.attempt ?? 1),
  };
}

/**
 * 单个 SSE 事件 → 新状态（不可变）。只处理 `task.*` 与 `error`；其余原样返回。
 */
export function reduceTaskEvent(state, ev) {
  const p = ev?.payload ?? {};
  switch (ev?.type) {
    case "task.task_started": {
      const task = {
        taskId: String(p.task_id ?? ""),
        goal: String(p.goal ?? ""),
        status: "running",
        subtasks: [],
      };
      return {
        ...state,
        tasks: [...state.tasks, task],
        lastTask: null,
        selected: null,
        notice: "",
        error: "",
      };
    }
    case "task.plan_ready":
      return replaceTask(state, String(p.task_id ?? ""), (task) => {
        const previous = new Map(task.subtasks.map((st) => [st.id, st]));
        return {
          ...task,
          subtasks: (p.subtasks ?? []).map((entry) => {
            const id = String(entry.id ?? "");
            const old = previous.get(id);
            return {
              id,
              title: String(entry.goal ?? old?.title ?? ""),
              acceptance: String(entry.acceptance ?? old?.acceptance ?? ""),
              status: old?.status ?? "pending",
              milestones: old?.milestones ?? [],
              reason: old?.reason ?? "",
              reply: old?.reply ?? "",
              attempt: old?.attempt ?? 1,
            };
          }),
        };
      });
    case "task.subtask_started":
      return replaceTask(state, String(p.task_id ?? ""), (task) =>
        upsertSubtask(task, p),
      );
    case "task.subtask_progress":
      return replaceTask(state, String(p.task_id ?? ""), (task) => {
        const subtaskId = String(p.subtask_id ?? "");
        return {
          ...task,
          subtasks: task.subtasks.map((st) =>
            st.id === subtaskId
              ? { ...st, milestones: [...st.milestones, milestoneLine(ev)] }
              : st,
          ),
        };
      });
    case "task.subtask_completed":
      return replaceTask(state, String(p.task_id ?? ""), (task) => {
        const subtaskId = String(p.subtask_id ?? "");
        return {
          ...task,
          subtasks: task.subtasks.map((st) =>
            st.id === subtaskId
              ? {
                  ...st,
                  status: p.ok ? "done" : "failed",
                  reason: String(p.reason ?? st.reason ?? ""),
                  reply: replyExcerpt(p.reply ?? st.reply),
                  attempt: Number(p.attempt ?? st.attempt ?? 1),
                }
              : st,
          ),
        };
      });
    case "task.task_finished":
      return finishTask(state, String(p.task_id ?? ""), "done", p, false);
    case "task.task_failed":
      return finishTask(state, String(p.task_id ?? ""), "failed", p, true);
    case "error":
      return { ...state, error: `${p.code}: ${p.message}` };
    default:
      return state;
  }
}

function finishTask(state, taskId, status, payload, failed) {
  const task = state.tasks.find((entry) => entry.taskId === taskId);
  if (!task) return state; // 晚到的旧任务事件：不复活快照、不污染新任务
  const outcomes = new Map(
    (payload.outcomes ?? []).map((item) => [String(item.subtask_id ?? ""), item]),
  );
  const failedIds = new Set((payload.failed ?? []).map(String));
  const snapshot = {
    ...task,
    status,
    subtasks: task.subtasks.map((st) => {
      if (outcomes.has(st.id)) return applyOutcome(st, outcomes.get(st.id));
      if (failed && failedIds.has(st.id)) {
        return { ...st, status: "failed", reason: String(payload.reason ?? st.reason ?? "") };
      }
      return st;
    }),
  };
  const n = (payload.outcomes ?? []).filter((item) => item.ok).length;
  const notice = failed
    ? `任务失败：${payload.code ?? ""} ${payload.reason ?? ""}`.trim()
    : `任务完成：${n}/${(payload.outcomes ?? []).length} 子任务通过（${task.goal}）`;
  return {
    ...state,
    tasks: state.tasks.filter((entry) => entry.taskId !== taskId),
    lastTask: snapshot,
    selected: state.selected,
    notice,
  };
}

function validateSelection(state, taskId, subtaskId) {
  if (!taskId || !subtaskId) return null;
  const task = findTask(state, taskId);
  if (!task || !task.subtasks.some((st) => st.id === subtaskId)) return null;
  return { taskId, subtaskId };
}

/** 选择视图：`("", "")` ⇒ 主视图；非法选择 fail-closed 回主视图。 */
export function selectTaskAgent(state, taskId, subtaskId) {
  return { ...state, selected: validateSelection(state, taskId, subtaskId) };
}

/** 当前/最近一次任务（在途优先，其次收尾快照）。 */
export function currentTask(state) {
  return state.tasks.length > 0 ? state.tasks[state.tasks.length - 1] : state.lastTask;
}

/** 标签模型：首位 `main`，其后当前/最近任务的子任务（主题缩写 + 状态徽标）。 */
export function taskTabModel(state) {
  const task = currentTask(state);
  if (!task) return [];
  const selected = state.selected;
  const tabs = [
    {
      key: "main",
      taskId: "",
      subtaskId: "",
      label: "main",
      status: "main",
      active: !selected,
    },
  ];
  for (const st of task.subtasks) {
    const mark =
      st.status === "done" ? "✓" : st.status === "failed" ? "✗" : st.status === "running" ? "⟳" : "·";
    const title = abbreviateGoal(st.title) || `子任务 ${st.id}`;
    tabs.push({
      key: `${task.taskId}:${st.id}`,
      taskId: task.taskId,
      subtaskId: st.id,
      label: `${mark} ${title}`,
      status: st.status,
      active: Boolean(
        selected && selected.taskId === task.taskId && selected.subtaskId === st.id,
      ),
    });
  }
  return tabs;
}

/** 当前选中视图（`{task, subtask}`）；主视图/非法选择 ⇒ null。 */
export function activeAgent(state) {
  const selected = state.selected;
  if (!selected) return null;
  const task = findTask(state, selected.taskId);
  const subtask = task?.subtasks.find((st) => st.id === selected.subtaskId);
  return task && subtask ? { task, subtask } : null;
}
