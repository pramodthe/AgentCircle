# HTTP API

Every endpoint the product exposes. Base URL `http://localhost:8000`.

**Conventions**

- Auth is `Authorization: Bearer <jwt>`. Routes marked **public** take none; everything
  else returns `401` without a valid token.
- Request bodies are JSON unless the route is marked `multipart/form-data`.
- Responses are plain dicts serialized by `serialize()` — `_id` is a string, every
  datetime is ISO-8601 **with an explicit UTC offset**.
- Errors are FastAPI's `{"detail": "..."}`. `422` bodies may carry Pydantic's list form;
  the client reads `detail[0].msg` in that case.
- No route accepts an owner id in its body. Ownership comes from the token (R1.5).

---

## Health and runtime

### `GET /health` — public
Pings Mongo, then returns the live stack.
```json
{ "status": "ok", "database": "mongodb",
  "model": {"configured": bool, "provider": "openrouter", "model": "openai/gpt-4o-mini",
            "mode": "live" | "deterministic_fallback", "warnings": []},
  "embeddings": {"provider","model","dimensions","space","degraded","semantic"},
  "rerank": {"enabled": bool, "model": str|null, "degraded": bool},
  "research": {"available": bool, "provider": "exa"|null, "search_type": "auto"} }
```

### `GET /api/runtime/status` — public
The same four blocks without the database ping. Used by the explainer page.

---

## Auth — `/api/auth`

### `POST /api/auth/register` → `201`
```json
{ "email": "maya@example.com", "password": "≥8 ≤72 bytes",
  "display_name": "Maya Chen", "handle": "optional ≤24" }
```
→ `AuthResponse`: `{access_token, token_type: "bearer", user: public_user, onboarding}`
`409` if the email exists.

### `POST /api/auth/login` → `200`
`{email, password}` → `AuthResponse`. `401` with one identical message for every failure.

### `GET /api/auth/me`
`{user: public_user, profile, persona, onboarding}`.

`onboarding` = `{complete, steps: {account, profile, sources, extras, persona}, source_count, coverage}`.

---

## Profile — `/api/profile`

### `GET /api/profile`
The signed-in member's profile, plus `avatar_media_id`, `avatar_ai_generated`,
`cover_media_id`, `cover_ai_generated`.

### `PATCH /api/profile`
Any subset of: `display_name headline bio location pronouns organization role website
availability skills interests looking_for likes dislikes hobbies theme`.
Unknown keys are ignored; `theme` is allowlisted to `accent background font layout song_url`.

→ the updated profile **plus `retrieval_synced: bool`** (R2.4). `false` means the profile
saved but the declared-claims source could not be embedded — the UI must say "Saved, but
not searchable yet".

### `POST /api/profile/photo` → `201` · `multipart/form-data`
`file`, `kind` = `avatar` | `cover`, `ai_generated` = bool.
→ the `profile_media` row. `422` for an unknown slot or unsupported type.
**Never embedded, never searchable** (C25).

### `DELETE /api/profile/photo/{kind}` → `204`

### `GET /api/profile/photo/{media_id}/raw` — public
Image bytes, `Cache-Control: public, max-age=3600`. Scoped to `profile_media` ids, so it
can never serve a consent-gated persona photo.

### `GET /api/profile/{handle}` — public
```json
{ "user": {"_id","display_name","handle"},          // public_member — allowlist
  "profile": { ...profile, ...profile media ids },
  "persona": {"headline","summary","skills":[str],"interests":[str],"looking_for":[str]} }
```
Persona **summary only**. Raw chunks stay private. `404` if the handle is unknown.

---

## Persona — `/api/persona`

### `GET /api/persona`
`{persona, sources, onboarding}`.

### `POST /api/persona/sources/upload` → `201` · `multipart/form-data`
`file`: `.pdf .docx .txt .md .markdown`, ≤8MB.
→ the `persona_sources` row. `413` too large · `422` unsupported type or no readable text.

### `POST /api/persona/sources/link` → `201`
`{url}` — scheme optional, added as `https://`. → the source row. `422` if unfetchable or
empty.

### `GET /api/persona/sources` → `PersonaSource[]`

### `DELETE /api/persona/sources/{source_id}` → `204`
Deletes the source, its chunks, any persona claim left without support, and any
`agent_memory` citing a removed chunk. `404` if it is not yours.

### `POST /api/persona/build?rebuild=false`
Learns from every source not already in `extracted_source_ids`, merging into the stored
persona. `?rebuild=true` re-derives from scratch. Marks onboarding complete.
→ `{persona, onboarding}`. `409` when the member has no chunks yet.

### `GET /api/persona/log?limit=50` → `LearningEntry[]`
Owner-only, newest first, ordered by `seq`.

### `GET /api/persona/lint`
`{findings: LintFinding[], clean: bool}`. Deterministic, model-free, never auto-fixes.

### `GET /api/persona/search?q=&limit=6`
Your own grounded chunks — what an agent answer would cite. `422` if `q` < 3 chars.

---

## Community — `/api/community`

### `GET /api/community/settings` · `PATCH /api/community/settings`
`{comment_enabled, comment_topics[], review_before_publish, discoverable,
photo_search_enabled, research_enabled}`.

**PATCH merges onto stored values, then sanitises** (C10). Topics are filtered against the
8-topic allowlist. Defaults: everything closed except `discoverable: true` and
`review_before_publish: true`.

### `GET /api/community/posts` → `CommunityPost[]`
Newest first, each decorated with `author: {display_name, handle}`.

### `POST /api/community/posts` → `201`
`{title: 6–200, body: 20–6000, topics?: ≤8}`. Topics are inferred from the text when
omitted.

### `GET /api/community/posts/{post_id}`
```json
{ "post": {...,"author":{...}},
  "comments": [ ...CommunityComment, "responder": {user_id, display_name, handle, headline} ],
  "my_votes":   {comment_id: -1|1},
  "my_outcomes":{subject_id: Outcome},
  "trust":      {responder_id: TrustBreakdown} }
```
Answers first (best-voted first); declines sink to the bottom but are kept.

### `POST /api/community/posts/{post_id}/recruit`
**Author only** — `403` otherwise, because every recruited agent is an LLM call.
Embeds the post, retrieves candidate chunks, ranks by fit × reputation × trust ×
confidence, caps at 6, drafts a comment per responder, records declines as context gaps.
```json
{ "post": {...}, "recruited": int, "commented": int, "declined": int,
  "reason": "…"   // only when nothing was eligible
}
```

### `POST /api/community/comments/{comment_id}/vote`
`{value: -1 | 0 | 1}` → the recounted comment. `403` on your own agent's comment.

### `GET /api/community/pending` → `CommunityComment[]`
Your agent's comments awaiting your release (`published: false, declined: false`).

### `POST /api/community/comments/{comment_id}/publish`
`404` if it is not yours. This is the approval gate — the model never publishes.

### `GET /api/community/gaps` → `ContextGap[]`
Unresolved questions your agent could not answer.

### `GET /api/community/gaps/demand`
`{demand: [{key, question, count, sources[], ids[], last_asked}], total_unanswered}`.
Grouped by normalised question, ranked by count then recency.

### `POST /api/community/gaps/resolve`
`{gap_ids: [1..50]}` → `{resolved: int}`. Scoped to the owner.

---

## Discovery — `/api/discover`

### `POST /api/discover`
```json
{ "query": "8–500 chars", "limit": 1–25 (8), "min_match_percent": 0–100 (50) }
```
```json
{ "query": "...",
  "matches": [{
     "user_id", "member": {user_id, display_name, handle, avatar_media_id, …},
     "score", "fusion_score", "rerank_score"?,
     "vector_rank", "keyword_rank", "vector_score", "keyword_score",
     "match_percent", "similarity_basis": "rerank"|"vector"|"keyword_only",
     "trust", "trust_detail": TrustBreakdown,
     "evidence": [{text ≤280, source_title, source_id, score}],
     "matched_terms": [str], "why_it_clicks": [str],
     "headline","location","skills","interests","looking_for","persona_summary"
  }],
  "retrieval": {"vector":"atlas"|"local", "keyword":"atlas"|"local",
                "fusion":"reciprocal_rank", "rerank": model|"off"|"skipped",
                "embedding_space", "semantic": bool, "similarity": basis},
  "threshold": {"min_match_percent": int, "hidden_below_threshold": int} }
```

`match_percent` is an **absolute** similarity, not a rank (C8). Thresholding happens before
the limit, so raising the bar surfaces the next candidate rather than shortening the page.
Members who opted out of discovery are excluded before ranking; deleted accounts are
dropped after.

### `GET /api/discover/status`
`{atlas_vector, atlas_text, atlas_enabled, embeddings, rerank}` — the path actually live.

---

## Media (searchable photos) — `/api/media`

### `GET /api/media/status`
`{available, model, dimensions, space}`. `available: false` = no Voyage key; the surface is
off rather than guessing.

### `POST /api/media` → `201` · `multipart/form-data`
`file` (PNG/JPEG/WebP/GIF, ≤6MB), `caption` (12–300 chars, **required**).
`422` on bad type/size/caption · `409` past 24 photos.
A photo that cannot be embedded is still stored, with `indexed: false`.

### `GET /api/media` → `MemberPhoto[]` — your own.

### `GET /api/media/user/{user_id}` → `MemberPhoto[]`
Empty unless that member opted into photo search — **or** you are that member.

### `GET /api/media/{media_id}/raw` → bytes, `Cache-Control: private, max-age=3600`.

### `DELETE /api/media/{media_id}` → `204`. `404` if it is not yours.

### `GET /api/media/search?q=&limit=12`
```json
{ "refused": true,  "reason": "…", "results": [] }          // appearance query — §9
{ "refused": false, "available": false, "reason": "…", "results": [] }   // no key
{ "refused": false, "available": true,  "results": [{...photo, score, member}] }
```
A refusal is computed **before** any vector or database call. Consent is a filter inside
the query, never a post-ranking pass. `422` if `q` < 3 chars · `503` if the embed fails.

---

## Interviews — `/api/interviews`

### `GET /api/interviews/presets`
`{presets: {collaboration|hiring|feedback|founders: [str]}, max_questions: 8}`.

### `GET /api/interviews/settings` · `PATCH /api/interviews/settings`
`{interview_enabled, interview_topics[], disclose_personal}`. PATCH merges onto stored (C10).

### `POST /api/interviews` → `202`
```json
{ "subject_id": "...", "goal": "8–400 chars", "questions": ["1–8 items"] }
```
Returns the **pending** row immediately with `subject: {user_id, display_name, handle}`.
`404` unknown member · `400` interviewing yourself · `403` subject has not enabled
interviews · `422` no non-blank questions.

Poll `GET /api/interviews/{id}` until `status` is `complete` or `failed`.

### `GET /api/interviews` → `Interview[]` — yours, newest first, each with `subject`.

### `GET /api/interviews/{interview_id}`
```json
{ "_id","asker_id","subject_id","goal","questions",
  "status": "pending"|"complete"|"failed",
  "rows": [{question, kind, answered, answer, citations[], confidence,
            decline_kind: null|"not_in_profile"|"permission"|"no_model"|"error",
            decline_reason}],
  "verdict": {recommendation: "connect"|"maybe"|"pass", rationale, met[], missing[],
              confidence, coverage},
  "offer","runtime_mode","model",
  "answered_count","question_count","blocked_count","error"?, "subject" }
```
Filtered on `asker_id` — `404` for anyone else, including the subject. A run pending longer
than 300s reports `failed`.

### `GET /api/interviews/network/paths?limit=10`
```json
{ "paths": [{ "user_id", "hops", "via": [topics],
              "member": public_member, "through": [public_member] }] }
```
Two hops via `$graphLookup`. Members who opted out of discovery are not walked through.
Identities and shared topics only — never memory text.

---

## Outcomes — `/api/outcomes`

### `GET /api/outcomes/labels`
`{great:{score:0.95,weight:0.30}, useful:{0.75,0.25}, neutral:{0.50,0.15},
waste:{0.15,0.30}, passed:{0.35,0.08}}`.

### `POST /api/outcomes` → `201`
```json
{ "subject_id","label","context":"community","context_id","predicted_score"?,"note"? }
```
→ `{outcome, trust: TrustBreakdown, calibration}`.
Idempotent per `(reporter, context_id, subject)`. `403` on yourself · `422` unknown label ·
`404` unknown member. For `context: "community"` the server prefers the `recruit_score` the
agent actually predicted over any client-supplied `predicted_score`.

### `GET /api/outcomes` → `Outcome[]` with `subject: {display_name, handle}`.

### `GET /api/outcomes/calibration`
`{samples, bias, mean_error, confidence_multiplier, summary}` — plain-language summary of
whether your agent has been over-promising.

### `GET /api/outcomes/trust/{subject_id}`
`{value, direct, propagated, contributors, reasons[]}` — why your agent rates them this way.

---

## Social — `/api/social`

### `POST /api/social/connections` → `201`
`{recipient_id, note?, source: "discovery"|"interview"|"community"|"feed"|"direct",
context_id?}`. A crossing pending request **auto-accepts**. `400` self/unknown source ·
`404` unknown member.

### `GET /api/social/connections/{other_id}` → the pair document, or `{"status":"none"}`.

### `POST /api/social/connections/{other_id}/respond`
`{accept: bool}`. **Recipient only** — `403` otherwise · `404` if nothing is pending.

### `POST /api/social/connections/{other_id}/withdraw`
**Requester only** — `403` otherwise · `404` if nothing is pending.

### `GET /api/social/connections`
`{accepted[], incoming[], outgoing[], provenance: {source: count}}`, each row carrying
`member: {user_id, display_name, handle, headline, accent, avatar_media_id, …}`.

### `GET /api/social/feed`
`{posts[], my_reactions: {post_id: reaction}, connection_count}`. Connections first, then
the wider network. Each post carries `author`, `from_connection`, and a **server-decided**
`story_active`.

### `POST /api/social/feed` → `201`
`{body: 1–4000, presentation: "post"|"story", image_media_id?, location?}`.
A body ≥120 chars (≥60 for a story) is chunked, embedded, and added to the author's
persona; the response then carries `ingested: true` and `ingested_chunks`. An
`image_media_id` you do not own is `422`.

### `POST /api/social/feed/media` → `201` · `multipart/form-data`
`file`, `kind` = `post` | `clip`. Images ≤6MB; clips MP4/WebM/MOV ≤20MB.
→ `{_id, media_type, kind, url}`. **Presentation only, never searchable.**

### `GET /api/social/feed/media/{media_id}/raw` → bytes.

### `POST /api/social/feed/draft`
`{notes: 3–2000}` → `{body, runtime_mode, model}`. A **draft**; the member still posts it.
Without a model, the notes come back lightly polished with
`runtime_mode: "deterministic_fallback"`.

### `POST /api/social/feed/story` → `201` · `multipart/form-data`
`file` (image), `caption?`. Image-first. The photo is presentation only; a caption clearing
the 60-char floor still becomes episodic memory.

### `GET /api/social/feed/story/{media_id}/raw` → bytes (alias of the feed media route).

### `POST /api/social/feed/agent` → `201`
Composes a post from stored activity — gaps the agent could not answer, interviews it ran —
templated, never model-generated, carrying its `evidence` rows. `409` when there is nothing
to report.

### `POST /api/social/feed/{post_id}/react`
`{reaction: "like"|"insightful"|"same"|null}` → the post with **recounted**
`reaction_counts`. `422` unknown reaction · `404` unknown post.

---

## Messages — `/api/messages`

All four routes require an **accepted** connection — `403` otherwise, `404` for an unknown
member.

### `GET /api/messages` → `MessageConversation[]`
`{conversation_id, member_id, member, last_message, unread_count, updated_at}`.

### `GET /api/messages/{other_id}`
`{conversation_id, member, messages[]}` — marks the thread read as a side effect.

### `POST /api/messages/{other_id}` → `201`
`{body: 1–2000}` → the stored message. `422` if blank or too long.

### `POST /api/messages/{other_id}/read` → `204`

---

## Research — `/api/research`

### `GET /api/research/status` — public
`{available, provider, search_type}`.

### `POST /api/research` → `202`
`{subject_id, goal: 8–300}` → the pending brief.

Four gates, in order, **before any search is issued**:

| Gate | Failure |
|---|---|
| Subject `research_enabled` (opt-in) | `403` |
| `protected_goal_reason(goal)` | `422` with the reason |
| Daily budget from Exa's `costDollars` | `429` with spend vs budget |
| Exa key present | `503` |

Also `400` for researching yourself · `404` unknown member.

### `GET /api/research` → `ResearchBrief[]` (without `sources`), yours only.

### `GET /api/research/{brief_id}`
```json
{ "_id","asker_id","subject_id","goal","status","summary",
  "findings": [{claim, source_url}],
  "open_questions": [str],
  "sources":             [ ...confirmed to be this member, with matched_on ],
  "unconfirmed_sources": [ ...same name, unattributed, never findings ],
  "declined", "decline_reason",
  "decline_kind": "unconfirmed_identity"|"no_results"|"no_model"|"ungrounded"|"model_error",
  "dropped_claims", "runtime_mode", "model", "cost_usd", "queries", "error"? }
```
`sources` means **confirmed** in every status, including declines (C17). Filtered on
`asker_id` — `404` for anyone else. A brief pending longer than 420s reports `failed`.

---

## Status-code conventions

| Code | Meaning here |
|---|---|
| `200` | Read, or a mutation whose result is the resource |
| `201` | Created — register, sources, posts, comments-adjacent writes, uploads |
| `202` | Accepted — interviews and research, which run in the background |
| `204` | Deleted / marked read |
| `400` | Structurally impossible request (self-connect, self-interview, self-research) |
| `401` | No token, expired token, or the account no longer exists |
| `403` | A consent boundary, or acting on someone else's record |
| `404` | Not found, **or found but not yours** (interviews, briefs, sources, photos) |
| `409` | Conflict — duplicate email, nothing to build from, nothing to report, photo cap |
| `413` | Upload too large |
| `422` | Validation, unsupported type, refused goal, unresolvable media |
| `429` | Research budget exhausted for the rolling 24h |
| `503` | A required external service has no key or failed |
