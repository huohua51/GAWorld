"""I/O helpers (HTML extraction, news caching, future RAG ingestion)."""

from gaworld.io.web_scrape import (
    extract_meta_description,
    extract_news_main_content,
    extract_title,
    fetch_news_excerpt,
    normalize_text,
    strip_html,
)

__all__ = [
    "extract_meta_description",
    "extract_news_main_content",
    "extract_title",
    "fetch_news_excerpt",
    "normalize_text",
    "strip_html",
]
