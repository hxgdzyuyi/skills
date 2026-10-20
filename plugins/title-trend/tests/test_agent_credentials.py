import json

import pytest
from pydantic import ValidationError

from title_trend import credentials
from title_trend.agent import (
    candidate_tokens,
    tokenizer,
    validate_advice,
    validate_selection,
)
from title_trend.config import Settings
from title_trend.errors import SafeError

TITLE = "用 Python 自动化办公，如何减少重复工作？"
SELECTION = {
    "topic": "Python自动化办公",
    "candidates": [
        {"keyword": "Python 自动化", "anchors": ["Python", "自动化"], "relevance": "原文工具与用途"}
    ],
}
ADVICE = {
    "analysis": "编辑判断：保留原文工具与场景，便于读者理解。",
    "keyword_suggestions": ["保留自动化办公主题"],
    "recommended_titles": [
        {"title": "Python 自动化办公：如何减少重复工作？", "direction": "明确工具用途"},
        {"title": "减少重复工作，如何用 Python 自动化办公？", "direction": "问题前置"},
    ],
}


def test_jieba_and_custom_dictionary(tmp_path):
    dictionary = tmp_path / "dict.txt"
    dictionary.write_text("量子计算平台 10000 nz\n", encoding="utf-8")
    cutter = tokenizer(Settings(user_dictionary=str(dictionary)))
    tokens = candidate_tokens("量子计算平台与 OpenAI、AI、GPT-4 的应用", cutter)
    assert "量子计算平台" in tokens and "GPT-4" in tokens and "OpenAI" in tokens and "AI" in tokens
    assert validate_selection(SELECTION, TITLE, cutter).candidates[0].keyword == "Python 自动化"


@pytest.mark.parametrize(
    "alteration", ["extra_score", "six", "duplicate", "hotword", "anchor", "no_anchor"]
)
def test_selection_rejects_unvalidated_model_output(alteration):
    raw = json.loads(json.dumps(SELECTION))
    if alteration == "extra_score":
        raw["score"] = 99
    if alteration == "six":
        raw["candidates"] *= 6
    if alteration == "duplicate":
        raw["candidates"] *= 2
    if alteration == "hotword":
        raw["candidates"][0]["keyword"] = "Python 股票"
        raw["candidates"][0]["anchors"] = ["Python"]
    if alteration == "anchor":
        raw["candidates"][0]["anchors"] = ["新闻"]
    if alteration == "no_anchor":
        raw["candidates"][0]["anchors"] = []
    with pytest.raises((ValidationError, ValueError)):
        validate_selection(raw, TITLE, tokenizer(Settings()))


@pytest.mark.parametrize(
    "kind", ["score", "numeric", "promise", "entity", "chinese_entity", "off_topic", "secret"]
)
def test_advice_validation(kind):
    raw = json.loads(json.dumps(ADVICE))
    if kind == "score":
        raw["recommended_titles"][0]["score"] = 99
    if kind == "numeric":
        raw["analysis"] = "搜索量达到99999"
    if kind == "promise":
        raw["recommended_titles"][0]["title"] = "Python 保证收益翻倍"
    if kind == "entity":
        raw["recommended_titles"][0]["title"] = "Python 与 NASA 官宣"
    if kind == "chinese_entity":
        raw["recommended_titles"][0]["title"] = "Python 获马云强烈推荐"
    if kind == "off_topic":
        raw["recommended_titles"][0]["title"] = "股票投资机会"
    if kind == "secret":
        raw["analysis"] = "sensitive-model-key"
    with pytest.raises((ValidationError, ValueError)):
        validate_advice(
            raw,
            TITLE,
            validate_selection(SELECTION, TITLE, tokenizer(Settings())),
            ("sensitive-model-key",),
        )


def test_credentials_reject_plaintext_and_chained_backend(monkeypatch):
    bad = type("PlaintextKeyring", (), {"priority": 1})()
    monkeypatch.setattr(credentials.keyring, "get_keyring", lambda: bad)
    with pytest.raises(SafeError) as error:
        credentials.get_secret("dataforseo-password")
    assert error.value.code == "keyring_unavailable"
    assert "禁止明文" in str(error.value)


def test_secure_credentials_status_and_delete_without_leaks(monkeypatch):
    store = {("title-trend.v1", slot): "super-secret-unique" for slot in credentials.SLOTS}
    keyring_type = type(
        "Keyring",
        (),
        {
            "__module__": "keyring.backends.macOS",
            "priority": 1,
            "get_password": lambda self, s, k: store.get((s, k)),
            "set_password": lambda self, s, k, v: store.__setitem__((s, k), v),
            "delete_password": lambda self, s, k: store.pop((s, k)),
        },
    )
    monkeypatch.setattr(credentials.sys, "platform", "darwin")
    monkeypatch.setattr(credentials.keyring, "get_keyring", lambda: keyring_type())
    status = credentials.credential_status()
    assert "super-secret" not in json.dumps(status)
    assert all(v["configured"] for v in status["credentials"].values())
    credentials.delete_credentials()
    assert not store


def test_config_rejects_model_settings_and_credentials():
    for values in (
        {"model_endpoint": "https://example.com/api"},
        {"model_api_key": "must-not-store"},
    ):
        with pytest.raises(ValidationError):
            Settings(**values)


def test_legacy_non_sensitive_config_migrates(tmp_path, monkeypatch):
    from title_trend.config import load_settings, save_settings

    monkeypatch.setenv("TITLE_TREND_CONFIG_DIR", str(tmp_path))
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "model_endpoint": "https://old.example/chat",
                "model_name": "old",
                "model_auth_header": "Authorization",
                "model_auth_prefix": "Bearer ",
                "cache_ttl_seconds": 600,
            }
        )
    )
    settings = load_settings()
    assert settings.cache_ttl_seconds == 600
    save_settings(settings)
    assert "model_" not in path.read_text()
    path.write_text('{"model_api_key":"secret-sentinel"}')
    with pytest.raises(SafeError) as error:
        load_settings()
    assert "secret-sentinel" not in str(error.value)


def test_configure_only_requests_dataforseo(monkeypatch, capsys):
    from title_trend import cli

    prompts, saved = [], {}
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli, "secure_backend", lambda: None)
    monkeypatch.setattr(cli, "load_settings", Settings)
    monkeypatch.setattr(cli, "get_secret", lambda *args: None)
    monkeypatch.setattr(cli, "hidden", lambda prompt: prompts.append(prompt) or "secret-sentinel")
    monkeypatch.setattr(cli, "set_secret", lambda slot, value: saved.__setitem__(slot, value))
    monkeypatch.setattr(cli, "save_settings", lambda settings: None)
    cli.configure()
    assert set(saved) == {"dataforseo-login", "dataforseo-password"}
    assert len(prompts) == 2
    assert "secret-sentinel" not in capsys.readouterr().out


def test_delete_removes_unused_legacy_model_credential(monkeypatch):
    store = {slot: "secret" for slot in (*credentials.SLOTS, *credentials.LEGACY_SLOTS)}

    class Backend:
        def get_password(self, service, slot):
            return store.get(slot)

        def delete_password(self, service, slot):
            store.pop(slot)

    monkeypatch.setattr(credentials, "secure_backend", Backend)
    credentials.delete_credentials()
    assert store == {}


def test_cli_unknown_password_argument_never_echoed(monkeypatch, capsys):
    from title_trend.cli import main

    monkeypatch.setattr("sys.argv", ["title-trend", "configure", "--password", "secret-sentinel"])
    with pytest.raises(SystemExit):
        main()
    assert "secret-sentinel" not in capsys.readouterr().err
