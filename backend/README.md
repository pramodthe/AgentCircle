# AgentCircle API

FastAPI + MongoDB backend for AgentCircle. Setup, configuration, and the product overview live in the [repository README](../README.md); the engineering contract lives in [`spec/`](../spec/README.md).

`main.py` is a thin route layer — every store, client, and agent is built once in the `lifespan` and hung on `app.state`.

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run ruff check .
uv run pytest
```

`Settings` reads `../.env` then `.env`, so the repo-root `.env` applies when uvicorn is launched from here.

## Scripts

```bash
uv run python -m scripts.seed_users              # 50+ demo members + network; --reset recreates them
uv run python -m scripts.create_search_indexes   # Atlas vector/text indexes (--status, --only, --drop, --recreate, --wait)
uv run python -m scripts.reembed                 # re-embed every vector after a provider change (--dry-run)
uv run python -m scripts.backup                  # snapshot every collection to ../snapshots/
uv run python -m scripts.restore <dir> --target-uri <uri>
uv run python -m scripts.migrate --target-uri <uri> --write-env   # backup + restore + indexes
uv run python -m scripts.check_llm               # confirm LLM_MODEL (default GPT-5.6 Luna) actually answers
```

## Modules

| File | Owns |
|---|---|
| `accounts.py` | users, profiles, `persona_sources`, `persona_chunks` — every method takes `user_id` |
| `auth.py` | JWT issue/verify, `CurrentUser` / `OptionalUser` dependencies |
| `persona.py` · `ingestion.py` | ingest → chunk → embed → cited persona |
| `search.py` · `rerank.py` | `$vectorSearch` + `$search` fused by RRF, then cross-encoder rerank |
| `embeddings.py` | `voyage` \| `mongodb` \| `openai` \| `local`; every vector carries its space |
| `community.py` · `community_agent.py` | posts, votes, context gaps; grounded comment or decline |
| `interview.py` | per-question retrieval → answered/unanswered table + verdict |
| `agent_memory.py` · `memory_graph.py` · `memory_log.py` | private per-edge memory, shareable edge graph, extraction log + lint |
| `outcomes.py` | outcomes, directional trust propagation, calibration |
| `social.py` · `messages.py` | feed, connections, reactions; direct messages |
| `media.py` · `profile_media.py` | photos as retrieval evidence, appearance-query refusal |
| `research.py` | Exa briefs behind consent, protected-attribute, budget, and identity gates |
| `mock_mongo.py` | mongomock swap-in for `USE_MOCK_MONGODB=true` and the test suite |

## Tests

`tests/conftest.py` forces `EMBEDDING_PROVIDER=local`, blanks every provider key, and enables mongomock **before any app import**, then asserts it took effect. Stores are built on mongomock and runtimes constructed with `model=None`, so no test calls an LLM or an embedding API. Keep it that way — the suite went from 55s to rate-limited timeouts the one time a real key leaked in.

```bash
uv run pytest
uv run pytest tests/test_media.py::test_appearance_queries_are_refused
```

## Invariants worth knowing before editing

- **Approval gate.** Agents produce content; a state change another human sees comes from a separate user-initiated call.
- **Untrusted model output.** Citations are intersected with the chunks actually supplied; permission maps are allowlisted key by key; data ownership comes from server context.
- **Mode is always recorded.** `live`, `deterministic_fallback`, `fallback_after_error`, `no_grounding` — `runtime_mode` travels with stored output so a fallback can't be mistaken for a live answer later.
- **Stores return serialized dicts** via `serialize()`; routes return plain dicts, not response models.
- **`public_user` is the owner's own record only** (it keeps `email`). For anyone else use `public_member`, which is an allowlist.
- **Never embed in a loop.** Providers meter by request count — batch through `embed_batch()`. Measured 63.6s versus 0.40s for four questions.

The full list is [`spec/constraints.md`](../spec/constraints.md) (C1–C28) and [`CLAUDE.md`](../CLAUDE.md).
