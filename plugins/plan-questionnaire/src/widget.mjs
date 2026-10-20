import { App } from "@modelcontextprotocol/ext-apps";

const app = new App({ name: "plan-questionnaire-ui", version: "0.1.1" }, {});
const root = document.querySelector("#app");
let record, token, summary = "", busy = false, sent = false, ready = false;
let message = "";
let refreshedId;
const drafts = new Map();

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function draft(q) {
  if (!drafts.has(q.id)) {
    const a = record.answers.find(a => a.question_id === q.id);
    drafts.set(q.id, { question_id: q.id, selected_option_ids: a?.selected_option_ids ?? [],
      text: a?.text ?? "", note: a?.note ?? "", other: Boolean(a?.text) });
  }
  return drafts.get(q.id);
}
function isAnswered(q) {
  const a = draft(q);
  return q.type === "text" ? Boolean(a.text.trim())
    : Boolean(a.selected_option_ids.length || (a.other && a.text.trim()));
}
function progress() {
  const node = root.querySelector("#progress");
  if (node) node.textContent = `${record.questionnaire.questions.filter(isAnswered).length} / ${record.questionnaire.questions.length} 题已回答`;
  if (message.startsWith("请完成：") && record.questionnaire.questions.every(q =>
    (!q.required || isAnswered(q)) && (!draft(q).other || draft(q).text.trim()))) setMessage("");
}
function receive(result) {
  if (result.isError) throw new Error(result.content?.find(c => c.type === "text")?.text || "操作未完成");
  const next = result.structuredContent?.questionnaire;
  if (!next) return;
  const shouldRender = !record || next.id !== record.id || next.status !== record.status;
  if (!record || next.id !== record.id) { drafts.clear(); sent = false; message = ""; }
  if (next.status === "submitted") drafts.clear();
  record = next;
  token = result._meta?.submission_token ?? token;
  summary = result.structuredContent.answer_summary ?? "";
  if (shouldRender) render();
}
function renderQuestion(q, index, locked) {
  const field = el("fieldset", "question");
  field.id = `question-${q.id}`;
  field.disabled = locked;
  const legend = el("legend");
  legend.append(el("span", "number", String(index + 1)), el("span", "", q.title));
  field.append(legend);
  if (q.description) field.append(el("p", "description", q.description));
  const kind = q.type === "multiple" ? "可多选" : q.type === "text" ? "文字回答" : "单选";
  field.append(el("p", "hint", `${kind} · ${q.required ? "必答" : "选答"}`));
  const a = draft(q);
  if (q.type === "text") {
    const input = el("textarea", "text-answer");
    input.rows = 3; input.maxLength = 5000; input.value = a.text;
    input.setAttribute("aria-label", q.title);
    input.placeholder = "写下你的想法…";
    input.addEventListener("input", () => { a.text = input.value; progress(); });
    field.append(input);
  } else {
    const choices = el("div", "choices");
    q.options.forEach(option => {
      const label = el("label", "choice");
      const input = el("input");
      input.type = q.type === "multiple" ? "checkbox" : "radio";
      input.name = q.id; input.value = option.id; input.checked = a.selected_option_ids.includes(option.id);
      const body = el("span", "choice-body");
      const heading = el("span", "choice-title");
      heading.append(el("span", "option-key", option.id), el("span", "", option.label));
      if (option.recommended) heading.append(el("span", "badge", "建议"));
      body.append(heading);
      if (option.description) body.append(el("span", "choice-description", option.description));
      input.addEventListener("change", () => {
        if (q.type === "single") {
          a.selected_option_ids = [option.id]; a.other = false; a.text = "";
          const otherArea = field.querySelector(".other-text");
          if (otherArea) { otherArea.hidden = true; otherArea.value = ""; }
        } else {
          a.selected_option_ids = [...choices.querySelectorAll('input[type="checkbox"]:checked')].map(i => i.value);
        }
        progress();
      });
      label.append(input, body); choices.append(label);
    });
    field.append(choices);
    if (q.allow_other) {
      const label = el("label", "choice other-choice");
      const check = el("input");
      check.type = q.type === "single" ? "radio" : "checkbox";
      check.name = q.id; check.value = "__other"; check.checked = a.other;
      label.append(check, el("span", "choice-title", "我有其他想法"));
      const input = el("textarea", "other-text");
      input.rows = 3; input.maxLength = 5000; input.value = a.text;
      input.placeholder = "描述你倾向的方案…";
      input.setAttribute("aria-label", `${q.title}：其他想法`);
      input.hidden = !a.other;
      check.addEventListener("change", () => {
        a.other = check.checked; input.hidden = !a.other;
        if (q.type === "single" && a.other) a.selected_option_ids = [];
        if (!a.other) { a.text = ""; input.value = ""; }
        else input.focus();
        progress();
      });
      input.addEventListener("input", () => { a.text = input.value; progress(); });
      field.append(label, input);
    }
  }
  const details = el("details", "notes");
  details.open = Boolean(a.note);
  details.append(el("summary", "", "补充说明（可选）"));
  const note = el("textarea");
  note.rows = 2; note.maxLength = 3000; note.value = a.note;
  note.placeholder = "限制、顾虑，或想一起调整的细节…";
  note.setAttribute("aria-label", `${q.title}：补充说明`);
  note.addEventListener("input", () => { a.note = note.value; });
  details.append(note); field.append(details);
  return field;
}
function setMessage(text) {
  message = text;
  const node = root.querySelector("#status");
  if (node) { node.textContent = text; node.hidden = !text; }
}
function render() {
  root.replaceChildren();
  const locked = record.status === "submitted";
  const header = el("header");
  header.append(el("div", "eyebrow", locked ? "答案已保存" : "方案讨论"));
  header.append(el("h1", "", record.questionnaire.title));
  if (record.questionnaire.description) header.append(el("p", "intro", record.questionnaire.description));
  const form = el("form");
  form.noValidate = true;
  record.questionnaire.questions.forEach((q, i) => form.append(renderQuestion(q, i, locked)));
  const footer = el("footer");
  const count = el("span", "progress"); count.id = "progress";
  const button = el("button", "primary", sent ? "已发送到对话" : locked ? "继续讨论" : "提交并继续讨论");
  button.type = "submit"; button.disabled = busy || sent || !ready;
  footer.append(count, button);
  const status = el("p", "status", message); status.id = "status"; status.role = "status"; status.hidden = !message;
  form.append(footer, status);
  if (locked) {
    const details = el("details", "answer-copy");
    details.open = Boolean(message && !sent);
    details.append(el("summary", "", "查看 / 复制我的答复"));
    const area = el("textarea");
    area.readOnly = true; area.value = summary; area.rows = 6;
    area.setAttribute("aria-label", "已提交答复");
    area.addEventListener("focus", () => area.select());
    details.append(area); form.append(details);
  }
  form.addEventListener("submit", submit);
  root.append(header, form); progress();
}
async function sendToConversation() {
  const result = await app.sendMessage({
    role: "user", content: [{ type: "text", text: `${summary}\n\n请根据我的回答继续讨论。` }],
  }, { timeout: 15000 });
  if (result.isError) throw new Error("宿主未接收消息");
  sent = true;
  setMessage("答复已发送到当前对话。");
}
async function submit(event) {
  event.preventDefault();
  if (busy || sent || !ready) return;
  const missing = record.questionnaire.questions.find(q => q.required && !isAnswered(q));
  const invalidOther = record.questionnaire.questions.find(q => draft(q).other && !draft(q).text.trim());
  if (missing || invalidOther) {
    const q = missing || invalidOther;
    setMessage(`请完成：${q.title}`);
    const field = document.getElementById(`question-${q.id}`);
    field?.scrollIntoView({ block: "center" });
    field?.querySelector("input, textarea")?.focus({ preventScroll: true });
    return;
  }
  busy = true;
  const button = root.querySelector("button.primary");
  button.disabled = true; button.textContent = "正在提交…";
  try {
    if (record.status !== "submitted") {
      if (!token) throw new Error("问卷尚未连接完成，请重新打开");
      const result = await app.callServerTool({ name: "submit_questionnaire", arguments: {
        questionnaire_id: record.id, submission_token: token,
        answers: record.questionnaire.questions.map(q => {
          const a = draft(q);
          return { question_id: q.id, selected_option_ids: a.selected_option_ids,
            text: q.type === "text" || a.other ? a.text : "", note: a.note };
        }),
      } }, { timeout: 15000 });
      receive(result);
    }
    try { await sendToConversation(); }
    catch { setMessage("答案已保存，但尚未发回对话。可以重试「继续讨论」，或复制下方答复。"); }
  } catch (error) { setMessage(`提交未完成：${error.message}`); }
  finally { busy = false; render(); }
}

function theme(context) {
  document.documentElement.dataset.theme = context?.theme === "dark" ? "dark" : "light";
}
app.ontoolresult = (result) => {
  try { receive(result); refresh(); }
  catch (error) { setMessage(error.message); }
};
app.onhostcontextchanged = theme;
app.onerror = (error) => { if (record) setMessage(`连接异常：${error.message}`); };
async function refresh() {
  if (!ready || !record || refreshedId === record.id) return;
  refreshedId = record.id;
  try { receive(await app.callServerTool({ name: "get_questionnaire", arguments: { questionnaire_id: record.id } }, { timeout: 15000 })); }
  catch { setMessage("暂时无法刷新已保存状态；提交时会再次核对。"); }
}
(async () => {
  try {
    await app.connect();
    ready = true;
    theme(app.getHostContext());
    if (record) render();
    await refresh();
  } catch {
    root.replaceChildren(el("p", "status", "问卷尚未连接到对话。请通过「打开讨论问卷」工具重新打开。"));
  }
})();
