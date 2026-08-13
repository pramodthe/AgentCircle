# Data model

Every MongoDB collection the product uses. Field names, types, defaults, and indexes
are **normative** — a rebuild must match them so tests and the frontend type contracts
align.

Stores return documents through `serialize()`: ObjectId → `str`, datetime → ISO-8601
with UTC offset (`Z` or `+00:00`). Never return raw BSON to the client.

**Partition rule:** anything a member owns is filtered by `user_id` (or `owner_id` /
`asker_id` / `reporter_id`) taken from the JWT, never from a request body.

---

## Collections index

| Collection | Module | Purpose |
|---|---|---|
| `users` | accounts | Auth identity |
| `profiles` | accounts | Declared profile + theme |
| `persona_sources` | accounts | One ingested source |
| `persona_chunks` | accounts | Verbatim evidence + embedding |
| `personas` | accounts | Cited structured summary |
| `member_settings` | accounts | Consent map |
| `community_posts` | community | Agent Community posts |
| `community_comments` | community | Grounded comments / declines |
| `comment_votes` | community | Votes (recounted) |
| `context_gaps` | community | Unanswered demand |
| `outcomes` | outcomes | Recorded interaction outcomes |
| `member_trust` | outcomes | Directional trust |
| `agent_calibration` | outcomes | Agent optimism bias |
| `interviews` | interview | Async interview runs |
| `connections` | social | Order-independent pairs |
| `feed_posts` | social | Feed posts / stories |
| `feed_reactions` | social | Reactions (recounted) |
| `feed_media` | social | Post/clip presentation media |
| `story_media` | social | Story presentation media |
| `media_blobs` | media / profile_media / social | Raw bytes (Binary) |
| `persona_media` | media | Searchable evidence photos |
| `profile_media` | profile_media | Avatar / cover (never embedded) |
| `direct_messages` | messages | DMs between accepted connections |
| `agent_memory` | agent_memory | Private per-edge memory |
| `memory_edges` | memory_graph | Shareable who-knows-whom |
| `memory_log` | memory_log | Append-only learning log |
| `research_briefs` | research | Deep research briefs |

### Atlas Search indexes (exactly 3 on free tier)

| Priority | Index name | Collection | Type |
|---|---|---|---|
| 1 | `persona_chunks_vector` | `persona_chunks` | vectorSearch on `embedding` |
| 2 | `profiles_text` | `profiles` | search (Lucene) |
| 3 | `persona_media_vector` | `persona_media` | vectorSearch on `embedding` |

Create via `scripts/create_search_indexes.py`. Quota is **per cluster**. Report what did
not fit; do not fail the whole script.

---

## Shared helpers

### `pair_id(a, b) -> str`
```
":".join(sorted((a, b)))
```
Used as `_id` for connections, `conversation_id` for DMs, `edge_id` for agent_memory
and memory_edges. One pair → one document.

### Embedding `space`
```
"{provider}:{model}:{dimensions}"
```
- `voyage` and `mongodb` both store provider as **`voyage`** (same model family).
- Local tests: typically `local:…:128`.
- Photo evidence: `voyage:voyage-multimodal-3.5:1024`.
Retrieval **always** filters on `space`. Wrong space → empty results, never silent mix.

### Id prefixes

| Prefix | Entity |
|---|---|
| (uuid hex) | `users._id` |
| `src_` / `src_declared_{user_id}` | persona sources |
| `chk_` | persona chunks |
| `post_` | community posts |
| `cmt_{post_id}_{responder_id}` | community comments (deterministic) |
| `gap_` | context gaps |
| `out_` | outcomes |
| `{reporter_id}:{subject_id}` | member_trust |
| `int_` | interviews |
| `fp_` | feed posts |
| `fm_` | feed media |
| `sm_` | story media |
| `med_` | persona (searchable) media |
| `pm_{kind}_{user_id}` | profile media (deterministic) |
| `dm_` | direct messages |
| `mem_` | agent_memory |
| `log_` | memory_log |
| `res_` | research briefs |

---

## `users`

| Field | Type | Notes |
|---|---|---|
| `_id` | str | uuid hex |
| `email` | str | unique, lowercased |
| `password_hash` | str | bcrypt; never leave API |
| `display_name` | str | ≤80 |
| `handle` | str | unique, `[a-z0-9_]{1,24}`, reserved-word list |
| `onboarding_complete` | bool | default `false` |
| `created_at` | datetime | UTC |
| `updated_at` | datetime | UTC |

**Indexes:** unique `email`, unique `handle`, `created_at` desc.

**Projections:**
- `public_user` — all fields except `password_hash` (**owner only**; includes email).
- `public_member` — allowlist only: `_id`, `display_name`, `handle`.

---

## `profiles`

| Field | Type | Default / limit |
|---|---|---|
| `_id` | str | = `user_id` |
| `user_id` | str | |
| `display_name` | str | ≤80 |
| `headline` | str | ≤160 |
| `bio` | str | ≤2000 |
| `location` | str | ≤120 |
| `pronouns` | str | ≤40 |
| `organization` | str | ≤120 |
| `role` | str | ≤120 |
| `website` | str | ≤300 |
| `availability` | str | ≤120 |
| `skills` | list[str] | max 25 |
| `interests` | list[str] | max 25 |
| `looking_for` | list[str] | max 10 |
| `likes` | list[str] | max 25 |
| `dislikes` | list[str] | max 25 |
| `hobbies` | list[str] | max 25 |
| `theme` | object | see below |
| `created_at` | datetime | |
| `updated_at` | datetime | |

**Theme allowlist** (only these keys; per-key max length):

| Key | Max | Default on create |
|---|---|---|
| `accent` | 24 | `"violet"` |
| `layout` | 40 | `"classic"` |
| `background` | 400 | (optional) |
| `font` | 60 | (optional) |
| `song_url` | 300 | (optional) |

**Theme MUST NOT appear in `declared_profile_text()` or any chunk.**

On profile save: if `declared_profile_text(profile)` length ≥ 80, upsert source
`src_declared_{user_id}` titled `"What you said about yourself"`, kind `declared`,
chunk+embed. Else delete that source / store no chunk. Response includes
`retrieval_synced: bool`.

---

## `persona_sources`

| Field | Type | Notes |
|---|---|---|
| `_id` | str | `src_{hex16}` or `src_declared_{user_id}` |
| `user_id` | str | |
| `title` | str | ≤200 |
| `kind` | str | `declared` \| `upload` \| `link` \| `post` \| `episodic` |
| `detail` | str | ≤400 |
| `characters` | int | |
| `chunk_count` | int | |
| `preview` | str | first ~400 chars |
| `created_at` | datetime | |
| `updated_at` | datetime | |

**Indexes:** `(user_id, created_at desc)`.

---

## `persona_chunks`

| Field | Type | Notes |
|---|---|---|
| `_id` | str | `chk_{hex20}` |
| `user_id` | str | |
| `source_id` | str | |
| `source_title` | str | |
| `text` | str | verbatim |
| `ordinal` | int | order within source |
| `characters` | int | |
| `embedding` | list[float] | |
| `space` | str | `provider:model:dims` |
| `visibility` | str | `"private"` |
| `created_at` | datetime | |
| `updated_at` | datetime | |

**Indexes:** `(user_id, source_id, ordinal)`, `(user_id, space)`, `space`.

Chunking defaults: size **1200**, overlap **180**. Embed via **`embed_batch`**, never a loop.

---

## `personas`

| Field | Type | Notes |
|---|---|---|
| `_id` | str | = `user_id` |
| `user_id` | str | |
| `headline` | str | |
| `summary` | str | |
| `skills` | list[PersonaItem] | |
| `interests` | list[PersonaItem] | |
| `looking_for` | list[PersonaItem] | |
| `notable` | list[PersonaItem] | |
| `extraction_mode` | str | `model` \| `heuristic` \| `empty` |
| `extraction_model` | str \| null | |
| `extraction_error` | str \| optional | |
| `source_count` | int | |
| `chunk_count` | int | |
| `chunks_seen` | int | incremental tracking |
| `extracted_source_ids` | list[str] | |
| `learned_now` | int | last pass delta |
| `coverage` | `{missing: string[], score: 0..1}` | |
| `created_at` | datetime | |
| `updated_at` | datetime | |

**PersonaItem:**
```
{
  "value": str,
  "chunk_id": str,
  "source_id": str,
  "source_title": str,
  "support": [{ "chunk_id", "source_id", "source_title" }]  // optional multi-source
}
```

Citation that does not resolve to a supplied chunk → **drop the item**.
Rebuilds **merge** into existing persona; never silently replace (see design §persona).

---

## `member_settings`

`_id` = `user_id`. Sparse upsert. Defaults applied when missing:

| Field | Default | Notes |
|---|---|---|
| `comment_enabled` | `false` | |
| `comment_topics` | `[]` | from allowlist of 8 topics |
| `review_before_publish` | `true` | |
| `discoverable` | `true` | **opt-out** |
| `photo_search_enabled` | `false` | **opt-in** |
| `research_enabled` | `false` | **opt-in** |
| `interview_enabled` | `false` | |
| `interview_topics` | `[]` | |
| `disclose_personal` | `false` | |
| `created_at` / `updated_at` | datetime | |

**PATCH must merge onto stored values, then sanitise.** Never rebuild from defaults.

**Comment topics allowlist:** `product`, `engineering`, `design`, `hiring`, `fundraising`,
`go_to_market`, `research`, `operations`.

---

## `community_posts`

| Field | Type |
|---|---|
| `_id` | `post_{hex16}` |
| `author_id` | str |
| `title` | ≤200 |
| `body` | ≤6000 |
| `topics` | list[str] |
| `comment_count` | int |
| `declined_count` | int |
| `recruited_at` | datetime \| null |
| `created_at` / `updated_at` | datetime |

---

## `community_comments`

| Field | Type |
|---|---|
| `_id` | `cmt_{post_id}_{responder_id}` unique per pair |
| `post_id` | str |
| `responder_id` | str |
| `body` | ≤2400 |
| `citations` | `[{chunk_id, source_id, source_title, excerpt}]` |
| `declined` | bool |
| `decline_reason` | str |
| `runtime_mode` | `live` \| `no_grounding` \| `deterministic_fallback` \| `fallback_after_error` |
| `model` | str \| null |
| `recruit_score` | float |
| `published` | bool |
| `score` | int |
| `up_votes` / `down_votes` | int |
| `created_at` / `updated_at` | datetime |

**Unique index:** `(post_id, responder_id)`.

If citations empty after verification → demote to `declined: true`.

---

## `comment_votes`

| Field | Type |
|---|---|
| `comment_id` | str |
| `voter_id` | str |
| `value` | -1 \| 0 \| 1 |
| `updated_at` | datetime |

**Unique:** `(comment_id, voter_id)`. Tallies on the comment are **recounted** from these docs.

---

## `context_gaps`

| Field | Type |
|---|---|
| `_id` | `gap_{hex16}` |
| `user_id` | str | subject who could not answer |
| `question` | ≤400 |
| `source` | `community` \| `interview` |
| `post_id` | optional |
| `resolved` | bool default false |
| `resolved_at` | optional |
| `created_at` | datetime |

**Demand grouping:** normalize question (lowercase, strip filler/punctuation, sort content
tokens) → bucket by key → sort by `-count`, `-last_asked`.

---

## `outcomes`

| Field | Type |
|---|---|
| `_id` | `out_{hex}` |
| `reporter_id` | str |
| `subject_id` | str |
| `label` | `great` \| `useful` \| `neutral` \| `waste` \| `passed` |
| `score` | float | from label table |
| `weight` | float | from label table |
| `context` | str e.g. `community` |
| `context_id` | str |
| `predicted_score` | float \| null |
| `note` | ≤400 optional |
| `created_at` / `updated_at` | |
| `cleared_at` | optional |

**Unique:** `(reporter_id, context_id, subject_id)` — idempotent upsert.

### Label table (normative)

| Label | score | weight |
|---|---|---|
| great | 0.95 | 0.30 |
| useful | 0.75 | 0.25 |
| neutral | 0.50 | 0.15 |
| waste | 0.15 | 0.30 |
| passed | 0.35 | 0.08 |

---

## `member_trust`

| Field | Type |
|---|---|
| `_id` | `{reporter_id}:{subject_id}` |
| `reporter_id` | str |
| `subject_id` | str |
| `trust` | float 0..1 | starts near 0.5 |
| `last_score` | float |
| `interactions` | int |
| `created_at` / `updated_at` | |

Directional: A→B ≠ B→A.

**Update:** `trust = current*(1-weight) + score*weight`, clamp [0,1].

**Constants:** `NEUTRAL_TRUST=0.5`, `PROPAGATION_CEILING=0.28`, `CONSENSUS_AT=3.0`,
`PROPAGATION_WITH_DIRECT=0.20`, `FULL_RELIABILITY_AT=5`.

---

## `agent_calibration`

| Field | Type |
|---|---|
| `_id` | = `reporter_id` |
| `samples` | int |
| `total_error` | float |
| `total_abs_error` | float |
| `bias` | float |
| `mean_error` | float |
| timestamps | |

`confidence_multiplier`: if `samples ≥ 3` and `bias > 0` → `max(0.6, 1 - bias)` else `1.0`.

---

## `interviews`

| Field | Type |
|---|---|
| `_id` | `int_{hex16}` |
| `asker_id` | str |
| `subject_id` | str |
| `goal` | str |
| `questions` | list[str] max 8 |
| `status` | `pending` \| `complete` \| `failed` |
| `rows` | list[InterviewRow] |
| `verdict` | `{recommendation, rationale, confidence, …}` |
| `offer` | optional pitch text |
| `runtime_mode` | str |
| `model` | str \| null |
| `answered_count` | int |
| `question_count` | int |
| `blocked_count` | int |
| `error` | str on fail |
| timestamps | |

**InterviewRow:**
```
{
  "question": str,
  "kind": "professional" | "personal" | "contact",
  "answered": bool,
  "answer": str,
  "citations": [...],
  "confidence": float,
  "decline_kind": null | "not_in_profile" | "permission" | "no_model",
  "decline_reason": str
}
```

**Verdict `recommendation`:** only `connect` \| `maybe` \| `pass`.

Readable **only** by `asker_id`. `STALE_AFTER_SECONDS = 300`.

---

## `connections`

| Field | Type |
|---|---|
| `_id` | = `pair_id` |
| `members` | sorted `[a, b]` |
| `requester_id` | str |
| `recipient_id` | str |
| `status` | `pending` \| `accepted` \| `ignored` \| `withdrawn` |
| `note` | ≤400 optional |
| `source` | `discovery` \| `interview` \| `community` \| `feed` \| `direct` |
| `context_id` | optional |
| `responded_at` | optional |
| timestamps | |

Crossing pending requests → **auto-accept**. Only recipient responds; only requester withdraws.

---

## `feed_posts`

| Field | Type |
|---|---|
| `_id` | `fp_*` |
| `author_id` | str |
| `body` | ≤4000 |
| `kind` | `human` \| `agent` |
| `presentation` | `post` \| `story` |
| `evidence` | list (agent posts only) |
| `ingested` | bool |
| `ingested_chunks` | int |
| `image_media_id` | optional |
| `image_media_type` | optional |
| `location` | ≤80 optional |
| `reaction_counts` | `{like?, insightful?, same?}` |
| timestamps | |

**Ingest threshold:** post ≥ **120** chars; story ≥ **60**. Creates a persona source of
kind `post` / episodic. Agent posts are **templated** from stored activity (gaps +
interviews), never free LLM prose.

Stories active for **24 hours**.

---

## `feed_reactions`

Unique `(post_id, user_id)`. Fields: `post_id`, `user_id`, `reaction`
(`like` \| `insightful` \| `same` \| null to clear), `updated_at`.
Counts on the post are **recounted**.

---

## `feed_media` / `story_media`

Presentation-only metadata pointing at `media_blobs`. **Never** embedded into persona
search. Ids `fm_*` / `sm_*`.

---

## `media_blobs`

| Field | Type |
|---|---|
| `_id` | matches media metadata id |
| `user_id` | str |
| `media_type` | e.g. `image/jpeg` |
| `bytes` | BSON Binary |
| `kind` | optional (`post`, `clip`, `avatar`, …) |

Shared by persona photos, profile photos, and feed media. Search never `$lookup`s this
into ranking paths unnecessarily.

---

## `persona_media` (searchable evidence photos)

| Field | Type |
|---|---|
| `_id` | `med_*` |
| `user_id` | str |
| `caption` | 12–300 chars **required** |
| `media_type` | |
| `size_bytes` | max 6MB |
| `embedding` | list[float] \| null |
| `space` | multimodal space or null |
| `indexed` | bool | false if no multimodal key |
| timestamps | |

Max **24** photos per user. Consent filter (`photo_search_enabled`) applied **inside**
the DB query. Opt-in default false.

---

## `profile_media` (avatar / cover)

| Field | Type |
|---|---|
| `_id` | `pm_{kind}_{user_id}` deterministic |
| `user_id` | str |
| `kind` | `avatar` \| `cover` |
| `media_type` | |
| `size_bytes` | |
| `ai_generated` | bool |
| timestamps | |

**Never embedded. Never in `declared_profile_text`. Never in people or photo search.**
No caption required. Separate module from `media.py` on purpose.

Public projection: `{avatar_media_id, avatar_ai_generated, cover_media_id, cover_ai_generated}`.

---

## `direct_messages`

| Field | Type |
|---|---|
| `_id` | `dm_*` |
| `conversation_id` | = `pair_id` |
| `sequence` | int |
| `participants` | sorted `[a,b]` |
| `sender_id` / `recipient_id` | str |
| `body` | ≤2000 |
| `created_at` | monotonic per convo |
| `read_at` | null until marked |

Requires **accepted** connection. Bodies are **not** ingested as persona chunks.

---

## `agent_memory`

| Field | Type |
|---|---|
| `_id` | `mem_*` |
| `owner_id` | str |
| `counterparty_id` | str |
| `edge_id` | = `pair_id` |
| `kind` | `interview_asked` \| `interview_answered` \| `message` \| `outcome` |
| `text` | ≤2000 |
| `embedding` | list[float] |
| `space` | str |
| `chunk_id` | optional |
| `source_title` | optional |
| `created_at` | datetime |

**Every read filters `{owner_id, edge_id, space}` inside the query.** Never merge into
persona. If cited `chunk_id` deleted → delete memory.

**Indexes:** `(owner_id, edge_id, created_at desc)`, `(owner_id, space)`, `chunk_id`.

---

## `memory_edges`

| Field | Type |
|---|---|
| `owner_id` | str |
| `counterparty_id` | str |
| `edge_id` | pair_id |
| `rel` | `INTERVIEWED` \| `CONNECTED` \| `MESSAGED` |
| `strength` | int (incremented) |
| `via` | list[str] shared topics |
| `evidence` | list of `{chunk_id, …}` only if cited |
| `first_seen` / `last_seen` | datetime |

**Unique:** `(owner_id, counterparty_id)`. Traversal: `$graphLookup`, max depth **1**
(contacts-of-contacts). Honour `discoverable` before walk. Paths return identities +
topics only — **never** `agent_memory` text.

---

## `memory_log`

| Field | Type |
|---|---|
| `_id` | `log_*` |
| `user_id` | str |
| `seq` | int |
| `kind` | `source_added` \| `source_removed` \| `persona_learned` \| `memory_written` \| `edge_recorded` |
| `summary` | ≤300 |
| `detail` | object |
| `created_at` | datetime |

Owner-only timeline. Lint (`lint_persona`) is model-free and **never auto-fixes**:
findings `orphaned_claim`, `uncited_claim`, `contradiction`, `unused_source`.

---

## `research_briefs`

| Field | Type |
|---|---|
| `_id` | `res_*` |
| `asker_id` | str |
| `subject_id` | str |
| `goal` | str |
| `status` | `pending` \| `complete` \| `failed` |
| `summary` | str |
| `findings` | list |
| `open_questions` | list |
| `sources` | **confirmed** pages only |
| `unconfirmed_sources` | uncorroborated, unattributed |
| `declined` | bool |
| `decline_reason` / `decline_kind` | |
| `dropped_claims` | int |
| `runtime_mode` / `model` | |
| `cost_usd` / `queries` | |
| `error` | on fail |
| timestamps | |

Readable only by `asker_id`. `STALE_AFTER_SECONDS = 420`. No batch endpoint.

---

## Reserved handles

```
admin, api, agent, agents, about, auth, community, discover, explore, feed,
help, home, login, logout, me, messages, network, new, onboarding, profile,
register, search, settings, signup, support, system, user, users
```

---

## Orphaned / do-not-use collections

These may still exist on old clusters from the deleted demo domain. **Nothing in the
product reads or writes them.** Do not recreate:

`agents`, `memories`, `context_vectors`, `posts`, `conversations`, `messages` (legacy),
`intro_requests`, `agent_memories`, `agent_settings` (legacy), `relationships`,
`checkpoints`, `tasks`, `outcome_events`.
