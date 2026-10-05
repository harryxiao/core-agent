<script>
  import { getLLMConfig, saveLLMConfig } from "../lib/api.js";

  const REF_PATTERN = /^\$\{.+\}$/;

  let form = $state({
    provider: "",
    model: "",
    endpoint: "",
    api_key_ref: "",
    reasoning_effort: "",
    embedding_model: "",
    context_window: 0,
    output_reserve: "",
    max_rounds: "",
  });
  let effective = $state({ token_budget: null, max_rounds: null });
  let status = $state("");
  let error = $state("");
  let loaded = $state(false);

  async function load() {
    try {
      const body = await getLLMConfig();
      form = {
        provider: body.provider,
        model: body.model,
        endpoint: body.endpoint,
        api_key_ref: body.api_key_ref,
        reasoning_effort: body.reasoning_effort || "",
        embedding_model: body.embedding_model,
        context_window: body.context_window,
        output_reserve: "",
        max_rounds: "",
      };
      // 回显**生效值**：token_budget 是后端派生结果（窗口 − 输出预留），前端不自行推算（ADR-0092）。
      effective = { token_budget: body.token_budget, max_rounds: body.max_rounds };
      loaded = true;
    } catch (exc) {
      error = String(exc.message || exc);
    }
  }

  async function save() {
    error = "";
    status = "";
    if (!REF_PATTERN.test(form.api_key_ref)) {
      // 前端这层只是少一次无谓往返，不是安全边界（后端照样拒明文）。
      error = "API Key 必须为 ${VAR} 引用，禁止明文";
      return;
    }
    try {
      await saveLLMConfig({
        provider: form.provider,
        model: form.model,
        endpoint: form.endpoint,
        api_key_ref: form.api_key_ref,
        reasoning_effort: form.reasoning_effort,
        embedding_model: form.embedding_model,
        context_window: form.context_window,
        output_reserve: form.output_reserve,
        max_rounds: form.max_rounds,
      });
      status = "已保存并生效";
      await load();
    } catch (exc) {
      error = String(exc.message || exc);
    }
  }

  load();
</script>

<section>
  {#if error}<p class="error">{error}</p>{/if}
  {#if status}<p class="ok">{status}</p>{/if}

  <form
    onsubmit={(e) => {
      e.preventDefault();
      save();
    }}
  >
    <label>提供商 <input bind:value={form.provider} disabled={!loaded} /></label>
    <label>模型 <input bind:value={form.model} disabled={!loaded} /></label>
    <label>端点 <input bind:value={form.endpoint} disabled={!loaded} /></label>
    <label>
      API Key 引用（${"{VAR}"}，只引用不落明文）
      <input bind:value={form.api_key_ref} disabled={!loaded} />
    </label>
    <label>推理强度 <input bind:value={form.reasoning_effort} disabled={!loaded} /></label>
    <label>嵌入模型 <input bind:value={form.embedding_model} disabled={!loaded} /></label>
    <label>
      上下文窗口（tokens，0 = 未配置）
      <input type="number" bind:value={form.context_window} disabled={!loaded} />
    </label>
    <label>
      输出预留（留空 = 不改动，缺省 8192）
      <input type="number" bind:value={form.output_reserve} disabled={!loaded} />
    </label>
    <label>
      最大轮数（留空 = 不改动）
      <input type="number" bind:value={form.max_rounds} disabled={!loaded} />
    </label>
    <button type="submit" disabled={!loaded}>保存</button>
  </form>

  <p class="meta">
    生效预算 token_budget：{effective.token_budget ?? "（未配置窗口）"} ／ 最大轮数：
    {effective.max_rounds ?? "（未知）"}
  </p>
</section>

<style>
  form {
    display: grid;
    gap: 0.6rem;
    max-width: 480px;
  }
  label {
    display: grid;
    gap: 0.2rem;
    font-size: 0.85rem;
    color: #59636e;
  }
  input {
    padding: 0.45rem;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    font-size: 0.95rem;
  }
  button {
    justify-self: start;
    padding: 0.5rem 1.2rem;
    border-radius: 6px;
    border: 1px solid #1f6feb;
    background: #1f6feb;
    color: #fff;
    cursor: pointer;
  }
  .meta {
    color: #59636e;
    font-size: 0.85rem;
  }
  .error {
    color: #cf222e;
  }
  .ok {
    color: #1a7f37;
  }
</style>
