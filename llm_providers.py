import os
import requests

from config import CONFIG


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
        try:
            with requests.post(
                self.url,
                json=payload,
                timeout=(10, self.timeout),
                stream=True,
            ) as r:
                r.raise_for_status()
                parts = []
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    data = requests.models.complexjson.loads(line)
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
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.getenv(api_key_env)
        self.timeout = timeout
        self.stream = bool(stream)
        self.max_tokens = max_tokens
        self.temperature = temperature

    def call(self, prompt):
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
        if self.stream:
            payload["stream"] = True
            with requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=(10, self.timeout),
                stream=True,
            ) as r:
                r.raise_for_status()
                parts = []
                for raw_line in r.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    line = raw_line.strip()
                    # Skip SSE metadata / keep-alive lines such as:
                    # `event: message`, `: keep-alive`, or empty chunks.
                    if not line or line.startswith(":") or line.startswith("event:"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    line = line[5:].strip()
                    if not line:
                        continue
                    if line == "[DONE]":
                        break
                    try:
                        data = requests.models.complexjson.loads(line)
                    except ValueError:
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

        r = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]


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
                attempts.append({
                    "scheme": scheme or "none",
                    "status": r.status_code,
                    "authorization_sent": "Authorization" in headers,
                    "x_api_key_sent": "x-api-key" in headers,
                })
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
                print(f"⚠️ 跳过不支持的 LLM provider 类型: {name} ({p_type})")
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

    def call(self, prompt, task=None, agent_id=None):
        provider_name = self._select_provider(task=task, agent_id=agent_id)
        if provider_name not in self.providers:
            raise ValueError(f"Provider '{provider_name}' not found in config.")
        return self.providers[provider_name].call(prompt)


LLM_ROUTER = LLMRouter(CONFIG)


def call_llm(prompt, task=None, agent_id=None):
    """Public helper for model calls used across the simulator."""
    return LLM_ROUTER.call(prompt, task=task, agent_id=agent_id)
