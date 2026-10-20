import math
from datetime import date

import pytest

from title_trend.models import Metrics, Month
from title_trend.scoring import aggregate, choose_end, score_keyword, shift_month

TODAY = date(2026, 9, 28)


def test_fixed_formula_constant_baseline(series):
    m = score_keyword(series(), "2026-08", TODAY)
    demand = 100 * math.log(101) / math.log(100001)
    assert m.demand == pytest.approx(demand)
    assert m.trend == 50
    assert m.growth == 50
    assert m.growth_pct == 0
    assert m.score == pytest.approx(0.4 * demand + 30)


def test_zero_is_scorable_not_missing(series):
    zero = score_keyword(series([0] * 12), "2026-08", TODAY)
    assert (zero.score, zero.demand, zero.trend, zero.growth) == (0, 0, 0, 0)
    assert zero.growth_pct is None
    missing = score_keyword(series([None] * 12), "2026-08", TODAY)
    assert missing.score is None
    assert "缺失" in missing.reason


def test_zero_base_and_low_base_are_suppressed(series):
    m = score_keyword(series([0] * 9 + [10] * 3), "2026-08", TODAY)
    assert m.growth_pct is None
    assert m.growth == pytest.approx(5.5)
    assert m.trend == 87.5
    high = score_keyword(series([0] * 9 + [100] * 3), "2026-08", TODAY)
    assert high.growth == 100


def test_negative_growth_and_upper_cap(series):
    m = score_keyword(series([1000] * 9 + [0] * 3), "2026-08", TODAY)
    assert (m.score, m.growth, m.trend, m.growth_pct) == (0, 0, 0, -100)
    large = score_keyword(series([0] * 9 + [10**12] * 3), "2026-08", TODAY)
    assert large.demand == 100
    assert 0 <= large.score <= 100


@pytest.mark.parametrize("index", [0, 5, 8, 11])
def test_missing_months_never_imputed(series, index):
    row = series()
    del row.months[index]
    assert score_keyword(row, "2026-08", TODAY).score is None


def test_current_month_ignored_and_common_window(series):
    row = series()
    original = score_keyword(row, "2026-08", TODAY)
    row.months.append(Month(month="2026-09", volume=10**12))
    assert score_keyword(row, "2026-08", TODAY) == original
    assert score_keyword(row, "2026-09", TODAY).score is None
    assert score_keyword(series(end="2026-06"), "2026-06", TODAY).score is None
    assert score_keyword(series(end="2026-07"), "2026-07", TODAY).score is not None
    row.months.pop(11)  # No shifting to a keyword's own older end date.
    assert score_keyword(row, "2026-08", TODAY).score is None


def test_status_anchor_and_calendar():
    assert (
        choose_end(
            {"last_year_in_monthly_searches": 2026, "last_month_in_monthly_searches": 9}, TODAY
        )
        == "2026-08"
    )
    assert shift_month("2026-01", -1) == "2025-12"
    with pytest.raises(ValueError):
        choose_end({}, TODAY)


def test_aggregation_requires_every_selected_keyword(series):
    m = score_keyword(series(), "2026-08", TODAY)
    assert aggregate([m, m]).score == m.score
    assert aggregate([m, Metrics()]).score is None
    assert aggregate([]).score is None
    second = score_keyword(series([200] * 12), "2026-08", TODAY)
    assert aggregate([m, second]).score == pytest.approx((m.score + second.score) / 2)
    assert score_keyword(series(), "2026-08", TODAY) == m  # No collection-dependent normalization.


def test_incomplete_history_retains_available_volume(series):
    row = series()
    del row.months[0]
    m = score_keyword(row, "2026-08", TODAY)
    assert m.score is None and m.demand is None
    assert m.recent_monthly_volume == 100 and m.previous_monthly_volume == 100
    assert m.growth_pct == 0
    row.status = "stale"
    assert score_keyword(row, "2026-08", TODAY).score is None
