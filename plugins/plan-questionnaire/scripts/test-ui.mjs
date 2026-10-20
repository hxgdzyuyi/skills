import { chromium } from "playwright";
import { readFileSync, mkdtempSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";
import { QuestionnaireStore, publicRecord, answerSummary } from "../src/store.mjs";

const directory = mkdtempSync(join(tmpdir(), "questionnaire-ui-test-"));
const store = new QuestionnaireStore(directory);
const initial = store.create(JSON.parse(readFileSync("examples/current-question.json", "utf8")));
const html = readFileSync("dist/widget.html", "utf8");
const result = r => ({ content: [], structuredContent: {
  questionnaire: publicRecord(r), answer_summary: answerSummary(r),
}, _meta: { submission_token: r.submission_token } });
const browser = await chromium.launch({ channel: "chrome", headless: true });
let page;
try {
  page = await browser.newPage({ viewport: { width: 960, height: 1100 } });
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => { if (m.type() === "error") console.error("Browser:", m.text()); });
  const messages = [];
  let rejectMessages = true;
  await page.exposeFunction("hostCall", async ({ name, arguments: args }) => {
    try {
      if (name === "get_questionnaire") return result(store.get(args.questionnaire_id));
      if (name === "submit_questionnaire") return result(store.submit(args));
      throw new Error("unknown");
    } catch (e) { return { isError: true, content: [{ type: "text", text: e.message }] }; }
  });
  await page.exposeFunction("hostMessage", async params => {
    messages.push(params);
    return { isError: rejectMessages };
  });
  await page.setContent('<iframe title="问卷" style="border:0;width:800px;height:1050px"></iframe>');
  await page.evaluate(({ html, initialResult }) => {
    const frame = document.querySelector("iframe");
    window.initialQuestionnaireResult = initialResult;
    window.addEventListener("message", async e => {
      if (e.source !== frame.contentWindow) return;
      const m = e.data;
      (window.rpcMessages ??= []).push(m);
      if (m.jsonrpc !== "2.0") return;
      const reply = r => frame.contentWindow.postMessage({ jsonrpc: "2.0", id: m.id, result: r }, "*");
      if (m.method === "ui/initialize") return reply({
        protocolVersion: "2026-01-26", hostInfo: { name: "test-host", version: "1.0.0" },
        hostCapabilities: { serverTools: {}, message: { text: {} } },
        hostContext: { theme: "light", displayMode: "inline", availableDisplayModes: ["inline"], platform: "web" },
      });
      if (m.method === "ui/notifications/initialized") {
        frame.contentWindow.postMessage({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params: window.initialQuestionnaireResult }, "*");
      }
      if (m.method === "tools/call") return reply(await window.hostCall(m.params));
      if (m.method === "ui/message") return reply(await window.hostMessage(m.params));
      if (m.method === "ui/update-model-context") return reply({});
    });
    frame.srcdoc = html;
  }, { html, initialResult: result(initial) });
  const frame = page.frameLocator("iframe");
  await frame.getByRole("button", { name: "提交并继续讨论" }).waitFor();
  assert.equal(await frame.locator("input:checked").count(), 0, "no preselection");
  await frame.getByRole("button", { name: "提交并继续讨论" }).click();
  await frame.getByRole("status").filter({ hasText: "请完成" }).waitFor();
  assert.equal(store.get(initial.id).status, "pending");
  mkdirSync("test-results", { recursive: true });
  await frame.getByRole("radio", { name: /两者结合/ }).check();
  await frame.getByText("补充说明（可选）").click();
  await frame.getByRole("textbox", { name: /补充说明/ }).fill("测试：反击次数后续确定。");
  await page.screenshot({ path: "test-results/questionnaire-desktop.png", fullPage: true });
  await frame.getByRole("button", { name: "提交并继续讨论" }).click();
  await frame.getByRole("status").filter({ hasText: "答案已保存，但尚未发回对话" }).waitFor();
  const saved = store.get(initial.id);
  assert.equal(saved.status, "submitted");
  assert.deepEqual(saved.answers[0].selected_option_ids, ["C"]);
  assert.match(saved.answers[0].note, /反击次数/);
  rejectMessages = false;
  await frame.getByRole("button", { name: "继续讨论", exact: true }).click();
  await frame.getByRole("status").filter({ hasText: "答复已发送到当前对话" }).waitFor();
  assert.equal(messages.length, 2);
  assert.match(messages[1].content[0].text, /两者结合/);
  assert.equal(store.get(initial.id).submitted_at, saved.submitted_at, "retry only sends, does not resubmit");
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.evaluate(() => { document.querySelector("iframe").style.width = "100%"; document.body.style.margin = "0"; });
  await page.screenshot({ path: "test-results/questionnaire-mobile.png", fullPage: true });
  const widthOK = await frame.locator("body").evaluate(el => el.scrollWidth <= window.innerWidth);
  assert.ok(widthOK, "no horizontal overflow on mobile");
  // A complete long questionnaire travels in one message, including mixed answer types.
  const long = store.create({
    title: "12 题长问卷测试",
    questions: Array.from({ length: 12 }, (_, i) => ({
      id: `q${i}`, title: `测试问题 ${i + 1}`,
      type: ["single", "multiple", "text"][i % 3],
      options: i % 3 === 2 ? [] : [{ id: "A", label: "方案甲" }, { id: "B", label: "方案乙", recommended: true }],
    })),
  });
  const messagesBeforeLong = messages.length;
  await page.evaluate(({ html, initialResult }) => {
    window.initialQuestionnaireResult = initialResult;
    document.querySelector("iframe").srcdoc = html;
  }, { html, initialResult: result(long) });
  await frame.getByRole("heading", { name: "12 题长问卷测试" }).waitFor();
  assert.equal(await frame.locator("fieldset").count(), 12);
  assert.equal(await frame.locator("input:checked").count(), 0);
  for (let i = 0; i < 11; i++) {
    const field = frame.locator("fieldset").nth(i);
    if (i % 3 === 2) await field.getByRole("textbox", { name: `测试问题 ${i + 1}`, exact: true }).fill(`答复 ${i + 1}`);
    else if (i % 3 === 1) {
      await field.getByRole("checkbox", { name: /方案甲/ }).check();
      await field.getByRole("checkbox", { name: /方案乙/ }).check();
    } else await field.getByRole("radio", { name: /方案甲/ }).check();
  }
  await frame.getByRole("button", { name: "提交并继续讨论" }).click();
  await frame.getByRole("status").filter({ hasText: "请完成：测试问题 12" }).waitFor({ state: "attached" });
  assert.equal(store.get(long.id).status, "pending", "missing final answer prevents partial submission");
  assert.equal(messages.length, messagesBeforeLong);
  assert.equal(await frame.locator(":focus").getAttribute("aria-label"), "测试问题 12");
  await frame.getByRole("textbox", { name: "测试问题 12", exact: true }).fill("最后一题的答复");
  await frame.getByRole("button", { name: "提交并继续讨论" }).click();
  await frame.getByRole("status").filter({ hasText: "答复已发送到当前对话" }).waitFor();
  const longSaved = store.get(long.id);
  assert.equal(longSaved.answers.length, 12);
  assert.deepEqual(longSaved.answers[1].selected_option_ids, ["A", "B"]);
  assert.equal(longSaved.answers[11].text, "最后一题的答复");
  assert.equal(messages.length, messagesBeforeLong + 1, "all answers sent in one conversation message");
  for (let i = 0; i < 12; i++) assert.ok(messages.at(-1).content[0].text.includes(`测试问题 ${i + 1}\n`));
  assert.ok(await frame.locator("body").evaluate(el => el.scrollWidth <= window.innerWidth));
  assert.deepEqual(errors, []);
  console.log("PASS: single questionnaire retry; 12 mixed questions rendered, validated, saved and sent in one message; mobile layout.");
} catch (error) {
  mkdirSync("test-results", { recursive: true });
  await page?.screenshot({ path: "test-results/ui-failure.png", fullPage: true });
  console.error(await page?.evaluate(() => ({ messages: window.rpcMessages, body: document.querySelector("iframe")?.contentDocument?.body?.innerText })));
  throw error;
} finally {
  await browser.close();
  rmSync(directory, { recursive: true, force: true });
}
