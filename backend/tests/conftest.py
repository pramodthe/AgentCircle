"""Keep the test suite offline and deterministic.

Several modules call the process-wide `embed_text()` rather than taking an injected
client, so once a real provider is configured in .env the suite starts making live
embedding calls — which is slow, costs money, and fails against per-minute rate limits
on any low tier. Tests must not depend on a key existing.

Set before any app import so the cached settings and embedding client are built from
these values.
"""

import os

os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["VOYAGE_API_KEY"] = ""
os.environ["MONGODB_AI_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
# Web search is metered per query. A live key here would make `pytest` spend money on
# every run and hit a real third party with fabricated names.
os.environ["EXA_API_KEY"] = ""
# No LLM key either: agent paths must exercise their fallback branches, not the network.
os.environ["FIREWORKS_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["USE_MOCK_MONGODB"] = "true"
# Long enough to satisfy the startup guard in auth.assert_signing_key_is_safe. Tests
# that boot the real app go through that check, so a short throwaway secret fails.
os.environ["JWT_SECRET"] = "test-only-signing-key-that-is-long-enough-to-pass-the-guard"

import pytest  # noqa: E402

from app.embeddings import get_embedding_client  # noqa: E402
from app.settings import get_settings  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _offline_defaults():
    get_settings.cache_clear()
    get_embedding_client.cache_clear()
    settings = get_settings()
    assert settings.embedding_provider == "local", (
        "tests must run on the local embedding provider; a live provider makes the "
        "suite depend on a network key and rate limits"
    )
    # Assert the blanking took, rather than trusting it. Every one of these is a metered
    # third-party call, and the failure mode is a test run that quietly spends money.
    # Blanking an env var yields SecretStr("") rather than None, so check the value.
    for name in ("voyage_api_key", "mongodb_ai_api_key", "exa_api_key", "openai_api_key"):
        secret = getattr(settings, name)
        assert not (secret and secret.get_secret_value()), (
            f"{name} leaked into the test environment"
        )
    yield
    get_settings.cache_clear()
    get_embedding_client.cache_clear()
