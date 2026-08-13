"""Chat-model construction shared by the agent runtime and the persona extractor.

Returns None when no key is configured. Every caller is expected to have a working
no-model path, so a missing key degrades features rather than breaking startup.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_openai import ChatOpenAI

from app.settings import Settings

PROVIDER_BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": None,
    "fireworks": "https://api.fireworks.ai/inference/v1",
}


@dataclass(frozen=True)
class ChatModelBundle:
    model: ChatOpenAI | None
    provider: str
    model_name: str
    warnings: tuple[str, ...] = ()

    @property
    def configured(self) -> bool:
        return self.model is not None


def _is_gpt5_reasoning_model(model_name: str) -> bool:
    """True for GPT-5 reasoning ids, including OpenRouter's `vendor/model` form."""
    bare = model_name.rsplit("/", 1)[-1].lower()
    return bare.startswith("gpt-5") and "chat" not in bare


def normalize_model_name(provider: str, model_name: str) -> tuple[str, list[str]]:
    """Reconcile the configured model id with what the provider actually expects.

    Every provider here speaks the OpenAI wire format but names models differently,
    and a wrong name fails at *invocation* time, not startup. Because the agent layer
    falls back on error by design, that surfaces as "the agent is inexplicably running
    in fallback" rather than as a config error. So flag it loudly up front instead.
    """
    warnings: list[str] = []

    if provider == "openai" and model_name.startswith("openai/"):
        # The vendor prefix OpenRouter requires is rejected by OpenAI itself.
        return model_name.split("/", 1)[1], warnings

    if provider == "fireworks" and not model_name.startswith("accounts/"):
        warnings.append(
            f"LLM_MODEL='{model_name}' is not a Fireworks model id. Fireworks expects "
            "'accounts/fireworks/models/<name>'. Requests will fail and every agent "
            "will silently run in fallback mode."
        )

    if provider == "openrouter" and "/" not in model_name:
        warnings.append(
            f"LLM_MODEL='{model_name}' has no vendor prefix. OpenRouter expects "
            "'<vendor>/<model>', for example 'openai/gpt-5.6-luna'."
        )

    return model_name, warnings


def resolve_provider(settings: Settings) -> tuple[str, str | None]:
    if settings.llm_api_key:
        return settings.llm_provider, settings.llm_api_key.get_secret_value()
    provider_keys = {
        "openrouter": settings.openrouter_api_key,
        "openai": settings.openai_api_key,
        "fireworks": settings.fireworks_api_key,
    }
    configured = provider_keys.get(settings.llm_provider)
    if configured:
        return settings.llm_provider, configured.get_secret_value()
    for provider, key in provider_keys.items():
        if key:
            return provider, key.get_secret_value()
    return settings.llm_provider, None


def build_chat_model(
    settings: Settings, *, temperature: float = 0.0
) -> ChatModelBundle:
    provider, api_key = resolve_provider(settings)
    model_name, warnings = normalize_model_name(provider, settings.llm_model)
    if not api_key:
        return ChatModelBundle(
            model=None,
            provider=provider,
            model_name=model_name,
            warnings=tuple(warnings),
        )

    base_url = settings.llm_base_url or PROVIDER_BASE_URLS[provider]
    # GPT-5 reasoning models reject temperature != 1. ChatOpenAI only auto-drops
    # that when the id starts with "gpt-5"; OpenRouter ids are prefixed
    # (`openai/gpt-5.6-luna`), so we omit it ourselves.
    chat_kwargs: dict = {
        "model": model_name,
        "api_key": api_key,
        "base_url": base_url,
        "timeout": settings.agent_timeout_seconds,
        "max_retries": 2,
    }
    if not _is_gpt5_reasoning_model(model_name):
        chat_kwargs["temperature"] = temperature
    model = ChatOpenAI(**chat_kwargs)
    return ChatModelBundle(
        model=model, provider=provider, model_name=model_name, warnings=tuple(warnings)
    )
