import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SERVER_VERSION = "0.1.0";
const RESOURCE_URI = `ui://code-knowledge-explorer/${SERVER_VERSION}/quiz.html`;
const MIME_TYPE = "text/html;profile=mcp-app";
const OPTION_IDS = ["A", "B", "C", "D"];
const __dirname = dirname(fileURLToPath(import.meta.url));

const resourceUiMeta = {
  csp: { connectDomains: [], resourceDomains: [] },
  permissions: {},
  prefersBorder: true
};

const modelUiMeta = {
  ui: { resourceUri: RESOURCE_URI, visibility: ["model"] },
  "ui/resourceUri": RESOURCE_URI,
  "openai/outputTemplate": RESOURCE_URI,
  "openai/widgetAccessible": true
};

const appUiMeta = {
  ui: { resourceUri: RESOURCE_URI, visibility: ["app"] }
};

const sessions = new Map();

function jsonSchema(properties, required = []) {
  return {
    type: "object",
    properties,
    required,
    additionalProperties: true
  };
}

const tools = [
  {
    name: "open_code_exploration_quiz",
    title: "打开代码探索测验",
    description: "为代码探索总结打开 MCP App 选择题界面。正确答案只保存在服务端，提交前不会显示。",
    inputSchema: jsonSchema(
      {
        title: { type: "string" },
        explorationGoal: { type: "string" },
        assumptions: { type: "array", items: { type: "string" } },
        repository: {
          type: "object",
          properties: {
            path: { type: "string" },
            name: { type: "string" }
          },
          additionalProperties: true
        },
        architectureSummary: { type: "object", additionalProperties: true },
        questions: {
          type: "array",
          minItems: 5,
          maxItems: 5,
          items: { type: "object", additionalProperties: true }
        },
        nextReading: {
          type: "array",
          items: { type: "object", additionalProperties: true }
        }
      },
      ["title", "explorationGoal", "architectureSummary", "questions"]
    ),
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: false
    },
    _meta: modelUiMeta
  },
  {
    name: "submit_code_exploration_quiz",
    title: "提交代码探索测验",
    description: "仅供 App 调用。对提交答案判题，并返回解释和代码证据。",
    inputSchema: jsonSchema(
      {
        sessionId: { type: "string" },
        answers: {
          type: "object",
          additionalProperties: { type: "string", enum: OPTION_IDS }
        }
      },
      ["sessionId", "answers"]
    ),
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false
    },
    _meta: appUiMeta
  },
  {
    name: "get_code_exploration_quiz_state",
    title: "读取代码探索测验状态",
    description: "仅供 App 调用。根据 sessionId 读取当前测验是否已经提交，用于 App 重新挂载后恢复结果页。",
    inputSchema: jsonSchema(
      {
        sessionId: { type: "string" }
      },
      ["sessionId"]
    ),
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false
    },
    _meta: appUiMeta
  }
];

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function result(id, payload) {
  send({ jsonrpc: "2.0", id, result: payload });
}

function error(id, code, message, data) {
  send({ jsonrpc: "2.0", id, error: { code, message, ...(data === undefined ? {} : { data }) } });
}

function asObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} 必须是对象。`);
  }
  return value;
}

function asString(value, fallback = "") {
  return typeof value === "string" ? value.trim() : fallback;
}

function normalizeOptionId(value) {
  const raw = asString(value).toUpperCase();
  if (OPTION_IDS.includes(raw)) return raw;
  const numeric = Number(value);
  if (Number.isInteger(numeric) && numeric >= 0 && numeric < OPTION_IDS.length) {
    return OPTION_IDS[numeric];
  }
  if (Number.isInteger(numeric) && numeric >= 1 && numeric <= OPTION_IDS.length) {
    return OPTION_IDS[numeric - 1];
  }
  return "";
}

function normalizeOptions(rawOptions) {
  if (!Array.isArray(rawOptions) || rawOptions.length !== 4) {
    throw new Error("每道选择题必须恰好包含四个选项。");
  }
  return rawOptions.map((option, index) => {
    if (typeof option === "string") {
      return { id: OPTION_IDS[index], text: option };
    }
    if (option && typeof option === "object") {
      return {
        id: normalizeOptionId(option.id) || OPTION_IDS[index],
        text: asString(option.text ?? option.label ?? option.value)
      };
    }
    return { id: OPTION_IDS[index], text: "" };
  }).map((option, index) => ({
    id: OPTION_IDS[index],
    text: option.text || `选项 ${OPTION_IDS[index]}`
  }));
}

function optionDisplayLength(text) {
  return Array.from(
    String(text ?? "")
      .replace(/\s+/g, "")
      .replace(/[，。,.、；;：:（）()【】[\]{}"'“”‘’]/g, "")
  ).length;
}

function assertCorrectOptionNotUniquelyLongest(options, correctOptionId, questionLabel) {
  const lengths = options.map((option) => ({
    id: option.id,
    length: optionDisplayLength(option.text)
  }));
  const correct = lengths.find((item) => item.id === correctOptionId);
  if (!correct) return;
  const maxLength = Math.max(...lengths.map((item) => item.length));
  const longestCount = lengths.filter((item) => item.length === maxLength).length;
  if (correct.length === maxLength && longestCount === 1) {
    throw new Error(`${questionLabel}的正确选项不能是唯一最长选项；请压缩正确项或补足干扰项，让四个选项长度和信息密度更接近。`);
  }
}

function normalizeEvidence(rawEvidence) {
  if (!Array.isArray(rawEvidence)) return [];
  return rawEvidence.map((item) => {
    if (typeof item === "string") return { path: item };
    if (!item || typeof item !== "object") return {};
    return {
      path: asString(item.path),
      line: item.line,
      lines: asString(item.lines),
      symbol: asString(item.symbol),
      reason: asString(item.reason)
    };
  }).filter((item) => item.path || item.symbol || item.lines || item.line);
}

function publicEvidence(evidence) {
  return evidence.map(({ path, line, lines, symbol }) => ({ path, line, lines, symbol }));
}

function normalizeQuestions(rawQuestions) {
  if (!Array.isArray(rawQuestions) || rawQuestions.length !== 5) {
    throw new Error("测验必须恰好包含五道题。");
  }
  return rawQuestions.map((raw, index) => {
    const questionLabel = `第 ${index + 1} 题`;
    const question = asObject(raw, questionLabel);
    const options = normalizeOptions(question.options);
    const correctOptionId = normalizeOptionId(
      question.correctOptionId ?? question.correctAnswer ?? question.answer ?? question.correctOption
    );
    if (!correctOptionId) {
      throw new Error(`${questionLabel}必须包含 A-D 中的唯一正确选项。`);
    }
    assertCorrectOptionNotUniquelyLongest(options, correctOptionId, questionLabel);
    return {
      id: asString(question.id, `q${index + 1}`) || `q${index + 1}`,
      stem: asString(question.stem ?? question.question),
      options,
      correctOptionId,
      knowledgePoint: asString(question.knowledgePoint),
      codeEvidence: normalizeEvidence(question.codeEvidence ?? question.evidence),
      explanation: asString(question.explanation),
      reviewFocus: asString(question.reviewFocus ?? question.remediation ?? question.followUp)
    };
  });
}

function publicQuestion(question) {
  return {
    id: question.id,
    stem: question.stem,
    options: question.options,
    knowledgePoint: question.knowledgePoint,
    codeEvidence: publicEvidence(question.codeEvidence)
  };
}

function normalizeQuiz(input) {
  const payload = asObject(input, "open_code_exploration_quiz 的参数");
  const questions = normalizeQuestions(payload.questions);
  return {
    sessionId: randomUUID(),
    title: asString(payload.title, "代码探索测验"),
    explorationGoal: asString(payload.explorationGoal),
    assumptions: Array.isArray(payload.assumptions) ? payload.assumptions.map((item) => asString(item)).filter(Boolean) : [],
    repository: payload.repository && typeof payload.repository === "object" ? payload.repository : {},
    architectureSummary: payload.architectureSummary && typeof payload.architectureSummary === "object" ? payload.architectureSummary : {},
    questions,
    nextReading: Array.isArray(payload.nextReading) ? payload.nextReading : []
  };
}

function publicQuiz(quiz) {
  return {
    sessionId: quiz.sessionId,
    title: quiz.title,
    explorationGoal: quiz.explorationGoal,
    assumptions: quiz.assumptions,
    repository: quiz.repository,
    architectureSummary: quiz.architectureSummary,
    questions: quiz.questions.map(publicQuestion),
    nextReading: quiz.nextReading
  };
}

function optionText(question, optionId) {
  return question.options.find((option) => option.id === optionId)?.text ?? "";
}

function recommendedReading(quiz, missedQuestions) {
  if (Array.isArray(quiz.nextReading) && quiz.nextReading.length > 0) {
    return quiz.nextReading;
  }
  const byPath = new Map();
  for (const question of missedQuestions.length ? missedQuestions : quiz.questions) {
    for (const evidence of question.codeEvidence) {
      if (evidence.path && !byPath.has(evidence.path)) {
        byPath.set(evidence.path, {
          path: evidence.path,
          reason: question.reviewFocus || question.knowledgePoint || "复习这道题对应的代码证据。"
        });
      }
    }
  }
  return Array.from(byPath.values()).slice(0, 5);
}

function masterySummary(score, total) {
  if (score === total) return "掌握较完整：你能把模块职责、调用关系和关键数据流对应到代码证据。";
  if (score >= 3) return "掌握不均衡：主线理解基本成立，但仍有部分边界或状态流转需要回到代码确认。";
  return "需要复习：建议先重新阅读入口、核心模块和数据流相关文件，再回到题目核对调用链。";
}

function gradeQuiz(input) {
  const payload = asObject(input, "submit_code_exploration_quiz 的参数");
  const sessionId = asString(payload.sessionId);
  const quiz = sessions.get(sessionId);
  if (!quiz) throw new Error("未找到测验会话，或该会话已经过期。");
  const answers = asObject(payload.answers, "answers");
  const results = quiz.questions.map((question, index) => {
    const userOptionId = normalizeOptionId(answers[question.id]);
    const isCorrect = userOptionId === question.correctOptionId;
    return {
      id: question.id,
      number: index + 1,
      stem: question.stem,
      userOptionId: userOptionId || "",
      userAnswer: userOptionId ? `${userOptionId}. ${optionText(question, userOptionId)}` : "未作答",
      correctOptionId: question.correctOptionId,
      correctAnswer: `${question.correctOptionId}. ${optionText(question, question.correctOptionId)}`,
      isCorrect,
      knowledgePoint: question.knowledgePoint,
      explanation: question.explanation,
      codeEvidence: question.codeEvidence,
      reviewFocus: question.reviewFocus
    };
  });
  const score = results.filter((item) => item.isCorrect).length;
  const missedQuestions = quiz.questions.filter((question) => {
    const resultItem = results.find((item) => item.id === question.id);
    return resultItem && !resultItem.isCorrect;
  });
  const submission = {
    sessionId,
    title: quiz.title,
    score,
    total: quiz.questions.length,
    percentage: Math.round((score / quiz.questions.length) * 100),
    masterySummary: masterySummary(score, quiz.questions.length),
    results,
    recommendedNextReading: recommendedReading(quiz, missedQuestions)
  };
  quiz.submission = submission;
  return submission;
}

async function openQuiz(args) {
  const quiz = normalizeQuiz(args);
  sessions.set(quiz.sessionId, quiz);
  return {
    content: [
      {
        type: "text",
        text: `已打开五道题的代码探索测验：${quiz.title}`
      }
    ],
    structuredContent: {
      quiz: publicQuiz(quiz)
    },
    _meta: {
      "openai/outputTemplate": RESOURCE_URI,
      "ui/resourceUri": RESOURCE_URI
    }
  };
}

async function submitQuiz(args) {
  const submission = gradeQuiz(args);
  return {
    content: [
      {
        type: "text",
        text: `测验已判题：${submission.score}/${submission.total}。${submission.masterySummary}`
      }
    ],
    structuredContent: {
      submission
    },
    _meta: {
      "openai/outputTemplate": RESOURCE_URI,
      "ui/resourceUri": RESOURCE_URI
    }
  };
}

async function getQuizState(args) {
  const payload = asObject(args, "get_code_exploration_quiz_state 的参数");
  const sessionId = asString(payload.sessionId);
  const quiz = sessions.get(sessionId);
  if (!quiz) {
    return {
      content: [{ type: "text", text: "未找到可恢复的测验状态。" }],
      structuredContent: {
        state: { sessionId, status: "missing" }
      }
    };
  }
  if (quiz.submission) {
    return {
      content: [{ type: "text", text: "已恢复已提交的测验结果。" }],
      structuredContent: {
        submission: quiz.submission
      },
      _meta: {
        "openai/outputTemplate": RESOURCE_URI,
        "ui/resourceUri": RESOURCE_URI
      }
    };
  }
  return {
    content: [{ type: "text", text: "测验尚未提交。" }],
    structuredContent: {
      state: { sessionId, status: "unsubmitted" }
    }
  };
}

async function readAppHtml() {
  return readFile(join(__dirname, "app.html"), "utf8");
}

async function handleToolCall(name, args) {
  if (name === "open_code_exploration_quiz") return openQuiz(args ?? {});
  if (name === "submit_code_exploration_quiz") return submitQuiz(args ?? {});
  if (name === "get_code_exploration_quiz_state") return getQuizState(args ?? {});
  throw new Error(`未知工具：${name}`);
}

async function handleRequest(message) {
  const { id, method, params } = message;
  if (id === undefined || id === null) return;

  switch (method) {
    case "initialize":
      return result(id, {
        protocolVersion: params?.protocolVersion ?? "2026-01-26",
        capabilities: {
          tools: { listChanged: false },
          resources: { listChanged: false },
          extensions: { "com.openai": {} }
        },
        serverInfo: {
          name: "code-knowledge-explorer",
          version: SERVER_VERSION
        },
        instructions: "读取真实代码并生成五道架构理解题后，调用 open_code_exploration_quiz 打开交互式测验。提交工具只供 App 调用。题目和解释尽量使用中文，且正确选项不能是唯一最长选项。"
      });
    case "ping":
      return result(id, {});
    case "tools/list":
      return result(id, { tools });
    case "resources/list":
      return result(id, {
        resources: [
          {
            uri: RESOURCE_URI,
            name: "代码知识探索测验",
            title: "代码知识探索测验",
            description: "用于学习导向代码探索的交互式选择题界面。",
            mimeType: MIME_TYPE,
            _meta: { ui: resourceUiMeta }
          }
        ]
      });
    case "resources/read":
      if (params?.uri !== RESOURCE_URI) {
        return error(id, -32602, `未知资源 URI：${params?.uri ?? ""}`);
      }
      return result(id, {
        contents: [
          {
            uri: RESOURCE_URI,
            mimeType: MIME_TYPE,
            text: await readAppHtml(),
            _meta: { ui: resourceUiMeta }
          }
        ]
      });
    case "prompts/list":
      return result(id, { prompts: [] });
    case "tools/call":
      return result(id, await handleToolCall(params?.name, params?.arguments));
    default:
      return error(id, -32601, `未知方法：${method}`);
  }
}

let buffer = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let newlineIndex;
  while ((newlineIndex = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, newlineIndex).replace(/\r$/, "");
    buffer = buffer.slice(newlineIndex + 1);
    if (!line.trim()) continue;
    let message;
    try {
      message = JSON.parse(line);
    } catch (parseError) {
      error(null, -32700, `解析 JSON 失败：${parseError.message}`);
      continue;
    }
    handleRequest(message).catch((requestError) => {
      error(message.id ?? null, -32000, requestError instanceof Error ? requestError.message : String(requestError));
    });
  }
});
