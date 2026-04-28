"""HTML extraction utilities used by the news / RAG pipeline.

These helpers used to live inline in ``generative_city_sim.py``. They
are extracted here to keep the simulator focused on its core loop and
to allow drop-in replacement (e.g. with ``trafilatura`` or
``readability-lxml``) in a single place.

Public API:

* :func:`strip_html`
* :func:`normalize_text`
* :func:`extract_title`
* :func:`extract_meta_description`
* :func:`extract_news_main_content`
* :func:`fetch_news_excerpt`

Behaviour matches the original implementation; please add tests before
swapping out the regex-based extractor.
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Iterable

import requests

from gaworld.io.http_guard import GuardedSession, get_default_session
from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.io.web_scrape")


# ---------------------------------------------------------------------
# Low-level cleaners
# ---------------------------------------------------------------------

def strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r" ", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_title(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
    if not match:
        return ""
    title = strip_html(match.group(1))
    return re.sub(r"\s+", " ", title).strip()


def extract_meta_description(text: str, *names: str) -> str:
    """Return the first meta tag whose ``name``/``property`` matches ``names``."""
    if not text or not names:
        return ""
    for name in names:
        pattern = (
            r'(?is)<meta[^>]+(?:name|property)=["\']%s["\'][^>]+content=["\'](.*?)["\'][^>]*>'
            % re.escape(name)
        )
        match = re.search(pattern, text)
        if match:
            content = normalize_text(strip_html(match.group(1)))
            if content:
                return content
        pattern_rev = (
            r'(?is)<meta[^>]+content=["\'](.*?)["\'][^>]+(?:name|property)=["\']%s["\'][^>]*>'
            % re.escape(name)
        )
        match = re.search(pattern_rev, text)
        if match:
            content = normalize_text(strip_html(match.group(1)))
            if content:
                return content
    return ""


# ---------------------------------------------------------------------
# Article body extraction (LD-JSON / <article> / paragraph fallback)
# ---------------------------------------------------------------------

def _extract_ld_json_article_body(text: str) -> str:
    if not text:
        return ""
    scripts = re.findall(
        r'(?is)<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        text,
    )
    for block in scripts:
        candidate = block.strip()
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            article_body = node.get("articleBody")
            if isinstance(article_body, str) and len(article_body.strip()) > 80:
                return normalize_text(article_body)
    return ""


def _extract_article_like_block(text: str) -> str:
    if not text:
        return ""
    candidate_patterns = [
        r"(?is)<article[^>]*>(.*?)</article>",
        r"(?is)<main[^>]*>(.*?)</main>",
        r'(?is)<div[^>]+(?:id|class)=["\'][^"\']*(?:article|content|story|post|entry|news|正文)[^"\']*["\'][^>]*>(.*?)</div>',
    ]
    for pattern in candidate_patterns:
        blocks = re.findall(pattern, text)
        for block in blocks:
            paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", block)
            parts = [normalize_text(strip_html(p)) for p in paragraphs]
            parts = [p for p in parts if len(p) >= 25]
            joined = "\n".join(parts)
            if len(joined) >= 180:
                return joined
    return ""


_PARAGRAPH_BLACKLIST: tuple[str, ...] = (
    "copyright",
    "subscribe",
    "登录",
    "注册",
    "隐私",
    "cookie",
    "版权所有",
)


def _extract_paragraph_fallback(text: str, blacklist: Iterable[str] = _PARAGRAPH_BLACKLIST) -> str:
    if not text:
        return ""
    paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", text)
    cleaned: list[str] = []
    for p in paragraphs:
        line = normalize_text(strip_html(p))
        lower = line.lower()
        if len(line) < 25:
            continue
        if any(b in lower for b in blacklist):
            continue
        cleaned.append(line)
    if not cleaned:
        return ""
    return "\n".join(cleaned[:16])


def extract_news_main_content(html_text: str) -> str:
    """Return the article body of an HTML page, with progressive fallback."""
    extractors = (
        _extract_ld_json_article_body,
        _extract_article_like_block,
        _extract_paragraph_fallback,
    )
    for extractor in extractors:
        content = extractor(html_text)
        if content and len(content) >= 120:
            return content
    return strip_html(html_text)


# ---------------------------------------------------------------------
# High-level fetch helper
# ---------------------------------------------------------------------

def fetch_news_excerpt(
    url: str,
    timeout: int = 8,
    max_chars: int = 2000,
    user_agent: str | None = None,
    return_title: bool = False,
    session: GuardedSession | None = None,
):
    """Fetch ``url`` and return the cleaned article body.

    Goes through a process-wide :class:`GuardedSession` so requests
    honour per-host rate limits, rotate User-Agent strings, and skip
    URLs that recently returned 4xx/5xx. ``user_agent`` overrides the
    rotator for one call when provided.

    Returns ``""`` (or ``("", "")`` when ``return_title=True``) on any
    transport / parsing error. Network errors are logged at ``WARNING``.
    """
    if not url:
        return ("", "") if return_title else ""
    sess = session or get_default_session()
    headers = {"User-Agent": user_agent} if user_agent else None
    try:
        resp = sess.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
        if not resp.encoding:
            resp.encoding = resp.apparent_encoding
        raw_text = resp.text or ""
    except requests.RequestException as exc:
        _LOG.warning("fetch_news_excerpt failed for %s: %s", url, exc)
        return ("", "") if return_title else ""
    if not raw_text:
        return ("", "") if return_title else ""
    content_type = (resp.headers.get("content-type") or "").lower()
    title = ""
    if "text/html" in content_type or "<html" in raw_text.lower():
        title = extract_title(raw_text)
        cleaned = extract_news_main_content(raw_text)
    else:
        cleaned = re.sub(r"\s+", " ", raw_text).strip()
    if max_chars and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rsplit(" ", 1)[0].strip() if " " in cleaned else cleaned[:max_chars]
    if return_title:
        return cleaned, title
    return cleaned
