# Tasks — build from an empty directory

Implement **in order**. Each task lists:

- **Files** to create or extend
- **Requirements** satisfied
- **Constraints** to re-read before coding
- **Verify** command / test

Check the box only when Verify passes. One task per agent turn when possible.
Backend first inside a phase; then routes; then UI.

After every phase:

```bash
cd backend && uv run pytest
cd ../frontend && npm run build   # once SPA exists
```

---

## Phase 0 — Empty repo → bootable API + SPA shell

### 0.1 Skeleton
- [x] Create tree from `design.md` §2 (empty modules OK).
- **Files:** `.env.example` (Atlas `MONGODB_URI`), 
  `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/main.py` (empty FastAPI),
  `frontend/package.json`, `index.html`, `vite.config.ts`, `tsconfig`s,
  `frontend/src/main.tsx` (hello).
- **Verify:** Atlas URI set in `.env`; `cd backend && uv sync`; `cd frontend && npm install`.
  (No local Docker MongoDB — use Atlas.)

### 0.2 Settings
- [x] Implement `Settings` exactly as `design.md` §3.
- **Files:** `backend/app/settings.py`
- **Req:** 11.3 · **Constr:** C17
- **Verify:** import Settings; loads `../.env`.

### 0.3 Serializers + mock mongo
- [x] `serialize()` ObjectId/datetime → str/ISO with offset.
- [x] `create_mock_client()` + pymongo 4.16 bulk-update shim if needed.
- **Files:** `serializers.py`, `mock_mongo.py`

### 0.4 Signing-key guard + auth primitives
- [x] `assert_signing_key_is_safe`, bcrypt >72 reject, JWT create/decode, CurrentUser.
- **Files:** `auth.py`
- **Req:** 1.2, 11.1, 11.3 · **Constr:** C17
- **Verify:** unit tests for password length + example secret vs remote URI.

### 0.5 Test harness
- [x] `tests/conftest.py` blanks keys **before** app import; asserts empty secrets;
  forces `local` embeddings + mongomock; JWT ≥32 chars.
- **Req:** 11.8 · **Constr:** C16
- **Verify:** `uv run pytest` runs (even if 0 tests).

### 0.6 AccountStore users + public_member
- [x] `create_user`, handles, `public_user`, **allowlist** `public_member`.
- **Files:** `accounts.py` (users section), `schemas.py` Register/Login
- **Req:** 1.1, 11.2 · **Constr:** C13
- **Verify:** `test_accounts.py` — public_member cannot grow new fields; hash never returned.

### 0.7 Auth router + lifespan ping
- [x] Routes `/api/auth/register|login|me`; lifespan connects Mongo; CORS per design §3.
- **Files:** `routers/auth.py`, `main.py`, `dependencies.py`
- **Req:** 1.1, 11.9
- **Verify:** register+login against mongomock via TestClient.

### 0.8 SPA auth shell
- [x] `api.ts` (token + auth namespace), `auth.tsx`, `Root.tsx` guards, `SignIn`+`EnterAs`,
  `demoAccounts.ts`, `AppShell` nav placeholders, `types.ts` auth types, basic `styles.css` tokens.
- **Files:** per `frontend.md`
- **Req:** 16.1, 16.2, 16.5
- **Verify:** `npm run build`; manual login against API.

**Phase 0 done when:** register/sign-in works; pytest offline; SPA builds.

---

## Phase 1 — Evidence layer (persona)

### 1.1 Embeddings
- [x] `EmbeddingClient` + `embed_batch` + `space()` + voyage/mongodb same space + local 128-d.
- **Files:** `embeddings.py` · **Constr:** C1, C14 · **Req:** 1.4, 11.4, 11.5
- **Verify:** `test_embeddings.py`

### 1.2 Ingestion
- [x] PDF/DOCX/TXT/MD + URL fetch + `chunk_text(1200,180)`.
- **Files:** `ingestion.py` · **Req:** 1.3

### 1.3 Sources + chunks in AccountStore
- [x] `add_source`, `list_sources`, `delete_source`, `list_chunks`, `search_chunks`,
  isolation by `user_id` + `space`.
- **Req:** 1.3, 11.1 · **Verify:** isolation tests in `test_accounts.py`

### 1.4 PersonaBuilder extract + citations
- [x] Model + heuristic paths; drop bad citations; refuse empty sources.
- **Files:** `persona.py`, `llm.py` · **Req:** 1.5–1.9
- **Constr:** never invent biography

### 1.5 merge_persona / prune_persona
- [x] Exact algorithms in `design.md` §7.
- **Constr:** C22 · **Req:** 1.10
- **Verify:** `test_persona_incremental.py`

### 1.6 Memory log + lint
- [x] `memory_log.py`; findings never auto-fix.
- **Req:** 1.11 · **Verify:** `test_memory_log.py`

### 1.7 Persona routes
- [x] Full `/api/persona/*` per `api.md`.
- **Files:** `routers/persona.py`
- **Verify:** upload → build → search own chunks.

### 1.8 Onboarding UI + documents panel
- [x] `Onboarding.tsx`, `AgentDocuments.tsx` wired to persona APIs.
- **Req:** 16.2 · **Verify:** `npm run build`

**Phase 1 done when:** resume upload yields a persona where every skill cites a chunk.

---

## Phase 2 — Profiles

### 2.1 Profile CRUD + declared source
- [x] `get_profile`, `update_profile`, `declared_profile_text`, `replace_declared_source`.
- **Constr:** C2 · **Req:** 2.1–2.4
- **Verify:** `test_declared_source.py`

### 2.2 Theme allowlist + not retrievable
- [x] **Constr:** C3 · **Verify:** `test_profile_theme.py` keyword-stuffed background

### 2.3 Profile routes + public handle
- [x] `GET /{handle}` uses `public_member` only.
- **Constr:** C13 · **Req:** 2.8

### 2.4 ProfileView + EditProfile + Me
- [x] Same backdrop/card nesting; padding on shell; redirects `/agent` `/profile`.
- **Constr:** C4 · **Req:** 2.7, 2.9 · **Files:** per `frontend.md`

**Phase 2 done when:** editor skill becomes a `declared` chunk; theme does not.

---

## Phase 3 — Discovery

### 3.1 PeopleSearch local paths
- [x] Vector cosine + keyword local; discoverable filter before rank; drop missing users.
- **Req:** 5.6, 5.7

### 3.2 RRF + match_percent + trust demote stub
- [x] RRF_K=60; match_percent relative; trust multiplier ≤1.
- **Constr:** C6 · **Req:** 5.1, 5.4, 5.5
- **Verify:** `test_search.py`

### 3.3 Atlas probe + index script
- [x] `probe()` real index state; `scripts/create_search_indexes.py`.
- **Constr:** C5 · **Req:** 5.3

### 3.4 Reranker
- [x] off vs skipped; retry 429; permanent latch only on 4xx auth/validation.
- **Constr:** C8, C15 · **Verify:** `test_rerank.py`

### 3.5 Discover router + UI + StackStatus
- [x] `/api/discover`, `/find` page, sidebar status.
- **Req:** 5.1, 11.10, 16.3

**Phase 3 done when:** NL query returns cited people and names the retrieval path.

---

## Phase 4 — Consent

### 4.1 member_settings + safe_* sanitizers
- [x] Defaults per data-model; PATCH merge-then-sanitise.
- **Constr:** C12 · **Req:** 10.1–10.3
- **Verify:** `test_community_api.py` partial PATCH

### 4.2 AgentPermissions UI
- [x] Wired to community + interview settings.
- **Req:** 10.2

**Phase 4 done when:** enabling research cannot reset `discoverable: false`.

---

## Phase 5 — Community + interviews

### 5.1 CommunityStore + rank_responders
- [x] Exact scoring in `design.md` §11; MAX_RESPONDERS=6; MIN=0.12.
- **Files:** `community.py` · **Req:** 4.1–4.3
- **Verify:** `test_community.py`

### 5.2 CommunityCommenter
- [x] draft + finalize citation demotion; runtime_mode; gaps on decline.
- **Files:** `community_agent.py` · **Req:** 4.4–4.7
- **Constr:** no templated opinion

### 5.3 Community router + UI
- [x] recruit author-only; vote recount; review_before_publish; gap demand.
- **Req:** 4.8, 4.9 · **Files:** routers + `Community.tsx`

### 5.4 InterviewAgent + store
- [x] Per-question retrieval; batch embed questions; three decline kinds; coverage math;
  verdict schema + guard; STALE 300s; naive datetime fix.
- **Constr:** C10, C18 · **Req:** 8.1–8.11
- **Verify:** `test_interview.py`

### 5.5 Interview router + UI (table + poll)
- [x] 202 + poll; asker-only GET.
- **Files:** `routers/interviews.py`, `Interview.tsx`

**Phase 5 done when:** ungrounded agent declines; decline shows in gap demand.

---

## Phase 6 — Outcomes / trust

### 6.1 OutcomeStore
- [x] Labels table; exponential trust; calibration; propagation ceiling; reliability.
- **Constr:** C11, C6 · **Req:** 9.1–9.6
- **Verify:** `test_outcomes.py` including 12-account hearsay mob

### 6.2 Wire trust into discover + recruit
- [x] Demote-only multipliers.

### 6.3 Outcomes API + UI hooks on community/interview
- **Files:** `routers/outcomes.py`

**Phase 6 done when:** recording `waste` changes next ranking nameably.

---

## Phase 7 — Social graph + feed

### 7.1 ConnectionStore
- [x] pair_id; cross-accept; permissions; provenance.
- **Req:** 3.1–3.3, 3.7 · **Verify:** `test_social.py`

### 7.2 FeedStore + ingest
- [x] should_ingest thresholds; chunk into persona; agent templated posts; recount reactions.
- **Req:** 3.4–3.6 · **Constr:** C1 (batch embed)

### 7.3 Social router + Feed/Connections UI
- [x] No stock member photos.
- **Constr:** C21 · **Req:** 3.8

**Phase 7 done when:** long niche post becomes discovery evidence.

---

## Phase 8 — Photos + avatars

### 8.1 MediaStore + MultimodalEmbedder
- [x] Caption rules; appearance_query_reason; consent in query; score scale; no local fallback.
- **Constr:** C7, C8 · **Req:** 6.1–6.8
- **Verify:** `test_media.py`

### 8.2 ProfileMediaStore
- [x] Separate module; never embedded.
- **Constr:** C20 · **Req:** 15.1–15.3
- **Verify:** `test_profile_media.py`

### 8.3 Avatar component + purge stock images
- [x] **Constr:** C21 · **Req:** 15.4

### 8.4 Media routes + Photos UI + Discover photo mode

**Phase 8 done when:** activity query ranks right photo; appearance refused; avatar not searchable.

---

## Phase 9 — Deep research

### 9.1 ExaClient + gates + identity_anchors
- [x] Read **C9 in full**. Anchors = org/location/domain only.
- **Constr:** C9, C8 · **Req:** 7.1–7.12
- **Verify:** `test_research.py`

### 9.2 ResearchStore async + stale 420
- [x] **Constr:** C18

### 9.3 Research router + UI
- [x] Unconfirmed unattributed.

**Phase 9 done when:** common-name subject with no public presence declines correctly.

---

## Phase 10 — Edge memory, graph, messages

### 10.1 AgentMemoryStore
- [x] Filter `(owner_id, edge_id, space)` in query; kinds allowlist; forget on chunk delete.
- **Constr:** C19 · **Req:** 12.1–12.6
- **Verify:** `test_agent_memory.py`

### 10.2 Wire memories_from_interview + never merge to persona
- **Req:** 12.3

### 10.3 MemoryGraphStore + `/network/paths`
- [x] Depth 1; discoverable before walk; no memory text.
- **Req:** 14.1–14.5 · **Verify:** `test_memory_graph.py`

### 10.4 MessageStore + routes + Messages UI
- [x] Accepted connection only; pair_id; not ingested.
- **Req:** 13.1–13.5 · **Verify:** `test_messages.py`

### 10.5 AgentMemory panel on Me
- [x] States wall-off plainly.

**Phase 10 done when:** Kenji↔Maya memory cannot appear in Kenji↔Priya recall.

---

## Phase 11 — Product surfaces + honesty

### 11.1 Landing + HowItWorks
- [x] Runtime status; decline equal weight.
- **Req:** 16.1, 16.4

### 11.2 Toast + skeletons everywhere
- **Req:** 16.6

### 11.3 Hardening pass
- [x] ISO timestamps with offset; CORS; discoverable defaults; JWT guard e2e.
- **Verify:** `test_hardening.py`

**Phase 11 done when:** visitor understands grounding without signing in.

---

## Phase 12 — Ops + seed

### 12.1 backup / restore / migrate
- [x] bson.json_util; copy restore into snapshot; refuse non-empty without `--force`.
- **Req:** 11.7

### 12.2 create_search_indexes + reembed docs in README comments

### 12.3 seed_users through ordinary signup path
- [x] Non-uniform consent; no embed on startup.
- **Constr:** C1 · **Req:** 17.1–17.3

### 12.4 Confirm deleted domain stays deleted
- [x] No `/api/agentcircle`, no LangGraph checkpointer.
- **Req:** 17.4

### 12.5 Final definition of done
- [x] All requirements have tests or typed routes; all constraints have tests;
  pytest green offline; `npm run build`; health honest; seed works; **no `.kiro/`**.

---

## Suggested Cursor cadence

1. Attach `@spec/tasks.md` + the design/data-model/api sections for the current phase.
2. Say: “Implement task X.Y only. Do not start the next task.”
3. Run Verify. Mark `[x]`. Commit if the user asks.
4. If a constraint test fails, fix the design violation — do not delete the test.
