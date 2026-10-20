from datetime import datetime, timezone

import pytest

from title_trend.models import KeywordData, Month
from title_trend.scoring import window_months


@pytest.fixture
def series():
    def make(values=None, end="2026-08", **kwargs):
        return KeywordData(
            keyword="Python 自动化",
            status="ok",
            fetched_at=datetime(2026, 9, 28, tzinfo=timezone.utc),
            months=[
                Month(month=m, volume=v) for m, v in zip(window_months(end), values or [100] * 12)
            ],
            **kwargs,
        )

    return make


def envelope(result, status=20000, task_status=20000, cost=0):
    return {
        "status_code": status,
        "cost": cost,
        "tasks": [{"status_code": task_status, "result": result}],
    }


def history(keyword="Python 自动化", volumes=None, **overrides):
    values = [100] * 12 if volumes is None else volumes
    dates = window_months("2026-08")
    row = {
        "keyword": keyword,
        "location_code": 2156,
        "language_code": "zh-CN",
        "period": "monthly",
        "device": ["desktop", "mobile", "tablet", "non_smartphones"],
        "searches": {
            d: [
                {"year": int(m[:4]), "month": int(m[5:]), "day": 1, "search_volume": v}
                for m, v in zip(dates, values)
            ]
            for d in ("desktop", "mobile", "tablet", "non_smartphones")
        },
    }
    return {**row, **overrides}
