# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Spec-driven workflow

This repo is built from markdown contracts, not from the code. Before implementing anything non-trivial, read the relevant contract; when requirements change, update the spec **first**, then the code.

Precedence when docs disagree:

| About | Winner |
|---|---|
| What the product *is* | `PRODUCT_SPEC.md` |
| What the code *must do* | `spec/requirements.md` (R1–R17) |
| What looks right but is wrong | `spec/constraints.md` (C1–C28) |
| Collections / fields / indexes | `spec/data-model.md` |
| Algorithms, module boundaries | `spec/design.md` |
| HTTP contract | `spec/api.md` |
| Routes, pages, `api.ts` | `spec/frontend.md` |
| Build order | `spec/tasks.md` |

`spec/constraints.md` is the highest-value file in the repo: **every entry is a bug that already shipped**, written as "the obvious implementation → what actually happened → the rule". Read the constraints for a subsystem before changing it — each one describes a change that will look like a simplification and will re-introduce a real failure. Prefer executing unchecked items in `spec/tasks.md` over inventing scope.

Never create `.kiro/`. Never rebuild the deleted single-user demo domain (`/api/agentcircle/*`, the LangGraph durable-workflow checkpointer, "Alex Morgan").

## Commands

```bash
# Backend (port 8000) — Python ≥3.12 via uv
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run ruff check .                 # line-length 100, select E,F,I,UP,B
uv run pytest
uv run pytest tests/test_media.py::test_appearance_queries_are_refused   # single test

# Frontend (port 5173, bound to 127.0.0.1)
cd frontend
npm install
npm run dev
npm run build      # tsc -b && vite build — this IS the type check; there is no JS test runner
```

Backend scripts (all from `backend/`, all `uv run python -m scripts.<name>`):

| Script | Use |
|---|---|
| `seed_users` | Demo accounts (`maya@`/`sofia@`/`elena@`/`kenji@`/`priya@example.com`, password `agentcircle`); `--reset` recreates. Goes through the ordinary signup path. |
| `create_search_indexes` | Atlas vector/text indexes; `--status`, `--only`, `--drop`, `--recreate`, `--wait` |
| `reembed` | Rewrite every vector after an embedding-provider change; `--dry-run` |
| `backup` / `restore` / `migrate` | Snapshot to `../snapshots/`, restore, or both + indexes in one command |
| `check_llm` | Confirm the configured model actually answers |

`tools/api_tester/` is a Streamlit UI for hitting the API without the SPA (`uv run --with streamlit --with httpx streamlit run app.py`).

## Configuration

`.env` lives at the **repo root**. `Settings` reads `../.env` then `.env`, so the root file applies when uvicorn is launched from `backend/`. `.env.example` holds names only.

Every key is optional and each unset key degrades to a *labelled* fallback rather than a guess: no LLM key → agents take decline paths; no Voyage key → rerank and photo search report themselves off; `EMBEDDING_PROVIDER=local` is a 128-dim hashed bag-of-tokens for tests and keyless dev, never for anything a user sees. `USE_MOCK_MONGODB=true` swaps in mongomock (UI-only, not durable). `JWT_SECRET` is the one hard gate: the app **refuses to boot** with the `.env.example` value against a remote database.

Switching embedding provider has exactly one correct order (C5): `reembed` → `create_search_indexes --recreate` → flip `EMBEDDING_PROVIDER`. Every stored vector carries its space (`provider:model:dimensions`) and retrieval filters on it, so a mismatch returns *nothing* rather than silent nonsense. `voyage` and `mongodb` deliberately share one space — `ai.mongodb.com` serves the same Voyage models (C6).

Atlas index quota is **per cluster** (free tier: 3), and this app needs exactly 3: `persona_chunks_vector`, `profiles_text`, `persona_media_vector`. A scoped DB user only sees its own database's indexes, so the cluster can be at quota while the app sees room (C26).

## Architecture

**One layer, one database.** No service layer, no second store, no ORM. `AccountStore` and its siblings own everything keyed by a signed-in user, and **every store method takes `user_id` explicitly**. Identity comes from a signed JWT and nothing else — never from a request body.

Wiring, which is the thing worth knowing before editing any route:

- `backend/app/main.py` `lifespan()` constructs every store, client, and agent **once** and hangs them on `app.state`; each store's `ensure_indexes()` runs there before serving.
- `dependencies.py` exposes them as `Annotated[X, Depends(get_x)]` aliases; routers in `app/routers/` are thin and stay thin.
- Stores return **serialized dicts** (`serialize()`: ObjectId → str, datetime → ISO-8601 *with* offset). Routes return plain dicts, not Pydantic response models — `AuthResponse` is the deliberate exception because the token shape is a contract.
- `main.py` also owns `/health` and `/api/runtime/status`, which report the live model / embedding / rerank / research paths.

Domain modules (see `backend/README.md` for the full table): `accounts` (users, profiles, `persona_sources`, `persona_chunks`) · `persona` + `ingestion` (ingest → chunk → embed → cited persona) · `search` + `rerank` + `embeddings` (`$vectorSearch` + `$search` fused by RRF, then cross-encoder) · `community` + `community_agent` · `interview` · `agent_memory` / `memory_graph` / `memory_log` · `outcomes` (directional trust, calibration) · `social` + `messages` · `media` / `profile_media` · `research`.

Frontend: `main.tsx` → `BrowserRouter` + `AuthProvider` → `Root.tsx` (route guards: `Protected` sends a signed-in user with no persona to `/onboarding`; `AnonymousOnly` bounces to the feed) → `AppShell.tsx` (nested routes + shared chrome, including the `StackStatus` line that renders the runtime truth). All HTTP goes through `src/api.ts` (`VITE_API_BASE_URL`, Bearer token from `localStorage`).

## Invariants

These are not style preferences; each exists because breaking it produced a real failure.

1. **Approval gate.** Agents produce *content* only. A state change another human sees — publishing a comment, accepting a connection, sending a message, posting to the feed — happens through a separate, user-initiated API call. A model response never drives a status transition.
2. **Model output is untrusted.** Citations are intersected with the chunks actually supplied to the prompt and dropped otherwise; an answer left with no surviving citation becomes a decline, never a publication (C24). Permission maps are allowlisted key by key. Data ownership comes from server context. Research queries are built in code.
3. **Declining is a feature.** An agent with no grounding says so. A fabricated opinion published under a real person's name is the worst failure this product has. Never invent biographical facts — the keyless persona path is deliberately thin and labels itself `heuristic`.
4. **Mode is always recorded.** `live` · `deterministic_fallback` · `fallback_after_error` · `no_grounding` · `permission_blocked`. `runtime_mode` travels with the stored artifact so a fallback can't be mistaken later for a live answer. Every layer has a working degraded mode and the UI looks identical either way — saying so is the only safeguard.
5. **`public_member` is an allowlist** (`_id`, `display_name`, `handle`) for everyone who isn't the owner; `public_user` keeps `email` and is the owner's own record only (C2).
6. **Never embed in a loop.** Providers meter by request count — batch through `embed_batch()`. Measured 63.6s vs 0.40s for four questions (C3). Nothing on the startup path may embed (C4).
7. **Trust demotes, never promotes** (C20), and no amount of propagated hearsay may move trust further than one first-hand outcome (C21). Re-run `test_no_amount_of_hearsay_outweighs_one_first_hand_outcome` after touching any constant in `outcomes.py`.
8. **Evidence photos and decoration are different collections** (C25). `persona_media` is embedded, caption-required, consent-gated; `profile_media` / `feed_media` is never embedded, never indexed, never reachable from a search endpoint. The separation *is* the enforcement.

## Locked stack

Do not introduce substitutes without an explicit spec change (`.cursor/rules/tech-stack.mdc`):

- **Backend:** Python ≥3.12 + FastAPI + uvicorn only. No second backend runtime.
- **Data + vectors:** MongoDB Atlas, same cluster for `$vectorSearch`. No Postgres, Redis-as-primary, Pinecone/Weaviate/Chroma/Qdrant.
- **LLM:** via `langchain-openai` `ChatOpenAI` against an OpenAI-compatible base URL; providers already wired are `openrouter | openai | fireworks`. LangChain/LangGraph/LangSmith are for agent orchestration and tracing **only** — not HTTP routing, auth, CRUD, or persistence.
- **Frontend:** React 19 + Vite 7 + TypeScript SPA, React Router 7. No server-side agent runtime in the frontend.

Prefer extending existing collections and indexes over adding new ones, and keep FastAPI routes thin.

## Tests

`tests/conftest.py` forces `EMBEDDING_PROVIDER=local`, blanks every provider key, and enables mongomock **before any app import**, then asserts it took effect. Several modules call the process-wide `embed_text()` rather than an injected client, so the moment a real key reaches the test environment the suite starts making live, billed, rate-limited calls — it went from 55s to timeouts the one time that happened. **No test may call an LLM or an embedding API.** Do not remove or weaken that file.

Stores are built on mongomock; agent runtimes are constructed with `model=None` so the decline/fallback branches are what gets exercised. `mock_mongo.py` monkeypatches mongomock's bulk-update signature to match PyMongo 4.16 — if a pymongo bump breaks bulk writes under test, look there first.
