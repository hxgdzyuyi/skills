from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FORMULA_VERSION = "bing-monthly-v1.0.0"
DEVICES = ("desktop", "mobile", "non_smartphones", "tablet")
LIVE_PATH = "/v3/keywords_data/bing/search_volume_history/live"


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().lower()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Market(StrictModel):
    id: str = "CN"
    name: str = "中国大陆"
    location_code: int = 2156
    language_code: str = "zh-CN"
    engine: Literal["Bing"] = "Bing"


MARKETS = {
    "CN": Market(),
    "HK": Market(id="HK", name="中国香港", location_code=2344),
    "TW": Market(id="TW", name="中国台湾", location_code=2158),
}


class Month(StrictModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    volume: int | None = Field(default=None, ge=0, le=10**12, strict=True)


class KeywordData(StrictModel):
    keyword: str
    status: Literal["ok", "zero", "no_data", "unsupported", "request_failed", "stale"]
    reason: str | None = None
    months: list[Month] = Field(default_factory=list)
    fetched_at: datetime | None = None
    expires_at: datetime | None = None
    source: str = "DataForSEO"
    endpoint: str = LIVE_PATH
    market: Market = Field(default_factory=Market)
    period: Literal["monthly"] = "monthly"
    devices: list[str] = Field(default_factory=lambda: list(DEVICES))
    cache_hit: bool = False
    ad_competition: float | None = None  # History v1 does not supply it.


class Metrics(StrictModel):
    score: float | None = None
    demand: float | None = None
    trend: float | None = None
    growth: float | None = None
    recent_monthly_volume: float | None = None
    previous_monthly_volume: float | None = None
    growth_pct: float | None = None
    reason: str | None = None


class KeywordReport(StrictModel):
    data: KeywordData
    metrics: Metrics
    relevance: str


class RecommendedTitle(StrictModel):
    title: str = Field(min_length=2, max_length=100)
    direction: str = Field(min_length=2, max_length=120)


class Advice(StrictModel):
    analysis: str = Field(min_length=2, max_length=700)
    keyword_suggestions: list[str] = Field(min_length=1, max_length=5)
    recommended_titles: list[RecommendedTitle] = Field(min_length=2, max_length=3)
    origin: Literal["agent", "simulation"] = "agent"


class Report(StrictModel):
    schema_version: str = "2.0"
    report_id: str | None = None
    stage: Literal["awaiting_advice", "complete"] = "awaiting_advice"
    formula_version: str = FORMULA_VERSION
    title: str
    market: Market
    simulated: bool = False
    generated_at: datetime
    period: str = "monthly"
    window_start: str | None = None
    window_end: str | None = None
    data_updated_at: str | None = None
    status_fetched_at: datetime | None = None
    metrics: Metrics = Field(default_factory=Metrics)
    keywords: list[KeywordReport] = Field(default_factory=list)
    coverage: dict = Field(default_factory=dict)
    advice: Advice | None = None
    warnings: list[str] = Field(default_factory=list)
    requests: dict = Field(default_factory=dict)
    disclaimer: str = "评分仅参考外部搜索需求与趋势，不代表微信公众号热度、点击率或爆款概率。月度数据并非实时热度。"
