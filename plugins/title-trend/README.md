# Title Trend Plugin

面向微信公众号创作者的外部搜索需求与趋势参考。由 Codex 等当前 Agent 理解标题、选择候选关键词并撰写建议，Python MCP 负责中文分词、真实 DataForSEO 查询、缓存、固定评分和完整评分卡。用户只需提出一次分析需求，Skill 组织三步标准工具调用。

**评分不代表微信公众号热度、点击率或爆款概率。** 首版只查询 Bing Search Volume History，不实现 Google，也不会切换到其他市场。真实中文覆盖尚待凭证联调；模拟成功不表示真实 API 验收通过。

## 安装与运行

核心要求：Python 3.10+，推荐已验证的 Python 3.12；安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)。Python 服务运行不需要 Node.js 或 DataForSEO CLI。主题理解与写作使用当前 Agent 的模型；无需另外的模型 API 地址或凭证，不依赖 MCP Sampling。

从此目录运行：

```sh
uv sync --frozen --no-dev --python 3.12
.venv/bin/title-trend configure
.venv/bin/title-trend credentials status
.venv/bin/title-trend prepare '用 Python 自动化办公，如何减少重复工作？'
.venv/bin/title-trend serve
```

`serve` 默认且仅提供 stdio；stdout 专用于 MCP。Windows 使用 `.venv\Scripts\title-trend.exe`。GUI 客户端推荐使用虚拟环境启动器的**绝对路径**。

可选，安装独立全局启动器（插件 `.mcp.json` 使用此启动器）：

```sh
uv tool install --with-requirements requirements.lock .
```

将 `uv tool dir --bin` 的目录加入客户端进程 PATH；如该 uv 版本不支持 `--with-requirements`，使用上面的冻结虚拟环境方案。Python 顶层依赖和所有传递依赖锁在 `uv.lock`；`requirements.lock` 为附带 hashes 的运行依赖导出。UI 构建依赖锁在 `ui/package-lock.json`。已经提交自包含 `src/title_trend/ui/report.html`，安装服务无需再构建 UI。

插件封装：`.codex-plugin/plugin.json`、`.mcp.json`、`skills/title-trend/SKILL.md`。可导入插件目录到支持此封装的客户端；普通 MCP 客户端使用以下配置，Skill 则作为标准 Agent Skill 单独安装。不会修改其他插件或自动安装到用户的市场目录。

## 凭证与非敏感配置

必须在本地交互式终端运行 `title-trend configure`，输入 DataForSEO API **login 与 API password**，仅此两项都隐藏输入，不支持密码命令行参数或管道输入。普通配置只记录词典路径与缓存、请求设置。**无需 Chat Completions endpoint、模型名称或模型 API Key。**

```sh
title-trend configure
title-trend credentials status
title-trend credentials delete
title-trend config-path
```

macOS 使用 `keyring.backends.macOS.Keyring`。Windows 仅接受官方 WinVaultKeyring；Linux 仅接受官方 SecretService/KWallet D-Bus 后端。拒绝 chained、null、fail、keyrings.alt 与明文文件后端；不可用时不会退回文件。其他系统后端的运行验证范围见 [验收记录](docs/validation.md)。

修复方法：macOS 解锁登录 Keychain 并允许当前 Python 访问；Windows 启用 Credential Manager；Linux 安装/解锁 Secret Service 或 KWallet、启动用户 D-Bus 会话，安装对应 keyring 系统依赖；使用 `python -m keyring diagnose` 检查后端（自行运行，不分享敏感输出）。若自动选择 ChainerBackend，可在 keyring 自身配置中选择官方系统后端，不能选择文件后端。没有图形会话/解锁凭证库时须先修复系统环境。

凭证只进入系统凭证库与对应服务的 HTTP 认证头。不会写入 Skill、模型 prompt、MCP 参数/返回、UI、SQLite 或日志。服务不输出 HTTP 原始响应、异常 repr 或堆栈，不跟随重定向。删除命令只删除 `title-trend.v1` 服务下的 DataForSEO 两项凭证，以及旧版遗留的 `model-api-key`（如有）；不删除缓存和非敏感配置。旧模型凭证不会被新版读取或使用。

查看 `title-trend config-path` 后可编辑非敏感 JSON，例如：

```json
{
  "user_dictionary": "/absolute/path/dictionary.txt",
  "cache_ttl_seconds": 86400,
  "metadata_ttl_seconds": 3600,
  "timeout_seconds": 45,
  "retry_count": 2,
  "min_request_interval": 1,
  "paid_cooldown_seconds": 300
}
```

从 v0.1 升级时，旧配置中的 endpoint/model/header 非敏感字段会被忽略；再次运行 configure 保存时清除这些字段，保留词典与请求设置。模型凭证不再出现在 status 中，可用 credentials delete 删除旧凭证（此命令也会删除 DataForSEO 凭证，需重新配置）。不要复制 Codex 的登录凭证到插件。

## 在 Codex 等 Agent 中使用

安装 Skill 与 MCP 后，直接提出“分析这个公众号标题：……”即可。当前 Agent 执行：

1. `prepare_title(title, market?)`：jieba 分词参考，无外部请求。
2. `analyze_title(title, selection, market?)`：接受 Agent 选出的1–5个候选短语，查询真实数据并确定性评分。
3. `complete_report(report_id, advice)`：合并 Agent 根据数据生成的分析、关键词建议和2–3个标题，返回完整评分卡与文字。

第二步输出明确的 awaiting_advice 状态；第三步不再查询数据，Agent 不能改写服务器保存的分数与搜索量。报告 ID 在同一 MCP 进程保留30分钟、最多128份；建议校验失败只重试第三步。服务重启/报告过期可重新查询，有效关键词缓存仍可复用。调用 schema、示例与限制见 [Agent 工作流](docs/agent-workflow.md)。

CLI 作为独立的数据工具不会自动运行 Agent。除固定模拟预览外，需传入当前 Agent 生成的候选词 JSON；可选建议 JSON 完成报告：

```sh
title-trend analyze '用 Python 自动化办公，如何减少重复工作？' --selection-file selection.json --json
title-trend analyze '用 Python 自动化办公，如何减少重复工作？' --selection-file selection.json --advice-file advice.json
```

jieba 自定义词典为 UTF-8，一行 `词语 频次 词性`，频次/词性可省略。例如 `自动化办公 10000 nz`。英文实体和缩写在分词前独立保留。首版选词较保守：短语必须有原标题锚点，新增的非原标题词会被拒绝；允许原词重组，避免为了提分加入热词。

## 当前 Codex 会话与正式连接

在已有源码与本地启动器的当前会话中，Agent 可以先读取 `skills/title-trend/SKILL.md`，通过本地 CLI 或标准 Python MCP 客户端组织三步流程，生成文字报告。可直接提出：“用 Title Trend 分析这个标题：……”。这不表示工具已挂载到 Codex 原生工具列表，也不表示原生 MCP Apps 评分卡已经验收。

正式注册 stdio MCP 可使用 [Codex 官方 MCP 管理命令](https://learn.chatgpt.com/docs/developer-commands#codex-mcp)：

```sh
codex mcp add title-trend -- /Users/qingyang/.local/bin/title-trend serve
```

路径对应本机已安装的启动器，其他机器需替换。该命令只注册 MCP 服务，不会自动安装 Skill。新会话可明确要求读取上述 Skill 的绝对路径，或安装完整 Plugin 来同时发现 Skill。添加后需客户端刷新连接；本机尚未验证当前桌面会话的热加载。无法刷新时重新进入任务加载。原生评分卡还取决于宿主的 MCP Apps 支持，文字报告始终可用。

## 客户端连接

通用 MCP JSON 示例（替换为真实绝对路径）：

```json
{
  "mcpServers": {
    "title-trend": {
      "command": "/absolute/path/title-trend/.venv/bin/title-trend",
      "args": ["serve"]
    }
  }
}
```

该结构可用于采用 `mcpServers` 的桌面客户端，例如 [Claude Desktop](https://py.sdk.modelcontextprotocol.io/get-started/real-host/)；支持 stdio 的其他客户端按自身配置格式填同一 command/args。在 [VS Code 的 MCP 配置](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)中对应 `servers.title-trend`：

```json
{
  "servers": {
    "title-trend": {
      "type": "stdio",
      "command": "/absolute/path/title-trend/.venv/bin/title-trend",
      "args": ["serve"]
    }
  }
}
```

这些是启动配置示例，未宣称已在相应桌面客户端验收。建议客户端查询工具超时设为 240 秒以容纳外部请求。宿主只需支持标准 MCP，无 UI 时收到完整 `content[].text` 与 `structuredContent`；支持 [MCP Apps](https://apps.extensions.modelcontextprotocol.io/api/) 时从 `_meta.ui.resourceUri` 读取 `ui://title-trend/report.html`，用 `text/html;profile=mcp-app` 展示评分卡。

## 本地模拟与宿主联调

无需任何凭证的固定模拟样例，仅支持这个标题，不会分析任意输入：

```sh
.venv/bin/title-trend analyze '用 Python 自动化办公，如何减少重复工作？' --demo
.venv/bin/title-trend preview --output docs/preview-simulated.html
.venv/bin/title-trend serve --demo
```

[模拟预览](docs/preview-simulated.html) 标为模拟数据。它只是浏览器静态预览。

**标准 SDK 宿主联调是另一条验证路径**：本仓库提供 simulation-only 本地测试宿主，用官方 MCP SDK 启动 Python stdio 服务、读取 UI 资源和完成 prepare → analyze → complete 三步（Agent输出使用明确标注的固定模拟样本），再使用官方 ext-apps `AppBridge` 与沙箱评分卡完成 `ui/initialize`、工具参数与结果通知、主题通知。它使用标准协议，不是普通 HTML 预览，也不依赖客户端私有 API。

```sh
cd ui
npm ci
npm run build
npm run host
# 打开 http://127.0.0.1:4177/
npm test
```

开发验证使用 Node 20+（本机 Node 25.2.1）；UI 测试优先使用已安装的 macOS Chrome，也可设置 `TITLE_TREND_CHROME` 为浏览器可执行路径，或运行 `npx playwright install chromium`。宿主与测试只访问模拟服务，不能发起真实付费查询。测试截图和 JSON 放在忽略版本控制的 `artifacts/`。

## 真实覆盖验证与成本

安全凭证配置完成后：

```sh
.venv/bin/title-trend verify-coverage --output coverage-real.json
```

此命令固定验证科技、职业工具、汽车、育儿、健康、养老、教育、生活方式、情绪与创作十个词，最多 **一个付费 History POST**，另有免费市场列表和更新状态 GET。没有模型调用；缓存有效时不付费。无自动循环或无上限请求。读取每词状态、四设备完整性、统计月份以及 API 返回 USD 成本后，才能判断实际覆盖。支持列表不是逐词覆盖证明。

正常分析最多 5 个候选词打包成一次 POST，已有缓存词不重复付费。免费 GET 最多两次重试；付费 POST 不自动重发；相同未完成/失败的付费批次有默认 300 秒冷却期，成本未知时明确标记。API 返回成本记录在结构化结果与本地请求 ledger；不硬编码价格。缓存默认 24 小时，过期刷新失败保留历史数据但不评分。

## 文档与验证

- [Agent 编排流程与工具参数](docs/agent-workflow.md)
- [完整评分公式](docs/scoring.md)
- [官方数据来源、覆盖与限制](docs/data-sources.md)
- [验证记录与待完成真实联调](docs/validation.md)

```sh
uv sync --frozen
.venv/bin/pytest -q
.venv/bin/ruff check src tests
uv build --wheel
```
