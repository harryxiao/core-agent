// 后端 REST/SSE 访问封装（唯一网络出口）。
// 同源：SPA 由 FastAPI 挂在 `/`，相对路径即后端；Tauri 壳下 sidecar 监听同端口。

async function toJson(resp) {
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    // 后端失败统一为结构化错误码（如 UI_LLM_CONFIG_INVALID）；不吞、不猜。
    throw new Error(`${body.error || "HTTP_" + resp.status}: ${body.message || "请求失败"}`);
  }
  return body;
}

/** 读有效 LLM 配置（含派生后的 token_budget 生效值）。 */
export async function getLLMConfig() {
  return toJson(await fetch("/llm-config"));
}

/** 保存 LLM 配置：后端校验 → 原子落盘 → 热生效；失败抛错且原值不被破坏。 */
export async function saveLLMConfig(payload) {
  return toJson(
    await fetch("/llm-config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

/** 新建会话（Web 模式）。 */
export async function createSession(mode = "web") {
  return toJson(
    await fetch("/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    }),
  );
}

/**
 * 跑一轮并逐帧产出 SSE 事件（`{type, payload}`）。
 * 用 fetch 读流而非 EventSource：`/run` 需要 POST body，EventSource 只支持 GET。
 */
export async function* runStream(sessionId, userInput) {
  const resp = await fetch("/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, user_input: userInput }),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`HTTP_${resp.status}: 会话流开启失败`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let cut = buf.indexOf("\n\n");
    while (cut >= 0) {
      const frame = buf.slice(0, cut);
      buf = buf.slice(cut + 2);
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (line) yield JSON.parse(line.slice(6));
      cut = buf.indexOf("\n\n");
    }
  }
}
