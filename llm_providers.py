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
        anthropic_version="2023-06-01",
        timeout=120,
        max_tokens=512,
        system=None,
        beta=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.getenv(api_key_env)
        self.anthropic_version = anthropic_version
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.system = system
        self.beta = beta

    def call(self, prompt):
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
            "Content-Type": "application/json",
        }
        if self.beta:
            headers["anthropic-beta"] = self.beta
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.system:
            payload["system"] = self.system
        r = requests.post(
            f"{self.base_url}/v1/messages",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("content", [{}])[0].get("text", "")


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
                    anthropic_version=cfg.get("anthropic_version", "2023-06-01"),
                    timeout=cfg.get("timeout", 120),
                    max_tokens=cfg.get("max_tokens", 512),
                    system=cfg.get("system"),
                    beta=cfg.get("anthropic_beta"),
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
