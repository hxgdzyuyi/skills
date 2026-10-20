from __future__ import annotations

import asyncio
import re
import secrets
import time
from collections import OrderedDict
from datetime import date

from pydantic import ValidationError

from .agent import (
    Candidate,
    Selection,
    candidate_tokens,
    tokenizer,
    validate_advice,
    validate_selection,
)
from .cache import Cache, utcnow
from .config import Settings, cache_dir, load_settings
from .errors import SafeError
from .models import MARKETS, Advice, KeywordReport, RecommendedTitle, Report, normalize
from .provider import DataForSEO
from .scoring import aggregate, choose_end, display_metrics, score_keyword, shift_month


def validate_title(title: str):
    if not isinstance(title, str) or not 2 <= len(title.strip()) <= 80:
        raise SafeError("title", "标题须为2–80个字符。")
    if re.search(r"[\x00-\x1f\x7f]", title) or not re.search(r"[\w\u4e00-\u9fff]", title):
        raise SafeError("title", "标题不能包含控制字符或仅含标点。")


def validate_market(market: str):
    if not isinstance(market, str) or market not in MARKETS:
        raise SafeError(
            "market", "仅支持明确选择的 CN、HK、TW Bing 简体中文市场；不会自动切换来源。"
        )


class ReportStore:
    """Bounded process-local facts. The agent submits prose, never replacement metrics."""

    def __init__(self, *, ttl_seconds=1800, capacity=128, clock=time.monotonic):
        self.ttl_seconds, self.capacity, self.clock = ttl_seconds, capacity, clock
        self.entries = OrderedDict()

    def add(self, report: Report, selection: Selection) -> Report:
        now = self.clock()
        self.entries = OrderedDict(
            (key, entry) for key, entry in self.entries.items() if entry[0] > now
        )
        while len(self.entries) >= self.capacity:
            self.entries.popitem(last=False)
        report = report.model_copy(deep=True)
        report.report_id = secrets.token_hex(16)
        self.entries[report.report_id] = (
            now + self.ttl_seconds,
            report,
            selection.model_copy(deep=True),
        )
        return report.model_copy(deep=True)

    def complete(self, report_id: str, raw: dict) -> Report:
        entry = self.entries.get(report_id)
        if entry is None or entry[0] <= self.clock():
            self.entries.pop(report_id, None)
            raise SafeError(
                "report_expired",
                "报告不存在或已过期（30分钟/服务重启）。请重新查询；有效关键词缓存可复用。",
            )
        expires, stored, selection = entry
        try:
            advice = validate_advice(raw, stored.title, selection)
        except (ValidationError, ValueError, TypeError, AttributeError):
            raise SafeError(
                "agent_advice",
                "Agent 建议未通过主题/事实/结构校验。请保留原标题词与事实，移除评分、数字断言和新实体后重试；已有数据保留，无需再次查询。",
            ) from None
        report = stored.model_copy(deep=True)
        report.advice = advice
        report.stage = "complete"
        self.entries[report_id] = (expires, report, selection)
        return report.model_copy(deep=True)


class Analyzer:
    def __init__(self, settings: Settings | None = None, *, provider=None):
        self.settings = settings or load_settings()
        self._provider = provider
        self.lock = asyncio.Lock()

    @property
    def provider(self):
        if self._provider is None:
            self._provider = DataForSEO(self.settings, Cache(cache_dir() / "data.sqlite3"))
        return self._provider

    def prepare(self, title: str, market: str = "CN") -> dict:
        validate_title(title)
        validate_market(market)
        return {
            "title": title.strip(),
            "market": MARKETS[market].model_dump(),
            "segmentation_candidates": candidate_tokens(title, tokenizer(self.settings)),
            "selection_schema": Selection.model_json_schema(),
            "next_step": "由当前 Agent 理解主题并选择1–5个候选搜索短语，再调用 analyze_title(title, selection, market)。分词仅辅助，尚未查询搜索数据。不得传评分或凭证。",
        }

    def selection(self, title: str, raw: dict) -> Selection:
        try:
            return validate_selection(raw, title, tokenizer(self.settings))
        except (ValidationError, ValueError, TypeError, AttributeError):
            raise SafeError(
                "agent_selection",
                "候选关键词未通过主题锚点/结构校验；未发起付费查询。请选择1–5个唯一短语，保留原标题词、实体与缩写，不加入无关热词或评分字段。",
            ) from None

    async def analyze(
        self, title: str, selection: dict, market: str = "CN"
    ) -> tuple[Report, Selection]:
        validate_title(title)
        validate_market(market)
        selected = self.selection(title, selection)
        async with self.lock:
            report = await self._analyze(title.strip(), selected, market)
            return report, selected

    async def _analyze(self, title: str, selection: Selection, market: str) -> Report:
        selected_market = MARKETS[market]
        today = date.today()
        warnings = []
        keywords = [c.keyword for c in selection.candidates]
        data, status, requests, status_fetched = await self.provider.query(
            keywords, selected_market
        )
        if len(data) != len(keywords) or any(
            normalize(d.keyword) != normalize(k) for d, k in zip(data, keywords)
        ):
            raise SafeError("api_alignment", "返回的关键词集合与请求不一致，停止评分。")
        try:
            end = choose_end(status, today)
        except ValueError:
            end = None
            warnings.append("无法确定来源最新完整统计月，暂不评分")
        metrics = [score_keyword(d, end, today) for d in data]
        total = aggregate(metrics)
        reports = [
            KeywordReport(data=d, metrics=display_metrics(m), relevance=c.relevance)
            for d, m, c in zip(data, metrics, selection.candidates)
        ]
        if total.score is None:
            warnings.append(total.reason)
        if any(d.status == "stale" for d in data):
            warnings.append("过期缓存只供查看，不参与评分")
        return Report(
            title=title,
            market=selected_market,
            generated_at=utcnow(),
            window_start=shift_month(end, -11) if end else None,
            window_end=end,
            data_updated_at=status.get("date_update"),
            status_fetched_at=status_fetched,
            metrics=display_metrics(total),
            keywords=reports,
            coverage={
                "selected": len(keywords),
                "returned": sum(bool(d.months) for d in data),
                "scorable": sum(m.score is not None for m in metrics),
                "policy": "all-selected-keywords-12-complete-months",
            },
            warnings=warnings,
            requests=requests,
        )


DEMO_TITLE = "用 Python 自动化办公，如何减少重复工作？"


def simulated_report(title: str = DEMO_TITLE, market: str = "CN") -> Report:
    from .models import KeywordData, Month
    from .scoring import window_months

    validate_title(title)
    if title != DEMO_TITLE:
        raise SafeError("demo_title", "模拟模式仅提供固定样例：" + DEMO_TITLE)
    if market not in MARKETS:
        raise SafeError("market", "不支持的模拟市场。")
    selected_market = MARKETS[market]
    today = date.today()
    end = shift_month(today.strftime("%Y-%m"), -1)
    selection = Selection(
        topic="Python自动化办公",
        candidates=[
            Candidate(
                keyword="Python 自动化办公",
                anchors=["Python", "自动化"],
                relevance="保留原标题工具与用途",
            ),
            Candidate(
                keyword="Python 办公", anchors=["Python", "办公"], relevance="检验更短的主题表达"
            ),
            Candidate(keyword="自动化办公", anchors=["自动化"], relevance="原标题核心场景"),
        ],
    )
    templates = [
        [140, 160, 190, 180, 210, 240, 270, 300, 310, 350, 420, 460],
        [250, 230, 270, 300, 290, 310, 330, 360, 350, 390, 410, 430],
        [180, 190, 220, 210, 230, 240, 250, 240, 260, 270, 290, 320],
    ]
    records = [
        KeywordData(
            keyword=c.keyword,
            status="ok",
            market=selected_market,
            source="模拟 DataForSEO（无真实 API 请求）",
            fetched_at=utcnow(),
            months=[Month(month=m, volume=v) for m, v in zip(window_months(end), vs)],
        )
        for c, vs in zip(selection.candidates, templates)
    ]
    metrics = [score_keyword(d, end, today) for d in records]
    return Report(
        title=title,
        market=selected_market,
        generated_at=utcnow(),
        simulated=True,
        stage="complete",
        window_start=shift_month(end, -11),
        window_end=end,
        metrics=display_metrics(aggregate(metrics)),
        keywords=[
            KeywordReport(data=d, metrics=display_metrics(m), relevance=c.relevance)
            for d, m, c in zip(records, metrics, selection.candidates)
        ],
        coverage={"selected": 3, "returned": 3, "scorable": 3},
        advice=Advice(
            analysis="模拟样本中，三个关键词近期搜索水平高于其历史基线。编辑判断：突出工具和具体用途，便于读者识别主题。",
            keyword_suggestions=[
                "保留 Python 与自动化办公，避免堆叠泛化热词。",
                "将减少重复工作的诉求放在标题后半句。",
            ],
            recommended_titles=[
                RecommendedTitle(
                    title="Python 自动化办公：如何减少重复工作？",
                    direction="先呈现工具与场景，再说明读者诉求",
                ),
                RecommendedTitle(
                    title="减少重复工作，如何用 Python 自动化办公？",
                    direction="将问题前置，保留原标题事实",
                ),
            ],
            origin="simulation",
        ),
        warnings=["模拟数据，仅验证本地流程与UI，不代表真实API覆盖或公众号表现"],
        requests={"paid_requests": 0, "metadata_requests": 0, "cost_usd": 0, "cache_hits": 0},
    )


def simulated_analysis(title: str, market: str, selection: Selection) -> Report:
    report = simulated_report(title, market)
    available = {normalize(row.data.keyword): row for row in report.keywords}
    if any(normalize(c.keyword) not in available for c in selection.candidates):
        raise SafeError(
            "demo_selection",
            "固定模拟样例仅提供 Python 自动化办公、Python 办公、自动化办公；不能模拟其他词的覆盖。",
        )
    report.keywords = [available[normalize(c.keyword)] for c in selection.candidates]
    metrics = [score_keyword(row.data, report.window_end, date.today()) for row in report.keywords]
    report.metrics = display_metrics(aggregate(metrics))
    for row, candidate in zip(report.keywords, selection.candidates):
        row.relevance = candidate.relevance
    report.coverage = {
        "selected": len(report.keywords),
        "returned": len(report.keywords),
        "scorable": len(report.keywords),
    }
    report.advice = None
    report.stage = "awaiting_advice"
    return report
