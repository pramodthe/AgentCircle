# AgentCircle — build-from-scratch specification

This folder is a **complete engineering contract**. A Cursor agent that has never seen this
repository should be able to recreate AgentCircle by reading only `spec/` +
`PRODUCT_SPEC.md`, then implementing `tasks.md` in order.

**Do not create `.kiro/`, `.kiro/specs/`, or any Kiro config.** Everything lives here as
markdown. The Cursor rule `.cursor/rules/spec-driven.mdc` points agents at this folder.

---

## Read order (mandatory)

| # | File | What you get |
|---|---|---|
| 1 | [`README.md`](README.md) | This file — how to use the spec |
| 2 | [`../PRODUCT_SPEC.md`](../PRODUCT_SPEC.md) | Product thesis, principles, feature intent |
| 3 | [`requirements.md`](requirements.md) | Testable EARS acceptance criteria (R1–R17) |
| 4 | [`constraints.md`](constraints.md) | Bugs that already shipped (C1–C28) — read before coding |
| 5 | [`data-model.md`](data-model.md) | Every Mongo collection, every field, indexes |
| 6 | [`design.md`](design.md) | Architecture, module APIs, algorithms, sequences |
| 7 | [`api.md`](api.md) | Every HTTP endpoint with request/response shapes |
| 8 | [`frontend.md`](frontend.md) | Routes, pages, components, types, `api.ts` |
| 9 | [`tasks.md`](tasks.md) | Ordered build checklist with exact files to create |

If two docs disagree:

| About | Winner |
|---|---|
| What the product *is* | `PRODUCT_SPEC.md` |
| What the code *must do* | `requirements.md` |
| Field names / indexes | `data-model.md` |
| Algorithm / module boundary | `design.md` |
| HTTP contract | `api.md` |
| UI structure | `frontend.md` |
| What looks right but is wrong | `constraints.md` |
| Build order | `tasks.md` |

---

## Cursor rebuild prompt

Open a **new empty directory** (or wipe the code, keep `spec/` + `PRODUCT_SPEC.md`).
Attach `@spec` and `PRODUCT_SPEC.md`. Paste:

```
You are rebuilding AgentCircle from scratch using only the specification in spec/.

ABSOLUTE RULES
1. Read ALL of: spec/README.md, PRODUCT_SPEC.md, spec/requirements.md,
   spec/constraints.md, spec/data-model.md, spec/design.md, spec/api.md,
   spec/frontend.md, then implement spec/tasks.md in order.
2. One task at a time. Mark [x] in tasks.md when that task’s tests pass.
3. Before each task, re-read every constraint it references. Do not skip them.
4. Never create .kiro/ or Kiro files.
5. Never invent biographical facts. Never let a model response change state
   another human sees (approval gate).
6. Identity = signed JWT only. Every store method takes user_id explicitly.
   Other members leave the API only via public_member (_id, display_name, handle).
7. Field names, collection names, and indexes MUST match spec/data-model.md exactly.
8. Algorithms MUST match spec/design.md (merge_persona, rank_responders, trust,
   RRF, appearance_query_reason, identity_anchors, etc.).
9. After each phase: cd backend && uv run pytest && cd ../frontend && npm run build
10. Precedence: PRODUCT_SPEC (product) > requirements (acceptance) > constraints
    (anti-patterns) > data-model / design / api / frontend (implementation).

Start with Phase 0, task 0.1. Stop and report when the phase Done-when criteria pass.
```

---

## What “done” means for a rebuild

- Every checkbox in `tasks.md` is `[x]`.
- `cd backend && uv run pytest` is green with **no network** (`conftest.py` asserts keys blank).
- `cd frontend && npm run build` typechecks.
- `GET /health` reports model / embeddings / rerank / research paths.
- Demo seed works: `uv run python -m scripts.seed_users` → sign in with `maya@example.com` / `agentcircle`.
- No `.kiro/` directory exists.

---

## Stack (locked)

| Layer | Choice |
|---|---|
| Language | Python ≥3.12 (`uv`), TypeScript (Vite 7, React 19) |
| API | FastAPI + uvicorn, port **8000** |
| Web | React Router 7 SPA, port **5173** (`127.0.0.1`) |
| DB | MongoDB Atlas (primary); tests use mongomock |
| Embeddings | `voyage` \| `mongodb` \| `openai` \| `local` (tests use `local`) |
| LLM | openrouter \| openai \| fireworks via `langchain-openai` ChatOpenAI |
| Research | Exa (optional) |
| Rerank | Voyage `rerank-2.5` (optional) |
| Multimodal | Voyage `voyage-multimodal-3.5` (optional) |
| Tests | pytest + mongomock; frontend has **no** Jest — `npm run build` is the check |

---

## Commands (must work after Phase 0)

```bash
cp .env.example .env
# Set MONGODB_URI to Atlas (mongodb+srv://…); no local Docker MongoDB.

cd backend && uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run ruff check .

cd ../frontend && npm install
npm run dev    # http://127.0.0.1:5173
npm run build
```

Escape hatches: `USE_MOCK_MONGODB=true` (UI-only, not durable); empty LLM key → decline paths.

---

## What this spec intentionally omits

- Pixel-perfect CSS. `frontend.md` defines structure, tokens, and honesty rules; visual polish is last.
- Production deploy / CI. Open questions in `PRODUCT_SPEC.md` §12 stay open.
- The deleted single-user demo domain (`/api/agentcircle/*`, LangGraph checkpointer). **Do not rebuild it.**
