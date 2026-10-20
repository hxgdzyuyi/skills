from __future__ import annotations

import calendar
import math
from datetime import date
from statistics import fmean

from .models import KeywordData, Metrics

VOLUME_CAP = 100_000
LOW_BASE = 100


def shift_month(month: str, offset: int) -> str:
    year, number = map(int, month.split("-"))
    total = year * 12 + number - 1 + offset
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def month_end(month: str) -> str:
    year, number = map(int, month.split("-"))
    return f"{month}-{calendar.monthrange(year, number)[1]:02d}"


def window_months(end: str) -> list[str]:
    return [shift_month(end, i) for i in range(-11, 1)]


def choose_end(status: dict, today: date) -> str:
    year = status.get("last_year_in_monthly_searches")
    month = status.get("last_month_in_monthly_searches")
    if (
        type(year) is not int
        or type(month) is not int
        or not 2000 <= year <= 2100
        or not 1 <= month <= 12
    ):
        raise ValueError("Invalid source status month")
    current = today.strftime("%Y-%m")
    reported = f"{year:04d}-{month:02d}"
    # No current or future months. Status is a source-wide anchor, never per-keyword cherry picking.
    return min(reported, shift_month(current, -1))


def score_keyword(data: KeywordData, end: str | None, today: date) -> Metrics:
    if not end:
        return Metrics(reason="更新状态不可用，无法确定共同统计窗口")
    if end >= today.strftime("%Y-%m"):
        return Metrics(reason="统计窗口包含未完成月份")
    months = {m.month: m.volume for m in data.months}
    if len(months) != len(data.months):
        return Metrics(reason="标准化数据存在重复月份")
    required = window_months(end)

    def known_mean(labels):
        return (
            fmean(months[m] for m in labels)
            if all(months.get(m) is not None for m in labels)
            else None
        )

    recent, previous = known_mean(required[-3:]), known_mean(required[-6:-3])
    available = {
        "recent_monthly_volume": recent,
        "previous_monthly_volume": previous,
        "growth_pct": 100 * (recent - previous) / previous
        if recent is not None and previous is not None and previous > 0
        else None,
    }
    if data.status not in {"ok", "zero"}:
        return Metrics(**available, reason=data.reason or data.status)
    if end < shift_month(today.strftime("%Y-%m"), -2):
        return Metrics(**available, reason="来源统计月份落后超过两个月，暂不评分")
    if any(months.get(m) is None for m in required):
        return Metrics(**available, reason="共同窗口需连续12个完整月及四类设备数据；存在缺失")
    values = [months[m] for m in required]
    recent = fmean(values[-3:])
    previous = fmean(values[-6:-3])
    if not any(values):
        return Metrics(
            score=0,
            demand=0,
            trend=0,
            growth=0,
            recent_monthly_volume=0,
            previous_monthly_volume=0,
            growth_pct=None,
        )
    demand = 100 * math.log1p(min(recent, VOLUME_CAP)) / math.log1p(VOLUME_CAP)
    # Position relative to this keyword's twelve monthly observations; ties use midrank.
    trend = 100 * (sum(v < recent for v in values) + 0.5 * sum(v == recent for v in values)) / 12
    if recent == 0:
        trend = 0
    delta = (recent - previous) / max(previous, LOW_BASE)
    # Delta in [-1, 1] maps to [0, 100]. Suppress neutral/positive growth for low demand.
    growth = 50 * (1 + max(-1, min(1, delta))) * min(1, recent / LOW_BASE)
    score = 0.4 * demand + 0.3 * trend + 0.3 * growth
    pct = 100 * (recent - previous) / previous if previous > 0 else None
    return Metrics(
        score=score,
        demand=demand,
        trend=trend,
        growth=growth,
        recent_monthly_volume=recent,
        previous_monthly_volume=previous,
        growth_pct=pct,
    )


def aggregate(metrics: list[Metrics]) -> Metrics:
    valid = [m for m in metrics if m.score is not None]
    # Every selected keyword is required. Missing words are not discarded to inflate a score.
    if not metrics or len(valid) != len(metrics):
        return Metrics(reason="数据不足，暂不评分：所有候选关键词均须满足共同12月窗口")
    result = Metrics(
        **{
            name: fmean(getattr(m, name) for m in valid)
            for name in ("score", "demand", "trend", "growth")
        }
    )
    return result


def display_metrics(metrics: Metrics) -> Metrics:
    # Never round components before computing an aggregate.
    return Metrics(
        **{k: round(v, 2) if isinstance(v, float) else v for k, v in metrics.model_dump().items()}
    )
