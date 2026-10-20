import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { QuestionnaireStore, answerSummary } from "../src/store.mjs";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const fixture = {
  title: "测试问卷",
  questions: [{ id: "q", title: "选择方案", options: [
    { id: "A", label: "方案一" }, { id: "B", label: "方案二", recommended: true },
  ] }],
};
function setup(t) {
  const path = mkdtempSync(join(tmpdir(), "plan-questionnaire-test-"));
  t.after(() => rmSync(path, { recursive: true, force: true }));
  return new QuestionnaireStore(path);
}
function submit(record, ids = ["A"], text = "") {
  return { questionnaire_id: record.id, submission_token: record.submission_token,
    answers: [{ question_id: "q", selected_option_ids: ids, text }] };
}
test("recommended options stay unanswered; idempotent creation and persistence", t => {
  const store = setup(t);
  const first = store.create({ ...fixture, idempotency_key: "test-draft" });
  assert.equal(first.status, "pending");
  assert.deepEqual(first.answers, []);
  assert.equal(answerSummary(first), "");
  assert.equal(store.create({ ...fixture, idempotency_key: "test-draft" }).id, first.id);
  assert.throws(() => store.create({ ...fixture, title: "changed", idempotency_key: "test-draft" }), /幂等键/);
  assert.deepEqual(new QuestionnaireStore(store.directory).get(first.id), first);
});
test("validate required answers, option IDs, single choice, token and path", t => {
  const store = setup(t);
  const r = store.create(fixture);
  assert.throws(() => store.submit(submit(r, [])), /请回答/);
  assert.throws(() => store.submit(submit(r, ["unknown"])), /不存在/);
  assert.throws(() => store.submit(submit(r, ["A", "B"])), /单选/);
  assert.throws(() => store.submit(submit(r, ["A"], "other")), /单选/);
  assert.throws(() => store.submit({ ...submit(r), submission_token: "bad" }), /凭据/);
  assert.throws(() => store.get("../../config"));
  assert.equal(store.get(r.id).status, "pending");
});
test("submission is durable, replay-safe and cannot silently replace a choice", t => {
  const store = setup(t);
  const r = store.create(fixture);
  const saved = store.submit(submit(r, ["B"]));
  assert.equal(saved.status, "submitted");
  assert.match(answerSummary(saved), /方案二/);
  assert.deepEqual(store.submit(submit(r, ["B"])), saved);
  assert.throws(() => store.submit(submit(r, ["A"])), /已提交/);
  assert.deepEqual(new QuestionnaireStore(store.directory).get(r.id), saved);
});
test("multi-select and free text; duplicate and unknown questions rejected", t => {
  const store = setup(t);
  const r = store.create({ title: "组合", questions: [
    { ...fixture.questions[0], type: "multiple" },
    { id: "text", type: "text", title: "说明" },
  ] });
  const input = { questionnaire_id: r.id, submission_token: r.submission_token, answers: [
    { question_id: "q", selected_option_ids: ["B", "A"], text: "补充方案", note: "注意事项" },
    { question_id: "text", text: "文字回答" },
  ] };
  assert.throws(() => store.submit({ ...input, answers: [...input.answers, input.answers[0]] }), /重复/);
  assert.throws(() => store.submit({ ...input, answers: [...input.answers, { question_id: "unknown", text: "x" }] }), /不存在/);
  const saved = store.submit(input);
  assert.deepEqual(saved.answers[0].selected_option_ids, ["A", "B"]);
  assert.match(answerSummary(saved), /文字回答/);
  assert.match(answerSummary(saved), /注意事项/);
});
test("actual stdio MCP server exposes App resource and returns submitted answers", async t => {
  const store = setup(t);
  const transport = new StdioClientTransport({ command: process.execPath,
    args: [resolve("dist/server.mjs")], env: { PLAN_QUESTIONNAIRE_DATA_DIR: store.directory },
    stderr: "pipe" });
  let stderr = "";
  transport.stderr?.on("data", chunk => { stderr += chunk; });
  const client = new Client({ name: "questionnaire-test", version: "1.0.0" });
  t.after(async () => { await client.close(); });
  await client.connect(transport);
  const tools = (await client.listTools()).tools;
  assert.deepEqual(tools.find(t => t.name === "submit_questionnaire")._meta.ui.visibility, ["app"]);
  const shown = await client.callTool({ name: "show_questionnaire", arguments: fixture });
  assert.equal(shown.isError, undefined, stderr);
  assert.equal(shown.structuredContent.questionnaire.status, "pending");
  assert.equal(shown.structuredContent.questionnaire.submission_token, undefined);
  assert.ok(shown._meta.submission_token);
  const resources = await client.listResources();
  assert.equal(resources.resources.length, 1);
  const resource = await client.readResource({ uri: resources.resources[0].uri });
  assert.equal(resource.contents[0].mimeType, "text/html;profile=mcp-app");
  assert.match(resource.contents[0].text, /方案讨论问卷/);
  const record = shown.structuredContent.questionnaire;
  const saved = await client.callTool({ name: "submit_questionnaire", arguments: {
    questionnaire_id: record.id, submission_token: shown._meta.submission_token,
    answers: [{ question_id: "q", selected_option_ids: ["A"] }],
  } });
  assert.equal(saved.structuredContent.questionnaire.status, "submitted");
  const reread = await client.callTool({ name: "get_questionnaire", arguments: { questionnaire_id: record.id } });
  assert.match(reread.structuredContent.answer_summary, /方案一/);
  assert.equal(stderr, "");
});
