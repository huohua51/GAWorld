"""LLM provider router (currently a re-export of the legacy module).

The intent is to migrate ``llm_providers`` here without changing the
public surface. For now we re-export the existing symbols so callers
can switch their imports without a behavioural change.
"""

from llm_providers import (  # noqa: F401 — re-export
    LLM_ROUTER,
    AnthropicProvider,
    LLMRouter,
    OllamaProvider,
    OpenAIProvider,
    call_llm,
)

__all__ = [
    "LLM_ROUTER",
    "AnthropicProvider",
    "LLMRouter",
    "OllamaProvider",
    "OpenAIProvider",
    "call_llm",
]
