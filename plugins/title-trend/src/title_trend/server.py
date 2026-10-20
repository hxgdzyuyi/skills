from __future__ import annotations

import logging
from importlib.resources import files

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server

from .agent import Selection
from .errors import SafeError
from .models import Advice, Report
from .service import Analyzer, ReportStore, simulated_analysis, validate_market, validate_title

UI_URI = "ui://title-trend/report.html"
UI_MIME = "text/html;profile=mcp-app"


def number(value, suffix="") -> str:
    return "无数据" if value is None else f"{value:g}{suffix}"


def text_report(report: Report) -> str:
    score = (
        number(report.metrics.score, "/100")
        if report.metrics.score is not None
        else "数据不足，暂不评分"
    )
    lines = [
        "【模拟数据 · 非真实 API】" if report.simulated else "【外部搜索趋势参考】",
        f"原标题：{report.title}",
        f"Trend Potential Score：{score}",
        f"搜索需求 {number(report.metrics.demand)}/100；趋势热度 {number(report.metrics.trend)}/100；增长 {number(report.metrics.growth)}/100",
        f"来源：{'模拟' if report.simulated else 'DataForSEO'} / {report.market.engine} / {report.market.name} ({report.market.location_code}, {report.market.language_code}) / 月度 / 四类设备合计",
        f"统计范围：{report.window_start or '未知'} 至 {report.window_end or '未知'}；来源更新：{report.data_updated_at or '未知'}；报告生成：{report.generated_at.isoformat()}",
        f"覆盖：{report.coverage.get('scorable', 0)}/{report.coverage.get('selected', 0)} 候选关键词可评分",
        f"公式：{report.formula_version}",
        "核心候选关键词（由 API 决定是否存在数据）：",
    ]
    for row in report.keywords:
        d, m = row.data, row.metrics
        lines += [
            f"- {d.keyword} [{d.status}]：最近3月平均 {number(m.recent_monthly_volume, ' 次/月')}；前3月平均 {number(m.previous_monthly_volume, ' 次/月')}；变化 {number(m.growth_pct, '%')}；趋势热度 {number(m.trend)}；增长分 {number(m.growth)}；需求分 {number(m.demand)}；关键词分 {number(m.score)}；广告竞争：{number(d.ad_competition)}（History未提供）",
            f"  获取：{d.fetched_at.isoformat() if d.fetched_at else '未知'}；缓存{'命中' if d.cache_hit else '未命中'}；过期：{d.expires_at.isoformat() if d.expires_at else '未知'}；设备与统计缺失不补零。",
        ]
        if d.reason or m.reason:
            lines.append("  原因：" + (d.reason or m.reason))
    if report.advice is not None:
        lines += [
            f"简短分析（{report.advice.origin}，编辑判断）：{report.advice.analysis}",
            "关键词建议：",
        ]
        lines += ["- " + s for s in report.advice.keyword_suggestions]
        lines.append("推荐标题（未经再次查询，不附评分）：")
        lines += [f"- {t.title} — {t.direction}" for t in report.advice.recommended_titles]
    else:
        lines += [
            "当前阶段：数据与评分已返回，等待当前 Agent 生成分析与标题建议。",
            (
                f"请根据以上校验数据调用 complete_report(report_id='{report.report_id}', advice)，获得完整评分卡与文字报告。"
                if report.report_id
                else "CLI 已返回数据；完整报告需要 Agent 提供建议JSON（--advice-file）。"
            ),
            "Agent 不得提交评分、权重或搜索量。",
        ]
    lines += ["说明：" + w for w in report.warnings]
    lines += [
        f"本次 DataForSEO 付费请求：{report.requests.get('paid_requests', 0)}；API返回成本USD：{'未知' if report.requests.get('cost_unknown') else report.requests.get('cost_usd', 0)}；关键词缓存命中：{report.requests.get('cache_hits', 0)}",
        report.disclaimer,
    ]
    return "\n".join(lines)


def create_server(*, demo: bool = False, analyzer=None, store=None) -> Server:
    server = Server("title-trend", version="0.2.0")
    worker = analyzer
    reports = store or ReportStore()

    @server.list_tools()
    async def list_tools():
        base = {
            "title": {"type": "string", "minLength": 2, "maxLength": 80},
            "market": {"type": "string", "enum": ["CN", "HK", "TW"], "default": "CN"},
        }
        selection_schema = Selection.model_json_schema()
        selection_defs = selection_schema.pop("$defs", {})
        advice_schema = Advice.model_json_schema()
        advice_defs = advice_schema.pop("$defs", {})
        advice_schema["properties"].pop("origin")
        annotations = types.ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, idempotentHint=False, openWorldHint=True
        )
        return [
            types.Tool(
                name="prepare_title",
                title="准备标题候选词",
                description="jieba分词仅供当前Agent理解主题和选择候选短语。无需模型API；不请求外部数据。下一步调用analyze_title。",
                inputSchema={
                    "type": "object",
                    "properties": base,
                    "required": ["title"],
                    "additionalProperties": False,
                },
                annotations=types.ToolAnnotations(readOnlyHint=True, openWorldHint=False),
            ),
            types.Tool(
                name="analyze_title",
                title="查询标题搜索趋势并评分",
                description="接受当前Agent选出的1–5个相关候选短语，直接查询DataForSEO Bing月度历史并由Python固定公式评分。先用prepare_title辅助选词，结果后用complete_report提交当前Agent生成的建议；不接受模型凭证、分数或权重。"
                + (" 当前为固定模拟模式。" if demo else ""),
                inputSchema={
                    "type": "object",
                    "properties": {**base, "selection": selection_schema},
                    "$defs": selection_defs,
                    "required": ["title", "selection"],
                    "additionalProperties": False,
                },
                annotations=annotations,
                _meta={"ui": {"resourceUri": UI_URI}},
            ),
            types.Tool(
                name="complete_report",
                title="完成标题趋势报告",
                description="将当前Agent根据已返回真实数据生成的分析、关键词建议和2–3个标题与服务器保存的评分合并，返回完整评分卡及文字。只接受report_id和建议，不接受替换数据、评分或权重，不再次请求DataForSEO。校验失败可以修正建议重试。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "report_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
                        "advice": advice_schema,
                    },
                    "$defs": advice_defs,
                    "required": ["report_id", "advice"],
                    "additionalProperties": False,
                },
                annotations=types.ToolAnnotations(
                    readOnlyHint=True, destructiveHint=False, openWorldHint=False
                ),
                _meta={"ui": {"resourceUri": UI_URI}},
            ),
        ]

    @server.list_resources()
    async def list_resources():
        return [
            types.Resource(
                uri=UI_URI,
                name="标题趋势评分卡",
                mimeType=UI_MIME,
                description="仅展示Server数据，不持有凭证或调用外部API",
            )
        ]

    @server.read_resource()
    async def read_resource(uri):
        if str(uri) != UI_URI:
            raise ValueError("Unknown resource")
        html = files("title_trend").joinpath("ui/report.html").read_text(encoding="utf-8")
        return [
            ReadResourceContents(
                html,
                UI_MIME,
                {
                    "ui": {
                        "csp": {"connectDomains": [], "resourceDomains": []},
                        "prefersBorder": True,
                    }
                },
            )
        ]

    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        nonlocal worker
        try:
            allowed = {
                "prepare_title": ({"title", "market"}, {"title"}),
                "analyze_title": ({"title", "market", "selection"}, {"title", "selection"}),
                "complete_report": ({"report_id", "advice"}, {"report_id", "advice"}),
            }
            if name not in allowed:
                raise SafeError("tool", "未知工具。")
            keys, required = allowed[name]
            if (
                not isinstance(arguments, dict)
                or set(arguments) - keys
                or not required <= set(arguments)
            ):
                raise SafeError(
                    "arguments",
                    "工具参数无效；请按工具schema传入原标题/候选词或报告ID/建议，不接受凭证、评分和权重。",
                )
            if name == "complete_report":
                report_id = arguments["report_id"]
                if (
                    not isinstance(report_id, str)
                    or len(report_id) != 32
                    or any(c not in "0123456789abcdef" for c in report_id)
                ):
                    raise SafeError("arguments", "report_id 格式无效。")
                if not isinstance(arguments["advice"], dict):
                    raise SafeError("arguments", "advice 必须是建议对象。")
                report = reports.complete(report_id, arguments["advice"])
            else:
                title, market = arguments["title"], arguments.get("market", "CN")
                validate_title(title)
                validate_market(market)
                worker = worker or Analyzer()
                if name == "prepare_title":
                    prepared = worker.prepare(title, market)
                    return types.CallToolResult(
                        content=[
                            types.TextContent(
                                type="text",
                                text="分词参考："
                                + "、".join(prepared["segmentation_candidates"])
                                + "\n"
                                + prepared["next_step"],
                            )
                        ],
                        structuredContent=prepared,
                    )
                if not isinstance(arguments["selection"], dict):
                    raise SafeError("arguments", "selection 必须是候选词对象。")
                if demo:
                    selection = worker.selection(title, arguments["selection"])
                    report = simulated_analysis(title, market, selection)
                else:
                    report, selection = await worker.analyze(title, arguments["selection"], market)
                report = reports.add(report, selection)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=text_report(report))],
                structuredContent=report.model_dump(mode="json"),
            )
        except SafeError as error:
            return types.CallToolResult(
                isError=True,
                content=[types.TextContent(type="text", text=error.message)],
                structuredContent={"error": {"code": error.code, "message": error.message}},
            )
        except Exception:
            # Never expose exception repr, raw HTTP body, request headers or traceback.
            return types.CallToolResult(
                isError=True,
                content=[
                    types.TextContent(
                        type="text", text="本地分析失败。请检查配置、词典及缓存目录权限。"
                    )
                ],
                structuredContent={"error": {"code": "internal", "message": "本地分析失败"}},
            )

    return server


async def run_stdio(demo: bool = False):
    # The SDK can log exceptions/requests at DEBUG. Suppress library handlers in production.
    logging.disable(logging.CRITICAL)
    server = create_server(demo=demo)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
