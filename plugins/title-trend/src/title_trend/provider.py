from __future__ import annotations

import asyncio
import math
import time
from datetime import date

import httpx
from filelock import FileLock

from .cache import Cache, request_identity, utcnow
from .config import Settings
from .credentials import get_secret
from .errors import SafeError
from .models import DEVICES, LIVE_PATH, KeywordData, Market, Month, normalize

ORIGIN = "https://api.dataforseo.com"
LOCATIONS_PATH = "/v3/keywords_data/bing/search_volume_history/locations_and_languages"
STATUS_PATH = "/v3/keywords_data/bing/status"


def cost_value(value) -> float | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    ):
        return float(value)
    return None


def results(body: dict) -> list:
    if not isinstance(body, dict) or body.get("status_code") != 20000:
        raise SafeError("api_status", "DataForSEO 请求未成功；请检查账户、配额与服务状态。")
    tasks = body.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 1 or not isinstance(tasks[0], dict):
        raise SafeError("api_structure", "DataForSEO 返回结构异常。")
    task = tasks[0]
    if task.get("status_code") != 20000:
        raise SafeError("api_task", "DataForSEO 任务失败；未将错误视为零搜索量。")
    value = task.get("result")
    if value is None:
        return []
    if not isinstance(value, list):
        raise SafeError("api_structure", "DataForSEO 结果结构异常。")
    return value


def normalize_result(keyword: str, row: dict | None, market: Market) -> KeywordData:
    now = utcnow()
    base = dict(keyword=keyword, market=market, fetched_at=now)
    if row is None or not row.get("searches"):
        return KeywordData(**base, status="no_data", reason="API 未返回搜索历史；不等于真实零值")
    if (
        row.get("location_code") != market.location_code
        or row.get("language_code") != market.language_code
        or row.get("period") != "monthly"
    ):
        return KeywordData(
            **base, status="request_failed", reason="返回市场、语言或粒度与请求不一致"
        )
    searches = row["searches"]
    if not isinstance(searches, dict):
        return KeywordData(**base, status="request_failed", reason="搜索历史结构异常")
    by_device = {}
    all_months = set()
    try:
        for device in DEVICES:
            observations = searches.get(device)
            if observations is None:
                observations = []
            if not isinstance(observations, list):
                raise ValueError()
            series = {}
            for item in observations:
                if not isinstance(item, dict):
                    raise ValueError()
                year, month, day = item.get("year"), item.get("month"), item.get("day")
                if any(type(v) is not int for v in (year, month, day)) or day != 1:
                    raise ValueError()
                date(year, month, day)
                label = f"{year:04d}-{month:02d}"
                if label in series:
                    raise ValueError()
                value = item.get("search_volume")
                if value is not None and (type(value) is not int or not 0 <= value <= 10**12):
                    raise ValueError()
                series[label] = value
                all_months.add(label)
            by_device[device] = series
    except (ValueError, TypeError, OverflowError):
        return KeywordData(**base, status="request_failed", reason="搜索量、日期或重复月份校验失败")
    normalized = []
    for month in sorted(all_months):
        values = [by_device[d].get(month) for d in DEVICES]
        total = sum(values) if all(v is not None for v in values) else None
        if total is not None and total > 10**12:
            return KeywordData(**base, status="request_failed", reason="搜索量超出校验上限")
        normalized.append(Month(month=month, volume=total))
    if not normalized or all(m.volume is None for m in normalized):
        return KeywordData(
            **base,
            status="no_data",
            months=normalized,
            reason="缺少完整设备范围的数据；未将缺失设备补为零",
        )
    zero = all(m.volume == 0 for m in normalized)
    return KeywordData(**base, status="zero" if zero else "ok", months=normalized)


class DataForSEO:
    def __init__(
        self,
        settings: Settings,
        cache: Cache,
        *,
        client: httpx.AsyncClient | None = None,
        namespace: str = "production",
    ):
        self.settings, self.cache = settings, cache
        if client is not None and namespace == "production":
            raise ValueError("Injected transports require an explicit test cache namespace")
        self.client = client
        self.namespace = namespace
        self.last_request = 0.0
        self.lock = asyncio.Lock()
        self.calls = {
            "paid_requests": 0,
            "metadata_requests": 0,
            "cost_usd": 0.0,
            "cost_unknown": False,
            "cache_hits": 0,
        }

    async def _request(self, path: str, payload=None) -> dict:
        # Vault deletion/replacement takes effect on the next operation.
        auth = httpx.BasicAuth(get_secret("dataforseo-login"), get_secret("dataforseo-password"))
        # GETs may retry. A POST timeout/read error could already have incurred a charge.
        attempts = 1 if payload is not None else self.settings.retry_count + 1
        for attempt in range(attempts):
            delay = self.settings.min_request_interval - (time.monotonic() - self.last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self.last_request = time.monotonic()
            owned = self.client is None
            client = self.client or httpx.AsyncClient(
                timeout=self.settings.timeout_seconds, follow_redirects=False, trust_env=False
            )
            try:
                if payload is None:
                    self.calls["metadata_requests"] += 1
                    response = await client.get(
                        ORIGIN + path, auth=auth, timeout=self.settings.timeout_seconds
                    )
                else:
                    self.calls["paid_requests"] += 1
                    response = await client.post(
                        ORIGIN + path,
                        json=payload,
                        auth=auth,
                        timeout=self.settings.timeout_seconds,
                    )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < attempts - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                if response.status_code != 200:
                    raise SafeError(
                        "api_http", "DataForSEO HTTP 请求失败。请检查凭证、余额或限流。"
                    )
                body = response.json()
                if not isinstance(body, dict):
                    raise ValueError()
                return body
            except httpx.TransportError:
                if attempt < attempts - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                raise SafeError(
                    "api_network", "DataForSEO 网络请求失败；付费请求未自动重发，请稍后重试。"
                ) from None
            except (ValueError, TypeError):
                raise SafeError("api_json", "DataForSEO 返回无效 JSON。") from None
            finally:
                if owned:
                    await client.aclose()
        raise SafeError("api_request", "DataForSEO 请求失败。")

    async def metadata(self) -> tuple[list, dict, object]:
        values = []
        fetched = None
        for path in (LOCATIONS_PATH, STATUS_PATH):
            key = self.namespace + path
            cached = self.cache.get_metadata(key)
            if cached:
                value, at = cached
            else:
                raw = results(await self._request(path))
                # Only validated fields are persisted: no provider text, credentials, task.data.
                if path == LOCATIONS_PATH:
                    value = [
                        {
                            "language_code": x.get("language_code"),
                            "locations": [
                                y.get("location_code")
                                for y in x.get("available_locations", [])
                                if isinstance(y, dict)
                            ],
                        }
                        for x in raw
                        if isinstance(x, dict) and isinstance(x.get("available_locations"), list)
                    ]
                else:
                    if not raw or not isinstance(raw[0], dict):
                        raise SafeError("api_status", "Bing 更新状态不可用。")
                    value = {
                        k: raw[0].get(k)
                        for k in (
                            "actual_data",
                            "date_update",
                            "last_year_in_monthly_searches",
                            "last_month_in_monthly_searches",
                        )
                    }
                    if value["date_update"] is not None:
                        try:
                            date.fromisoformat(value["date_update"])
                        except (ValueError, TypeError):
                            value["date_update"] = None
                at = self.cache.put_metadata(key, value, self.settings.metadata_ttl_seconds)
            values.append(value)
            if path == STATUS_PATH:
                fetched = at
        return values[0], values[1], fetched

    async def query(
        self, keywords: list[str], market: Market
    ) -> tuple[list[KeywordData], dict, dict, object]:
        async with self.lock:
            file_lock = FileLock(
                str(self.cache.path) + ".request.lock", timeout=180, thread_local=False
            )
            await asyncio.to_thread(file_lock.acquire)
            try:
                return await self._query_locked(keywords, market)
            finally:
                file_lock.release()

    async def _query_locked(self, keywords, market):
        self.calls = {
            "paid_requests": 0,
            "metadata_requests": 0,
            "cost_usd": 0.0,
            "cost_unknown": False,
            "cache_hits": 0,
        }
        identities = [
            request_identity(k, market, LIVE_PATH, self.settings.devices, self.namespace)
            for k in keywords
        ]
        cached = [self.cache.get(i) for i in identities]
        status, fetched = {}, None
        try:
            locations, status, fetched = await self.metadata()
            supported = any(
                x["language_code"] == market.language_code
                and market.location_code in x["locations"]
                for x in locations
            )
            if not supported:
                return (
                    [
                        KeywordData(
                            keyword=k,
                            status="unsupported",
                            market=market,
                            reason="最新官方支持列表未包含指定地区与语言组合",
                        )
                        for k in keywords
                    ],
                    status,
                    dict(self.calls),
                    fetched,
                )
            missing = [k for k, c in zip(keywords, cached) if c is None or c.status == "stale"]
            output = {normalize(c.keyword): c for c in cached if c and c.status != "stale"}
            self.calls["cache_hits"] = len(output)
            if missing:
                batch = {
                    "requests": sorted(
                        [identities[keywords.index(k)] for k in missing], key=lambda x: x["keyword"]
                    )
                }
                if not self.cache.reserve(batch, self.settings.paid_cooldown_seconds):
                    raise SafeError(
                        "paid_cooldown", "相同付费请求仍在冷却期，避免重复扣费；稍后重试。"
                    )
                cost = None
                try:
                    body = await self._request(
                        LIVE_PATH,
                        [
                            {
                                "keywords": missing,
                                "location_code": market.location_code,
                                "language_code": market.language_code,
                                "period": "monthly",
                                "device": sorted(self.settings.devices),
                            }
                        ],
                    )
                    cost = cost_value(body.get("cost"))
                    self.calls["cost_usd"] = cost or 0.0
                    self.calls["cost_unknown"] = cost is None
                    rows = results(body)
                    index = {}
                    for row in rows:
                        if not isinstance(row, dict) or not isinstance(row.get("keyword"), str):
                            raise SafeError("api_structure", "DataForSEO 关键词结果结构异常。")
                        key = normalize(row["keyword"])
                        if key in index:
                            raise SafeError("api_structure", "DataForSEO 返回重复关键词。")
                        index[key] = row
                    for keyword in missing:
                        record = normalize_result(keyword, index.get(normalize(keyword)), market)
                        self.cache.put(
                            identities[keywords.index(keyword)],
                            record,
                            self.settings.cache_ttl_seconds,
                        )
                        output[normalize(keyword)] = record
                    self.cache.finish(batch, cost, "received")
                except SafeError:
                    self.cache.finish(batch, cost, "failed_or_uncertain")
                    self.calls["cost_unknown"] = cost is None
                    raise
            return [output[normalize(k)] for k in keywords], status, dict(self.calls), fetched
        except SafeError as error:
            records = []
            for keyword, record in zip(keywords, cached):
                if record:
                    if record.status == "stale":
                        record.reason += "；刷新失败：" + error.message
                    records.append(record)
                else:
                    records.append(
                        KeywordData(
                            keyword=keyword,
                            status="request_failed",
                            market=market,
                            reason=error.message,
                        )
                    )
            return records, status, dict(self.calls), fetched
