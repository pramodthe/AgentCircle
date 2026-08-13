# Constraints

**Every entry here is a bug that shipped.** None was found by review; all were found by
*running* the app. Several passed their own tests at the time.

They are written as: what the obvious implementation is, what actually happened, and what
the rule is. Read the ones for a subsystem **before** changing it — each describes a
change that will look like a simplification and will re-introduce a real failure.

| # | Subsystem | One-line rule |
|---|---|---|
| C1 | Search | Detect index availability; never configure or infer it |
| C2 | Auth | `public_member` is an allowlist, not a denylist |
| C3 | Embeddings | Never embed in a loop |
| C4 | Startup | Startup must not embed |
| C5 | Embeddings | Provider migration has a fixed three-step order |
| C6 | Embeddings | Name the vector space after the model, not the billing route |
| C7 | Rerank | A rate limit is not a permanent failure |
| C8 | Search | `match_percent` is absolute, not rank-relative |
| C9 | Search | Local and Atlas scores must share one scale |
| C10 | Settings | A PATCH merges onto stored values before sanitising |
| C11 | Settings | A stored `None` is "unset", not `False` |
| C12 | Serialization | Stamp the UTC offset at the boundary |
| C13 | Time | BSON returns naive datetimes; comparisons raise |
| C14 | Research | Citation grounding is not identity resolution |
| C15 | Research | Nothing name-derived may be an identity anchor |
| C16 | Research | Topic words may not be identity anchors |
| C17 | Research | `sources` means "confirmed" in every status |
| C18 | Profile | Theme buys nothing; declared fields buy reach |
| C19 | Profile UI | The card covers the backdrop exactly |
| C20 | Ranking | Trust demotes, never promotes |
| C21 | Trust | Hearsay may never outweigh first-hand experience |
| C22 | Interview | Permission declines are out of the coverage denominator |
| C23 | Persona | A rebuild must not be able to lose a fact |
| C24 | Grounding | An uncited answer is demoted, never published |
| C25 | Media | Presentation images and evidence photos are different collections |
| C26 | Atlas | Index quota is per cluster; visibility is per user |
| C27 | Ordering | Same-tick timestamps need an explicit sequence |
| C28 | CORS | Dev servers use two spellings and drifting ports |

---

## C1 — `$search` against a missing index returns nothing, not an error

**The obvious thing:** a config flag, `ENABLE_ATLAS_VECTOR_SEARCH=true`, or inferring
availability from whether a query returned results.

**What happened:** a flag drifts out of step with the cluster, and the failure is silent —
the app runs on the local fallback while the index sits there unused. Worse, inferring
from behaviour made the API report `"atlas"` while returning nothing at all, because
`$search` against a missing index returns an *empty result set* rather than raising.

**The rule.** `PeopleSearch.probe()` reads real index state at startup
(`list_search_indexes()` → `status == "READY"`). `atlas_enabled` is a **kill switch**, not
the enable path. Every response reports the path that actually served it. A status that
lies is worse than one that admits a fallback.

*Applies to:* `search.py`, `discovery.py`, `/api/discover/status`.

---

## C2 — A denylist on user documents leaks the next field somebody adds

**The obvious thing:** one `public_user()` that strips `password_hash` and returns
everything else — it is used everywhere and nothing is obviously wrong.

**What happened:** `GET /api/profile/{handle}` takes **no authentication at all** and was
returning every member's email address to anonymous callers. Nobody had added `email` to
the strip list. The bug was invisible for as long as nobody read the response body.

**The rule.** Two projections, permanently:
- `public_user` — strips `password_hash`, keeps `email`. **Owner only.**
- `public_member` — an **allowlist**: `_id`, `display_name`, `handle`. Everyone else.

A field added to `users` next year cannot repeat this.
Pinned by `test_public_member_is_an_allowlist_so_new_fields_cannot_leak`.

---

## C3 — Providers meter by request count, not tokens

**The obvious thing:** `for question in questions: embed(question)`. It reads fine and is
correct.

**What happened:** four interview questions took **63.6 seconds** one at a time versus
**0.40 seconds** through `embed_batch()` — 157×. Each sequential call hit the per-minute
rate limit and then waited out its own backoff. This was the entire cause of "interviews
are slow".

**The rule.** If you are embedding more than one thing, batch it. `embed_batch()` is the
default; `embed()` is for the genuinely single case.

*Applies to:* interviews (all questions), persona chunking, memory writes, any migration
script.

---

## C4 — Startup must not embed

**The obvious thing:** seed demo data on boot, embedding as you go. Free against the local
hash provider.

**What happened:** against a real embedding API that is a dozen billed, rate-limited calls
per boot, and startup hangs behind retry backoff.

**The rule.** No embedding call on the startup path. Seeding is guarded by checking stored
vector dimensions, so a provider switch still triggers the upgrade path without making
every boot pay for it.

---

## C5 — Provider migration has one correct order

**The rule.** In this order, always:

1. `scripts/reembed.py` — rewrite every vector in the new space
2. `scripts/create_search_indexes.py --recreate` — rebuild indexes at the new dimension
3. flip `EMBEDDING_PROVIDER`

Building the index first means indexing old vectors at the new dimension, which Atlas
rejects. Flipping config first means every query filters on a space no stored vector has.

---

## C6 — The vector space is named after the model, not the door you paid at

**The obvious thing:** `space = f"{provider}:{model}:{dims}"` with `provider` taken
straight from config. `mongodb` and `voyage` are different providers, so different spaces.

**What happened:** they are not different spaces. `ai.mongodb.com/v1/embeddings` serves the
*same Voyage models*, billed to an Atlas org. Naming the space after the billing route
means the day someone moves billing, every stored vector is stranded in an orphaned space
and retrieval returns nothing — loudly, but pointlessly, since the vectors were fine.

**The rule.** `_space_provider()` maps both `voyage` and `mongodb` to `voyage`.
`_space_model()` maps `voyage-4*` to `voyage-4-series`. Dimensions always stay in the key.
`describe()` still reports the *real* provider so the status line stays truthful.
Pinned by `test_mongodb_and_voyage_share_one_vector_space`.

Related: `voyage_route(settings)` is one door for all three Voyage APIs — `/embeddings`,
`/rerank`, `/multimodalembeddings`. Quota is metered **per account per minute**, so
leaving rerank on Voyage while embeddings moved to MongoDB meant ordinary search traffic
starved the reranker. Six searches in ten seconds was enough.

---

## C7 — A 429 is routine; treating it as permanent kills the feature silently

**The obvious thing:** `except httpx.HTTPError: self._failed = True`. A failing reranker
should stop costing a round trip per search.

**What happened:** embeddings and reranking share one account and one per-minute quota, so
429s are *expected*. One of them permanently downgraded every later search for the life of
the process. Observed live: `match_percent` went from a meaningful 99/75/75 spread to a
useless 99/98/98 cluster between two consecutive queries, with nothing in the log.

**The rule.** Only `PERMANENT_STATUSES = {400, 401, 403, 404, 422}` latch the reranker off.
429 and 5xx retry with backoff, then skip **that one query** and stay enabled. The API
reports three states, not two: model name (ran), `"off"` (disabled), `"skipped"` (this
query only). Reporting a rate-limited query as `"off"` sends you looking for a broken key.

---

## C8 — `match_percent` was a rank in disguise

**The obvious thing:** `50 + 49 * sqrt(score / top_score)` — a nice spread, always looks
reasonable.

**What happened:** two failures. The same person scored differently depending on who else
matched that query, and the formula's floor was 50, so "hide anything under 50%" could
never hide anything.

**The rule.** `match_percent` comes from a measurement that means the same thing in every
query, in preference order: `rerank_score` → `vector_score` on the `(1 + cos) / 2` scale →
`0` with basis `keyword_only`. RRF is deliberately **not** a source: it combines ranks, is
flat by construction (rank 1 vs rank 2 differ by ~1.6%), and a percentage derived from it
varies with pool size rather than with fit. Ordering still comes from fusion + rerank; this
only decides the number shown and what the threshold cuts.

---

## C9 — Two code paths, two scales, one field name

**What happened:** the local fallback returned raw cosine while Atlas returns
`(1 + cos) / 2`. The same person scored 0.64 locally and 0.82 on the cluster. Invisible
while the number was only ever compared against its own query — a real discrepancy the
moment it is reported as a similarity or used as a threshold.

**The rule.** Every fallback path rescales to Atlas's convention. Applies to
`PeopleSearch._vector_local` and `MediaStore._search_local`. Pinned by
`test_both_retrieval_paths_report_scores_on_the_same_scale`.

---

## C10 — Sanitising a bare PATCH resets everything it did not mention

**The obvious thing:** `safe_community_settings(payload)` — the sanitiser already fills
defaults for missing keys, so just run the patch through it.

**What happened:** turning on research switched photo sharing off and forced
`discoverable` back to **True**, quietly re-exposing a member who had opted out. The UI
happened to send the whole object, so only direct API callers hit it.

**The rule.** Merge onto the member's stored values **first**, then sanitise:
`safe(**{**current, **patch.model_dump(exclude_unset=True)})`. Rebuilding from defaults is
right for sanitising and wrong for a partial update. Same rule in
`/api/community/settings` and `/api/interviews/settings`.

---

## C11 — A stored `None` is not `False`

**The obvious thing:** `{key: stored[key] for key in DEFAULTS if key in stored}` — a key
that is present is a real value.

**What happened:** several accounts had `discoverable: None` (written before the field had
a default). `key in stored` treated that as configured, and `bool(None)` is `False`, so
saving *any unrelated setting* would have silently removed them from search. It never
surfaced only because `undiscoverable_ids()` matches an explicit `False`.

**The rule.** Filter on `stored.get(key) is not None`, never on `key in stored`. For an
opt-*out* field the difference inverts the member's intent.

---

## C12 — A naive timestamp is parsed as the reader's local time

**What happened:** BSON has no timezone, so PyMongo returns a **naive** datetime, and
`isoformat()` on that produces `2026-08-13T03:32:33` with no suffix. ECMAScript parses
that as the *viewer's* local time. A browser at UTC−7 rendered every feed post under seven
hours old as "just now", and a 19-hour-old post as "12h". Nothing errored; the number was
just wrong by the reader's offset.

**The rule.** `serialize()` stamps UTC on any naive datetime before `isoformat()`, at the
boundary — including inside nested dicts and lists. Not `tz_aware=True` on the client,
which would make every in-process comparison that currently subtracts two stored datetimes
start raising.

---

## C13 — Naive-vs-aware comparison raises

**What happened:** `utcnow() - row["created_at"]` throws `TypeError` when the stored value
came back from Mongo naive. It shows up in stale-run detection, which is exactly the code
path nobody exercises until something has already gone wrong.

**The rule.** Every place that compares a stored datetime to `utcnow()` normalises first:
`if created.tzinfo is None: created = created.replace(tzinfo=UTC)`. Present in
`InterviewStore._resolve_stale`, `ResearchStore._resolve_stale`, `story_is_active`,
`MessageStore.send`.

---

## C14 — A correctly-cited brief about the wrong person

**The obvious thing:** check that every claim's URL was actually returned by the search.
That is real grounding, and it is what the persona and interview layers already do.

**What happened:** the first live brief returned **18 genuine, correctly-cited sources and
dropped zero claims** — every one about a *different real person with the same name*.
Every URL checked out, because checking that a source exists is not checking that it is
about the right person. For a common name, citation-grounding alone produces a confident
dossier that merges strangers.

**The rule.** Citation grounding and identity resolution are two different guarantees and
both are required. A source becomes evidence only if it corroborates an **entity anchor**
the member declared. Everything else is `unconfirmed_sources`, shown unattributed.

---

## C15 — The handle is derived from the name that caused the collision

**What happened:** the handle `kenji_tanaka` appearing in a URL "confirmed" a namesake's
paper. The guard was validating a match using the very thing that produced the collision.

**The rule.** `identity_anchors()` rejects any token containing, or contained in, a part
of the display name. Nothing name-derived may anchor — including the handle, which is
auto-generated from the display name in the first place.

---

## C16 — Field overlap is the *most* likely collision, not the least

**What happened:** `infrastructure` and `energy`, pulled from the member's headline,
confirmed five papers by the same wrong person — who also works on energy infrastructure.

**The rule.** Anchors come from **entity fields only**: `organization`, `location`,
website domain. Never `role`, never `headline`, never topic words. Those describe what
someone does; a namesake in the same field shares them by definition.

---

## C17 — A field that means something different during a decline

**The obvious thing:** on `unconfirmed_identity`, put the pages you found into `sources` so
the caller has something to show.

**What happened:** `sources` means "confirmed to be this member" in every successful brief.
Making it mean "pages with this name on them" during a decline is exactly how a caller ends
up rendering a stranger's pages as a member's work.

**The rule.** `sources` = confirmed, in **every** status. Unconfirmed pages go to
`unconfirmed_sources` and are rendered unattributed. Humans can disambiguate; agents must
not guess.

---

## C18 — Restyling a page must not buy reach

Two directions, both load-bearing:

**Declared fields buy reach.** Before `src_declared_{user_id}` existed, the editor told
members that these fields were what they got found for — and it was false. Retrieval
answered only from uploaded documents, so someone could state exactly what they wanted to
be found for and never be found for it.

**Theme buys nothing.** `theme` is presentation-only, allowlisted key by key on write,
absent from `declared_profile_text()`, and absent from the `profiles_text` index mappings
(`dynamic: false` is deliberate). Without that, page customization becomes an SEO surface —
a keyword-stuffed `background` value would rank. Pinned by
`test_theme_edits_never_become_retrievable`.

The same rule governs `profile_media`: an avatar is never embedded, never indexed, never
reachable from a search endpoint (see C25).

---

## C19 — Two rendering traps found by looking at the screen

**C19a.** `.profile-shell` needs padding, or the card covers the backdrop *exactly* and
every background choice is a silent no-op. The feature looks broken in a way that reads as
"the setting doesn't save".

**C19b.** The editor's live preview must keep the same backdrop/card structure as
`/u/:handle`. A preview with a different structure renders dark themes as unreadable while
the real page is fine — a preview that lies about the page is worse than no preview.

---

## C20 — Trust is a multiplier capped at no-op

**The obvious thing:** `score * (0.5 + trust)` — reward people you have had good
experiences with.

**What happened:** RRF scores are deliberately flat (rank 1 vs 2 differ by ~1.6%), so any
meaningful upward multiplier lets "people you like" outrank "people who know the answer".

**The rule.** `trust_factor = min(1.0, 0.55 + trust * 0.9)`. Neutral is a no-op, a bad
history demotes, a good history cannot promote. Applied in both `PeopleSearch` (after
reranking) and `rank_responders`. Pinned by
`test_trust_cannot_promote_an_irrelevant_person_above_a_relevant_one` and
`test_trust_demotes_but_never_promotes_an_irrelevant_person`.

---

## C21 — Strangers outweighed first-hand experience

**What happened:** an earlier propagation formula let a coordinated group of accounts move
a member's trust further than the member's own recorded outcome had. Wrong, and cheap to
attack.

**The rule, asserted as a test against a 12-account mob:**

> No amount of propagated signal may move you further from neutral than a single
> first-hand outcome would.

Enforced by `PROPAGATION_CEILING = 0.28` and `CONSENSUS_AT = 3.0` (propagation saturates on
accumulated *reliability*, not on one loud voice), plus reporter reliability =
track record × calibration accuracy, so a fresh account moves nothing.

**Re-run `test_no_amount_of_hearsay_outweighs_one_first_hand_outcome` after touching any
constant in `outcomes.py`.**

---

## C22 — Counting permission declines punishes the subject for the asker's questions

**The obvious thing:** coverage = answered / total questions.

**What happened:** an asker could depress anyone's verdict by adding "what's your email" —
a question the subject is *structurally* not allowed to answer.

**The rule.** `coverage()` excludes `permission` declines from the denominator. A
`not_in_profile` decline *does* count, because that genuinely is missing context. Pinned by
`test_permission_declines_do_not_count_against_coverage`.

---

## C23 — A rebuild that re-derives can lose what it already knew

**The obvious thing:** rebuild the persona from all chunks on each build. Simple, one code
path.

**What happened:** extraction is not deterministic and the prompt window is bounded, so a
long source is truncated differently each run — a second build can quietly *drop* a fact
the first one found. That is the wrong shape for something a member is told their agent
knows about them.

**The rule.** `extract_incremental` + `merge_persona`: each source contributes its own
passes, results are unioned, items keep **every** supporting chunk. Nothing is removed
except by `prune_persona`, which only drops a claim whose evidence is actually gone.
`?rebuild=true` exists for the rare genuinely-wrong persona.

---

## C24 — An uncited answer is demoted, never published

Applied identically in three places, and it is the same rule each time:

- `CommunityCommenter._finalize` — citations that do not resolve to a supplied chunk are
  dropped; if none survive, the whole comment becomes a decline.
- `InterviewAgent.run` — same, per row; an answer left with no citation becomes
  unanswered. A question the model *omitted* is marked unanswered, not dropped.
- `ResearchAgent.run` — a finding whose `source_url` was not in the returned set is
  dropped; a brief with nothing left declines.

A model will cheerfully cite an index or URL it invented. A fabricated attribution under a
real person's name is the worst failure this product has.

---

## C25 — Avatars and evidence photos are governed by opposite rules

**The obvious thing:** one `media` collection with a `kind` field.

**What happened (and why the separation exists):** the UI once rendered five hard-coded
stock photographs as member identity — a story card labelled "Kenji" showed a stranger. On
a product whose whole claim is that what you see about someone is grounded in what they
supplied, an unrelated photograph presented as a person is a fabricated visual claim.

**The rule.** Two stores, permanently:
- `persona_media` is **evidence** — embedded, caption required (≥12 chars, it is what the
  photo is matched on), consent-gated (`photo_search_enabled`, opt-in), governed by §9.
- `profile_media` / `feed_media` is **decoration** — never embedded, never indexed, never
  reachable from a search endpoint, absent from `declared_profile_text`.

One collection means one wrong `$vectorSearch` filter away from an avatar being retrievable
by appearance, which is precisely what §9 exists to prevent. The separation *is* the
enforcement. An AI-generated portrait is allowed but stored `ai_generated: true` and
labelled — the member chose it, so the answer is to say so.

---

## C26 — Search-index quota is per cluster; visibility is per user

**What happened:** index creation failed with `maximum number of FTS indexes` while
`list_search_indexes()` showed exactly one. A scoped database user only sees indexes in its
own database, so the cluster can be at quota while the app sees room.

**The rule.** Before concluding anything about the tier, enumerate **every** database with
an admin-capable user. Free tier allows 3 indexes per cluster, Flex 10. This product needs
exactly 3 — `persona_chunks_vector`, `profiles_text`, `persona_media_vector` — so the free
tier fits it with nothing spare, and a cluster shared with another project will not.

`create_search_indexes.py` creates in priority order and **reports what it could not fit**
rather than failing the whole script.

---

## C27 — Two writes in the same tick sort arbitrarily

**What happened:** messages written in the same millisecond came back in an unstable order,
and an append-only log with an unstable order is not much of a record.

**The rule.** Carry an explicit integer sequence alongside the timestamp:
`direct_messages.sequence` (per conversation) and `memory_log.seq` (per user). `MessageStore.send`
additionally nudges `created_at` forward by a microsecond when it would not exceed the
previous message's.

---

## C28 — The dev origin has two spellings and a drifting port

**What happened:** `npm run dev` binds `127.0.0.1` while `FRONTEND_ORIGIN` usually says
`localhost`, and the browser treats those as different origins. Vite also hops to 5174+
when 5173 is taken.

**The rule.** `allowed_origins()` expands each configured origin into both spellings.
`local_dev_origin_regex()` adds a loopback port regex **only when the configured origin is
itself loopback** — a production origin stays an exact allowlist, never a regex that would
accept any local tab. Pinned by `test_loopback_frontend_origin_accepts_both_spellings` and
`test_production_frontend_origin_is_not_a_localhost_regex`.

---

## Standing rules that are not bugs (yet)

These are known-fragile, deliberate, and cheap to break by "simplifying":

- **Recruitment full-scans `persona_chunks`** via `chunks_by_user` in the local path.
  Prototype scale only. `search_chunks_global` already pushes the work into
  `$vectorSearch` when the index exists.
- **`local` embeddings are a 128-dim hashed bag-of-tokens** with a hand-tuned
  `TOKEN_ALIASES` map. It matches shared vocabulary, not meaning. It exists for tests and
  keyless dev; it is not fit for anything a user sees.
- **`tests/conftest.py` blanks every provider key before any app import** and asserts it
  took. Several modules call the process-wide `embed_text()` rather than an injected client,
  so the moment a real key lands in `.env` the suite starts making live calls — it went from
  55s to rate-limited timeouts. Do not remove that file.
- **`mock_mongo.py` monkeypatches mongomock's bulk-update signature** to match PyMongo 4.16.
  If a pymongo bump breaks bulk writes under test, that shim is the place to look.
