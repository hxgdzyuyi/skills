import asyncio
import json
from datetime import timedelta

import httpx
import pytest
from conftest import envelope, history

from title_trend.cache import Cache, request_identity, utcnow
from title_trend.config import Settings
from title_trend.models import DEVICES, LIVE_PATH, MARKETS
from title_trend.provider import DataForSEO, normalize_result


def test_cache_identity_and_expiration(tmp_path, series):
    cache = Cache(tmp_path / "cache.db")
    identity = request_identity(" Python   自动化 ", MARKETS["CN"], LIVE_PATH, list(DEVICES))
    same = request_identity("python 自动化", MARKETS["CN"], LIVE_PATH, list(reversed(DEVICES)))
    record = series()
    record.fetched_at = utcnow()
    cache.put(identity, record, 100)
    assert cache.get(same).status == "ok"
    assert cache.get(same).cache_hit
    for key, value in [
        ("location_code", 2344),
        ("language_code", "en"),
        ("period", "daily"),
        ("devices", ["desktop"]),
        ("namespace", "test"),
        ("date_from", "2026-01-01"),
        ("endpoint", "/other"),
    ]:
        assert cache.get({**same, key: value}) is None
    expired = cache.get(identity, now=record.fetched_at + timedelta(seconds=100))
    assert expired.status == "stale" and expired.months == record.months
    record.status = "request_failed"
    cache.put({**identity, "keyword": "failed"}, record, 100)
    assert cache.get({**identity, "keyword": "failed"}) is None


def test_reservation_cooldown(tmp_path):
    cache = Cache(tmp_path / "cache.db")
    assert cache.reserve({"requests": [1]}, 300)
    assert not cache.reserve({"requests": [1]}, 300)
    cache.finish({"requests": [1]}, 0.075, "received")
    with cache.connect() as db:
        assert db.execute("SELECT cost_usd FROM request_ledger").fetchone()[0] == 0.075


def test_device_aggregation_and_real_zero():
    data = normalize_result("Python 自动化", history(), MARKETS["CN"])
    assert data.months[-1].volume == 400
    assert data.ad_competition is None
    zero = normalize_result("Python 自动化", history(volumes=[0] * 12), MARKETS["CN"])
    assert zero.status == "zero" and zero.months[-1].volume == 0
    row = history()
    del row["searches"]["tablet"][0]
    assert normalize_result("Python 自动化", row, MARKETS["CN"]).months[0].volume is None
    assert normalize_result("test", None, MARKETS["CN"]).status == "no_data"
    assert (
        normalize_result("test", history(location_code=2344), MARKETS["CN"]).status
        == "request_failed"
    )


@pytest.mark.parametrize("kind", ["negative", "duplicate", "float", "null", "date"])
def test_malformed_values(kind):
    row = history()
    point = row["searches"]["mobile"][0]
    if kind == "negative":
        point["search_volume"] = -1
    if kind == "duplicate":
        row["searches"]["mobile"].append(point)
    if kind == "float":
        point["search_volume"] = 1.2
    if kind == "null":
        point["search_volume"] = None
    if kind == "date":
        point["day"] = 20
    data = normalize_result("test", row, MARKETS["CN"])
    if kind == "null":
        assert data.months[0].volume is None
    else:
        assert data.status == "request_failed"


def provider(tmp_path, monkeypatch, post_handler, supported=True):
    monkeypatch.setattr("title_trend.provider.get_secret", lambda slot: "test-secret")
    calls = []

    def handle(request):
        calls.append(request)
        if request.url.path.endswith("locations_and_languages"):
            return httpx.Response(
                200,
                json=envelope(
                    [
                        {
                            "language_code": "zh-CN",
                            "available_locations": [{"location_code": 2156 if supported else 2840}],
                        }
                    ]
                ),
            )
        if request.url.path.endswith("status"):
            return httpx.Response(
                200,
                json=envelope(
                    [
                        {
                            "actual_data": True,
                            "date_update": "2026-09-03",
                            "last_year_in_monthly_searches": 2026,
                            "last_month_in_monthly_searches": 8,
                        }
                    ]
                ),
            )
        return post_handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    cache = Cache(tmp_path / "cache.db")
    settings = Settings(min_request_interval=0.1)
    return DataForSEO(settings, cache, client=client, namespace="test"), calls


async def test_bounded_query_cache_and_cost(tmp_path, monkeypatch):
    p, calls = provider(
        tmp_path, monkeypatch, lambda r: httpx.Response(200, json=envelope([history()], cost=0.075))
    )
    first, status, counts, _ = await p.query(["Python 自动化"], MARKETS["CN"])
    assert first[0].status == "ok" and status["actual_data"]
    assert counts["paid_requests"] == 1 and counts["cost_usd"] == 0.075
    second, _, counts, _ = await p.query(["Python 自动化"], MARKETS["CN"])
    assert second[0].cache_hit and counts["paid_requests"] == 0 and counts["cache_hits"] == 1
    assert len(calls) == 3
    assert json.loads(calls[-1].content)[0]["period"] == "monthly"
    assert not json.loads(calls[-1].content)[0].get("date_from")
    await p.client.aclose()


@pytest.mark.parametrize("kind", ["timeout", "http", "task", "json"])
async def test_api_errors_never_zero_or_repeated_paid(tmp_path, monkeypatch, kind):
    def post(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("SECRET traceback", request=request)
        if kind == "http":
            return httpx.Response(503, text="SECRET upstream body")
        if kind == "task":
            return httpx.Response(200, json=envelope(None, task_status=40501, cost=0.075))
        return httpx.Response(200, text="SECRET invalid json")

    p, calls = provider(tmp_path, monkeypatch, post)
    data, _, counts, _ = await p.query(["Python 自动化"], MARKETS["CN"])
    assert data[0].status == "request_failed"
    assert "SECRET" not in data[0].model_dump_json()
    assert counts["paid_requests"] == 1
    assert not p.cache.get(
        request_identity("Python 自动化", MARKETS["CN"], LIVE_PATH, p.settings.devices, "test")
    )
    await p.query(["Python 自动化"], MARKETS["CN"])
    assert len([r for r in calls if r.method == "POST"]) == 1
    if kind == "task":
        assert counts["cost_usd"] == 0.075
    await p.client.aclose()


async def test_unsupported_never_paid(tmp_path, monkeypatch):
    p, calls = provider(
        tmp_path, monkeypatch, lambda r: pytest.fail("Must not POST"), supported=False
    )
    data, _, _, _ = await p.query(["test"], MARKETS["CN"])
    assert data[0].status == "unsupported" and all(r.method == "GET" for r in calls)
    await p.client.aclose()


async def test_stale_kept_when_refresh_fails(tmp_path, monkeypatch, series):
    p, _ = provider(tmp_path, monkeypatch, lambda r: httpx.Response(503))
    record = series()
    record.fetched_at = utcnow() - timedelta(days=2)
    p.cache.put(
        request_identity("Python 自动化", MARKETS["CN"], LIVE_PATH, p.settings.devices, "test"),
        record,
        60,
    )
    data, _, _, _ = await p.query(["Python 自动化"], MARKETS["CN"])
    assert data[0].status == "stale" and data[0].months
    assert "刷新失败" in data[0].reason
    await p.client.aclose()


async def test_concurrent_instances_share_cache_without_duplicate_paid_request(
    tmp_path, monkeypatch
):
    p, calls = provider(
        tmp_path, monkeypatch, lambda r: httpx.Response(200, json=envelope([history()], cost=0.075))
    )
    other = DataForSEO(p.settings, Cache(p.cache.path), client=p.client, namespace="test")
    reports = await asyncio.gather(
        p.query(["Python 自动化"], MARKETS["CN"]), other.query(["Python 自动化"], MARKETS["CN"])
    )
    assert all(r[0][0].status == "ok" for r in reports)
    assert len([r for r in calls if r.method == "POST"]) == 1
    await p.client.aclose()


async def test_free_metadata_retries_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr("title_trend.provider.get_secret", lambda slot: "test-only")
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    p = DataForSEO(
        Settings(retry_count=1, min_request_interval=0.1),
        Cache(tmp_path / "c.db"),
        client=client,
        namespace="test",
    )
    data, _, counts, _ = await p.query(["Python 自动化"], MARKETS["CN"])
    assert data[0].status == "request_failed"
    assert counts["metadata_requests"] == 2 and counts["paid_requests"] == 0
    assert len(calls) == 2
    await client.aclose()
