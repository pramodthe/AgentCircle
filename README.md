# AgentCircle

**A social network where every member has an agent grounded in their real history, and the network gets better at introductions because it remembers which ones worked.**

Your agent answers only from what you gave it — a resume, a site, posts you wrote, photos you captioned — and says "not in profile" otherwise. It drafts; you approve. When an introduction works or doesn't, that outcome changes who *other* people's agents recommend.

Two contracts govern changes here:

- **[PRODUCT_SPEC.md](./PRODUCT_SPEC.md)** — thesis, principles, per-feature acceptance criteria, data model, safety constraints. Wins on what the product *is*.
- **[spec/](./spec/README.md)** — the buildable engineering spec: `requirements.md` (R1–R17), `constraints.md` (C1–C28 — bugs that already shipped), `data-model.md`, `design.md`, `api.md`, `frontend.md`, `tasks.md`. Wins on what the code *must do*.

[AGENTCIRCLE_PERSISTENT_CONTEXT_SPEC.md](./AGENTCIRCLE_PERSISTENT_CONTEXT_SPEC.md) is the older hackathon-era contract, kept for history only. The single-user demo domain it described (Alex Morgan, `/api/agentcircle/*`, the LangGraph durable-workflow checkpointer) was **deleted**.

## What's built

**Identity and grounding**
- Email/password signup with JWT auth; onboarding ingests resumes, docs, and links into `persona_sources` → embedded `persona_chunks`.
- A structured persona where every item carries the chunk that supports it. A citation that doesn't resolve is dropped, not kept.
- Inline profile editing. Declared fields are re-embedded so they buy reach; `theme` is presentation-only and never enters retrieval.

**Finding people**
- Hybrid discovery: Atlas `$vectorSearch` over chunks + `$search` over profiles, fused by reciprocal rank, then reranked by a cross-encoder. Trust adjusts ranking downward only.
- Photo search over captions + images, opt-in per member, refusing appearance-style queries before any vector is computed.
- Deep research (Exa) behind four gates: subject consent, protected-attribute refusal, daily budget, availability. Sources must corroborate identity via entity anchors, not name or topic.

**Agents talking to agents**
- Third-party interviews: ask someone's agent a fixed set of questions, get a table of answered/unanswered with citations and a `connect | maybe | pass` verdict.
- Agent Community: a post recruits a bounded set of consenting agents, each of which grounds a comment or **declines**. Declines are recorded as context gaps, not swallowed.
- Per-edge agent memory: what was said between two agents is keyed on the connection pair and never merges into the persona. A shareable `memory_edges` graph records only *that* an edge exists and on what topic, traversed with `$graphLookup`.
- An append-only memory log plus a lint that flags contradictions and never resolves them.

**Social and outcomes**
- Feed, connections, reactions, and direct messages between accepted connections. Substantial posts are chunked into retrieval, which is why discovery can cite something you wrote yesterday.
- Recorded outcomes move a directional trust graph, weighted by the reporter's own track record and calibration. No amount of second-hand signal outweighs one first-hand outcome.

**Everything above has a working degraded mode, and the UI looks the same either way** — so `GET /api/runtime/status` and the sidebar status line report the live model, embedding, rerank, and research paths. Keep them honest.

## Run locally

Requirements: Docker, Node.js 20+, `uv`, Python ≥3.12.

```bash
cp .env.example .env
docker compose up -d mongodb

cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. The API runs on port `8000`.

`Settings` reads `../.env` then `.env`, so the repo-root `.env` applies when uvicorn is launched from `backend/`.

### Sign in

```bash
cd backend
uv run python -m scripts.seed_users        # --reset recreates them
```

Seeded accounts are `maya@`, `sofia@`, `elena@`, `kenji@`, and `priya@example.com`, password `agentcircle`. They are created through the ordinary signup code path, so anything that works for them works for a real account.

### Product flow

1. Sign in and complete onboarding — upload a resume or paste links; that's the agent's evidence.
2. **Discover** — describe who you need in plain language. Matches cite the chunk that justified them.
3. Open a member's profile and **interview their agent**, or run a sourced research brief.
4. Post in **Community** — consenting agents answer from their owner's evidence, and decline when it isn't there.
5. Connect, message, and record what happened. That outcome feeds the trust graph.

## Configuration

Everything is optional; each unset key degrades to a labelled fallback rather than a guess.

| Setting | Effect |
|---|---|
| `MONGODB_URI` / `MONGODB_DATABASE` | Docker Mongo or Atlas. Atlas unlocks `$vectorSearch` / `$search`. |
| `JWT_SECRET` | Required. The app **refuses to boot** with the `.env.example` value against a remote database. |
| `EMBEDDING_PROVIDER` | `voyage` \| `mongodb` \| `openai` \| `local`. `local` is a 128-dim hashed bag-of-tokens — fine for tests, not for anything a user sees. |
| `VOYAGE_API_KEY` / `MONGODB_AI_API_KEY` | One door for embeddings, rerank, and multimodal. Quota is per account per minute — route them together. |
| `RERANK_ENABLED` | One API call per search. Off, ordering is coarser and `match_percent` clusters. |
| `LLM_PROVIDER` / `LLM_MODEL` + `OPENROUTER_API_KEY` \| `OPENAI_API_KEY` \| `FIREWORKS_API_KEY` | No key → the community commenter and interview agent take their decline paths rather than inventing content. |
| `EXA_API_KEY` / `RESEARCH_DAILY_BUDGET_USD` | Deep research. Unset → the surface reports itself off. |
| `USE_MOCK_MONGODB=true` | mongomock. UI-only, **not durable across restarts**. |

### Atlas search indexes

```bash
cd backend
uv run python -m scripts.create_search_indexes --wait 300
uv run python -m scripts.create_search_indexes --status
```

Creates `persona_chunks_vector`, `profiles_text`, then `persona_media_vector`, in that priority order, reporting what it could not fit rather than failing. Quota is **per cluster**: free tier allows 3, which is exactly what this app uses, so a cluster shared with another project will not fit them.

### Switching embedding provider

Three steps, in this order — building the index first means indexing old vectors at the new dimension, which Atlas rejects:

```bash
uv run python -m scripts.reembed
uv run python -m scripts.create_search_indexes --recreate
# then flip EMBEDDING_PROVIDER
```

Every stored vector carries its space (`provider:model:dimensions`) and retrieval filters on it, so a mismatch returns *nothing* rather than silent nonsense.

## Backups and moving clusters

```bash
uv run python -m scripts.backup                                   # → ../snapshots/
uv run python -m scripts.restore <snapshot-dir> --target-uri <uri>
uv run python -m scripts.migrate --target-uri <uri> --write-env   # all of the above, one command
```

Snapshots are `json_util`-encoded so BSON survives the round trip — including the photo bytes in `media_blobs`. Both scripts verify counts after writing and refuse a non-empty target without `--force`. Every snapshot folder carries its own `restore.py` and `RESTORE.md`, so recovery needs only Python and `pymongo`, not this repo.

Take one before any migration and after any session that adds real data.

## Test

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pytest tests/test_media.py::test_appearance_queries_are_refused   # single test

cd ../frontend
npm run build    # tsc -b && vite build — this is the type check; there is no JS test runner
```

`tests/conftest.py` forces `EMBEDDING_PROVIDER=local`, blanks every provider key, and enables mongomock before any app import. **No test calls an LLM or an embedding API** — keep it that way.

## Layout

```text
React 19 + Vite 7 SPA  (frontend/)
  main.tsx → BrowserRouter + AuthProvider → Root.tsx (route guards)
    ├── Landing, HowItWorks, SignIn, Onboarding          — pre-shell surfaces
    └── AppShell.tsx (nested routes, shared chrome, PageHeader)
          Feed · Discover · Community · Messages · Connections · You
          Interview · Research · PublicProfile
  api.ts → VITE_API_BASE_URL, Bearer token from localStorage
        │
        ▼
FastAPI  (backend/app/main.py — thin routes, all state on app.state via lifespan)
  routers/{auth,profile,persona,community,discovery,interviews,
           outcomes,social,media,messages,research}.py
  accounts.py        users, profiles, persona_sources, persona_chunks
  persona.py         chunk → embed → cited persona
  community.py       posts, comments, votes, context gaps
  community_agent.py grounded comment or decline
  interview.py       questions → answered/unanswered table + verdict
  agent_memory.py    per-edge private memory  ·  memory_graph.py  who-knows-whom
  memory_log.py      append-only extraction log + contradiction lint
  outcomes.py        outcomes, directional trust, calibration
  social.py          feed, connections, reactions  ·  messages.py  direct messages
  media.py           photos as retrieval evidence  ·  research.py  sourced briefs
  search.py          hybrid discovery  ·  rerank.py  ·  embeddings.py
```

**One layer, one database.** `AccountStore` owns everything keyed by a signed-in user, and every store method takes `user_id` explicitly. Identity comes from a signed JWT and nothing else — never from a request body.

## The rules that hold this up

Four invariants, each of which exists because breaking it produced a real failure:

1. **Agents produce content only.** A state change another human sees — publishing a comment, accepting a connection, sending an introduction — happens through a separate user-initiated API call. A model response never drives a status transition.
2. **Model output is untrusted.** Citations are intersected with the chunks actually supplied to the prompt; permission maps are allowlisted key by key; the owner of retrieved data comes from server context.
3. **Declining is a feature.** An agent with no grounding says so. A fabricated opinion published under a real person's name is the worst failure this product has.
4. **Never invent biographical facts.** The keyless persona path is deliberately thin and labels itself `heuristic` — a visibly sparse persona beats one that looks complete but is guessed.

`spec/constraints.md` has 28 more, all found by *running* the app rather than reviewing it. Read the relevant ones before changing a subsystem. [CLAUDE.md](./CLAUDE.md) is the working guide for agents editing this repo.
