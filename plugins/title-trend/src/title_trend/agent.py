from __future__ import annotations

import logging
import re

import jieba
from pydantic import Field

from .config import Settings
from .errors import SafeError
from .models import Advice, StrictModel, normalize

jieba.setLogLevel(logging.ERROR)
STOP = {
    "如何",
    "为什么",
    "什么",
    "我们",
    "你们",
    "一个",
    "这些",
    "那些",
    "可以",
    "需要",
    "标题",
    "文章",
    "关于",
    "哪些",
    "怎样",
    "不是",
    "还是",
    "真的",
    "自己",
}


def tokenizer(settings: Settings) -> jieba.Tokenizer:
    cutter = jieba.Tokenizer()
    if settings.user_dictionary:
        try:
            cutter.load_userdict(settings.user_dictionary)
        except Exception:
            raise SafeError(
                "dictionary", "自定义词典加载失败。请检查路径、UTF-8 编码与 jieba 格式。"
            ) from None
    return cutter


def candidate_tokens(title: str, cutter: jieba.Tokenizer) -> list[str]:
    # Protect Latin product names/abbreviations before Chinese segmentation.
    fragments = re.split(r"([A-Za-z][A-Za-z0-9.+#_-]*)", title)
    words = []
    for fragment in fragments:
        tokens = (
            [fragment]
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9.+#_-]*", fragment)
            else cutter.lcut(fragment)
        )
        for token in tokens:
            token = token.strip()
            if len(token) >= 2 and re.search(r"[\w\u4e00-\u9fff]", token) and token not in STOP:
                if normalize(token) not in {normalize(w) for w in words}:
                    words.append(token)
    return words[:40]


class Candidate(StrictModel):
    keyword: str = Field(min_length=2, max_length=100)
    anchors: list[str] = Field(min_length=1, max_length=3)
    relevance: str = Field(min_length=2, max_length=180)


class Selection(StrictModel):
    topic: str = Field(min_length=2, max_length=180)
    candidates: list[Candidate] = Field(min_length=1, max_length=5)


def validate_selection(raw: dict, title: str, cutter: jieba.Tokenizer) -> Selection:
    selection = Selection.model_validate(raw)
    title_key = normalize(title)
    seen = set()
    for candidate in selection.candidates:
        key = normalize(candidate.keyword)
        if (
            key in seen
            or re.search(r"[\x00-\x1f\x7f]", candidate.keyword)
            or not re.search(r"[\w\u4e00-\u9fff]", key)
        ):
            raise ValueError("Duplicate or invalid keyword")
        seen.add(key)
        if any(
            len(a.strip()) < 2
            or normalize(a) in STOP
            or normalize(a) not in title_key
            or normalize(a) not in key
            for a in candidate.anchors
        ):
            raise ValueError("Keyword must have a direct original-title anchor")
        # Conservative v1: only original words and recombinations, no unrelated new hot terms.
        if key not in title_key:
            for token in cutter.lcut(key):
                if re.search(r"[\w\u4e00-\u9fff]", token) and normalize(token) not in title_key:
                    raise ValueError("Ungrounded keyword term")
        candidate.keyword = candidate.keyword.strip()
    return selection


def validate_advice(
    raw: dict, title: str, selection: Selection, forbidden: tuple[str, ...] = ()
) -> Advice:
    # Origin belongs to the server. The agent cannot relabel its output as validated facts.
    if "origin" in raw:
        raise ValueError("Agent must not supply origin")
    advice = Advice.model_validate(raw)
    serialized = advice.model_dump_json()
    if any(secret and secret in serialized for secret in forbidden):
        raise ValueError("Credential content rejected")
    # The card/text renderer supplies all numeric data; prose must not invent numeric claims.
    for number in re.findall(r"\d+(?:\.\d+)?", serialized):
        if number not in title:
            raise ValueError("Ungrounded numeric claim")
    originals = {normalize(x) for x in re.findall(r"[A-Za-z][A-Za-z0-9.+#_-]*", title)}
    anchors = [normalize(a) for c in selection.candidates for a in c.anchors]
    seen = set()
    grammar = {
        "如何",
        "怎么",
        "为什么",
        "怎样",
        "用",
        "关于",
        "与",
        "和",
        "的",
        "你",
        "我",
        "我们",
        "把",
        "从",
        "到",
        "让",
        "来",
        "为",
        "吗",
        "呢",
        "也",
        "还",
        "能",
        "就",
        "在",
        "有",
        "是",
        "做",
        "看",
        "读",
        "这",
        "一个",
        "一次",
    }
    cutter = jieba.Tokenizer()
    for recommended in advice.recommended_titles:
        key = normalize(recommended.title)
        if key in seen or not any(a in key for a in anchors):
            raise ValueError("Duplicate or off-topic title")
        seen.add(key)
        for term in cutter.lcut(key):
            if (
                re.search(r"[\w\u4e00-\u9fff]", term)
                and term not in grammar
                and term not in normalize(title)
            ):
                raise ValueError("New title fact, name or topic term")
        if any(
            normalize(x) not in originals
            for x in re.findall(r"[A-Za-z][A-Za-z0-9.+#_-]*", recommended.title)
        ):
            raise ValueError("New English name or entity")
        for promise in (
            "保证",
            "稳赚",
            "必涨",
            "翻倍",
            "爆款",
            "震惊",
            "官宣",
            "最新消息",
            "宣布",
            "证实",
        ):
            if promise in key and promise not in normalize(title):
                raise ValueError("Unsupported fact or promise")
    return advice
