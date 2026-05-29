# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""Model abstraction layer - provider-agnostic LLM interface.

This module defines the contract for LLM providers and ships implementations
for Anthropic (Claude) and OpenAI-compatible APIs. To add a new provider
(e.g., a Siemens-trained model), implement the `LLMProvider` protocol.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

from sw360_review_agent.config import ModelConfig

logger = structlog.get_logger(__name__)


@dataclass
class LLMMessage:
    """A single message in a conversation."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None  # Provider-specific raw response


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    To support a new model (e.g., Siemens-trained), implement this interface
    and register it in the provider factory.
    """

    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str | None = None,
    ) -> LLMResponse:
        """Generate a completion from the given messages.

        Args:
            messages: Conversation messages (system + user + optional assistant).
            temperature: Override config temperature for this call.
            max_tokens: Override config max_tokens for this call.
            response_format: If "json", request JSON output from the model.

        Returns:
            LLMResponse with generated content.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up provider resources (HTTP clients, etc.)."""
        ...


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider (Claude Opus 4.5/4.6, Sonnet, etc.)."""

    def __init__(self, config: ModelConfig) -> None:
        import anthropic

        api_key = config.api_key or None  # Falls back to ANTHROPIC_API_KEY env var
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = config.model_name
        self._default_temperature = config.temperature
        self._default_max_tokens = config.max_tokens

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str | None = None,
    ) -> LLMResponse:
        # Anthropic separates system message from conversation
        system_msg = ""
        conversation: list[dict[str, str]] = []

        for msg in messages:
            if msg.role == "system":
                system_msg = msg.content
            else:
                conversation.append({"role": msg.role, "content": msg.content})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": conversation,
            "temperature": temperature if temperature is not None else self._default_temperature,
            "max_tokens": max_tokens or self._default_max_tokens,
        }
        if system_msg:
            kwargs["system"] = system_msg

        logger.debug("anthropic_generate", model=self._model, msg_count=len(conversation))
        response = await self._client.messages.create(**kwargs)

        content = response.content[0].text if response.content else ""

        return LLMResponse(
            content=content,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            raw=response,
        )

    async def close(self) -> None:
        await self._client.close()


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible provider (works with OpenAI, Azure, vLLM, Ollama, etc.).

    This is the recommended provider for Siemens-trained models that expose
    an OpenAI-compatible chat completions endpoint.
    """

    def __init__(self, config: ModelConfig) -> None:
        from openai import AsyncOpenAI

        kwargs: dict[str, Any] = {}
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.base_url:
            kwargs["base_url"] = config.base_url

        self._client = AsyncOpenAI(**kwargs)
        self._model = config.model_name
        self._default_temperature = config.temperature
        self._default_max_tokens = config.max_tokens

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str | None = None,
    ) -> LLMResponse:
        formatted_messages = [{"role": m.role, "content": m.content} for m in messages]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": formatted_messages,
            "temperature": temperature if temperature is not None else self._default_temperature,
            "max_tokens": max_tokens or self._default_max_tokens,
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        logger.debug("openai_generate", model=self._model, msg_count=len(formatted_messages))
        response = await self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        content = choice.message.content or ""

        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }

        return LLMResponse(
            content=content,
            model=response.model or self._model,
            usage=usage,
            raw=response,
        )

    async def close(self) -> None:
        await self._client.close()


class CustomHTTPProvider(LLMProvider):
    """Generic HTTP provider for any model endpoint.

    Sends POST requests with a standard payload and expects a JSON response.
    Use this for Siemens-trained models or any custom inference endpoint
    that doesn't follow the OpenAI API format.

    Expected request format:
        POST {base_url}/generate
        {
            "messages": [...],
            "model": "...",
            "temperature": 0.1,
            "max_tokens": 4096
        }

    Expected response format:
        {
            "content": "generated text",
            "model": "model-name",
            "usage": {"input_tokens": N, "output_tokens": N}
        }
    """

    def __init__(self, config: ModelConfig) -> None:
        import httpx

        if not config.base_url:
            raise ValueError("CustomHTTPProvider requires 'base_url' in model config")

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            headers=headers,
            timeout=120.0,
        )
        self._model = config.model_name
        self._default_temperature = config.temperature
        self._default_max_tokens = config.max_tokens

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str | None = None,
    ) -> LLMResponse:
        payload = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "model": self._model,
            "temperature": temperature if temperature is not None else self._default_temperature,
            "max_tokens": max_tokens or self._default_max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        logger.debug("custom_http_generate", model=self._model)
        resp = await self._client.post("/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()

        return LLMResponse(
            content=data.get("content", ""),
            model=data.get("model", self._model),
            usage=data.get("usage", {}),
            raw=data,
        )

    async def close(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Provider Factory
# ---------------------------------------------------------------------------

_PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAICompatibleProvider,
    "custom": CustomHTTPProvider,
}


def register_provider(name: str, provider_class: type[LLMProvider]) -> None:
    """Register a custom LLM provider.

    Use this to add support for new model providers at runtime:
        from sw360_review_agent.models import register_provider
        register_provider("siemens_llm", SiemensLLMProvider)

    Then set `model.provider: "siemens_llm"` in config.yaml.
    """
    _PROVIDER_REGISTRY[name] = provider_class


def create_provider(config: ModelConfig) -> LLMProvider:
    """Create an LLM provider instance from configuration.

    Args:
        config: Model configuration specifying provider, model name, etc.

    Returns:
        Configured LLMProvider instance.

    Raises:
        ValueError: If provider name is not registered.
    """
    provider_name = config.provider.lower()
    if provider_name not in _PROVIDER_REGISTRY:
        available = ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        raise ValueError(
            f"Unknown model provider '{provider_name}'. "
            f"Available: {available}. "
            f"Use register_provider() to add custom providers."
        )

    provider_class = _PROVIDER_REGISTRY[provider_name]
    logger.info("creating_llm_provider", provider=provider_name, model=config.model_name)
    return provider_class(config)


def parse_json_response(response: LLMResponse) -> list[dict[str, Any]]:
    """Parse LLM response content as JSON array.

    Handles common LLM quirks like markdown code fences around JSON.
    """
    content = response.content.strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [line for line in lines[1:] if not line.strip().startswith("```")]
        content = "\n".join(lines)

    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict):
            return [parsed]
        return []
    except json.JSONDecodeError:
        logger.warning("failed_to_parse_llm_json", content_preview=content[:200])
        return []
