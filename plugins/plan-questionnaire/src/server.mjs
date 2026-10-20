import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { registerAppResource, registerAppTool, RESOURCE_MIME_TYPE } from "@modelcontextprotocol/ext-apps/server";
import { QuestionnaireStore, showSchema, getSchema, submitSchema, publicRecord, answerSummary } from "./store.mjs";
import { startPreview } from "./preview.mjs";

export const RESOURCE_URI = "ui://plan-questionnaire/v1.html";
const root = dirname(fileURLToPath(import.meta.url));
export function toolResult(record) {
  return {
    content: [{ type: "text", text: record.status === "submitted"
      ? answerSummary(record)
      : `问卷「${record.questionnaire.title}」已打开，等待用户在问卷中作答。问卷 ID：${record.id}。未提交前不要推测答案。` }],
    structuredContent: { questionnaire: publicRecord(record), answer_summary: answerSummary(record) },
    _meta: { submission_token: record.submission_token },
  };
}
export function createServer(store = new QuestionnaireStore(), html = readFileSync(join(root, "widget.html"), "utf8")) {
  const server = new McpServer({ name: "plan-questionnaire", version: "0.1.1" }, {
    instructions: "方案讨论有超过三项可独立回答的待确认事项，或用户要求长问卷、集中选择时，使用 show_questionnaire 一次显示多题（最多12题），整份提交回当前对话。只有用户明确要求逐题讨论或问题存在前后依赖时才逐题问。用户提交后调用 get_questionnaire 核对答案再继续讨论。submit_questionnaire 仅供用户界面调用，不替用户选择。不要把推荐项当作用户的决定。",
  });
  registerAppResource(server, "discussion-questionnaire", RESOURCE_URI, {}, async () => ({
    contents: [{ uri: RESOURCE_URI, mimeType: RESOURCE_MIME_TYPE, text: html,
      _meta: { ui: { prefersBorder: true, csp: { connectDomains: [], resourceDomains: [] } },
        "openai/widgetDescription": "方案讨论问卷，用户可选择答案并提交回当前对话。" } }],
  }));
  const invoke = (fn) => async (args) => {
    try { return toolResult(fn(args)); }
    catch (e) { return { isError: true, content: [{ type: "text", text: e.message }] }; }
  };
  registerAppTool(server, "show_questionnaire", {
    title: "打开讨论问卷",
    description: "在当前对话显示包含1–12题的 MCP Apps 问卷，集中处理超过原生输入三题上限的方案讨论。支持混合单选、多选、文本及补充说明，整份一次提交。仅在用户明确要求或题目有前后依赖时逐题提问。不会自动选择推荐项或提交。",
    inputSchema: showSchema,
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
    _meta: { ui: { resourceUri: RESOURCE_URI }, "openai/outputTemplate": RESOURCE_URI,
      "openai/widgetAccessible": true },
  }, invoke(args => store.create(args)));
  registerAppTool(server, "get_questionnaire", {
    title: "读取问卷与答案",
    description: "按问卷 ID 读取提交状态和用户的实际答案。pending 表示尚未作答，不代表同意推荐项。",
    inputSchema: getSchema,
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
    _meta: { ui: { visibility: ["model", "app"] }, "openai/widgetAccessible": true },
  }, invoke(args => store.get(args.questionnaire_id)));
  registerAppTool(server, "submit_questionnaire", {
    title: "提交我的答案",
    description: "仅由问卷界面在用户点击提交后调用；保存真实回答，重复提交相同答案不重复写入。",
    inputSchema: submitSchema,
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
    _meta: { ui: { visibility: ["app"] }, "openai/widgetAccessible": true, "openai/visibility": "private" },
  }, invoke(args => store.submit(args)));
  return server;
}

if (process.argv.includes("--preview")) {
  const store = new QuestionnaireStore();
  const example = JSON.parse(readFileSync(join(root, "example.json"), "utf8"));
  await startPreview(store, store.create(example), readFileSync(join(root, "widget.html"), "utf8"));
} else if (!process.env.PLAN_QUESTIONNAIRE_IMPORT_ONLY) {
  const server = createServer();
  await server.connect(new StdioServerTransport());
}
