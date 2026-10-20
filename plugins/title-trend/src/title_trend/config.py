from __future__ import annotations

import json
import os
from pathlib import Path

from platformdirs import user_cache_path, user_config_path
from pydantic import Field, ValidationError, field_validator

from .errors import SafeError
from .models import DEVICES, StrictModel


class Settings(StrictModel):
    timeout_seconds: float = Field(default=45, ge=1, le=120)
    cache_ttl_seconds: int = Field(default=86400, ge=60, le=604800)
    metadata_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    min_request_interval: float = Field(default=1, ge=0.1, le=60)
    retry_count: int = Field(default=2, ge=0, le=2)
    paid_cooldown_seconds: int = Field(default=300, ge=60, le=3600)
    user_dictionary: str | None = None
    devices: list[str] = Field(default_factory=lambda: list(DEVICES))

    @field_validator("devices")
    @classmethod
    def all_devices(cls, value):
        if sorted(value) != sorted(DEVICES):
            raise ValueError("v1 fixes all four devices; changing scope requires a formula version")
        return sorted(value)


def config_dir() -> Path:
    # An isolated directory is useful for tests and distinct profiles. No secrets in this directory.
    return Path(os.environ.get("TITLE_TREND_CONFIG_DIR", user_config_path("title-trend")))


def cache_dir() -> Path:
    return Path(os.environ.get("TITLE_TREND_CACHE_DIR", user_cache_path("title-trend")))


def load_settings() -> Settings:
    path = config_dir() / "config.json"
    try:
        if not path.exists():
            return Settings()
        data = json.loads(path.read_text())
        # v0.1 stored non-sensitive model connection settings. Ignore only these exact
        # legacy keys during migration; never accept credential values in the file.
        for legacy in ("model_endpoint", "model_name", "model_auth_header", "model_auth_prefix"):
            data.pop(legacy, None)
        return Settings.model_validate(data)
    except (OSError, ValueError, TypeError, AttributeError, ValidationError):
        raise SafeError(
            "configuration", "配置文件无效。请运行 title-trend configure 修复非敏感设置。"
        ) from None


def save_settings(settings: Settings) -> None:
    root = config_dir()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / "config.json"
    temp = root / "config.json.tmp"
    temp.write_text(json.dumps(settings.model_dump(), ensure_ascii=False, indent=2))
    temp.chmod(0o600)
    temp.replace(path)
