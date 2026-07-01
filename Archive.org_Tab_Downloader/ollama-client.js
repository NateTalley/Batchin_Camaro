/** Ollama chat client with tool-calling loop. */

async function ollamaChat(baseUrl, model, messages) {
  const resp = await fetch(`${baseUrl.replace(/\/$/, "")}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      messages,
      tools: TOOL_DEFINITIONS,
      stream: false
    })
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Ollama HTTP ${resp.status}: ${text}`);
  }
  return resp.json();
}

async function listOllamaModels(baseUrl) {
  const resp = await fetch(`${baseUrl.replace(/\/$/, "")}/api/tags`);
  if (!resp.ok) throw new Error(`Ollama HTTP ${resp.status}`);
  const data = await resp.json();
  return (data.models || []).map(m => m.name).filter(Boolean);
}

async function runAgentTurn({ baseUrl, model, messages, downloadHandler, maxRounds = 8 }) {
  const toolLog = [];
  const working = [...messages];

  for (let round = 0; round < maxRounds; round++) {
    const data = await ollamaChat(baseUrl, model, working);
    const msg = data.message || {};
    working.push(msg);

    const toolCalls = msg.tool_calls || [];
    if (!toolCalls.length) {
      return { content: msg.content || "", messages: working, toolLog };
    }

    for (const tc of toolCalls) {
      const fn = tc.function || {};
      const name = fn.name || "";
      let args = {};
      try {
        args = typeof fn.arguments === "string" ? JSON.parse(fn.arguments) : (fn.arguments || {});
      } catch (_) { /* keep empty args */ }
      toolLog.push(`${name}(${JSON.stringify(args)})`);
      const result = await executeAgentTool(name, args, downloadHandler);
      working.push({
        role: "tool",
        content: JSON.stringify(result),
        tool_name: name
      });
    }
  }

  return {
    content: "Reached maximum tool rounds. Try a simpler request.",
    messages: working,
    toolLog
  };
}
