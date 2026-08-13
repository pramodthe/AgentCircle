# Design

How the system fits together, and why each seam is where it is. Field names and indexes
are in `data-model.md`; HTTP shapes are in `api.md`. This file owns **module boundaries and
algorithms**.

---

## 1. Shape

```
React 19 / Vite 7 SPA  (port 5173)
  main.tsx → BrowserRouter + AuthProvider → Root.tsx (route guards)
       ├── Landing, HowItWorks, SignIn, Onboarding      pre-shell
       └── AppShell (nested routes, shared chrome)
             Feed · Discover · Community · Messages · Connections · Me
             Interview · Research · PublicProfile
       │  api.ts  →  VITE_API_BASE_URL, Bearer token from localStorage
       ▼
FastAPI (app/main.py)  (port 8000)  — thin routes, all state on app.state via lifespan
       ├── routers/{auth,profile,persona,community,discovery,interviews,
       │            outcomes,social,media,messages,research}.py
       ├── AccountStore        accounts.py      users, profiles, sources, chunks, personas, settings
       ├── CommunityStore      community.py     posts, comments, votes, gaps
       ├── CommunityCommenter  community_agent.py   grounded comment or decline
       ├── OutcomeStore        outcomes.py      outcomes, directional trust, calibration
       ├── InterviewStore      interview.py     async interview runs
       ├── InterviewAgent      interview.py     answer table + verdict
       ├── PersonaBuilder      persona.py       chunk → embed → cited persona
       ├── EmbeddingClient     embeddings.py    voyage | mongodb | openai | local
       ├── PeopleSearch        search.py        $vectorSearch + $search, RRF
       ├── Reranker            rerank.py        cross-encoder over the survivors
       ├── MediaStore          media.py         photos as evidence (§9)
       ├── ProfileMediaStore   profile_media.py avatars/covers (never searchable)
       ├── ConnectionStore     social.py        order-independent pairs
       ├── FeedStore           social.py        posts, stories, reactions, feed media
       ├── MessageStore        messages.py      DMs between accepted connections
       ├── AgentMemoryStore    agent_memory.py  private per-edge memory
       ├── MemoryGraphStore    memory_graph.py  shareable who-knows-whom
       ├── MemoryLog           memory_log.py    append-only learning log + lint
       └── ResearchStore/Exa   research.py      sourced briefs, identity-gated
       ▼
MongoDB 8 (Docker) or Atlas — one database, one layer
```

**One layer, one database.** Every store method takes `user_id` explicitly and filters on
it. There is no second domain, no LangGraph checkpointer, and no `/api/agentcircle/*`.
Only `langchain-openai` remains, for `ChatOpenAI` in `llm.py`.

### Store construction

All stores are built once in `lifespan()` and hung on `app.state`. Routes reach them via
`Annotated[..., Depends(...)]` aliases in `dependencies.py`. Stores return **serialized
dicts** (`serialize()`: ObjectId → str, datetime → ISO-8601 with offset); routes return
plain dicts, not Pydantic response models. The one exception is `AuthResponse`, which is a
response model because the token shape is a contract.

Each store exposes `ensure_indexes()`, called from `lifespan` before serving.

---

## 2. The four invariants everything else rests on

### 2.1 The approval gate

Agents produce **content**. A state change another human sees — publishing a comment,
accepting a connection, sending a message, posting to the feed — happens exclusively
through a separate, user-initiated API call.

No model response may carry an authority-bearing state command. `review_before_publish` is
the same rule inside the community flow; `POST /api/social/feed/draft` returns a draft the
member still has to post.

### 2.2 Model output is untrusted

- Citations are intersected with the chunks actually supplied to the prompt, and dropped
  otherwise (§5.3, §6.2, §8.3).
- Permission maps are allowlisted key by key on write (`safe_community_settings`,
  `safe_interview_settings`, `PROFILE_THEME_FIELDS`).
- The owner of any retrieved data comes from server context, never from model input.
- Research queries are built in code; a model that writes its own queries can be argued
  into researching something else.

### 2.3 Every model call records its mode

`live` · `deterministic_fallback` (no key) · `fallback_after_error` · plus
`no_grounding` (community) and `permission_blocked` (interview). `runtime_mode` travels
with the stored artifact, so a fallback can never be mistaken for a live answer later.

### 2.4 Degrade loudly

Every layer has a working degraded mode and the app looks identical either way. The only
thing stopping a fallback from passing as the real system is saying so:
`GET /api/runtime/status` and `/health` report model, embeddings, rerank, and research
paths; `AppShell`'s status line renders it.

---

## 3. Persona: evidence and summary

Two layers, deliberately separate.

```
persona_sources ──1:N──▶ persona_chunks     verbatim text + embedding + provenance  = EVIDENCE
                              │
                              ▼  extraction
                         personas          structured items, each citing a chunk    = SUMMARY
```

### 3.1 Ingestion (`ingestion.py`)

`extract_upload(filename, data, max_characters)` → `ExtractedSource(title, text, kind,
detail)`; PDF via `pypdf`, DOCX via `python-docx` (paragraphs **and** table cells), plain
text otherwise. `fetch_url(url, timeout, max_characters)` normalises the URL, follows
redirects, decomposes `script/style/noscript/nav/footer/header/form/svg/iframe`, and takes
the title from `<title>` or the first `<h1>`.

`chunk_text(text, size, overlap)` packs paragraphs up to `size` (1200), carrying the last
`overlap` (180) characters forward across a boundary, hard-splitting an oversized paragraph
rather than dropping it. Overlap is clamped to `size // 2`.

### 3.2 `PersonaBuilder.prepare_chunks(source)`

Chunks, then **one** `embed_batch` call, returning rows with `text`, `ordinal`, `embedding`,
`space`, `characters`. Never a loop (C3).

### 3.3 Incremental extraction

```
build(rebuild=False):
    chunks   = all of the user's chunks
    seen     = persona.extracted_source_ids        (empty when rebuild)
    fresh    = chunks whose source_id not in seen
    persona  = extract_incremental(new_chunks=fresh, existing=persona, extras=profile_bits)
    persona.extracted_source_ids = seen ∪ {every source_id}
    persona.learned_now = len(fresh)
```

`extract_incremental` walks `fresh` in windows of `WINDOW = 24`, at most `MAX_WINDOWS = 4`,
and folds each window's extraction into the accumulated persona with `merge_persona`.

**`merge_persona(existing, addition)`** — additive and idempotent:

- items keyed by `_norm(value)` (lowercased, whitespace-collapsed);
- each item accumulates **every** distinct `chunk_id` in `support[]`, with the flat
  `chunk_id`/`source_id`/`source_title` fields promoted from `support[0]` for callers that
  already read them;
- `headline` and `summary` **supersede** when the addition has them — a newer source
  describes a more current person. Evidence-bearing lists never supersede.

**`prune_persona(persona, removed_chunk_ids)`** — drops support entries whose chunk is gone
and any item left with none. This is the only thing that removes a claim (C23).

**`_finalize`** attaches citations: an item whose `chunk_index` is outside the supplied
window is **dropped**, not kept.

**Heuristic path** (`chat.model is None`): headline and lists come from what the member
typed, summary is the opening 600 characters of the first chunk, labelled
`extraction_mode: "heuristic"`. Deliberately thin — a visibly sparse persona beats one that
looks complete but is guessed.

### 3.4 Coverage and lint

`coverage` = `{missing[], score}` over five slots (skills, interests, looking-for,
location, headline). `lint_persona()` is deterministic and model-free: `orphaned_claim`,
`uncited_claim`, `contradiction` (two versions of a claim differing only in a number —
compared by "skeleton", the claim with digits and number-words replaced by `#`),
`unused_source`. It **never** fixes anything: picking a winner between "six years" and
"eight years" would be manufacturing a fact.

---

## 4. Retrieval

### 4.1 Embedding spaces

`space() = f"{_space_provider()}:{_space_model()}:{dimensions}"`, stored beside every
vector; every query filters on it.

- `_space_provider()` maps `{voyage, mongodb} → "voyage"` (C6).
- `_space_model()` maps `voyage-4*` → `voyage-4-series`; dimensions always stay in the key.
- `local` is a 128-dim hashed bag-of-tokens with a `TOKEN_ALIASES` map. Shared vocabulary,
  not meaning. Tests and keyless dev only.
- `EmbeddingError` is **never** caught into a local fallback — mixing spaces inside one
  collection corrupts every later comparison.
- Retries: 429 honours `Retry-After` then exponential backoff to `MAX_RETRIES = 6`;
  4xx other than 429 fails immediately.

`voyage_route(settings)` returns the base URL and key for **all three** Voyage APIs, chosen
by `EMBEDDING_PROVIDER`, so embeddings, rerank, and multimodal spend one quota (C6).

### 4.2 Hybrid people search (`search.py`)

```
query
  ├─ embed ──▶ $vectorSearch over persona_chunks   (filter: user_id ≠ viewer, space)
  │              fallback: scored scan, rescaled to (1 + cos)/2
  └─────────▶ $search over profiles (Lucene, fuzzy maxEdits 1, prefixLength 2,
                 boost ×2 on skills/looking_for/headline, highlights on)
                 fallback: token-overlap with the same field weights
         │
         ▼  reciprocal rank fusion,  RRF_K = 60,  ranked per PERSON not per chunk
    ~60 candidates
         │
         ▼  rerank the top `rerank_candidates` (20) with rerank-2.5
    score = rerank_score × min(1, 0.55 + trust×0.9)      [or fusion × same, if no rerank]
         │
         ▼  match_percent = rerank_score → vector_score → 0/keyword_only     (C8)
         ▼  threshold BEFORE limit; report hidden_below_threshold
         ▼  why_it_clicks (human-readable, no internals)
```

**Why RRF.** Cosine similarity and BM25 are not on a comparable scale; adding them lets
whichever has the wider range dominate. RRF only asks how near the top of its own list a
candidate appeared.

**Why rerank after RRF, not instead of it.** RRF's cost is discarding score magnitude — a
candidate that *dominates* one retriever gets no credit for it. A cross-encoder reads query
and candidate together, which recovers exactly that. Observed: a post scoring 0.9163 while
the next chunk scored 0.72 still ranked its author third; after reranking, first
(0.8438 vs 0.2832), with `match_percent` spreading 99/78/74 instead of clustering 99/98/98.

**What the reranker reads** (`_candidate_text`): headline, top 8 skills, top 4 looking-for,
400 chars of persona summary, then the candidate's evidence excerpts — their own words
first.

**Availability** is probed at startup, never configured (C1). `atlas_enabled=False` is a
kill switch. Both retrievers latch their flag off on a failed aggregate.

### 4.3 Discovery route composition

`discovery.py` pulls the candidate universe once, drops `undiscoverable_ids()` **before**
ranking, resolves trust in one `trust_map` call, runs `search()`, then drops matches whose
`users` document is gone (deleted account), then batches profile images — read *after*
ranking, precisely so a photo can never be a retrieval surface.

### 4.4 Photo search (`media.py`)

A separate endpoint over `voyage:voyage-multimodal-3.5:1024`, deliberately **not** fused
into people search: multimodal vectors are not comparable to text ones, and keeping the
result sets separate keeps them legible as different claims.

The §9 constraint is enforced by four mechanisms, in this order:

1. `appearance_query_reason(query)` refuses **before any vector is computed** — checks
   `APPEARANCE_FRAMES` (an appearance frame turns even a neutral word into a phenotype
   query) then `APPEARANCE_TERMS`. Returns a reason, not results. Gender words are
   deliberately absent (R10.4).
2. `photo_search_enabled` is **opt-in**, applied as `allowed_user_ids` **inside** the
   query in both the Atlas and local paths — never a post-ranking pass.
3. A caption of 12–300 characters is required, and the vector covers caption *and* image.
4. The caption is the evidence in the UI; the image supports the claim.

`MultimodalEmbedder` has **no local fallback**. A hashed stand-in cannot look at an image,
so with no key the surface reports itself off and uploads are stored `indexed: false`.
Endpoint is `/v1/multimodalembeddings` (not `/v1/embeddings`), images as base64 data URLs.

---

## 5. Agent Community

### 5.1 Recruitment (`rank_responders`)

```
for each member with candidate chunks:
    skip unless settings.comment_enabled
    skip if post.topics and member.comment_topics and no overlap
    best_score = max over the member's chunks in the current space
                 (use chunk["score"] when $vectorSearch already produced it)
    skip if best_score < MIN_RECRUIT_SCORE (0.12)

    reputation_factor = 0.5 + reputation/2                    # 0.5 neutral for newcomers
    trust_factor      = min(1.0, 0.55 + trust × 0.9)          # demote only          (C20)
    recruit_score     = best_score × reputation_factor × trust_factor × confidence_multiplier

sort desc, take MAX_RESPONDERS (6)
```

Fit is measured against the member's **best** chunk, not their average: a specialist with
one strong chunk should beat a generalist who is vaguely near the topic everywhere.

Every recruited agent is an LLM call, so this is the dominant cost driver. Only the post
author can trigger it.

`comment_reputation` = `clamp(0.5 + mean(comment.score)/6, 0.05, 1.0)`, defaulting to 0.5
with no history so newcomers can be recruited at all.

### 5.2 The comment (`CommunityCommenter.draft`)

Sees the top 6 ranked chunks as numbered excerpts. The system prompt requires a citation
per substantive claim and states that declining is the correct answer more often than not.
Structured output: `CommentDraft{declined, decline_reason, body, chunk_indexes, offer}`.

### 5.3 `_finalize` — the grounding gate

```
if draft.declined or body is blank            → decline (live)
citations = [chunks[i] for i in chunk_indexes if 0 <= i < len(window)]
if not citations                              → decline (live)   "could not be tied back"
body += "\n\nCould help with: {offer}"        if offer
```

Four decline modes, each with its own `runtime_mode`: `no_grounding` (no chunks at all),
`deterministic_fallback` (no model), `fallback_after_error` (model raised), `live` (the
model or the citation gate declined).

### 5.4 Storage and publication

`_id = cmt_{post_id}_{responder_id}` with a unique index on `(post_id, responder_id)`, so
re-running recruitment updates rather than stacking. `published = not declined and not
review_before_publish`. Declines become `context_gaps` against the **responder**.

Votes are recounted from `comment_votes` (never incremented), a member cannot vote on their
own agent's comment, and the tally feeds `comment_reputation`, which feeds the next
recruitment — that is the loop.

---

## 6. Interviews

### 6.1 Async shape

`POST /api/interviews` validates, checks the subject's `interview_enabled`, writes a
`pending` row, returns **202** in ~0.1s, and queues `_run_interview_job` on
`BackgroundTasks`. Clients poll. Nothing resumes a job across a restart, so
`_resolve_stale` reports a run older than `STALE_AFTER_SECONDS` (300) as failed rather
than spinning forever, and any exception in the job is written onto the interview.

### 6.2 The job

```
question_vectors = embeddings.embed_batch(questions)          # ONE request        (C3)
for each vector:
    grounding  = accounts.search_chunks(subject, vector, space, limit=3)
    remembered = memory.recall(owner=subject, counterparty=asker, vector, space, limit=2)
    chunks_per_question.append(grounding + remembered-as-chunks)
rows, offer  = agent.run(...)
verdict      = agent.verdict(...)
record gaps for every not_in_profile row
graph.record(INTERVIEWED) both directions      — the edge is shareable
memory.remember_many(...)                      — what was said is not
interviews.complete(...)
```

Retrieval is **per question**: a hiring question and a hobbies question need different
parts of the same profile. Memory is offered in the same shape as a chunk so it passes
through the existing citation check rather than around it. Failing to remember must not
fail the interview.

### 6.3 Consent, then the model

```
classify_question(q):  contact  if any CONTACT_MARKERS
                       personal if any PERSONAL_MARKERS
                       else professional

contact                              → decline(permission), unconditionally
personal and not disclose_personal   → decline(permission)
no askable questions left            → runtime_mode = permission_blocked
chat.model is None                   → decline(no_model) for every askable row
```

Consent resolves before the model sees anything, so a boundary cannot be argued out of.

### 6.4 The answer table

Excerpts are numbered **globally** across all questions, so a citation maps to exactly one
chunk. For each returned answer: unresolvable indexes are dropped; if `not answered` or the
answer is blank or **no citation survives**, the row becomes `not_in_profile`. Any askable
question the model omitted is marked `not_in_profile` too — never silently dropped.

### 6.5 Verdict

`coverage = answered / (rows excluding permission declines)` (C22).

`_guard`: a `connect` on coverage < 0.5 is downgraded to `maybe` with the reason prepended;
`confidence = min(model_confidence, coverage)`. The model sees the unanswered rows but
optimizes for a helpful-sounding answer — coverage is the objective floor.

`Verdict.recommendation` is `Literal["connect","maybe","pass"]`. The schema is what makes
hire/date-style verdicts structurally impossible rather than merely discouraged.

Without a model: a count, explicitly labelled as not a judgement, confidence 0.

---

## 7. Outcomes and trust

```
record(reporter, subject, label, context, context_id, predicted_score, note)
  ├─ upsert outcomes on (reporter_id, context_id, subject_id)     idempotent
  ├─ _apply_trust:  trust = trust·(1−w) + score·w,  clamp [0,1]   directional
  └─ _apply_calibration (when predicted_score present):
         bias = Σ(predicted − actual) / samples                   signed
```

For a `community` outcome the route prefers the `recruit_score` the agent actually
predicted over anything the client sent, so calibration measures the agent, not the caller.

### 7.1 Effective trust

```
reliability(r) = min(1, reports/5) × max(0.4, 1 − mean_error)      [accuracy only after 3 samples]

propagated = Σ(trust_i × reliability_i) / Σ reliability_i
weight     = min(1, Σ reliability_i / CONSENSUS_AT)

direct and propagated:  blend = PROPAGATION_WITH_DIRECT × weight
                        value = direct·(1−blend) + propagated·blend
direct only:            value = direct
propagated only:        pull  = PROPAGATION_CEILING × weight
                        value = 0.5 + (propagated − 0.5) × pull
neither:                value = 0.5
```

**The invariant (C21):** no amount of propagated signal may move a member further from
neutral than one first-hand outcome would. `PROPAGATION_CEILING = 0.28`,
`CONSENSUS_AT = 3.0`, `PROPAGATION_WITH_DIRECT = 0.20`, `FULL_RELIABILITY_AT = 5`.
Propagation saturates on accumulated *reliability*, so one established member never speaks
for the network, and a brand-new account moves nothing.

`effective_trust` returns the reasons alongside the number; the UI shows them.

`confidence_multiplier` = `max(0.6, 1 − bias)` when `samples ≥ 3` and `bias > 0`, else 1.0.
An agent that is merely unlucky is not silenced.

---

## 8. Deep research

```
POST /api/research
  gate 1  subject.research_enabled           → 403        opt-in, subject's decision
  gate 2  protected_goal_reason(goal)        → 422        reason, not an empty brief
  gate 3  spend_since(asker, now−24h)        → 429        metered from Exa's costDollars
  gate 4  exa.available                      → 503        no key, no pretence
  ─────────────────────────────────────────────────  nothing above issues a search
  create pending brief → 202
  background:
      queries  = build_queries(name, headline, organization, goal)   ≤ 4, code-authored
      sources  = dedupe(exa.search(q) for q in queries)              5 results each
      confirmed, unconfirmed = corroborate(sources, identity_anchors(profile, name, handle))
      brief    = ResearchAgent.run(name, goal, confirmed, unconfirmed)
      complete(brief, cost, queries)
```

### 8.1 Identity anchors

```
identity_anchors(profile, name, handle):
    name_parts = words(name)
    usable(w)  = len(w) ≥ 4 and w not in ANCHOR_STOPWORDS
                 and no name part contains w and w contains no name part
    from organization, location:  every usable word
    from website:                 the bare domain, if usable
```

**Entity fields only.** Never `role`, never `headline` (C16). Nothing name-derived,
including the handle (C15). With no anchors, nothing can be confirmed — refusing to guess
is the point.

`corroborate` splits sources on whether any anchor appears in
`title + snippet + url`, lowercased. Confirmed sources carry `matched_on`.

### 8.2 Synthesis

`ResearchAgent.run` declines rather than speculating in four cases: no sources at all
(`no_results`); sources but none confirmed (`unconfirmed_identity`); no model (`no_model` —
sources kept, never characterised); nothing survives grounding (`ungrounded`). A finding
whose `source_url` was not in `allowed` is dropped and counted in `dropped_claims`.

`strip_contact_details` runs on every snippet, summary, and claim.

---

## 9. Social layer

**Connections.** `_id = pair_id(a, b)` (sorted, order-independent) so a pair holds exactly
one document. A pending request from the other side becomes an **acceptance** — two people
reaching for each other is a connection, not a conflict. Only the recipient responds; only
the requester withdraws. `source` records provenance; `provenance_counts` is the signal for
which part of the product actually works.

**Feed.** `should_ingest(body, presentation)` gates ingestion at 120 characters for a post,
60 for a story. A story is filed as `kind: "episodic"` with a dated title — a dated episode
and a standing claim are different statements about a person, and an agent that flattens
them reports last Tuesday as a permanent trait. `story_is_active` is decided **server-side**
on a 24h window; only the card expires, never the memory.

Ordering: connections (and the viewer) first, then the wider network, each by recency, so a
young network looks alive rather than empty. Reactions are **recounted** from
`feed_reactions`.

`build_agent_post` is **templated** over stored activity (gap count, interview counts) and
carries the records it came from. A model asked to write this would embellish; the whole
value is that it reports real events. `_join_sentences` avoids doubling terminal
punctuation when a clause ends by quoting a question.

**Media split.** `persona_media` (evidence, embedded, consent-gated) vs `feed_media` /
`story_media` / `profile_media` (presentation, never embedded, never searchable). Bytes for
all of them live in `media_blobs`; the metadata collection is what decides the rules (C25).

**Messages.** Require an **accepted** connection. Keyed on `pair_id`, ordered by a
per-conversation `sequence` (C27). Bodies are **not** ingested as persona chunks.

---

## 10. Memory: two collections, two disclosure levels

```
agent_memory   PRIVATE     what was said on one edge      never traversed, never in persona
memory_edges   SHAREABLE   that an edge exists + topic    traversed by $graphLookup
```

An agent that remembers conversations is more useful and immediately a disclosure risk: if
Kenji's agent recalls what Maya's agent said while Kenji is talking to Priya, a private
exchange has leaked through a third party.

So memory is stored **on the edge**, keyed `pair_id(owner, counterparty)`, and `recall`
filters on `(owner_id, edge_id, space)` **inside the query**. Post-filtering is how this
kind of leak happens — one forgotten branch and the data is already out of the database.

Edge memory is **never merged into the persona**: the persona is what discovery, the
commenter, and third-party interviews all read, so anything reaching it is effectively
public to the network. A memory derived from a cited answer keeps that citation and is
deleted when the chunk is (`forget_chunks`).

`memories_from_interview` writes **both** sides — the asker remembers what they learned,
the subject remembers what they were asked — as separate documents with separate owners.
Only answered rows become the asker's memory; a decline is already a context gap, and
turning "they had nothing on this" into a remembered claim would invert its meaning.

**Traversal** (`reachable`) uses `$graphLookup` at `MAX_DEPTH = 1` (contacts of contacts),
with `restrictSearchWithMatch` applying `allowed_ids` **inside** the walk — a member who
opted out of discovery is not a stepping stone either. Results are people and shared topics
only; never a sentence of memory. Ranked by shared-topic count, then hops. A Python
fallback mirrors the walk where the aggregation is unavailable.

---

## 11. Degradation matrix

| Missing | Effect | How the user is told |
|---|---|---|
| LLM key | Community comments, interview answers, verdicts, research synthesis all take decline paths; feed draft returns the notes lightly polished | `runtime_mode`, `/api/runtime/status`, `extraction_mode: "heuristic"` |
| Voyage key | `local` 128-dim hashed embeddings; rerank off; photo search off, uploads `indexed: false` | `embeddings.semantic: false`, `rerank: "off"`, `/api/media/status` |
| Atlas indexes | Scored scans in Python for chunks, profiles, photos, and graph walk | `retrieval.vector/keyword: "local"`, sidebar reads "Limited search mode" |
| Exa key | Research returns 503 rather than an empty brief | `/api/research/status` |
| MongoDB | `USE_MOCK_MONGODB=true` swaps in mongomock — UI-only, not durable | — |

Rate limits are **not** failures: the embedding client and reranker back off and retry;
only `PERMANENT_STATUSES` disable reranking for the process (C7).

---

## 12. Security posture

- **Boot guard.** `assert_signing_key_is_safe` runs first in `lifespan` and refuses to
  start with the `.env.example` JWT secret against a remote database. Local databases and
  mongomock are exempt so development stays frictionless. Any secret under 32 bytes is
  rejected everywhere. A warning would be the obvious choice and the wrong one.
- **Identity.** Signed JWT only, HS256, 14-day TTL. `CurrentUser` / `OptionalUser`
  dependencies; store methods take `user_id`.
- **Passwords.** bcrypt; > 72 bytes rejected rather than truncated. Login returns one
  message for every failure.
- **Private-by-owner reads.** Interviews filter on `asker_id`; briefs filter on
  `asker_id`; agent memory filters on `owner_id` + `edge_id`; gaps and the learning log
  filter on `user_id`.
- **Unauthenticated routes**, deliberately: `GET /health`, `GET /api/runtime/status`,
  `GET /api/profile/{handle}`, `GET /api/profile/photo/{id}/raw` (an avatar must render on
  a public page — scoped to `profile_media` ids so it can never serve a consent-gated
  persona photo).
- **CORS.** Both spellings of the configured origin; a loopback port regex only when the
  configured origin is itself loopback (C28).

---

## 13. Testing strategy

Pytest only, backend only. `tests/conftest.py` forces `EMBEDDING_PROVIDER=local`, blanks
every provider key, enables mongomock **before any app import**, and then *asserts* it took
effect. Stores are built on `create_mock_client()`; agents are constructed with
`ChatModelBundle(model=None, ...)`. **No test ever calls an LLM or an embedding API** —
keep it that way.

The frontend has no test runner. `npm run build` (`tsc -b && vite build`) is the check.

Every requirement in `requirements.md` names the test that pins it. Every constraint in
`constraints.md` that can be pinned names its test too; the rest are enforced by structure
(separate collections, allowlists, gate ordering).
