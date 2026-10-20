# 本地验证记录

日期：2026-09-28，版本0.2.0（当前 Agent 提供 LLM）。仓库放置位置为独立的 `plugins/title-trend/`；检查当前目录与父目录后未发现适用的 AGENTS.md，没有覆盖其他插件。

## 架构修正

移除服务端模型 HTTP 适配器、endpoint/model/header 设置和模型凭证配置。Skill 指导当前 Agent 选择候选词和生成建议，Python 确定性评分。报告 schema 2.0 明确 awaiting_advice/complete 阶段；完成报告只能提交建议，不能替换服务器保存的数据。数值公式版本保持 bing-monthly-v1.0.0。

## 已通过

| 项目 | 结果与范围 |
|---|---|
| Python 3.12.8 | 57 项 pytest 全部通过 |
| Python 3.10.16 | 隔离环境运行同一 57 项 pytest，全部通过 |
| 分词兼容性 | jieba 0.42.1；中文词典、中文组合词、OpenAI/AI/GPT-4 保留通过，版本锁定 |
| 静态检查 | ruff check src tests 通过 |
| Plugin/Skill | plugin-creator validate_plugin 与 skill-creator quick_validate 通过 |
| 打包 | `uv build --wheel` 成功，wheel 含自包含 HTML 资源和 CLI |
| 安装运行 | 从 wheel 使用锁定依赖安装本地 `title-trend` 启动器；已验证模拟 CLI、stdio 工具和已打包 UI 资源 |
| stdio MCP | 官方 Python SDK ClientSession 真正启动服务并执行 initialize、tools/list、prepare_title → analyze_title → complete_report、resources/read；完整 content.text 与 structuredContent 可用 |
| 无 UI 降级 | 不声明 Apps 能力的 stdio 客户端收到完整评分/不足状态、关键量、市场、日期、分析与标题建议 |
| MCP Apps 宿主 | 官方 ext-apps 1.7.5 AppBridge SDK 本地宿主完成三步工具调用、ui/initialize、tool-input/result、主题通知；资源与结果来自真正 Python stdio MCP 调用，**数据为模拟** |
| UI | 明暗主题、375px 窄屏、综合 null、待 Agent 建议、完整报告内容、文字注入转义及失败后清除旧评分通过；浏览器 pageerror 为空；截图人工查看 |
| 系统凭证库 | macOS `keyring.backends.macOS.Keyring` 可用，status 仅显示状态；拒绝非安全后端、脱敏与删除逻辑使用隔离 mock 测试 |

本地 CLI 启动器：`/Users/qingyang/.local/bin/title-trend`。Plugin 源码在仓库中；尚未自动添加到客户端插件市场。UI 构建在 Node 25.2.1、Chrome headless 中验证。所有模拟调用及宿主验证都没有访问 DataForSEO 或模型 API。

测试覆盖：固定公式常量、正量稳定水平、低/零基数、负增长、极大量与封顶、真实零值与 null、缺失月份、当前月排除、来源延迟、所有候选的聚合门槛；缓存地区/语言/设备/接口/时间窗/测试 namespace 隔离和过期；跨实例并发只有一次付费请求；HTTP/JSON/任务/超时错误、付费冷却和免费 GET 重试上限；Agent 建议 JSON/未知字段/评分注入、无关热词、主题锚点、数字事实、新英文/中文实体、收益承诺、建议失败保留数据可直接修正重试；Agent 不能覆盖保存的分数/数据、建议重试无新查询、报告过期/容量淘汰、工具 JSON Schema 引用、旧模型配置迁移、仅两项 DataForSEO 隐藏输入与旧模型凭证删除。

可复现命令（在插件根目录）：

```sh
uv sync --frozen --python 3.12
.venv/bin/pytest -q
.venv/bin/ruff check src tests
uv run --frozen --isolated --python 3.10 pytest -q
uv build --wheel
cd ui
npm ci
npm run build
npm test
```

默认 Python 3.12 系统 pip 的独立 build 环境曾遇到本机证书链配置失败，改用 uv 的构建流程成功，没有关闭 TLS 验证。jieba 老版本正则会在首次导入/编译时产生 invalid escape 的第三方警告；分词和整个测试套件通过，未修改第三方源码。README 使用已验证的 uv 构建命令。

## 真实覆盖与待验收项

后续安全状态检查确认：本插件 `title-trend.v1` 下的 DataForSEO API login、API password 均已配置。只显示布尔状态与固定脱敏，不读取或搬迁其他服务凭证；新版不需要模型 API 配置。

最初的真实覆盖命令走过缺凭证失败路径：十个固定中文关键词均返回明确的 request_failed/缺少凭证原因，没有被填成零。实际 metadata_requests=0、paid_requests=0、cost_usd=0。没有请求真实 API，不能据此判断中文数据覆盖率。

凭证配置后重新运行固定十词覆盖验证，免费支持列表阶段请求失败，metadata_requests=1、paid_requests=0；十词均 request_failed，没有搜索数据。随后用安装启动器相同 Python 运行时只检查安全可显示的 HTTP 状态码，确认免费接口 HTTP 403。未打印原始响应、异常堆栈、认证头或凭证，也未继续付费查询。Keychain重新授权后，Python 3.10与3.12均成功读取两项凭证；再次检查免费接口得到HTTP 403、API内部码40104。依据[官方错误码说明](https://docs.dataforseo.com/v3/appendix-errors/)，这是账户验证尚未完成，需要在用户控制台完成要求的邮箱和/或手机验证。不是搜索覆盖结果；此轮仍未发起付费查询。

当前 Codex 全局 MCP 配置尚无 title-trend 条目，当前会话工具列表也未加载本插件；可通过本地命令执行 Skill 流程。官方 MCP 注册命令已写入 README，当前桌面会话热加载和原生评分卡尚未验收。

仍需：

1. 在 DataForSEO 控制台完成账户验证（内部码40104），然后重新运行固定十词 `verify-coverage`（最多一个付费 POST）核实当日支持列表、实际最新月、返回设备和中文历史覆盖。
2. 在目标 Agent 环境加载 Skill 与新版 MCP，验证其实际选词、解释数据和完成报告的行为。标准 SDK 测试中的 Agent 输出为固定模拟样本，不是 Codex 目标客户端对真实数据的验收。
3. 依据真实中文覆盖判断 CN Bing 是否适合作为主要参考；覆盖不足时仍按门槛返回 null，不切换市场、不补数据。若需改变设备范围或公式，必须写明新版本。
4. 在目标商业/桌面客户端中继续实机验收。当前通过的是基于官方 SDK 的**本地标准 Apps 测试宿主**，没有声称 Claude Desktop、VS Code、ChatGPT 或 Codex 的 UI 已验收。
5. Windows Credential Manager、Linux Secret Service/KWallet 的具体系统配置尚未实机测试；只启用官方系统后端白名单，缺少后端则拒绝保存。其他 Python 大版本尚未验证。

UI 静态预览、模拟评分以及模拟宿主通信通过，均不能代替上述真实 API 与目标 Agent/客户端验收。

本地检查产物（忽略版本控制）：`artifacts/host-validation.json`、`host-light.png`、`host-dark-narrow.png`、`host-missing.png`、`credentials-status.json`、`coverage-no-credentials.json`、`installed-wheel-demo.json`、`dist/title_trend-0.2.0-py3-none-any.whl` 与 `title-trend-plugin-0.2.0.zip`。模拟预览则提交在 `docs/preview-simulated.html`。
