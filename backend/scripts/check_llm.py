"""Verify LLM_MODEL actually exists on the configured provider, and can be called.

Model ids change often and a wrong one fails at request time, not startup. Because the
agent layer falls back on error by design, that surfaces as "everything is mysteriously
in fallback" rather than as a config error. Run this after changing provider or model.

    uv run python -m scripts.check_llm
    uv run python -m scripts.check_llm --list
    uv run python -m scripts.check_llm --list --filter deepseek
"""

from __future__ import annotations

import argparse

import httpx
from pydantic import BaseModel, Field

from app.llm import PROVIDER_BASE_URLS, build_chat_model, resolve_provider
from app.settings import get_settings

DEFAULT_BASE_URLS = {**PROVIDER_BASE_URLS, "openai": "https://api.openai.com/v1"}


class Ping(BaseModel):
    """Trivial schema — the point is proving structured output works at all."""

    ok: bool = Field(description="always true")
    note: str = Field(default="", max_length=80)


def list_models(base_url: str, api_key: str) -> list[str]:
    response = httpx.get(
        f"{base_url.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data", payload if isinstance(payload, list) else [])
    return sorted(row.get("id", "") for row in rows if row.get("id"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print every available model id")
    parser.add_argument("--filter", default="", help="substring filter for --list")
    args = parser.parse_args()

    settings = get_settings()
    provider, api_key = resolve_provider(settings)
    bundle = build_chat_model(settings)
    base_url = settings.llm_base_url or DEFAULT_BASE_URLS.get(provider)

    print(f"provider : {provider}")
    print(f"model    : {bundle.model_name}")
    print(f"base_url : {base_url}")
    for warning in bundle.warnings:
        print(f"WARNING  : {warning}")

    if not api_key:
        print("\nNo API key configured — set the key for this provider and re-run.")
        return

    try:
        available = list_models(base_url, api_key)
    except httpx.HTTPError as exc:
        print(f"\nCould not list models: {exc}")
        available = []

    if args.list and available:
        shown = [m for m in available if args.filter.lower() in m.lower()]
        print(f"\n{len(shown)} model(s){' matching ' + args.filter if args.filter else ''}:")
        for model in shown:
            print(f"  {model}")
        return

    if available:
        if bundle.model_name in available:
            print(f"\nOK: '{bundle.model_name}' is available on {provider}.")
        else:
            print(f"\nNOT FOUND: '{bundle.model_name}' is not in {provider}'s model list.")
            needle = bundle.model_name.rsplit("/", 1)[-1].split("-")[0]
            close = [m for m in available if needle and needle in m.lower()]
            if close:
                print("Closest matches:")
                for model in close[:12]:
                    print(f"  {model}")
            print("\nRun with --list to see everything.")
            return

    # Availability is not the same as usability: every structured path in this app
    # needs function calling, and plenty of served models do not have it.
    print("\nTesting structured output (required by persona, community, negotiation)…")
    try:
        result = bundle.model.with_structured_output(Ping).invoke(
            [{"role": "user", "content": "Reply with ok=true and a two-word note."}]
        )
        print(f"  OK: structured output works — {result}")
    except Exception as exc:
        print(f"  FAILED: {type(exc).__name__}: {str(exc)[:220]}")
        print(
            "  This model cannot serve structured output, so every agent will run in "
            "fallback. Pick a model with function-calling support."
        )


if __name__ == "__main__":
    main()
