"""I/O helpers (HTML extraction, news caching, future RAG ingestion)."""

from gaworld.io.http_guard import (
    FailureCache,
    GuardedSession,
    HostRateLimiter,
    UserAgentRotator,
    get_default_session,
    reset_default_session,
)
from gaworld.io.web_scrape import (
    extract_meta_description,
    extract_news_main_content,
    extract_title,
    fetch_news_excerpt,
    normalize_text,
    strip_html,
)

__all__ = [
    "FailureCache",
    "GuardedSession",
    "HostRateLimiter",
    "UserAgentRotator",
    "extract_meta_description",
    "extract_news_main_content",
    "extract_title",
    "fetch_news_excerpt",
    "get_default_session",
    "normalize_text",
    "reset_default_session",
    "strip_html",
]
