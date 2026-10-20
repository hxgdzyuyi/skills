# 方案讨论问卷

本地 MCP Apps 服务器与讨论技能。主要解决方案讨论超过原生 `request_user_input` 三题上限时，需要反复分批提问的问题：一份问卷支持 **1–12 题**，用户一次填写、统一提交，通过宿主的 `ui/message` 把整份答案发回当前对话。无需模型 API、云服务或公开端口。

四项以上可独立回答的事项优先集中成一份长问卷；只有明确要求逐题讨论或题目存在依赖时才逐题问。支持混合单选、多选、自由文本、其他方案与逐题补充说明。超过 12 题时按主题分卷。

## 文件与运行

- `src/`：MCP 服务器、答案校验、问卷界面和本地预览。
- `dist/`：打包后的独立服务器与 HTML，可直接作为本地插件运行，不依赖运行时安装 npm 包。
- `skills/discuss-with-questionnaire/`：讨论方案时使用问卷的规则。
- `examples/current-question.json`：当前 Mira 的第 3 题，未替用户作答。
- `examples/mechanics-long-questionnaire.json`：Mira 的 8 题机制问卷，不重复已经确认的决定。

```sh
npm ci --ignore-scripts
npm run build
npm test
npm run test:ui
npm run preview
```

预览命令只监听本机随机端口，地址打印在终端。本地预览可验证提交和存储，但不会替 MCP 宿主发送聊天消息。

## 工具

`show_questionnaire` 接收 `title`、`description`、`questions` 与可选 `idempotency_key`。每题包含 `id`、`title`、`type`（`single`、`multiple`、`text`）、`options`、`required` 和 `allow_other`。选项包含 `id`、`label`、`description` 和可选 `recommended`。

`get_questionnaire` 按 `questionnaire_id` 读取状态及答案。`submit_questionnaire` 仅向 App 暴露，用于用户点击提交后的保存。

数据默认位于 `~/.local/share/plan-questionnaire/`。设置 `PLAN_QUESTIONNAIRE_DATA_DIR` 可指定独立数据目录，测试使用临时目录。推荐选项不预选；提交后不允许静默覆盖，修改决定时创建新问卷。提交成功但聊天发送失败时，可以重试发送或复制已保存答复。

## 本地安装

本目录作为个人 marketplace 的 `plan-questionnaire` 插件安装。`mcp.json` 使用相对于插件根目录的工作目录与启动路径，兼容本机 CLI。当前机器的 Node 路径为 `/opt/homebrew/bin/node`，迁移机器时按实际位置调整。

同时提供根目录 `plugin.json` 与 `.codex-plugin/plugin.json`，兼容当前本机 Codex CLI 的插件清单读取方式。

```sh
npm run install:local
```

安装脚本保留个人 marketplace 中已有的插件，并在首次添加前备份目录配置。界面测试使用本机 Chrome 和隔离的临时问卷，不会替用户回答真实问题。

如果宿主尚未加载新插件，刷新插件或重新打开对话后再调用 `show_questionnaire`。安装完成不等于当前旧会话已获得新工具，须实际调用验证。

协议参考：[OpenAI MCP Apps quickstart](https://developers.openai.com/plugins/build/app-quickstart)、[UI bridge](https://developers.openai.com/plugins/build/chatgpt-ui)、[本地插件](https://developers.openai.com/plugins/build/plugins)。
