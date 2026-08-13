# Tasks — build from an empty directory

Implement **in order**. Each task lists:

- **Files** to create or extend
- **Requirements** satisfied (`R*` from `requirements.md`)
- **Constraints** to re-read before coding (`C*` from `constraints.md`)
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
- [x] Create tree from `design.md` §1 (empty modules OK).
- **Files:** `.env.example` (Atlas `MONGODB_URI`), 
  `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/main.py` (empty FastAPI),
  `frontend/package.json`, `index.html`, `vite.config.ts`, `tsconfig`s,
  `frontend/src/main.tsx` (hello).
- **Verify:** Atlas URI set in `.env`; `cd backend && uv sync`; `cd frontend && npm install`.
  (No local Docker MongoDB — use Atlas.)

### 0.2 Settings
- [x] Implement `Settings` exactly as `design.md` §1 Settings.
- **Files:** `backend/app/settings.py`
- **Req:** R17.1 · **Constr:** C4
- **Verify:** import Settings; loads `../.env`.

### 0.3 Serializers + mock mongo
- [x] `serialize()` ObjectId/datetime → str/ISO with offset.
- [x] `create_mock_client()` + pymongo 4.16 bulk-update shim if needed.
- **Files:** `serializers.py`, `mock_mongo.py`
- **Constr:** C12, C13

### 0.4 Signing-key guard + auth primitives
- [x] `assert_signing_key_is_safe`, bcrypt >72 reject, JWT create/decode, CurrentUser.
- **Files:** `auth.py`
- **Req:** R1.3, R1.5, R17.1 · **Constr:** (see design.md §12)
- **Verify:** unit tests for password length + example secret vs remote URI.

### 0.5 Test harness
- [x] `tests/conftest.py` blanks keys **before** app import; asserts empty secrets;
  forces `local` embeddings + mongomock; JWT ≥32 chars.
- **Req:** R17.1 (NFR: offline suite) · **Constr:** C4
- **Verify:** `uv run pytest` runs (even if 0 tests).

### 0.6 AccountStore users + public_member
- [x] `create_user`, handles, `public_user`, **allowlist** `public_member`.
- **Files:** `accounts.py` (users section), `schemas.py` Register/Login
- **Req:** R1.1, R1.2, R1.6, R1.7 · **Constr:** C2
- **Verify:** `test_accounts.py` — public_member cannot grow new fields; hash never returned.

### 0.7 Auth router + lifespan ping
- [x] Routes `/api/auth/register|login|me`; lifespan connects Mongo; CORS per design §12 / C28.
- **Files:** `routers/auth.py`, `main.py`, `dependencies.py`
- **Req:** R1.1, R1.4, R17.9 · **Constr:** C28
- **Verify:** register+login against mongomock via TestClient.

### 0.8 SPA auth shell
- [x] `api.ts` (token + auth namespace), `auth.tsx`, `Root.tsx` guards, `SignIn`+`EnterAs`,
  `demoAccounts.ts`, `AppShell` nav placeholders, `types.ts` auth types, basic `styles.css` tokens.
- **Files:** per `frontend.md` §§1–4, §8–9
- **Verify:** `npm run build`; manual login against API.

**Phase 0 done when:** register/sign-in works; pytest offline; SPA builds.

---

## Phase 1 — Evidence layer (persona)

### 1.1 Embeddings
- [x] `EmbeddingClient` + `embed_batch` + `space()` + voyage/mongodb same space + local 128-d.
- **Files:** `embeddings.py` · **Constr:** C3, C6 · **Req:** R3.5, R17.3, R17.4, R17.5
- **Verify:** `test_embeddings.py`

### 1.2 Ingestion
- [x] PDF/DOCX/TXT/MD + URL fetch + `chunk_text(1200,180)`.
- **Files:** `ingestion.py` · **Req:** R3.1–R3.4, R3.6

### 1.3 Sources + chunks in AccountStore
- [x] `add_source`, `list_sources`, `delete_source`, `list_chunks`, `search_chunks`,
  isolation by `user_id` + `space`.
- **Req:** R3.5–R3.8, R1.5 · **Verify:** isolation tests in `test_accounts.py`

### 1.4 PersonaBuilder extract + citations
- [x] Model + heuristic paths; drop bad citations; refuse empty sources.
- **Files:** `persona.py`, `llm.py` · **Req:** R4.1–R4.6
- **Constr:** C23, C24 — never invent biography

### 1.5 merge_persona / prune_persona
- [x] Exact algorithms in `design.md` §3.3.
- **Constr:** C23 · **Req:** R4.2–R4.5
- **Verify:** `test_persona_incremental.py`

### 1.6 Memory log + lint
- [x] `memory_log.py`; findings never auto-fix.
- **Req:** R4.8, R4.9 · **Verify:** `test_memory_log.py`

### 1.7 Persona routes
- [x] Full `/api/persona/*` per `api.md`.
- **Files:** `routers/persona.py`
- **Verify:** upload → build → search own chunks.

### 1.8 Onboarding UI + documents panel
- [x] `Onboarding.tsx`, `AgentDocuments.tsx` wired to persona APIs.
- **Files:** per `frontend.md` §5 Onboarding · **Verify:** `npm run build`

**Phase 1 done when:** resume upload yields a persona where every skill cites a chunk.

---

## Phase 2 — Profiles

### 2.1 Profile CRUD + declared source
- [x] `get_profile`, `update_profile`, `declared_profile_text`, `replace_declared_source`.
- **Req:** R2.1–R2.4 · **Constr:** C18
- **Verify:** `test_declared_source.py`

### 2.2 Theme allowlist + not retrievable
- [x] **Constr:** C18 · **Req:** R2.5, R2.6 · **Verify:** `test_profile_theme.py` keyword-stuffed background

### 2.3 Profile routes + public handle
- [x] `GET /{handle}` uses `public_member` only.
- **Constr:** C2 · **Req:** R2.7, R2.8

### 2.4 ProfileView + EditProfile + Me
- [x] Same backdrop/card nesting; padding on shell; redirects `/agent` `/profile`.
- **Constr:** C19 · **Req:** R2.6 · **Files:** per `frontend.md` §5 Me / EditProfile / PublicProfile

**Phase 2 done when:** editor skill becomes a `declared` chunk; theme does not.

---

## Phase 3 — Discovery

### 3.1 PeopleSearch local paths
- [x] Vector cosine + keyword local; discoverable filter before rank; drop missing users.
- **Req:** R9.1–R9.4, R9.8 · **Constr:** C1

### 3.2 RRF + match_percent + trust demote stub
- [x] RRF_K=60; match_percent **absolute** (R9.5 / C8); trust multiplier ≤1.
- **Constr:** C8, C9, C20 · **Req:** R9.5–R9.7
- **Verify:** `test_search.py`

### 3.3 Atlas probe + index script
- [x] `probe()` real index state; `scripts/create_search_indexes.py`.
- **Constr:** C1, C5, C26 · **Req:** R9.8

### 3.4 Reranker
- [x] off vs skipped; retry 429; permanent latch only on 4xx auth/validation.
- **Constr:** C7 · **Req:** R9.9, R17.8 · **Verify:** `test_rerank.py`

### 3.5 Discover router + UI + StackStatus
- [x] `/api/discover`, `/find` page, sidebar status.
- **Req:** R9.1, R9.10, R17.6 · **Files:** per `frontend.md` §5 Discover / §4 AppShell

**Phase 3 done when:** NL query returns cited people and names the retrieval path.

---

## Phase 4 — Consent

### 4.1 member_settings + safe_* sanitizers
- [x] Defaults per data-model; PATCH merge-then-sanitise.
- **Constr:** C10, C11 · **Req:** R5.1–R5.5
- **Verify:** `test_community_api.py` partial PATCH

### 4.2 AgentPermissions UI
- [x] Wired to community + interview settings.
- **Req:** R5.1–R5.3 · **Files:** per `frontend.md` §5 Me

**Phase 4 done when:** enabling research cannot reset `discoverable: false`.

---

## Phase 5 — Community + interviews

### 5.1 CommunityStore + rank_responders
- [x] Exact scoring in `design.md` §5.1; MAX_RESPONDERS=6; MIN=0.12.
- **Files:** `community.py` · **Req:** R6.1–R6.8 · **Constr:** C20
- **Verify:** `test_community.py`

### 5.2 CommunityCommenter
- [x] draft + finalize citation demotion; runtime_mode; gaps on decline.
- **Files:** `community_agent.py` · **Req:** R7.1–R7.7, R8.1 · **Constr:** C24
- **Constr:** no templated opinion

### 5.3 Community router + UI
- [x] recruit author-only; vote recount; review_before_publish; gap demand.
- **Req:** R6.1, R7.8, R7.9, R8.2–R8.4 · **Files:** routers + `Community.tsx` (`frontend.md` §5)

### 5.4 InterviewAgent + store
- [x] Per-question retrieval; batch embed questions; three decline kinds; coverage math;
  verdict schema + guard; STALE 300s; naive datetime fix.
- **Constr:** C13, C22, C24 · **Req:** R11.1–R11.14 · **Design:** §6
- **Verify:** `test_interview.py`

### 5.5 Interview router + UI (table + poll)
- [x] 202 + poll; asker-only GET.
- **Files:** `routers/interviews.py`, `Interview.tsx` · **Req:** R11.1, R11.13
  · per `frontend.md` §5 Interview

**Phase 5 done when:** ungrounded agent declines; decline shows in gap demand.

---

## Phase 6 — Outcomes / trust

### 6.1 OutcomeStore
- [x] Labels table; exponential trust; calibration; propagation ceiling; reliability.
- **Constr:** C20, C21 · **Req:** R12.1–R12.11 · **Design:** §7
- **Verify:** `test_outcomes.py` including 12-account hearsay mob

### 6.2 Wire trust into discover + recruit
- [x] Demote-only multipliers.
- **Constr:** C20 · **Req:** R9.7, R6.6, R12.11

### 6.3 Outcomes API + UI hooks on community/interview
- **Files:** `routers/outcomes.py` · **Req:** R12.10, R12.11

**Phase 6 done when:** recording `waste` changes next ranking nameably.

---

## Phase 7 — Social graph + feed

### 7.1 ConnectionStore
- [x] pair_id; cross-accept; permissions; provenance.
- **Req:** R13.1–R13.6 · **Verify:** `test_social.py`

### 7.2 FeedStore + ingest
- [x] should_ingest thresholds; chunk into persona; agent templated posts; recount reactions.
- **Req:** R14.1–R14.8 · **Constr:** C3 (batch embed)

### 7.3 Social router + Feed/Connections UI
- [x] No stock member photos.
- **Constr:** C25 · **Req:** R14.7 · **Files:** per `frontend.md` §5 Feed / Connections · §10 rule 4

**Phase 7 done when:** long niche post becomes discovery evidence.

---

## Phase 8 — Photos + avatars

### 8.1 MediaStore + MultimodalEmbedder
- [x] Caption rules; appearance_query_reason; consent in query; score scale; no local fallback.
- **Constr:** C9, C25 · **Req:** R10.1–R10.9 · **Design:** §4.4
- **Verify:** `test_media.py`

### 8.2 ProfileMediaStore
- [x] Separate module; never embedded.
- **Constr:** C25 · **Req:** R10.8 · **Verify:** `test_profile_media.py`

### 8.3 Avatar component + purge stock images
- [x] **Constr:** C25 · **Files:** per `frontend.md` §10 rule 4

### 8.4 Media routes + Photos UI + Discover photo mode
- **Req:** R10.1, R10.3, R10.8 · **Files:** per `frontend.md` §5 Discover

**Phase 8 done when:** activity query ranks right photo; appearance refused; avatar not searchable.

---

## Phase 9 — Deep research

### 9.1 ExaClient + gates + identity_anchors
- [x] Read **C14–C17 in full**. Anchors = org/location/domain only.
- **Constr:** C14, C15, C16, C17 · **Req:** R16.1–R16.11 · **Design:** §8
- **Verify:** `test_research.py`

### 9.2 ResearchStore async + stale 420
- [x] **Constr:** C13 · **Req:** R16.12

### 9.3 Research router + UI
- [x] Unconfirmed unattributed.
- **Req:** R16.6, R16.9 · **Files:** per `frontend.md` §5 Research · §10 rule 8

**Phase 9 done when:** common-name subject with no public presence declines correctly.

---

## Phase 10 — Edge memory, graph, messages

### 10.1 AgentMemoryStore
- [x] Filter `(owner_id, edge_id, space)` in query; kinds allowlist; forget on chunk delete.
- **Constr:** (design.md §10) · **Req:** R3.7 · **Design:** §10
- **Verify:** `test_agent_memory.py`

### 10.2 Wire memories_from_interview + never merge to persona
- **Design:** §10 · **Req:** R3.7

### 10.3 MemoryGraphStore + `/network/paths`
- [x] Depth 1; discoverable before walk; no memory text.
- **Design:** §10 · **Verify:** `test_memory_graph.py`

### 10.4 MessageStore + routes + Messages UI
- [x] Accepted connection only; pair_id; not ingested.
- **Req:** R15.1–R15.5 · **Verify:** `test_messages.py`
  · **Files:** per `frontend.md` §5 Messages

### 10.5 AgentMemory panel on Me
- [x] States wall-off plainly.
- **Files:** per `frontend.md` §5 Me · §10 rule 9

**Phase 10 done when:** Kenji↔Maya memory cannot appear in Kenji↔Priya recall.

---

## Phase 11 — Product surfaces + honesty

### 11.1 Landing + HowItWorks
- [x] Runtime status; decline equal weight.
- **Req:** R17.6, R17.10 · **Files:** per `frontend.md` §5 Landing / HowItWorks · §10 rules 1–2

### 11.2 Toast + skeletons everywhere
- **Files:** per `frontend.md` §10 rule 10

### 11.3 Hardening pass
- [x] ISO timestamps with offset; CORS; discoverable defaults; JWT guard e2e.
- **Req:** R17.1, R17.7, R17.9 · **Constr:** C12, C28
- **Verify:** `test_hardening.py`

**Phase 11 done when:** visitor understands grounding without signing in.

---

## Phase 12 — Ops + seed

### 12.1 backup / restore / migrate
- [x] bson.json_util; copy restore into snapshot; refuse non-empty without `--force`.
- **Files:** `scripts/backup.py`, `restore.py`, `migrate.py` (see README)

### 12.2 create_search_indexes + reembed docs in README comments
- **Constr:** C5, C26

### 12.3 seed_users through ordinary signup path
- [x] Non-uniform consent; no embed on startup.
- **Constr:** C4 · **Req:** R5.1, R5.2

### 12.4 Confirm deleted domain stays deleted
- [x] No `/api/agentcircle`, no LangGraph checkpointer.
- **Design:** §1 (one layer, one database)

### 12.5 Final definition of done
- [x] All requirements have tests or typed routes; all constraints have tests;
  pytest green offline; `npm run build`; health honest; seed works; **no `.kiro/`**.

---

## Suggested Cursor cadence

1. Attach `@spec/tasks.md` + the design/data-model/api sections for the current phase.
2. Say: “Implement task X.Y only. Do not start the next task.”
3. Run Verify. Mark `[x]`. Commit if the user asks.
4. If a constraint test fails, fix the design violation — do not delete the test.
