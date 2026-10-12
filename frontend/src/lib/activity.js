/**
 * TUI/Web 共享活动块标题语法（对齐 `src/core/ui/repl.py` + ui-scheme.md）。
 * 纯函数、零 DOM —— Web Chat / TaskPanel 与日后测试共用。
 */

export const TOOL_NAMES = {
  "tools.code_run": "Bash",
  "tools.file_read": "Read",
  "tools.file_write": "Write",
  "tools.file_patch": "Edit",
  "tools.file_delete": "Delete",
  "tools.delegate": "SubAgent",
  "tools.web_fetch": "WebFetch",
  "tools.gate_run": "Gate",
  "tools.context_read": "Context",
};

const TARGET_FIELDS = {
  "tools.file_read": "path",
  "tools.file_write": "path",
  "tools.file_patch": "path",
  "tools.file_delete": "path",
  "tools.web_fetch": "url",
  "tools.code_run": "script",
  "tools.delegate": "task",
  "tools.gate_run": "gate",
  "tools.context_read": "pointer",
};

const PAREN_TITLES = new Set([...Object.values(TOOL_NAMES), "Planner", "Thinking"]);
const MAX_TARGET_CHARS = 60;

export const THINKING_TITLE = "Thinking";
export const THINKING_TITLE_ACTIVE = "Thinking…";

/** 活动种类 → 前缀图标（与 TUI `_STEP_SYMBOLS` 对齐；Web 写进 summary）。 */
export const STEP_SYMBOLS = {
  Thinking: "✦",
  Bash: "$",
  Read: "◇",
  Write: "✎",
  Edit: "✏",
  Delete: "⌫",
  SubAgent: "⊕",
  Planner: "▤",
  WebFetch: "◎",
  Gate: "☑",
  Context: "⊞",
  raw: "⚠",
  subtask: "◈",
};

export function stepSymbol(kind) {
  return STEP_SYMBOLS[kind] || "·";
}

/** tool_id → 友好名；未映射则去掉 tools. 前缀。 */
export function toolName(toolId) {
  const name = String(toolId || "");
  if (TOOL_NAMES[name]) return TOOL_NAMES[name];
  const short = name.startsWith("tools.") ? name.slice("tools.".length) : name;
  return short || name;
}

/** 标题目标摘要（单行有界）；取不到 ⇒ ""。 */
export function toolTarget(toolId, args) {
  const field = TARGET_FIELDS[String(toolId || "")];
  if (!field || !args || typeof args !== "object" || Array.isArray(args)) return "";
  const value = args[field];
  if (typeof value !== "string") return "";
  const line = value.trim().split("\n", 1)[0].trim();
  if (!line) return "";
  return line.length > MAX_TARGET_CHARS ? `${line.slice(0, MAX_TARGET_CHARS)}…` : line;
}

/** 毫秒 → 人类可读；非法 ⇒ ""。 */
export function fmtMs(ms) {
  const value = Number(ms);
  if (!Number.isFinite(value) || value < 0) return "";
  const n = Math.trunc(value);
  if (n < 1000) return `${n}ms`;
  return `${(n / 1000).toFixed(1)}s`;
}

/**
 * 工具步骤块标题：`Name(摘要)`；完成落 ` · 1.2s` / ` · failed`（无 ⏺）。
 * @param {string} tool 友好名
 * @param {string} target 摘要
 * @param {{ ok?: boolean|null, ms?: unknown }} [opts]
 */
export function actionTitle(tool, target, opts = {}) {
  const { ok = null, ms } = opts;
  const base =
    PAREN_TITLES.has(tool) ? `${tool}(${target || ""})` : tool + (target ? `  ${target}` : "");
  if (ok === null || ok === undefined) return base;
  if (ok) {
    const elapsed = fmtMs(ms);
    return elapsed ? `${base} · ${elapsed}` : `${base} · ok`;
  }
  return `${base} · failed`;
}

/** 由 tool_id + args 直接生成标题（Chat / TaskPanel 入口）。 */
export function titleFromAction(toolId, args, opts = {}) {
  return actionTitle(toolName(toolId), toolTarget(toolId, args), opts);
}

/** Thinking 块标题：进行中带省略号；落静可附 ` · 1.2s`；禁止附原文。 */
export function thinkingTitle(active, ms) {
  if (active) return THINKING_TITLE_ACTIVE;
  const elapsed = fmtMs(ms);
  return elapsed ? `${THINKING_TITLE} · ${elapsed}` : THINKING_TITLE;
}

/** Web summary 行：图标 + 标题（图标与 TUI 折叠符同源）。 */
export function labeledTitle(kind, title) {
  return `${stepSymbol(kind)} ${title}`;
}
