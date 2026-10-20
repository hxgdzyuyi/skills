import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const servers = JSON.parse(execFileSync("codex", ["mcp", "list", "--json"], { encoding: "utf8" }));
const server = servers.find(s => s.name === "plan-questionnaire");
assert.ok(server?.enabled, "问卷 MCP 尚未安装或启用");
const directory = mkdtempSync(join(tmpdir(), "questionnaire-installed-test-"));
const client = new Client({ name: "installed-questionnaire-check", version: "1.0.0" });
try {
  const transport = new StdioClientTransport({
    ...server.transport,
    env: { ...process.env, ...(server.transport.env ?? {}), PLAN_QUESTIONNAIRE_DATA_DIR: directory },
    stderr: "pipe",
  });
  await client.connect(transport);
  const tools = (await client.listTools()).tools;
  assert.ok(tools.find(t => t.name === "show_questionnaire"));
  const resources = await client.listResources();
  const result = await client.readResource({ uri: resources.resources[0].uri });
  assert.equal(result.contents[0].mimeType, "text/html;profile=mcp-app");
  console.log("PASS: installed Codex MCP configuration starts successfully and exposes the questionnaire App.");
} finally {
  await client.close();
  rmSync(directory, { recursive: true, force: true });
}
