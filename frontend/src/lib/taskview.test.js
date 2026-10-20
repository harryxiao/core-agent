/**
 * 主/子 Agent 视图模型纯函数测试（change 0294 / ADR-0284）。
 * 覆盖：主题缩写/结果节选、reducer 全事件序列、收尾快照、选择校验、旧任务隔离、里程碑行。
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  AGENT_SCOPE,
  abbreviateGoal,
  activeAgent,
  initialTaskState,
  milestoneLine,
  reduceTaskEvent,
  replyExcerpt,
  selectTaskAgent,
  taskTabModel,
} from "./taskview.js";

const ev = (type, payload) => ({ type, payload });

function applyAll(events) {
  return events.reduce(reduceTaskEvent, initialTaskState());
}

const START = ev("task.task_started", { task_id: "t1", goal: "复合目标" });
const PLAN = ev("task.plan_ready", {
  task_id: "t1",
  subtasks: [
    { id: "1", goal: "查资料", acceptance: "给出来源" },
    { id: "2", goal: "汇总" },
  ],
});
const RUN1 = ev("task.subtask_started", {
  task_id: "t1",
  subtask_id: "1",
  goal: "查资料",
  acceptance: "给出来源",
});
const PROGRESS = ev("task.subtask_progress", {
  task_id: "t1",
  subtask_id: "1",
  event: "action_completed",
  data: {
    tool_id: "tools.code_run",
    args: { script: "echo hi" },
    ok: true,
    duration_ms: 1500,
  },
});
const DONE1 = ev("task.subtask_completed", {
  task_id: "t1",
  subtask_id: "1",
  ok: true,
  reason: "验收通过",
  reply: "答案 42",
  attempt: 1,
});

test("abbreviateGoal：单行、去空白、有界、空值回退", () => {
  assert.equal(abbreviateGoal("  调研\n并  汇总  "), "调研 并 汇总");
  assert.equal(abbreviateGoal(""), "");
  assert.equal(abbreviateGoal(null), "");
  const long = abbreviateGoal("查".repeat(50));
  assert.ok(long.length <= 14);
  assert.ok(long.endsWith("…"));
});

test("replyExcerpt：去空白并有界", () => {
  assert.equal(replyExcerpt(" 答案 42 "), "答案 42");
  assert.equal(replyExcerpt(""), "");
  const long = replyExcerpt("x".repeat(300));
  assert.equal(long.length, 240);
  assert.ok(long.endsWith("…"));
});

test("reducer 全事件序列：在途任务、子任务状态、里程碑与结果节选", () => {
  const state = applyAll([START, PLAN, RUN1, PROGRESS, DONE1]);
  assert.equal(state.tasks.length, 1);
  const task = state.tasks[0];
  assert.equal(task.taskId, "t1");
  assert.equal(task.goal, "复合目标");
  assert.equal(task.status, "running");
  assert.equal(task.subtasks.length, 2);

  const [first, second] = task.subtasks;
  assert.equal(first.status, "done");
  assert.equal(first.acceptance, "给出来源");
  assert.equal(first.milestones.length, 1);
  assert.match(first.milestones[0], /Shell\(echo hi\).*1\.5s/);
  assert.equal(first.reason, "验收通过");
  assert.equal(first.reply, "答案 42");
  assert.equal(second.status, "pending");
  assert.equal(second.title, "汇总");
});

test("选择校验：非法/跨任务同名 sid fail-closed", () => {
  let state = applyAll([START, PLAN, RUN1]);
  assert.equal(selectTaskAgent(state, "t1", "nope").selected, null);
  assert.equal(selectTaskAgent(state, "", "").selected, null);
  assert.deepEqual(selectTaskAgent(state, "t1", "1").selected, {
    taskId: "t1",
    subtaskId: "1",
  });

  state = reduceTaskEvent(state, ev("task.task_started", { task_id: "t2", goal: "第二个" }));
  state = selectTaskAgent(state, "t2", "1"); // t2 尚无子任务 ⇒ 不选中
  assert.equal(state.selected, null);
  assert.equal(activeAgent(state), null);
});

test("收尾快照：task_finished 保留 lastTask/选择/终态标签", () => {
  let state = applyAll([START, PLAN, RUN1, PROGRESS, DONE1]);
  state = selectTaskAgent(state, "t1", "1");
  state = reduceTaskEvent(
    state,
    ev("task.task_finished", {
      task_id: "t1",
      outcomes: [
        { subtask_id: "1", ok: true, reason: "验收通过", reply: "答案 42", attempt: 1 },
        { subtask_id: "2", ok: false, reason: "未达标", attempt: 2 },
      ],
    }),
  );

  assert.equal(state.tasks.length, 0);
  assert.equal(state.lastTask.taskId, "t1");
  assert.equal(state.lastTask.status, "done");
  assert.match(state.notice, /任务完成：1\/2/);
  assert.deepEqual(state.selected, { taskId: "t1", subtaskId: "1" });

  const view = activeAgent(state);
  assert.equal(view.task.taskId, "t1");
  assert.equal(view.subtask.id, "1");
  assert.equal(view.subtask.status, "done");

  const tabs = taskTabModel(state);
  assert.equal(tabs[0].label, "main");
  assert.equal(tabs[0].active, false);
  assert.equal(tabs.length, 3);
  assert.ok(tabs[1].label.includes("✓"));
  assert.ok(tabs[1].label.includes("查资料"));
  assert.equal(tabs[1].active, true);
  assert.ok(tabs[2].label.includes("✗"));
});

test("task_failed：失败快照保留，failed 列出的子任务落 ✗", () => {
  let state = applyAll([START, PLAN, RUN1]);
  state = selectTaskAgent(state, "t1", "1");
  state = reduceTaskEvent(
    state,
    ev("task.task_failed", {
      task_id: "t1",
      code: "ORCHESTRATION_FAILED",
      reason: "boom",
      failed: ["1"],
    }),
  );

  assert.equal(state.tasks.length, 0);
  assert.equal(state.lastTask.status, "failed");
  assert.equal(state.lastTask.subtasks[0].status, "failed");
  assert.match(state.notice, /任务失败/);
  assert.equal(activeAgent(state).subtask.id, "1");
  assert.ok(taskTabModel(state)[1].label.includes("✗"));
});

test("下一次 task_started 重置 lastTask、选择与标签", () => {
  let state = applyAll([START, PLAN, RUN1, DONE1]);
  state = reduceTaskEvent(state, ev("task.task_finished", { task_id: "t1", outcomes: [] }));
  state = selectTaskAgent(state, "t1", "1");
  state = reduceTaskEvent(state, ev("task.task_started", { task_id: "t2", goal: "新目标" }));

  assert.equal(state.lastTask, null);
  assert.equal(state.selected, null);
  assert.equal(state.tasks.length, 1);
  assert.equal(state.tasks[0].taskId, "t2");
  assert.deepEqual(
    taskTabModel(state).map((tab) => tab.label),
    ["main"],
  );
  assert.equal(activeAgent(state), null);
});

test("晚到的旧任务事件不复活 lastTask、不污染新任务", () => {
  let state = applyAll([START, PLAN, RUN1, DONE1]);
  state = reduceTaskEvent(state, ev("task.task_finished", { task_id: "t1", outcomes: [] }));
  state = reduceTaskEvent(state, ev("task.task_started", { task_id: "t2", goal: "新目标" }));
  const before = state;

  state = reduceTaskEvent(
    state,
    ev("task.subtask_started", { task_id: "t1", subtask_id: "1", goal: "旧任务" }),
  );
  state = reduceTaskEvent(
    state,
    ev("task.subtask_completed", { task_id: "t1", subtask_id: "1", ok: true }),
  );

  assert.equal(state.lastTask, null);
  assert.equal(state.tasks.length, 1);
  assert.equal(state.tasks[0].taskId, "t2");
  assert.equal(state.tasks[0].subtasks.length, 0);
  assert.equal(before.tasks[0].subtasks.length, 0);
});

test("无任务时标签为空；选中 main 时 main 激活", () => {
  let state = initialTaskState();
  assert.deepEqual(taskTabModel(state), []);

  state = applyAll([START, PLAN, RUN1]);
  const tabs = taskTabModel(state);
  assert.equal(tabs[0].label, "main");
  assert.equal(tabs[0].active, true); // 缺省主视图
  assert.equal(taskTabModel(selectTaskAgent(state, "t1", "1"))[0].active, false);
});

const AGENT_START = ev("agent.started", {
  agent_id: "coding:abcd",
  agent: "coding",
  title: "写代码",
});
const AGENT_PROGRESS = ev("agent.progress", {
  agent_id: "coding:abcd",
  event: "action_started",
  data: { round: 0, tool_id: "tools.file_write", args: { path: "a.py" } },
});
const AGENT_DONE = ev("agent.completed", {
  agent_id: "coding:abcd",
  ok: true,
  reply: "子结果",
});

test("委托子 Agent：无任务也出现 main + Agent 标签，可选中查看详情", () => {
  let state = applyAll([AGENT_START, AGENT_PROGRESS]);
  const tabs = taskTabModel(state);
  assert.deepEqual(
    tabs.map((tab) => tab.label),
    ["main", "⟳ Agent · 写代码"],
  );
  assert.equal(tabs[0].active, true);

  state = selectTaskAgent(state, AGENT_SCOPE, "coding:abcd");
  assert.deepEqual(state.selected, { taskId: AGENT_SCOPE, subtaskId: "coding:abcd" });
  const view = activeAgent(state);
  assert.equal(view.task.goal, "前台委托子 Agent");
  assert.equal(view.subtask.status, "running");
  assert.deepEqual(view.subtask.milestones, ["Write(a.py)"]);
  assert.equal(taskTabModel(state)[1].active, true);

  state = reduceTaskEvent(state, AGENT_DONE);
  assert.equal(state.delegates[0].status, "done");
  assert.equal(state.delegates[0].reply, "子结果");
  assert.ok(taskTabModel(state)[1].label.startsWith("✓"));
  assert.equal(activeAgent(state).subtask.reply, "子结果");

  state = selectTaskAgent(state, AGENT_SCOPE, "nope");
  assert.equal(state.selected, null);
});

test("agent.reset 清空委托与委托选择，不触碰任务选择", () => {
  let state = applyAll([AGENT_START]);
  state = selectTaskAgent(state, AGENT_SCOPE, "coding:abcd");
  state = reduceTaskEvent(state, ev("agent.reset", {}));
  assert.deepEqual(state.delegates, []);
  assert.equal(state.selected, null);
  assert.deepEqual(taskTabModel(state), []);

  let withTask = applyAll([START, PLAN, RUN1]);
  withTask = selectTaskAgent(withTask, "t1", "1");
  withTask = reduceTaskEvent(withTask, ev("agent.reset", {}));
  assert.deepEqual(withTask.selected, { taskId: "t1", subtaskId: "1" });
});

test("milestoneLine：动作行复用友好名 + 耗时；轮次级落步数", () => {
  assert.equal(
    milestoneLine(
      ev("task.subtask_progress", {
        event: "action_started",
        data: { tool_id: "tools.code_run", args: { script: "echo hi" } },
      }),
    ),
    "Shell(echo hi)",
  );
  assert.equal(milestoneLine(PROGRESS), "Shell(echo hi) · 1.5s");
  assert.equal(
    milestoneLine(
      ev("task.subtask_progress", {
        event: "step_completed",
        data: { round: 2, failed: true },
      }),
    ),
    "· 第 2 步（失败）",
  );
});
