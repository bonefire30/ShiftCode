"""
LLM profile configuration and minimal provider adapters for JAVA2GO evaluation.

This module intentionally supports only the fixed evaluation profiles requested by
the project. It is not a general-purpose LLM gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
import time
from typing import Any, Literal

from openai import OpenAI
from security import sanitize_exception

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: S110
    pass


LLMCallStatus = Literal["success", "error"]


@dataclass(frozen=True)
class LLMProfile:
    profile: str
    provider: str
    model: str
    api_key_env: str
    base_url: str | None = None
    temperature: float = 0
    timeout_ms: int = 120_000
    max_tokens: int | None = None


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        return {
            "promptTokens": self.prompt_tokens,
            "completionTokens": self.completion_tokens,
            "totalTokens": self.total_tokens,
        }


@dataclass(frozen=True)
class LLMError:
    type: str
    message: str
    retryable: bool

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "message": self.message, "retryable": self.retryable}


@dataclass(frozen=True)
class LLMResponse:
    text: str
    profile: str
    provider: str
    model: str
    base_url: str | None
    latency_ms: int
    usage: LLMUsage
    llm_call_status: LLMCallStatus
    error: LLMError | None = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "provider": self.provider,
            "model": self.model,
            "baseUrl": self.base_url,
            "latencyMs": self.latency_ms,
            "tokenUsage": self.usage.to_dict(),
            "llmCallStatus": self.llm_call_status,
            "error": self.error.to_dict() if self.error else None,
        }


PROFILES: dict[str, LLMProfile] = {
    "minimax": LLMProfile(
        profile="minimax",
        provider="minimax",
        model="MiniMax-M2.7",
        api_key_env="MINIMAX_API_KEY",
        base_url=os.environ.get("MINIMAX_BASE_URL") or None,
    ),
    "deepseek": LLMProfile(
        profile="deepseek",
        provider="deepseek",
        model="deepseek-v4-flash",
        api_key_env="DEEPSEEK_API_KEY",
        base_url=os.environ.get("DEEPSEEK_BASE_URL") or None,
    ),
    "codex-proxy": LLMProfile(
        profile="codex-proxy",
        provider="openai-compatible",
        model="GPT-5.3 Codex",
        api_key_env="CODEX_PROXY_API_KEY",
        base_url="https://zhaoshuyue.net.cn/v1",
    ),
}


def list_profiles() -> list[dict[str, Any]]:
    return [profile_public_dict(get_profile(name)) for name in PROFILES]


def profile_public_dict(profile: LLMProfile) -> dict[str, Any]:
    return {
        "profile": profile.profile,
        "provider": profile.provider,
        "model": profile.model,
        "baseUrl": profile.base_url,
        "apiKeyEnv": profile.api_key_env,
        "temperature": profile.temperature,
        "timeoutMs": profile.timeout_ms,
        "maxTokens": profile.max_tokens,
    }


def get_profile(name: str | None) -> LLMProfile:
    key = (name or os.environ.get("JAVA2GO_LLM_PROFILE") or "deepseek").strip()
    if key not in PROFILES:
        allowed = ", ".join(sorted(PROFILES))
        raise ValueError(f"invalid llm profile {key!r}; expected one of: {allowed}")
    profile = PROFILES[key]
    if key == "minimax":
        return replace(profile, base_url=os.environ.get("MINIMAX_BASE_URL") or None)
    if key == "deepseek":
        return replace(profile, base_url=os.environ.get("DEEPSEEK_BASE_URL") or None)
    return profile


def mock_enabled() -> bool:
    return (os.environ.get("JAVA2GO_LLM_MOCK") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def require_api_key(profile: LLMProfile, *, allow_mock: bool = True) -> str:
    if allow_mock and mock_enabled():
        return ""
    value = os.environ.get(profile.api_key_env)
    if not value:
        raise RuntimeError(f"missing API key environment variable: {profile.api_key_env}")
    return value


def validate_profile_runtime(profile: LLMProfile, *, allow_mock: bool = True) -> None:
    if allow_mock and mock_enabled():
        return
    require_api_key(profile, allow_mock=False)
    if profile.provider in {"minimax", "deepseek"} and not profile.base_url:
        env_name = "MINIMAX_BASE_URL" if profile.provider == "minimax" else "DEEPSEEK_BASE_URL"
        raise RuntimeError(
            f"missing OpenAI-compatible base URL for profile {profile.profile!r}; set {env_name}"
        )


def llm_metadata(
    profile: LLMProfile,
    *,
    latency_ms: int = 0,
    total_tokens: int | None = None,
    llm_call_status: LLMCallStatus = "success",
    conversion_status: str | None = None,
    prompt_version: str | None = "project-migration-v1",
    error: LLMError | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "profile": profile.profile,
        "provider": profile.provider,
        "model": profile.model,
        "baseUrl": profile.base_url,
        "latencyMs": latency_ms,
        "tokenUsage": {
            "promptTokens": None,
            "completionTokens": None,
            "totalTokens": total_tokens,
        },
        "llmCallStatus": llm_call_status,
        "promptVersion": prompt_version,
        "error": error.to_dict() if error else None,
    }
    if conversion_status is not None:
        metadata["conversionStatus"] = conversion_status
    return metadata


class LLMClient:
    def generate(self, messages: list[dict[str, str]]) -> LLMResponse:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    def __init__(self, profile: LLMProfile) -> None:
        self.profile = profile

    def generate(self, messages: list[dict[str, str]]) -> LLMResponse:
        del messages
        return LLMResponse(
            text=os.environ.get("JAVA2GO_LLM_MOCK_TEXT", ""),
            profile=self.profile.profile,
            provider=self.profile.provider,
            model=self.profile.model,
            base_url=self.profile.base_url,
            latency_ms=0,
            usage=LLMUsage(),
            llm_call_status="success",
        )


class OpenAICompatibleLLMClient(LLMClient):
    def __init__(self, profile: LLMProfile) -> None:
        self.profile = profile
        validate_profile_runtime(profile)
        kwargs: dict[str, Any] = {
            "api_key": require_api_key(profile, allow_mock=False),
            "timeout": profile.timeout_ms / 1000,
        }
        if profile.base_url:
            kwargs["base_url"] = profile.base_url
        self.client = OpenAI(**kwargs)

    def generate(self, messages: list[dict[str, str]]) -> LLMResponse:
        started = time.perf_counter()
        try:
            request: dict[str, Any] = {
                "model": self.profile.model,
                "messages": messages,
                "temperature": self.profile.temperature,
            }
            if self.profile.max_tokens is not None:
                request["max_tokens"] = self.profile.max_tokens
            resp = self.client.chat.completions.create(**request)
            usage = getattr(resp, "usage", None)
            choices = list(getattr(resp, "choices", None) or [])
            if not choices:
                raise ValueError("MalformedResponse: missing choices")
            choice = choices[0]
            msg = getattr(choice, "message", None)
            if msg is None:
                raise ValueError("MalformedResponse: missing choice message")
            return LLMResponse(
                text=str(getattr(msg, "content", "") or ""),
                profile=self.profile.profile,
                provider=self.profile.provider,
                model=self.profile.model,
                base_url=self.profile.base_url,
                latency_ms=int((time.perf_counter() - started) * 1000),
                usage=LLMUsage(
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                    total_tokens=getattr(usage, "total_tokens", None),
                ),
                llm_call_status="success",
            )
        except Exception as exc:  # noqa: BLE001
            return LLMResponse(
                text="",
                profile=self.profile.profile,
                provider=self.profile.provider,
                model=self.profile.model,
                base_url=self.profile.base_url,
                latency_ms=int((time.perf_counter() - started) * 1000),
                usage=LLMUsage(),
                llm_call_status="error",
                error=LLMError(
                    type=exc.__class__.__name__,
                    message=sanitize_exception(exc),
                    retryable=exc.__class__.__name__ in {"APITimeoutError", "APIConnectionError", "RateLimitError"},
                ),
            )


def build_llm_client(profile_name: str | None = None) -> LLMClient:
    profile = get_profile(profile_name)
    if mock_enabled():
        return MockLLMClient(profile)
    return OpenAICompatibleLLMClient(profile)
