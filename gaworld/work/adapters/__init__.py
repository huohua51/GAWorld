"""Work adapters — turn a WorkBrief into a real artifact on disk."""

from gaworld.work.adapters.base import AdapterContext, WorkAdapter
from gaworld.work.adapters.code import CodeAdapter
from gaworld.work.adapters.content import ContentAdapter
from gaworld.work.adapters.teaching import TeachingAdapter
from gaworld.work.adapters.web_design import WebDesignAdapter


def build_default_adapters() -> dict[str, WorkAdapter]:
    """Return the built-in adapter registry keyed by adapter name."""

    return {
        "web_design": WebDesignAdapter(),
        "code": CodeAdapter(),
        "content": ContentAdapter(),
        "teaching": TeachingAdapter(),
    }


__all__ = [
    "AdapterContext",
    "CodeAdapter",
    "ContentAdapter",
    "TeachingAdapter",
    "WebDesignAdapter",
    "WorkAdapter",
    "build_default_adapters",
]
