"""Versioned provider adapter for evidence-first benchmark runs.

This add-only module leaves ``llm_providers.py`` unchanged because sealed
experiments hash that file.  New evaluation protocols can opt into native
structured-output requests and per-transport-attempt audit metadata here.
The normal GAWorld simulator continues to use the original provider module.
"""

import json
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

from config import CONFIG
from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.llm")


# ---------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------
_RETRYABLE_HTTP = {408, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class LLMCallResult:
    """Text plus credential-free transport evidence for one logical call."""

    text: str
    metadata: dict[str, Any]


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        return resp is not None and resp.status_code in _RETRYABLE_HTTP
    return isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))


def _retrying(
    call: Callable[[], Any],
    *,
    attempts: int = 3,
    backoff: float = 1.5,
    provider: str = "",
    task: str = "",
    audit_records: list[dict[str, Any]] | None = None,
) -> Any:
    """Run ``call`` with bounded exponential backoff on transient errors."""
    delay = 0.6
    last_exc: BaseException | None = None
    for attempt in range(1, max(1, attempts) + 1):
        started_at = time.time()
        started = time.perf_counter()
        try:
            result = call()
        except Exception as exc:
            last_exc = exc
            retryable = _is_retryable(exc)
            will_retry = attempt < attempts and retryable
            if audit_records is not None:
                audit_records.append(
                    {
                        "attempt": attempt,
                        "max_attempts": max(1, attempts),
                        "started_at": started_at,
                        "ended_at": time.time(),
                        "latency_ms": int((time.perf_counter() - started) * 1000),
                        "success": False,
                        "retryable": retryable,
                        "will_retry": will_retry,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "provider": provider,
                        "task": task,
                    }
                )
            if not will_retry:
                raise
            _LOG.warning(
                "LLM call failed (attempt %d/%d, provider=%s, task=%s): %s 閳?retrying in %.1fs",
                attempt,
                attempts,
                provider,
                task,
                exc,
                delay,
            )
            time.sleep(delay)
            delay *= backoff
        else:
            if audit_records is not None:
                audit_records.append(
                    {
                        "attempt": attempt,
                        "max_attempts": max(1, attempts),
                        "started_at": started_at,
                        "ended_at": time.time(),
                        "latency_ms": int((time.perf_counter() - started) * 1000),
                        "success": True,
                        "retryable": False,
                        "will_retry": False,
                        "error_type": "",
                        "error_message": "",
                        "provider": provider,
                        "task": task,
                    }
                )
            return result
    # Unreachable, but keep mypy happy.
    if last_exc is not None:  # pragma: no cover
        raise last_exc
    raise RuntimeError("retrying() failed without exception")


class OllamaProvider:
    """Simple wrapper for Ollama-compatible text generation."""

    def __init__(self, url, model, timeout=120):
        self.url = url
        self.model = model
        self.timeout = timeout

    def call(self, prompt):
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
        }

        def _do() -> str:
            try:
                with requests.post(
                    self.url,
                    json=payload,
                    timeout=(10, self.timeout),
                    stream=True,
                ) as r:
                    r.raise_for_status()
                    parts: list[str] = []
                    for line in r.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        # Use stdlib json instead of requests' private complexjson alias.
                        try:
                            data = json.loads(line)
                        except (json.JSONDecodeError, TypeError):
                            continue
                        chunk = data.get("response", "")
                        if chunk:
                            parts.append(chunk)
                        if data.get("done"):
                            break
                    return "".join(parts)
            except requests.exceptions.ReadTimeout as exc:
                raise requests.exceptions.ReadTimeout(
                    f"Ollama provider timed out while calling model '{self.model}'. "
                    f"Current timeout={self.timeout}s. "
                    f"If this model is slow locally, increase config.py -> llm.providers timeout."
                ) from exc

        return _retrying(_do, provider=f"ollama:{self.model}", task="")


class OpenAIProvider:
    """OpenAI Chat Completions wrapper (single-turn)."""

    def __init__(
        self,
        base_url,
        model,
        api_key=None,
        api_key_env="OPENAI_API_KEY",
        timeout=120,
        stream=False,
        max_tokens=None,
        temperature=None,
        thinking=None,
        reasoning_effort=None,
        response_format=None,
        retry_attempts=3,
        retry_backoff=1.5,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.getenv(api_key_env)
        self.timeout = timeout
        self.stream = bool(stream)
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.thinking = thinking
        self.reasoning_effort = reasoning_effort
        if response_format is not None and not isinstance(response_format, dict):
            raise TypeError("response_format must be an object or None")
        self.response_format = dict(response_format) if response_format else None
        self.retry_attempts = int(retry_attempts)
        self.retry_backoff = float(retry_backoff)
        if self.retry_attempts < 1:
            raise ValueError("retry_attempts must be at least 1")

    def call_with_metadata(self, prompt) -> LLMCallResult:
        audit_records: list[dict[str, Any]] = []
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.thinking is not None:
            payload["thinking"] = self.thinking
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.response_format is not None:
            payload["response_format"] = dict(self.response_format)

        def _message_text(message: dict[str, Any]) -> str:
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                if parts:
                    return "".join(parts)
            if message.get("reasoning_content"):
                raise ValueError(
                    "OpenAI-compatible response contained reasoning_content but no "
                    "final content; increase max_tokens or disable thinking"
                )
            raise ValueError("OpenAI-compatible response contained no textual content")

        def _do_streaming() -> str:
            stream_payload = dict(payload, stream=True)
            with requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=stream_payload,
                timeout=(10, self.timeout),
                stream=True,
            ) as r:
                r.raise_for_status()
                parts: list[str] = []
                for raw_line in r.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    line = raw_line.strip()
                    # Skip SSE metadata / keep-alive lines such as:
                    # `event: message`, `: keep-alive`, or empty chunks.
                    if not line or line.startswith((":", "event:")):
                        continue
                    if not line.startswith("data:"):
                        continue
                    line = line[5:].strip()
                    if not line:
                        continue
                    if line == "[DONE]":
                        break
                    try:
                        data = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        # Some OpenAI-compatible backends emit non-JSON
                        # heartbeat payloads in `data:` frames.
                        continue
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    chunk = delta.get("content")
                    if isinstance(chunk, str) and chunk:
                        parts.append(chunk)
                        continue
                    if isinstance(chunk, list):
                        for item in chunk:
                            if isinstance(item, dict):
                                text = item.get("text")
                                if isinstance(text, str) and text:
                                    parts.append(text)
                        continue
                    message = choices[0].get("message") or {}
                    chunk = message.get("content")
                    if isinstance(chunk, str) and chunk:
                        parts.append(chunk)
                        continue
                    if isinstance(chunk, list):
                        for item in chunk:
                            if isinstance(item, dict):
                                text = item.get("text")
                                if isinstance(text, str) and text:
                                    parts.append(text)
                return "".join(parts)

        def _do_blocking() -> str:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            return _message_text(data["choices"][0]["message"])

        try:
            if self.stream:
                text = _retrying(
                    _do_streaming,
                    attempts=self.retry_attempts,
                    backoff=self.retry_backoff,
                    provider=f"openai:{self.model}",
                    task="",
                    audit_records=audit_records,
                )
            else:
                text = _retrying(
                    _do_blocking,
                    attempts=self.retry_attempts,
                    backoff=self.retry_backoff,
                    provider=f"openai:{self.model}",
                    task="",
                    audit_records=audit_records,
                )
        except Exception as exc:
            metadata = {
                "transport_attempts": audit_records,
                "transport_attempt_count": len(audit_records),
                "transport_retry_count": sum(int(record["will_retry"]) for record in audit_records),
            }
            try:
                exc.gaworld_call_metadata = metadata  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - unusual immutable exceptions
                pass
            raise
        return LLMCallResult(
            text=text,
            metadata={
                "transport_attempts": audit_records,
                "transport_attempt_count": len(audit_records),
                "transport_retry_count": sum(int(record["will_retry"]) for record in audit_records),
            },
        )

    def call(self, prompt):
        return self.call_with_metadata(prompt).text


class AnthropicProvider:
    """Anthropic/Claude message API wrapper."""

    def __init__(
        self,
        base_url,
        model,
        api_key=None,
        api_key_env="ANTHROPIC_API_KEY",
        api_key_envs=None,
        anthropic_version="2023-06-01",
        timeout=120,
        max_tokens=512,
        system=None,
        beta=None,
        authorization_bearer=False,
        authorization_scheme=None,
        include_x_api_key=True,
        authorization_retry_schemes=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        env_names = list(api_key_envs or [])
        if api_key_env and api_key_env not in env_names:
            env_names.insert(0, api_key_env)
        self.api_key = api_key
        self.api_key_source = "config.api_key" if api_key else ""
        if not self.api_key:
            for env_name in env_names:
                self.api_key = os.getenv(env_name)
                if self.api_key:
                    self.api_key_source = env_name
                    break
        self.api_key_envs = env_names
        self.anthropic_version = anthropic_version
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.system = system
        self.beta = beta
        if authorization_scheme is None and authorization_bearer:
            authorization_scheme = "bearer"
        self.authorization_scheme = str(authorization_scheme or "").strip().lower()
        self.authorization_bearer = self.authorization_scheme == "bearer"
        self.include_x_api_key = bool(include_x_api_key)
        self.authorization_retry_schemes = [
            str(item or "").strip().lower()
            for item in (authorization_retry_schemes or [])
            if str(item or "").strip()
        ]

    def call(self, prompt):
        if not self.api_key:
            env_names = ", ".join(self.api_key_envs) or "ANTHROPIC_API_KEY"
            raise ValueError(f"Anthropic provider API key not found. Set one of: {env_names}")
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.system:
            payload["system"] = self.system

        return _retrying(
            lambda: self._call_once(payload),
            provider=f"anthropic:{self.model}",
            task="",
        )

    def _call_once(self, payload):
        schemes = [self.authorization_scheme]
        for scheme in self.authorization_retry_schemes:
            if scheme not in schemes:
                schemes.append(scheme)
        attempts = []
        last_response = None
        last_exc = None
        for scheme in schemes:
            headers = {
                "anthropic-version": self.anthropic_version,
                "Content-Type": "application/json",
            }
            if self.include_x_api_key:
                headers["x-api-key"] = self.api_key
            if scheme == "bearer":
                headers["Authorization"] = f"Bearer {self.api_key}"
            elif scheme == "raw":
                headers["Authorization"] = self.api_key
            if self.beta:
                headers["anthropic-beta"] = self.beta
            r = requests.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            try:
                r.raise_for_status()
                data = r.json()
                parts = []
                for block in data.get("content", []):
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        parts.append(block["text"])
                return "".join(parts)
            except requests.exceptions.HTTPError as exc:
                last_response = r
                last_exc = exc
                attempts.append(
                    {
                        "scheme": scheme or "none",
                        "status": r.status_code,
                        "authorization_sent": "Authorization" in headers,
                        "x_api_key_sent": "x-api-key" in headers,
                    }
                )
                if r.status_code != 401:
                    break
                continue

        body = last_response.text.strip() if last_response is not None else ""
        if len(body) > 800:
            body = body[:800] + "..."
        env_names = ", ".join(self.api_key_envs) or "ANTHROPIC_API_KEY"
        status = last_response.status_code if last_response is not None else "unknown"
        raise requests.exceptions.HTTPError(
            f"Anthropic provider request failed with HTTP {status}. "
            f"base_url={self.base_url!r}, model={self.model!r}, "
            f"api_key_present={bool(self.api_key)}, api_key_envs=[{env_names}], "
            f"api_key_source={self.api_key_source!r}, attempts={attempts!r}, "
            f"response={body!r}"
        ) from last_exc


class LLMRouter:
    """Lightweight router for selecting providers by task or agent."""

    def __init__(self, config):
        self.config = config
        self.providers = self._init_providers()
        self.routing = config.get("llm", {}).get("routing", {})

    def _init_providers(self):
        providers = {}
        llm_cfg = self.config.get("llm", {})
        for name, cfg in llm_cfg.get("providers", {}).items():
            p_type = cfg.get("type")
            if p_type == "ollama":
                providers[name] = OllamaProvider(
                    cfg.get("url", "http://localhost:11434/api/generate"),
                    cfg["model"],
                    timeout=cfg.get("timeout", 120),
                )
            elif p_type == "openai":
                providers[name] = OpenAIProvider(
                    cfg.get("base_url", "https://api.openai.com/v1"),
                    cfg["model"],
                    api_key=cfg.get("api_key"),
                    api_key_env=cfg.get("api_key_env", "OPENAI_API_KEY"),
                    timeout=cfg.get("timeout", 120),
                    stream=cfg.get("stream", False),
                    max_tokens=cfg.get("max_tokens"),
                    temperature=cfg.get("temperature"),
                    thinking=cfg.get("thinking"),
                    reasoning_effort=cfg.get("reasoning_effort"),
                    response_format=cfg.get("response_format"),
                    retry_attempts=cfg.get("retry_attempts", 3),
                    retry_backoff=cfg.get("retry_backoff", 1.5),
                )
            elif p_type in ("claude", "anthropic"):
                providers[name] = AnthropicProvider(
                    cfg.get("base_url", "https://api.anthropic.com"),
                    cfg["model"],
                    api_key=cfg.get("api_key") or cfg.get("ANTHROPIC_AUTH_TOKEN"),
                    api_key_env=cfg.get("api_key_env", "ANTHROPIC_API_KEY"),
                    api_key_envs=cfg.get("api_key_envs"),
                    anthropic_version=cfg.get("anthropic_version", "2023-06-01"),
                    timeout=cfg.get("timeout", 120),
                    max_tokens=cfg.get("max_tokens", 512),
                    system=cfg.get("system"),
                    beta=cfg.get("anthropic_beta"),
                    authorization_bearer=cfg.get("authorization_bearer", False),
                    authorization_scheme=cfg.get("authorization_scheme"),
                    include_x_api_key=cfg.get("include_x_api_key", True),
                    authorization_retry_schemes=cfg.get("authorization_retry_schemes"),
                )
            else:
                print(f"閳跨媴绗?鐠哄疇绻冩稉宥嗘暜閹镐胶娈?LLM provider 缁鐎? {name} ({p_type})")
                continue
        if not providers:
            raise ValueError("No LLM providers configured.")
        return providers

    def _select_provider(self, task=None, agent_id=None):
        tasks = self.routing.get("tasks", {})
        if task and task in tasks:
            return tasks[task]
        agents = self.routing.get("agents", {})
        if agent_id is not None and str(agent_id) in agents:
            return agents[str(agent_id)]
        return self.routing.get("default") or next(iter(self.providers))

    def _resolve_chain(self, task=None, agent_id=None):
        """Return an ordered list of provider names to try for a single call.

        Resolution order:

        1. Primary provider chosen by :meth:`_select_provider`.
        2. Optional ``llm.routing.fallback`` list (global) 閳?these are
           appended after the primary, deduplicated, and any unknown
           name is silently skipped.

        The returned list is never empty (the primary is always
        included), so callers don't have to special-case fallback being
        absent.
        """
        primary = self._select_provider(task=task, agent_id=agent_id)
        chain: list[str] = [primary]
        fallback = self.routing.get("fallback", [])
        if isinstance(fallback, str):
            fallback = [fallback]
        if isinstance(fallback, (list, tuple)):
            for name in fallback:
                name = str(name).strip()
                if not name or name == primary or name in chain:
                    continue
                if name in self.providers:
                    chain.append(name)
        return chain

    def call_with_metadata(self, prompt, task=None, agent_id=None, variant=None) -> LLMCallResult:
        chain = self._resolve_chain(task=task, agent_id=agent_id)
        if not chain or chain[0] not in self.providers:
            raise ValueError(f"Provider '{chain[0] if chain else ''}' not found in config.")

        call_id = uuid.uuid4().hex[:8]
        prompt_chars = len(prompt or "")
        log = _LOG
        last_exc: BaseException | None = None
        transport_attempts: list[dict[str, Any]] = []
        provider_calls: list[dict[str, Any]] = []
        for index, provider_name in enumerate(chain):
            started = time.perf_counter()
            try:
                provider = self.providers[provider_name]
                call_with_metadata = getattr(provider, "call_with_metadata", None)
                if callable(call_with_metadata):
                    provider_result = call_with_metadata(prompt)
                    result = provider_result.text
                    provider_metadata = dict(provider_result.metadata)
                    attempts = list(provider_metadata.get("transport_attempts") or [])
                else:
                    result = provider.call(prompt)
                    attempts = []
                transport_attempts.extend(
                    {
                        **dict(attempt),
                        "router_provider": provider_name,
                        "fallback_index": index,
                    }
                    for attempt in attempts
                )
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                provider_calls.append(
                    {
                        "provider": provider_name,
                        "fallback_index": index,
                        "success": True,
                        "latency_ms": elapsed_ms,
                    }
                )
                log.debug(
                    "llm.call ok id=%s provider=%s fallback_index=%d task=%s agent=%s "
                    "prompt_chars=%d completion_chars=%d latency_ms=%d",
                    call_id,
                    provider_name,
                    index,
                    task or "",
                    agent_id if agent_id is not None else "",
                    prompt_chars,
                    len(result or ""),
                    elapsed_ms,
                )
                return LLMCallResult(
                    text=result,
                    metadata={
                        "router_call_id": call_id,
                        "selected_provider": provider_name,
                        "provider_calls": provider_calls,
                        "transport_attempts": transport_attempts,
                        "transport_attempt_count": len(transport_attempts),
                        "transport_retry_count": sum(
                            int(record.get("will_retry") is True) for record in transport_attempts
                        ),
                    },
                )
            except Exception as exc:
                metadata = getattr(exc, "gaworld_call_metadata", {})
                attempts = list((metadata or {}).get("transport_attempts") or [])
                transport_attempts.extend(
                    {
                        **dict(attempt),
                        "router_provider": provider_name,
                        "fallback_index": index,
                    }
                    for attempt in attempts
                )
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                provider_calls.append(
                    {
                        "provider": provider_name,
                        "fallback_index": index,
                        "success": False,
                        "latency_ms": elapsed_ms,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )
                log.warning(
                    "llm.call err id=%s provider=%s fallback_index=%d task=%s agent=%s "
                    "prompt_chars=%d latency_ms=%d error=%s",
                    call_id,
                    provider_name,
                    index,
                    task or "",
                    agent_id if agent_id is not None else "",
                    prompt_chars,
                    elapsed_ms,
                    exc,
                )
                last_exc = exc
                # Only fall through to the next provider if there is one
                # AND the failure looks transient (or auth/config).
                # Auth errors on the primary may indicate misconfig;
                # the fallback might still succeed if it has a different
                # credential, so we attempt it.
                if index + 1 >= len(chain):
                    break
                continue

        log.error(
            "llm.call failed across %d providers id=%s task=%s agent=%s",
            len(chain),
            call_id,
            task or "",
            agent_id if agent_id is not None else "",
        )
        assert last_exc is not None
        metadata = {
            "router_call_id": call_id,
            "selected_provider": None,
            "provider_calls": provider_calls,
            "transport_attempts": transport_attempts,
            "transport_attempt_count": len(transport_attempts),
            "transport_retry_count": sum(
                int(record.get("will_retry") is True) for record in transport_attempts
            ),
        }
        try:
            last_exc.gaworld_call_metadata = metadata  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - unusual immutable exceptions
            pass
        raise last_exc

    def call(self, prompt, task=None, agent_id=None, variant=None):
        return self.call_with_metadata(
            prompt,
            task=task,
            agent_id=agent_id,
            variant=variant,
        ).text


LLM_ROUTER = LLMRouter(CONFIG)


def call_llm(prompt, task=None, agent_id=None, variant=None):
    """Public helper for model calls used across the simulator.

    Each invocation:

    * runs through retry / backoff for transient errors,
    * is logged with provider, task, agent, prompt size, and latency,
    * raises the original :class:`requests` exception on hard failure.

    The ``variant`` parameter is reserved for A/B experiment variants
    ("A" = no LH Context, "B" = LH Context + personality injection).
    It does not change routing behaviour; the ABForkEngine handles
    prompt construction separately.
    """
    return LLM_ROUTER.call(prompt, task=task, agent_id=agent_id, variant=variant)
