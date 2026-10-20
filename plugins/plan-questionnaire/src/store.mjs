import { z } from "zod";
import { randomUUID, randomBytes, createHash, timingSafeEqual } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync, renameSync, openSync, closeSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const shortId = z.string().regex(/^[a-zA-Z0-9_-]{1,64}$/);
const text = (max) => z.string().trim().min(1).max(max);
const optionSchema = z.object({
  id: shortId,
  label: text(160),
  description: z.string().max(1200).default(""),
  recommended: z.boolean().default(false),
}).strict();
const questionSchema = z.object({
  id: shortId,
  title: text(400),
  description: z.string().max(2000).default(""),
  type: z.enum(["single", "multiple", "text"]).default("single"),
  options: z.array(optionSchema).max(12).default([]),
  required: z.boolean().default(true),
  allow_other: z.boolean().default(true),
}).strict().superRefine((q, ctx) => {
  if (q.type !== "text" && q.options.length < 2)
    ctx.addIssue({ code: "custom", message: "选择题至少需要两个选项" });
  if (q.type === "text" && q.options.length)
    ctx.addIssue({ code: "custom", message: "文本题不能包含选项" });
  if (new Set(q.options.map(o => o.id)).size !== q.options.length)
    ctx.addIssue({ code: "custom", message: "选项 ID 不得重复" });
});
export const showSchema = z.object({
  title: text(200),
  description: z.string().max(3000).default(""),
  questions: z.array(questionSchema).min(1).max(12),
  idempotency_key: z.string().min(1).max(200).optional(),
}).strict().superRefine((v, ctx) => {
  if (new Set(v.questions.map(q => q.id)).size !== v.questions.length)
    ctx.addIssue({ code: "custom", message: "问题 ID 不得重复" });
});
export const getSchema = z.object({ questionnaire_id: shortId }).strict();
export const submitSchema = z.object({
  questionnaire_id: shortId,
  submission_token: z.string().min(1).max(128),
  answers: z.array(z.object({
    question_id: shortId,
    selected_option_ids: z.array(shortId).max(12).default([]),
    text: z.string().max(5000).default(""),
    note: z.string().max(3000).default(""),
  }).strict()).max(12),
}).strict();

export class QuestionnaireStore {
  constructor(directory = process.env.PLAN_QUESTIONNAIRE_DATA_DIR ??
    join(homedir(), ".local/share/plan-questionnaire")) {
    this.directory = directory;
    mkdirSync(directory, { recursive: true, mode: 0o700 });
  }
  path(id) { return join(this.directory, `${shortId.parse(id)}.json`); }
  get(id) {
    try { return JSON.parse(readFileSync(this.path(id), "utf8")); }
    catch (e) {
      if (e.code === "ENOENT") throw new Error("找不到该问卷，请重新打开问卷");
      throw e;
    }
  }
  save(record) {
    const tmp = `${this.path(record.id)}.${randomUUID()}.tmp`;
    writeFileSync(tmp, JSON.stringify(record, null, 2) + "\n", { mode: 0o600, flag: "wx" });
    renameSync(tmp, this.path(record.id));
  }
  locked(id, callback) {
    const path = join(this.directory, `${shortId.parse(id)}.lock`);
    let fd;
    try { fd = openSync(path, "wx", 0o600); }
    catch (e) {
      if (e.code === "EEXIST") throw new Error("问卷正在保存，请稍后重试");
      throw e;
    }
    try { return callback(); }
    finally { closeSync(fd); unlinkSync(path); }
  }
  create(input) {
    const { idempotency_key, ...questionnaire } = showSchema.parse(input);
    const id = idempotency_key
      ? "q-" + createHash("sha256").update(idempotency_key).digest("hex").slice(0, 40)
      : randomUUID();
    return this.locked(id, () => {
      let existing;
      try { existing = JSON.parse(readFileSync(this.path(id), "utf8")); }
      catch (e) { if (e.code !== "ENOENT") throw e; }
      if (existing) {
        if (JSON.stringify(existing.questionnaire) !== JSON.stringify(questionnaire))
          throw new Error("同一幂等键对应的问题已存在；修改问题请使用新的幂等键");
        return existing;
      }
      const record = {
        id, questionnaire, status: "pending", created_at: new Date().toISOString(),
        submission_token: randomBytes(32).toString("hex"), answers: [],
      };
      this.save(record);
      return record;
    });
  }
  submit(input) {
    const value = submitSchema.parse(input);
    return this.locked(value.questionnaire_id, () => {
      const record = this.get(value.questionnaire_id);
      const actual = Buffer.from(value.submission_token);
      const expected = Buffer.from(record.submission_token);
      if (actual.length !== expected.length || !timingSafeEqual(actual, expected))
        throw new Error("提交凭据无效，请重新打开问卷");
      const byId = new Map();
      for (const a of value.answers) {
        if (byId.has(a.question_id)) throw new Error("同一问题不能重复提交");
        if (!record.questionnaire.questions.some(q => q.id === a.question_id))
          throw new Error("答案包含不存在的问题");
        byId.set(a.question_id, a);
      }
      const answers = record.questionnaire.questions.map(q => {
        const a = byId.get(q.id) ?? { question_id: q.id, selected_option_ids: [], text: "", note: "" };
        const ids = [...a.selected_option_ids];
        const ownText = a.text.trim();
        if (new Set(ids).size !== ids.length) throw new Error("选项不能重复");
        if (ids.some(id => !q.options.some(o => o.id === id))) throw new Error("答案包含不存在的选项");
        if (q.type === "text" && ids.length) throw new Error("文本题不能提交选项");
        if (q.type !== "text" && ownText && !q.allow_other) throw new Error("该题不允许自定义答案");
        if (q.type === "single" && ids.length + Number(Boolean(ownText)) > 1)
          throw new Error("单选题只能选择一项或填写一个自定义答案");
        if (q.required && !ids.length && !ownText) throw new Error(`请回答：${q.title}`);
        return { question_id: q.id, selected_option_ids: q.options.filter(o => ids.includes(o.id)).map(o => o.id),
          text: ownText, note: a.note.trim() };
      });
      if (record.status === "submitted") {
        if (JSON.stringify(answers) !== JSON.stringify(record.answers))
          throw new Error("该问卷已提交；如需修改决定，请在对话中说明或创建新的问卷");
        return record;
      }
      record.answers = answers;
      record.status = "submitted";
      record.submitted_at = new Date().toISOString();
      this.save(record);
      return record;
    });
  }
}
export function publicRecord(record) {
  const { submission_token, ...rest } = record;
  return rest;
}
export function answerSummary(record) {
  if (record.status !== "submitted") return "";
  const lines = [`问卷「${record.questionnaire.title}」已提交。`, `问卷 ID：${record.id}`];
  for (const q of record.questionnaire.questions) {
    const a = record.answers.find(a => a.question_id === q.id);
    const labels = q.options.filter(o => a.selected_option_ids.includes(o.id)).map(o => o.label);
    if (a.text) labels.push(a.text);
    lines.push(`\n${q.title}\n我的回答：${labels.join("；") || "未作答"}`);
    if (a.note) lines.push(`补充说明：${a.note}`);
  }
  return lines.join("\n");
}
