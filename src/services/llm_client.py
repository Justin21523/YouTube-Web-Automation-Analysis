# src/services/llm_client.py
"""
LLM Client - Unified interface for Language Model providers
Supports OpenAI, LLMVendor LLMProvider, and local models
"""

import os
import json
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, AsyncGenerator
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Standardized LLM response"""
    content: str
    model: str
    usage: Dict[str, int]
    finish_reason: Optional[str] = None
    raw_response: Optional[Any] = None


@dataclass
class Message:
    """Chat message"""
    role: str  # "system", "user", "assistant"
    content: str


class BaseLLMClient(ABC):
    """Base class for LLM clients"""

    def __init__(self, model: str, **kwargs):
        self.model = model
        self.default_params = kwargs

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate a response from a prompt"""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List[Message],
        **kwargs
    ) -> LLMResponse:
        """Generate a response from chat messages"""
        pass

    @abstractmethod
    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream generate response"""
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI API client"""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs
    ):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

        if not self.api_key:
            logger.warning("OpenAI API key not configured")

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate response using OpenAI API"""
        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.append(Message(role="user", content=prompt))

        return await self.chat(messages, **kwargs)

    async def chat(
        self,
        messages: List[Message],
        **kwargs
    ) -> LLMResponse:
        """Chat completion using OpenAI API"""
        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            data = {
                "model": kwargs.get("model", self.model),
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": kwargs.get("temperature", 0.7),
                "max_tokens": kwargs.get("max_tokens", 2048),
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=data,
                )
                response.raise_for_status()
                result = response.json()

            choice = result["choices"][0]

            return LLMResponse(
                content=choice["message"]["content"],
                model=result.get("model", self.model),
                usage=result.get("usage", {}),
                finish_reason=choice.get("finish_reason"),
                raw_response=result,
            )

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream response from OpenAI API"""
        import httpx

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2048),
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            content = chunk["choices"][0].get("delta", {}).get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue


class LLMVendorClient(BaseLLMClient):
    """LLMVendor LLMProvider API client"""

    def __init__(
        self,
        model: str = "llm_provider-3-haiku-20240307",
        api_key: Optional[str] = None,
        **kwargs
    ):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.getenv("LLM_VENDOR_API_KEY")
        self.base_url = "https://api.llm_vendor.com/v1"

        if not self.api_key:
            logger.warning("LLMVendor API key not configured")

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate response using LLMVendor API"""
        messages = [Message(role="user", content=prompt)]
        return await self.chat(messages, system_prompt=system_prompt, **kwargs)

    async def chat(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """Chat completion using LLMVendor API"""
        try:
            import httpx

            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "llm_vendor-version": "2023-06-01",
            }

            data = {
                "model": kwargs.get("model", self.model),
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "max_tokens": kwargs.get("max_tokens", 2048),
            }

            if system_prompt:
                data["system"] = system_prompt

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/messages",
                    headers=headers,
                    json=data,
                )
                response.raise_for_status()
                result = response.json()

            return LLMResponse(
                content=result["content"][0]["text"],
                model=result.get("model", self.model),
                usage={
                    "prompt_tokens": result.get("usage", {}).get("input_tokens", 0),
                    "completion_tokens": result.get("usage", {}).get("output_tokens", 0),
                },
                finish_reason=result.get("stop_reason"),
                raw_response=result,
            )

        except Exception as e:
            logger.error(f"LLMVendor API error: {e}")
            raise

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream response from LLMVendor API"""
        import httpx

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "llm_vendor-version": "2023-06-01",
        }

        data = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": kwargs.get("max_tokens", 2048),
            "stream": True,
        }

        if system_prompt:
            data["system"] = system_prompt

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/messages",
                headers=headers,
                json=data,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            if chunk.get("type") == "content_block_delta":
                                text = chunk.get("delta", {}).get("text", "")
                                if text:
                                    yield text
                        except json.JSONDecodeError:
                            continue


class OllamaClient(BaseLLMClient):
    """Ollama local model client"""

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        **kwargs
    ):
        super().__init__(model, **kwargs)
        self.base_url = os.getenv("OLLAMA_HOST", base_url)

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate response using Ollama API"""
        try:
            import httpx

            data = {
                "model": kwargs.get("model", self.model),
                "prompt": prompt,
                "stream": False,
            }

            if system_prompt:
                data["system"] = system_prompt

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=data,
                )
                response.raise_for_status()
                result = response.json()

            return LLMResponse(
                content=result.get("response", ""),
                model=result.get("model", self.model),
                usage={
                    "prompt_tokens": result.get("prompt_eval_count", 0),
                    "completion_tokens": result.get("eval_count", 0),
                },
                finish_reason="stop" if result.get("done") else None,
                raw_response=result,
            )

        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            raise

    async def chat(
        self,
        messages: List[Message],
        **kwargs
    ) -> LLMResponse:
        """Chat completion using Ollama API"""
        try:
            import httpx

            data = {
                "model": kwargs.get("model", self.model),
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": False,
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=data,
                )
                response.raise_for_status()
                result = response.json()

            return LLMResponse(
                content=result.get("message", {}).get("content", ""),
                model=result.get("model", self.model),
                usage={
                    "prompt_tokens": result.get("prompt_eval_count", 0),
                    "completion_tokens": result.get("eval_count", 0),
                },
                finish_reason="stop" if result.get("done") else None,
                raw_response=result,
            )

        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            raise

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream response from Ollama API"""
        import httpx

        data = {
            "model": kwargs.get("model", self.model),
            "prompt": prompt,
            "stream": True,
        }

        if system_prompt:
            data["system"] = system_prompt

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=data,
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            text = chunk.get("response", "")
                            if text:
                                yield text
                            if chunk.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue


class LLMClientFactory:
    """Factory for creating LLM clients"""

    _clients = {
        "openai": OpenAIClient,
        "llm_vendor": LLMVendorClient,
        "llm_provider": LLMVendorClient,
        "ollama": OllamaClient,
    }

    @classmethod
    def create(
        cls,
        provider: str = "openai",
        model: Optional[str] = None,
        **kwargs
    ) -> BaseLLMClient:
        """
        Create an LLM client

        Args:
            provider: Provider name (openai, llm_vendor, llm_provider, ollama)
            model: Model name (uses default if not specified)
            **kwargs: Additional provider-specific arguments

        Returns:
            LLM client instance
        """
        provider_lower = provider.lower()

        if provider_lower not in cls._clients:
            raise ValueError(f"Unknown LLM provider: {provider}")

        client_class = cls._clients[provider_lower]

        # Set default models
        default_models = {
            "openai": "gpt-4o-mini",
            "llm_vendor": "llm_provider-3-haiku-20240307",
            "llm_provider": "llm_provider-3-haiku-20240307",
            "ollama": "llama3.2",
        }

        if not model:
            model = default_models.get(provider_lower, "gpt-4o-mini")

        return client_class(model=model, **kwargs)

    @classmethod
    def get_default_client(cls) -> BaseLLMClient:
        """Get default LLM client based on environment"""
        # Check for API keys and return appropriate client
        if os.getenv("LLM_VENDOR_API_KEY"):
            return cls.create("llm_vendor")
        elif os.getenv("OPENAI_API_KEY"):
            return cls.create("openai")
        else:
            # Fall back to Ollama for local development
            return cls.create("ollama")


# Convenience function
def get_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs
) -> BaseLLMClient:
    """
    Get an LLM client

    Args:
        provider: Provider name (auto-detected if None)
        model: Model name
        **kwargs: Additional arguments

    Returns:
        LLM client
    """
    if provider:
        return LLMClientFactory.create(provider, model, **kwargs)
    return LLMClientFactory.get_default_client()


__all__ = [
    "LLMResponse",
    "Message",
    "BaseLLMClient",
    "OpenAIClient",
    "LLMVendorClient",
    "OllamaClient",
    "LLMClientFactory",
    "get_llm_client",
]
