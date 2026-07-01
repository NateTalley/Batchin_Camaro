/** Tool schemas and execution for the Ollama IA agent. */

const SYSTEM_PROMPT = `You are an Internet Archive assistant for Batchin' Camaro.
Use the provided tools to search archive.org, inspect item metadata, and start downloads.
Always use tools instead of guessing item IDs or file names.
For large batch downloads (more than 5 items), ask the user to confirm first.
Be concise and helpful.`;

const TOOL_DEFINITIONS = [
  {
    type: "function",
    function: {
      name: "search_archive",
      description: "Search Internet Archive items by keyword query.",
      parameters: {
        type: "object",
        properties: {
          query: { type: "string", description: "Search terms" },
          mediatype: {
            type: "string",
            enum: ["texts", "audio", "movies", "image", "software", "data"],
            description: "Optional mediatype filter"
          },
          rows: { type: "integer", description: "Max results (1-100)", default: 10 }
        },
        required: ["query"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "get_item_metadata",
      description: "Get metadata and downloadable file list for an archive.org item.",
      parameters: {
        type: "object",
        properties: {
          item_id: { type: "string", description: "Archive.org identifier" }
        },
        required: ["item_id"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "start_download",
      description: "Queue Internet Archive items for download using extension download settings.",
      parameters: {
        type: "object",
        properties: {
          item_ids: {
            type: "array",
            items: { type: "string" },
            description: "List of item identifiers"
          },
          want_text: { type: "boolean", default: true },
          want_pdf: { type: "boolean", default: true }
        },
        required: ["item_ids"]
      }
    }
  }
];

async function executeAgentTool(name, args, downloadHandler) {
  if (name === "search_archive") {
    const results = await searchItems(args.query || "", {
      mediatype: args.mediatype || null,
      rows: args.rows || 10
    });
    return { count: results.length, results };
  }
  if (name === "get_item_metadata") {
    const meta = await getMetadata((args.item_id || "").trim());
    return summarizeMetadata(meta, {
      wantText: args.want_text !== false,
      wantPdf: args.want_pdf !== false
    });
  }
  if (name === "start_download") {
    const itemIds = args.item_ids || [];
    if (downloadHandler) {
      await downloadHandler(itemIds, {
        wantText: args.want_text !== false,
        wantPdf: args.want_pdf !== false
      });
    }
    return { status: "queued", item_ids: itemIds };
  }
  return { error: `Unknown tool: ${name}` };
}
