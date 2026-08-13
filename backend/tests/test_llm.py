from app.llm import ChatModelBundle, build_chat_model, normalize_model_name, resolve_provider
from app.settings import Settings


def test_openai_strips_the_openrouter_vendor_prefix() -> None:
    name, warnings = normalize_model_name("openai", "openai/gpt-4o-mini")
    assert name == "gpt-4o-mini"
    assert warnings == []


def test_fireworks_flags_a_non_fireworks_model_id() -> None:
    """The default OpenRouter model would 404 on Fireworks and silently fall back."""
    name, warnings = normalize_model_name("fireworks", "openai/gpt-4o-mini")
    assert name == "openai/gpt-4o-mini", "the name is not rewritten, only flagged"
    assert warnings and "accounts/fireworks/models/" in warnings[0]


def test_fireworks_accepts_a_proper_model_id() -> None:
    name, warnings = normalize_model_name(
        "fireworks", "accounts/fireworks/models/kimi-k2-instruct"
    )
    assert name == "accounts/fireworks/models/kimi-k2-instruct"
    assert warnings == []


def test_openrouter_flags_a_missing_vendor_prefix() -> None:
    _, warnings = normalize_model_name("openrouter", "gpt-4o-mini")
    assert warnings and "vendor prefix" in warnings[0]


def test_provider_resolution_prefers_the_configured_provider_key() -> None:
    settings = Settings(
        llm_provider="fireworks",
        fireworks_api_key="fw-secret",
        openrouter_api_key="or-secret",
    )
    provider, key = resolve_provider(settings)
    assert provider == "fireworks"
    assert key == "fw-secret"


def test_provider_falls_back_to_any_available_key() -> None:
    settings = Settings(llm_provider="fireworks", openrouter_api_key="or-secret")
    provider, key = resolve_provider(settings)
    assert provider == "openrouter", "should use the key that actually exists"
    assert key == "or-secret"


def test_no_key_yields_an_unconfigured_bundle_that_still_carries_warnings() -> None:
    bundle = build_chat_model(Settings(llm_provider="fireworks", llm_model="gpt-4o-mini"))
    assert isinstance(bundle, ChatModelBundle)
    assert bundle.configured is False
    assert bundle.warnings, "a bad model id should be reported even before a key is added"
