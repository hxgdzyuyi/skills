import json
import os
import sys
from datetime import date

import pytest
from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_agent_credentials import ADVICE, SELECTION, TITLE

from title_trend.config import Settings
from title_trend.errors import SafeError
from title_trend.server import UI_MIME, UI_URI, text_report
from title_trend.service import Analyzer, ReportStore, simulated_report

DEMO_SELECTION = {
    "topic": "Python自动化办公",
    "candidates": [
        {
            "keyword": "Python 自动化办公",
            "anchors": ["Python", "自动化"],
            "relevance": "原文工具与用途",
        },
        {"keyword": "Python 办公", "anchors": ["Python", "办公"], "relevance": "原词组合"},
        {"keyword": "自动化办公", "anchors": ["自动化"], "relevance": "原标题场景"},
    ],
}


async def test_host_agent_flow_with_validated_data(series, monkeypatch):
    class Provider:
        calls = 0

        async def query(self, keywords, market):
            self.calls += 1
            return (
                [series()],
                {"last_year_in_monthly_searches": 2026, "last_month_in_monthly_searches": 8},
                {"paid_requests": 1},
                None,
            )

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 28)

    monkeypatch.setattr("title_trend.service.date", FixedDate)
    provider = Provider()
    analyzer = Analyzer(Settings(), provider=provider)
    prepared = analyzer.prepare(TITLE)
    assert "Python" in prepared["segmentation_candidates"] and provider.calls == 0
    report, selection = await analyzer.analyze(TITLE, SELECTION)
    assert report.metrics.score is not None and report.advice is None
    store = ReportStore()
    report = store.add(report, selection)
    metrics = report.metrics.model_dump()
    report.metrics.score = 100
    complete = store.complete(report.report_id, ADVICE)
    assert complete.stage == "complete" and complete.advice.origin == "agent"
    assert complete.metrics.model_dump() == metrics and provider.calls == 1
    assert len(complete.advice.recommended_titles) == 2
    text = text_report(complete)
    for expected in (
        "Trend Potential Score",
        "Python",
        "次/月",
        "关键词建议",
        "推荐标题",
        "DataForSEO",
        "广告竞争",
    ):
        assert expected in text


async def test_bad_advice_can_retry_without_query(series):
    class Provider:
        calls = 0

        async def query(self, *args):
            self.calls += 1
            return [series()], {}, {}, None

    provider = Provider()
    report, selection = await Analyzer(Settings(), provider=provider).analyze(TITLE, SELECTION)
    store = ReportStore()
    report = store.add(report, selection)
    with pytest.raises(SafeError) as error:
        store.complete(report.report_id, {**ADVICE, "score": 100})
    assert error.value.code == "agent_advice"
    assert store.complete(report.report_id, ADVICE).keywords and provider.calls == 1


async def test_selection_failure_prevents_paid_query():
    class ForbiddenProvider:
        async def query(self, *args):
            raise AssertionError("Must not query")

    with pytest.raises(SafeError) as error:
        await Analyzer(Settings(), provider=ForbiddenProvider()).analyze(
            TITLE, {**SELECTION, "score": 99}
        )
    assert error.value.code == "agent_selection"


def test_report_expiry_and_capacity():
    from title_trend.agent import tokenizer, validate_selection

    selection = validate_selection(DEMO_SELECTION, TITLE, tokenizer(Settings()))
    clock = [0]
    store = ReportStore(ttl_seconds=10, capacity=1, clock=lambda: clock[0])
    first = store.add(simulated_report(), selection)
    second = store.add(simulated_report(), selection)
    with pytest.raises(SafeError):
        store.complete(first.report_id, ADVICE)
    clock[0] = 11
    with pytest.raises(SafeError) as error:
        store.complete(second.report_id, ADVICE)
    assert error.value.code == "report_expired"


async def test_stdio_agent_tools_and_ui_resource(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "title_trend.cli", "serve", "--demo"],
        env={
            **os.environ,
            "TITLE_TREND_CONFIG_DIR": str(tmp_path / "config"),
            "TITLE_TREND_CACHE_DIR": str(tmp_path / "cache"),
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name: t for t in (await session.list_tools()).tools}
            assert set(tools) == {"prepare_title", "analyze_title", "complete_report"}
            for name in ("analyze_title", "complete_report"):
                assert tools[name].meta["ui"]["resourceUri"] == UI_URI
                Draft202012Validator.check_schema(tools[name].inputSchema)
            prepared = await session.call_tool("prepare_title", {"title": TITLE})
            assert "Python" in prepared.structuredContent["segmentation_candidates"]
            args = {"title": TITLE, "selection": DEMO_SELECTION}
            Draft202012Validator(tools["analyze_title"].inputSchema).validate(args)
            result = await session.call_tool("analyze_title", args)
            assert result.structuredContent["simulated"] is True and not result.isError
            assert result.structuredContent["stage"] == "awaiting_advice"
            assert result.structuredContent["advice"] is None
            metrics = result.structuredContent["metrics"]
            report_id = result.structuredContent["report_id"]
            rejected = await session.call_tool(
                "complete_report", {"report_id": report_id, "advice": {**ADVICE, "score": 100}}
            )
            assert rejected.isError
            args = {"report_id": report_id, "advice": ADVICE}
            Draft202012Validator(tools["complete_report"].inputSchema).validate(args)
            complete = await session.call_tool("complete_report", args)
            assert not complete.isError
            assert complete.structuredContent["stage"] == "complete"
            assert complete.structuredContent["metrics"] == metrics
            assert complete.structuredContent["requests"]["paid_requests"] == 0
            assert (
                "推荐标题" in complete.content[0].text and "关键词建议" in complete.content[0].text
            )
            resource = await session.read_resource(UI_URI)
            assert resource.contents[0].mimeType == UI_MIME
            assert resource.contents[0].meta["ui"]["csp"]["connectDomains"] == []
            assert "APP_BUNDLE" not in resource.contents[0].text
            for tool_name, args in (
                (
                    "analyze_title",
                    {"title": TITLE, "selection": DEMO_SELECTION, "password": "secret"},
                ),
                (
                    "complete_report",
                    {"report_id": report_id, "advice": ADVICE, "metrics": {"score": 100}},
                ),
                ("prepare_title", {"title": TITLE, "market": {}}),
            ):
                invalid = await session.call_tool(tool_name, args)
                assert invalid.isError
            assert not (tmp_path / "cache").exists()


def test_simulation_explicitly_marked():
    report = simulated_report()
    assert report.simulated and "模拟" in text_report(report)
    assert report.requests["paid_requests"] == 0


def test_cli_no_model_configuration_requirement(monkeypatch, capsys):
    from title_trend.cli import main

    monkeypatch.setattr("sys.argv", ["title-trend", "analyze", TITLE])
    with pytest.raises(SystemExit):
        main()
    assert "--selection-file" in capsys.readouterr().err
    monkeypatch.setattr("sys.argv", ["title-trend", "prepare", TITLE])
    main()
    assert "Python" in json.loads(capsys.readouterr().out)["segmentation_candidates"]
