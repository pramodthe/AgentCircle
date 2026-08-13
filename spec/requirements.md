# Requirements

Testable acceptance criteria in EARS form. Each requirement is a contract a rebuild must
satisfy; each **Verify** line names the pytest that pins it (tests live in
`backend/tests/`). A requirement with no test is not done.

Reading order: this file says *what must be true*. `design.md` says how.
`constraints.md` says which plausible implementations are already known to be wrong.

**Legend.** `SHALL` = mandatory. `SHALL NOT` = a violation is a bug even if tests pass.
Numbers in prose (limits, thresholds, constants) are normative — see `data-model.md`.

---

## R1 — Identity and authentication

**R1.1** WHEN a client registers with an email that already exists THE SYSTEM SHALL
return `409` and create nothing.

**R1.2** WHEN a client registers THE SYSTEM SHALL allocate a handle from the display
name, lowercase, `[a-z0-9_]` only, ≤24 chars, never a reserved word, and unique —
appending a numeric suffix on collision.

**R1.3** WHEN a password longer than 72 bytes is submitted THE SYSTEM SHALL reject it.
It SHALL NOT hash a truncated prefix.
*(bcrypt truncates silently; accepting it means a 100-char password is equivalent to its
first 72 bytes.)*

**R1.4** WHEN login fails for any reason THE SYSTEM SHALL return the identical message
`"Incorrect email or password"`, so the endpoint cannot enumerate accounts.

**R1.5** THE SYSTEM SHALL derive the acting user identity **only** from a signed JWT.
Every store method SHALL take `user_id` as an explicit argument. No route SHALL accept an
owner id from a request body or query string.

**R1.6** WHEN a user document leaves the API THE SYSTEM SHALL use `public_user` (strips
`password_hash`, keeps `email`) **only** for the owner, and `public_member` (allowlist:
`_id`, `display_name`, `handle`) for every other member.

**R1.7** WHEN a field is added to `users` later THE SYSTEM SHALL NOT expose it to other
members. `public_member` is an allowlist, not a denylist.

Verify: `test_accounts.py::test_password_hash_round_trips_and_rejects_wrong_password`,
`::test_password_longer_than_bcrypt_limit_is_rejected_not_truncated`,
`::test_access_token_round_trips_and_rejects_tampering`,
`::test_email_is_normalized_and_handles_stay_unique`,
`::test_reserved_handles_are_not_allocated`,
`::test_public_user_never_exposes_password_hash`,
`::test_a_members_email_never_reaches_another_member`,
`::test_public_member_is_an_allowlist_so_new_fields_cannot_leak`.

---

## R2 — Profile, declared claims, and theme

**R2.1** WHEN `PATCH /api/profile` is called THE SYSTEM SHALL write only the fields in
`PROFILE_TEXT_FIELDS` and `PROFILE_LIST_FIELDS`, truncated to their limits, and SHALL
ignore any other key.

**R2.2** WHEN a profile is saved AND `declared_profile_text(profile)` is ≥ 80 characters
THE SYSTEM SHALL re-derive one persona source with the deterministic id
`src_declared_{user_id}`, chunk and embed it, and replace (never accumulate) the previous
chunks for that source.

**R2.3** WHEN `declared_profile_text(profile)` is < 80 characters THE SYSTEM SHALL delete
that source and store no chunk.

**R2.4** IF the embedding call fails during a profile save THEN THE SYSTEM SHALL still
persist the profile and SHALL return `retrieval_synced: false`. "Saved" and "searchable"
are different claims.

**R2.5** THE SYSTEM SHALL accept only the keys in `PROFILE_THEME_FIELDS` into
`profiles.theme`, each truncated to its per-key limit.

**R2.6** THE SYSTEM SHALL NOT include `theme` in `declared_profile_text()`, in any
persona chunk, in `profiles_text` index mappings, or in any ranking input. Restyling a
page SHALL NOT change who gets found.

**R2.7** WHEN `display_name` changes THE SYSTEM SHALL propagate it to the `users`
document, which is what auth reads.

**R2.8** WHEN `GET /api/profile/{handle}` is called (no authentication) THE SYSTEM SHALL
return `public_member`, the profile, and the persona **summary only** — never raw chunks,
never email.

Verify: `test_declared_source.py` (all), `test_profile_theme.py` (all),
`test_accounts.py::test_profile_update_ignores_unknown_fields`.

---

## R3 — Sources and ingestion

**R3.1** THE SYSTEM SHALL accept uploads with suffix `.pdf`, `.docx`, `.txt`, `.md`,
`.markdown` and SHALL reject anything else with `422` and a message naming what is
supported.

**R3.2** WHEN an upload exceeds `MAX_UPLOAD_BYTES` (8MB) THE SYSTEM SHALL return `413`.

**R3.3** WHEN a URL is ingested THE SYSTEM SHALL normalise it (adding `https://` when the
scheme is missing), reject non-HTTP(S), follow redirects, strip `script`, `style`,
`noscript`, `nav`, `footer`, `header`, `form`, `svg`, `iframe`, and take the title from
`<title>` or the first `<h1>`.

**R3.4** WHEN text is chunked THE SYSTEM SHALL split on paragraph boundaries packing up
to `chunk_characters` (1200) with `chunk_overlap_characters` (180) carried forward, SHALL
hard-split a single oversized paragraph rather than dropping it, and SHALL cover all
input text.

**R3.5** WHEN more than one chunk is embedded THE SYSTEM SHALL use `embed_batch` in a
single request. THE SYSTEM SHALL NOT call `embed()` in a loop.

**R3.6** WHEN a source produces no usable text THE SYSTEM SHALL return `422` and store
nothing.

**R3.7** WHEN a source is deleted THE SYSTEM SHALL delete its chunks, prune every persona
item whose only remaining support was those chunks, drop those source ids from
`extracted_source_ids`, and delete any `agent_memory` row citing a removed chunk.

**R3.8** A user SHALL NOT be able to delete another user's source.

Verify: `test_accounts.py::test_chunking_covers_all_text_and_respects_size`,
`::test_oversized_paragraph_is_split_rather_than_dropped`,
`::test_html_extraction_drops_scripts_and_navigation`,
`::test_url_normalization_adds_scheme_and_rejects_junk`,
`::test_deleting_a_source_removes_its_chunks`,
`::test_a_user_cannot_delete_another_users_source`,
`test_agent_memory.py::test_forgetting_a_chunk_removes_the_memory_it_supported`.

---

## R4 — Persona construction

**R4.1** WHEN `POST /api/persona/build` is called with no chunks THE SYSTEM SHALL return
`409` and SHALL NOT create a persona.

**R4.2** THE SYSTEM SHALL extract **incrementally**: only sources not in
`extracted_source_ids` are passed to the model, and the result is merged into the stored
persona. A second build SHALL NOT be able to lose a fact the first build found.

**R4.3** WHEN merging THE SYSTEM SHALL key items by normalised value and accumulate
**every** supporting chunk in `support[]`. Prose fields (`headline`, `summary`) supersede;
evidence-bearing item lists never do.

**R4.4** WHEN a persona item cites a chunk index that was not in the supplied window THE
SYSTEM SHALL drop that item. An unverifiable attribution SHALL NOT be stored.

**R4.5** WHEN a claim is supported by two sources and one is deleted THE SYSTEM SHALL
keep the claim with the remaining support. WHEN the only support is deleted THE SYSTEM
SHALL drop the claim.

**R4.6** WHEN no chat model is configured THE SYSTEM SHALL take the heuristic path and
label it `extraction_mode: "heuristic"`. THE SYSTEM SHALL NOT manufacture biographical
facts on any path.

**R4.7** THE SYSTEM SHALL compute `coverage` as `{missing: string[], score: 0..1}` over
skills, interests, looking-for, location, headline.

**R4.8** `GET /api/persona/lint` SHALL be deterministic and model-free, SHALL report
`orphaned_claim`, `uncited_claim`, `contradiction`, `unused_source`, and SHALL NOT fix
anything.

**R4.9** THE SYSTEM SHALL append one `memory_log` row per learning event
(`source_added`, `source_removed`, `persona_learned`, `memory_written`, `edge_recorded`)
with a per-user monotonic `seq`, readable only by its owner.

Verify: `test_persona_incremental.py` (all), `test_memory_log.py` (all),
`test_accounts.py::test_persona_build_stores_chunks_and_reports_missing_fields`.

---

## R5 — Consent and permissions

**R5.1** THE SYSTEM SHALL default `comment_enabled`, `photo_search_enabled`,
`research_enabled`, `interview_enabled`, `disclose_personal` to **false**, and
`review_before_publish` to **true**.

**R5.2** THE SYSTEM SHALL default `discoverable` to **true** (opt-out), and SHALL honour
an explicit `false` before any ranking runs.

**R5.3** WHEN a settings PATCH arrives THE SYSTEM SHALL merge it onto the member's stored
values and then sanitise. It SHALL NOT rebuild from defaults — toggling one consent SHALL
NOT silently revoke another.

**R5.4** WHEN a stored setting is `None` (never configured) THE SYSTEM SHALL treat it as
absent and apply the default. It SHALL NOT coerce `None` with `bool()`.

**R5.5** THE SYSTEM SHALL allowlist every permission key on write
(`safe_community_settings`, `safe_interview_settings`) and SHALL NOT accept a permission
value that originated in a model response.

**R5.6** THE SYSTEM SHALL resolve consent **before** any model call, so a boundary cannot
be argued out of by a prompt.

Verify: `test_community.py::test_community_settings_default_closed`,
`::test_settings_reject_unknown_topics`,
`test_community_api.py::test_a_patch_never_resets_settings_it_did_not_mention`,
`::test_a_patch_never_resets_interview_settings_it_did_not_mention`,
`::test_an_unset_setting_never_opts_a_member_out_of_search`,
`::test_an_explicit_opt_out_still_survives_an_unrelated_save`,
`test_hardening.py::test_members_are_discoverable_by_default`,
`::test_a_member_who_never_touched_settings_stays_discoverable`,
`test_interview.py::test_interviews_are_off_by_default`,
`test_research.py::test_research_is_opt_in_and_defaults_off`,
`test_media.py::test_photo_search_is_opt_in_and_defaults_off`.

---

## R6 — Agent Community: recruitment

**R6.1** ONLY the post author SHALL be able to trigger `POST /api/community/posts/{id}/recruit`.
Any other caller SHALL receive `403`.

**R6.2** THE SYSTEM SHALL rank candidate responders by their **best** persona chunk
(not their average), multiplied by comment reputation, asker trust, and the asker's own
`confidence_multiplier`.

**R6.3** THE SYSTEM SHALL exclude any member whose `comment_enabled` is false, and — when
the post carries topics and the member declared topics — any member with no overlapping
topic.

**R6.4** THE SYSTEM SHALL drop candidates scoring below `MIN_RECRUIT_SCORE` (0.12) and
SHALL cap fan-out at `MAX_RESPONDERS` (6).

**R6.5** THE SYSTEM SHALL ignore chunks whose `space` does not match the current
embedding space.

**R6.6** Trust SHALL be a multiplier capped at 1.0 (`min(1.0, 0.55 + trust * 0.9)`). It
SHALL be able to demote and SHALL NOT be able to promote an irrelevant member into a
thread.

**R6.7** A new member with no comment history SHALL have reputation 0.5, not 0.

**R6.8** WHEN recruitment runs twice on one post THE SYSTEM SHALL update each responder's
single comment (`_id = cmt_{post_id}_{responder_id}`, unique on `(post_id, responder_id)`)
rather than adding a second.

Verify: `test_community.py::test_recruitment_prefers_relevant_personas_and_skips_opted_out`,
`::test_topic_consent_filters_recruitment`,
`::test_chunks_from_a_stale_embedding_space_are_not_recruited`,
`::test_reputation_reorders_equally_relevant_responders`,
`::test_new_member_reputation_is_neutral_not_zero`,
`::test_recruiting_twice_updates_rather_than_duplicates`,
`test_outcomes.py::test_trust_demotes_but_never_promotes_an_irrelevant_person`,
`test_community_api.py::test_recruitment_produces_a_cited_comment_and_respects_consent`.

---

## R7 — Agent Community: the comment contract

**R7.1** An agent comment SHALL answer only from its member's own `persona_chunks` and
SHALL cite the excerpts it used.

**R7.2** WHEN the supplied chunks do not ground a specific, useful response THE SYSTEM
SHALL return `declined: true` with a reason. Declining is a correct outcome, not an error.

**R7.3** WHEN no chat model is configured THE SYSTEM SHALL decline with
`runtime_mode: "deterministic_fallback"`. THE SYSTEM SHALL NOT emit a templated opinion
under a real person's name.

**R7.4** WHEN a model call raises THE SYSTEM SHALL decline with
`runtime_mode: "fallback_after_error"`.

**R7.5** WHEN the member has no chunks at all THE SYSTEM SHALL decline with
`runtime_mode: "no_grounding"`.

**R7.6** WHEN citations are resolved THE SYSTEM SHALL drop any index outside the supplied
window, and IF no citation survives THEN THE SYSTEM SHALL demote the whole comment to a
decline. An uncited answer SHALL NOT be published.

**R7.7** THE SYSTEM SHALL store `runtime_mode` on the comment, so a fallback can never be
mistaken for a live answer after the fact.

**R7.8** WHEN the responder has `review_before_publish: true` THE SYSTEM SHALL store the
comment with `published: false`, and only the responder SHALL be able to publish it.

**R7.9** A member SHALL NOT vote on their own agent's comment. Vote tallies SHALL be
**recounted** from `comment_votes`, never incremented.

Verify: `test_community.py::test_commenter_declines_when_no_model_is_configured`,
`::test_commenter_declines_without_grounding`,
`::test_commenter_keeps_only_resolvable_citations`,
`::test_uncitable_answer_is_demoted_to_a_decline`,
`::test_commenter_survives_a_model_failure`,
`::test_votes_are_recomputed_and_drive_reputation`,
`::test_you_cannot_vote_on_your_own_agents_comment`,
`::test_review_before_publish_holds_the_comment_until_its_member_releases_it`,
`::test_publish_requires_ownership`,
`test_community_api.py::test_review_mode_keeps_a_comment_unpublished_until_released`.

---

## R8 — Context gaps

**R8.1** WHEN an agent declines on grounding (`not_in_profile` in an interview, or any
community decline) THE SYSTEM SHALL record a `context_gaps` row against the **subject**,
carrying the question that was asked.

**R8.2** `gap_demand()` SHALL group gaps by `normalize_question()` — lowercased, punctuation
stripped, filler words removed, content tokens sorted and deduplicated — and rank by
`-count`, then `-last_asked`.

**R8.3** Resolving gaps SHALL be scoped to the owner. A member SHALL NOT be able to clear
another member's gaps.

**R8.4** A resolved gap SHALL leave the demand list.

Verify: `test_phase6.py::test_normalize_question_collapses_near_duplicates`,
`::test_gap_demand_ranks_by_how_often_something_is_asked`,
`::test_resolving_gaps_is_scoped_to_the_owner`,
`::test_resolved_gaps_leave_the_demand_list`,
`test_community.py::test_declines_are_stored_and_become_context_gaps`.

---

## R9 — Discovery

**R9.1** THE SYSTEM SHALL run two retrievers — `$vectorSearch` over `persona_chunks` and
`$search` over `profiles` — and fuse them by reciprocal rank with `RRF_K = 60`.

**R9.2** THE SYSTEM SHALL rank per **person**, not per chunk: a member's first appearing
chunk sets their vector rank; later chunks contribute evidence only.

**R9.3** THE SYSTEM SHALL exclude the searcher from their own results, and SHALL exclude
members in `undiscoverable_ids()` **before** ranking.

**R9.4** THE SYSTEM SHALL drop any match whose `users` document is missing (deleted
account) rather than returning a nameless row.

**R9.5** `match_percent` SHALL be an **absolute** similarity in `[0,100]`, sourced in
preference order: `rerank_score` → `vector_score` (on the `(1 + cos) / 2` scale) →
`0` with basis `keyword_only`. It SHALL NOT be derived from RRF, and the same person SHALL
score the same in a smaller pool.

**R9.6** THE SYSTEM SHALL apply `min_match_percent` **before** the limit, and SHALL report
`hidden_below_threshold`. Raising the bar SHALL NOT reorder the survivors.

**R9.7** Trust SHALL apply as `min(1.0, 0.55 + trust * 0.9)`, after reranking, and SHALL
NOT promote an irrelevant person above a relevant one.

**R9.8** THE SYSTEM SHALL detect index availability at startup by reading real index
state (`list_search_indexes()` → `status == "READY"`), never by inferring from an empty
result set, and SHALL report the path actually used (`atlas` | `local`) on every response.

**R9.9** Reranking SHALL return `None` when it did not run, and the response SHALL
distinguish three states: the model name (ran), `"off"` (unavailable/disabled), `"skipped"`
(available but this query did not rerank).

**R9.10** `why_it_clicks` SHALL be human-readable and SHALL NOT leak vectors, raw scores,
or internal field names.

Verify: `test_search.py` (all), `test_phase6.py::test_search_reports_rerank_off_when_it_did_not_run`,
`test_rerank.py::test_search_distinguishes_a_disabled_reranker_from_a_skipped_query`.

---

## R10 — Photo search (spec §9)

**R10.1** `photo_search_enabled` SHALL default false, and consent SHALL be applied as a
filter **inside** the database query in both the Atlas and local paths — never as a
post-ranking pass.

**R10.2** THE SYSTEM SHALL require a caption of ≥12 and ≤300 characters, and the stored
vector SHALL cover caption **and** image.

**R10.3** WHEN a query matches `APPEARANCE_TERMS` or `APPEARANCE_FRAMES` THE SYSTEM SHALL
return `{refused: true, reason, results: []}` **before** computing any vector or touching
the database.

**R10.4** Gender words SHALL NOT be in `APPEARANCE_TERMS`. "women in climate tech" is a
legitimate search.

**R10.5** Photo vectors SHALL live in `voyage:voyage-multimodal-3.5:1024` and SHALL NOT be
reachable from people search.

**R10.6** WITHOUT a multimodal key THE SYSTEM SHALL report the surface off, store uploads
with `indexed: false`, and SHALL NOT substitute a local embedding.

**R10.7** Both retrieval paths SHALL report scores on the same `(1 + cos) / 2` scale.

**R10.8** A member's photos SHALL NOT appear on their public page until they opt in;
their own page SHALL always show them.

**R10.9** A member SHALL NOT delete another member's photo. Max 24 photos per member,
max 6MB each, PNG/JPEG/WebP/GIF only.

Verify: `test_media.py` (all).

---

## R11 — Interviews and verdict

**R11.1** `POST /api/interviews` SHALL return `202` with a `pending` row within ~0.1s and
SHALL run the agent work in a background job. Clients poll `GET /api/interviews/{id}`.

**R11.2** THE SYSTEM SHALL embed all questions in **one** `embed_batch` call, and SHALL
retrieve **per question** (a hiring question and a hobbies question need different parts
of the profile).

**R11.3** Every row SHALL be `answered: true` with resolving citations, or unanswered.
There SHALL be no third state.

**R11.4** WHEN a citation index does not resolve THE SYSTEM SHALL drop it; IF an answer is
left with none THEN it SHALL be demoted to unanswered.

**R11.5** WHEN the model omits a question entirely THE SYSTEM SHALL mark it unanswered
rather than dropping the row.

**R11.6** THE SYSTEM SHALL distinguish three decline kinds and SHALL NOT collapse them:
`not_in_profile` (becomes a context gap), `permission` (a boundary), `no_model`.

**R11.7** Contact questions (`CONTACT_MARKERS`, case-insensitive) SHALL be refused
unconditionally, before any model call, regardless of settings.

**R11.8** Personal questions SHALL be refused unless the subject set `disclose_personal`.

**R11.9** `coverage()` SHALL exclude `permission` declines from the denominator, so an
asker cannot depress a subject's verdict by adding "what's your email".

**R11.10** `Verdict.recommendation` SHALL be exactly one of `connect | maybe | pass`,
enforced by the schema.

**R11.11** WHEN coverage < 0.5 AND the model returned `connect` THE SYSTEM SHALL downgrade
to `maybe` and say why. Confidence SHALL be capped at coverage.

**R11.12** WITHOUT a model THE SYSTEM SHALL report a count and state explicitly that it is
not a judgement, with confidence 0.

**R11.13** An interview SHALL be readable only by its `asker_id`.

**R11.14** A run pending longer than `STALE_AFTER_SECONDS` (300) SHALL be reported as
failed. An exception in the background job SHALL be written onto the interview.

Verify: `test_interview.py` (all), `test_hardening.py::test_a_pending_interview_from_a_dead_process_reports_failed`,
`::test_naive_timestamps_from_mongo_do_not_break_stale_detection`,
`::test_a_completed_interview_carries_its_counts`,
`::test_a_failed_background_job_records_why`.

---

## R12 — Outcomes, trust, and calibration

**R12.1** An outcome SHALL be idempotent per `(reporter_id, context_id, subject_id)`.
Changing your mind updates; it does not stack.

**R12.2** A member SHALL NOT record an outcome about themselves. An unknown label SHALL
be rejected.

**R12.3** Direct trust SHALL update exponentially:
`trust = current * (1 - weight) + score * weight`, clamped to `[0,1]`, starting from
`NEUTRAL_TRUST = 0.5`. It SHALL be **directional** — A→B is a separate document from B→A.

**R12.4** `passed` SHALL be a weaker signal than `waste` (weight 0.08 vs 0.30).

**R12.5** **The propagation invariant.** No amount of second-hand signal SHALL move a
member further from neutral than one first-hand outcome would. Enforced by
`PROPAGATION_CEILING = 0.28` and `CONSENSUS_AT = 3.0`.

**R12.6** A reporter's weight SHALL be `history × calibration accuracy`, where history is
`min(1, reports / FULL_RELIABILITY_AT)`. A brand-new account SHALL move nothing.

**R12.7** WHEN direct experience exists THE SYSTEM SHALL let the network shift it by at
most `PROPAGATION_WITH_DIRECT` (0.20) × consensus weight.

**R12.8** `confidence_multiplier` SHALL apply only after ≥3 samples and only to positive
bias, floored at 0.6.

**R12.9** `effective_trust` SHALL return the reasons behind the number.

**R12.10** WHEN the outcome context is `community` THE SYSTEM SHALL prefer the
`recruit_score` the agent actually predicted over any `predicted_score` the client sent.

**R12.11** A recorded outcome SHALL change who is recruited on the next identical query.

Verify: `test_outcomes.py` (all) — in particular
`::test_no_amount_of_hearsay_outweighs_one_first_hand_outcome`,
`::test_a_brand_new_account_cannot_poison_the_network`,
`::test_your_own_experience_outweighs_the_networks`,
`::test_a_recorded_outcome_changes_who_gets_recruited_next_time`;
`test_search.py::test_a_recorded_bad_outcome_demotes_someone_in_discovery`.

---

## R13 — Connections

**R13.1** THE SYSTEM SHALL key a connection on `pair_id(a, b)` — sorted, order-independent
— so a pair can hold exactly one document.

**R13.2** WHEN B requests A while A's request to B is pending THE SYSTEM SHALL auto-accept.

**R13.3** ONLY the recipient SHALL answer a request; ONLY the requester SHALL withdraw it.
Any other actor SHALL receive `403`.

**R13.4** A member SHALL NOT connect with themselves. An unknown `source` SHALL be rejected.

**R13.5** A repeat request SHALL NOT duplicate the record.

**R13.6** Every connection SHALL carry provenance (`discovery` | `interview` | `community`
| `feed` | `direct`), surfaced as counts.

Verify: `test_social.py::test_pair_id_is_order_independent` through
`::test_pending_separates_incoming_from_outgoing`.

---

## R14 — Feed, posts, and stories

**R14.1** WHEN a post's body is ≥120 characters (≥60 for a story) THE SYSTEM SHALL chunk,
embed, and add it to the author's persona as a source, and SHALL mark the post
`ingested`. Shorter posts SHALL NOT be ingested.

**R14.2** A story SHALL be filed as `kind: "episodic"` with a dated title
(`Story · YYYY-MM-DD`), not as a standing claim.

**R14.3** `story_is_active` SHALL be decided **server-side** on a 24-hour window. Only the
card expires; the episodic memory SHALL persist.

**R14.4** Feed ordering SHALL put connections (and the viewer) first, then the wider
network, each by recency.

**R14.5** Reactions SHALL be recounted from `feed_reactions`, never incremented. An unknown
reaction SHALL be rejected. A reaction on a missing post SHALL return `404`.

**R14.6** An agent post SHALL be **templated** from stored activity (gaps + interviews)
and SHALL carry the evidence rows it was derived from. It SHALL NOT be model-generated.
WHEN there is no activity THE SYSTEM SHALL return `409`.

**R14.7** Composer media (photos, clips, story images) SHALL be presentation only —
stored under `fm_*` / `sm_*`, never in `persona_media`, never searchable.

**R14.8** `POST /api/social/feed/draft` SHALL return a **draft** and SHALL NOT publish.
The member still has to post it.

Verify: `test_social.py::test_short_posts_are_not_ingested_into_retrieval` through
`::test_story_image_is_stored_as_presentation_not_persona_media`.

---

## R15 — Direct messages

**R15.1** THE SYSTEM SHALL require an **accepted** connection in both directions of the
conversation before reading or sending. Otherwise `403`.

**R15.2** Messages SHALL be keyed by `conversation_id = pair_id(a, b)` and ordered by a
per-conversation monotonic `sequence`, so two messages written in the same tick keep a
stable order.

**R15.3** A blank or oversized (>2000 chars) message SHALL be rejected.

**R15.4** Incoming messages SHALL stay unread until the recipient opens the thread.

**R15.5** Message bodies SHALL NOT be ingested as persona chunks.

Verify: `test_messages.py` (all).

---

## R16 — Deep research (spec §10)

**R16.1** THE SYSTEM SHALL resolve four gates, in this order, **before** issuing a single
search: subject consent (`research_enabled`, opt-in) → protected attributes → daily budget
→ availability.

**R16.2** WHEN the goal names a protected attribute THE SYSTEM SHALL return `422` with a
reason, not an empty brief.

**R16.3** WHEN the asker has spent ≥ `RESEARCH_DAILY_BUDGET_USD` in a rolling 24h,
metered from Exa's own `costDollars`, THE SYSTEM SHALL return `429`.

**R16.4** Queries SHALL be built in code (`build_queries`), bounded at `MAX_QUERIES` (4),
and anchored on the name. A model SHALL NOT write its own queries.

**R16.5** `identity_anchors()` SHALL admit only entity fields — organization, location,
website domain. It SHALL NOT admit anything name-derived (including the handle) and
SHALL NOT admit topic words from the headline or role.

**R16.6** A source that corroborates no anchor SHALL go to `unconfirmed_sources`, SHALL be
shown unattributed, and SHALL NOT become a finding. WHEN nothing is confirmed THE SYSTEM
SHALL decline with `decline_kind: "unconfirmed_identity"`.

**R16.7** WHEN a member has declared nothing to anchor on THE SYSTEM SHALL confirm nothing.

**R16.8** A finding whose `source_url` was not in the returned set SHALL be dropped, and
`dropped_claims` SHALL be reported. IF no finding survives THEN the brief SHALL decline.

**R16.9** `sources` SHALL mean "confirmed to be this member" in **every** status,
including declines.

**R16.10** Contact details SHALL be stripped from every snippet, summary, and finding.

**R16.11** A brief SHALL be readable only by its `asker_id`. There SHALL be no batch
endpoint.

**R16.12** A brief pending longer than `STALE_AFTER_SECONDS` (420) SHALL report failed.

Verify: `test_research.py` (all).

---

## R17 — Runtime honesty, degradation, and hardening

**R17.1** THE SYSTEM SHALL refuse to boot when `JWT_SECRET` is still the `.env.example`
value **and** the database is remote. Local databases and mongomock are exempt. A secret
under 32 bytes SHALL be rejected everywhere.

**R17.2** Every model call SHALL record which mode produced it: `live`,
`deterministic_fallback`, `fallback_after_error`, plus `no_grounding` (community) and
`permission_blocked` (interview).

**R17.3** Every stored vector SHALL carry `space()` = `provider:model:dimensions`, and
every retrieval SHALL filter on it. A provider change SHALL yield no results rather than
comparisons across incompatible spaces.

**R17.4** `voyage` and `mongodb` SHALL resolve to the **same** vector space; `voyage-4*`
models SHALL share the `voyage-4-series` space key.

**R17.5** `EmbeddingError` SHALL NOT be caught into a local fallback.

**R17.6** `GET /health` and `GET /api/runtime/status` SHALL report the live model,
embedding, rerank, and research paths, and the UI SHALL surface them.

**R17.7** Every datetime leaving a store SHALL carry an explicit UTC offset, including
inside nested dicts and lists.

**R17.8** A rate limit (429) SHALL NOT permanently disable reranking; only
`PERMANENT_STATUSES` (400/401/403/404/422) SHALL.

**R17.9** CORS SHALL accept both `localhost` and `127.0.0.1` spellings of the configured
origin, and SHALL apply a loopback port regex **only** when the configured origin is
itself loopback.

**R17.10** WHEN no LLM key is configured every agent surface SHALL take its decline path.
WHEN no vector index exists retrieval SHALL fall back to a scored scan and say so.

Verify: `test_hardening.py` (all), `test_embeddings.py` (all), `test_rerank.py` (all),
`test_llm.py` (all).

---

## Non-functional

| Requirement | Target | Where enforced |
|---|---|---|
| Discovery latency, no model call | < 500ms | `search.py` pool bounds |
| Live agent work | < 45s, async above that | `agent_timeout_seconds`, `BackgroundTasks` |
| Recruitment fan-out | ≤ 6 LLM calls per post | `MAX_RESPONDERS` |
| Research spend | ≤ `RESEARCH_DAILY_BUDGET_USD` / member / 24h | `research.spend_since` |
| Embedding requests | 1 per batch, never per item | `embed_batch` |
| Test suite | offline, no LLM or embedding API call, ever | `tests/conftest.py` |

**Privacy.** Owner derived from server context. Retrieval filtered by owner and space
*before* data enters a prompt. Embeddings never in a public response. No compiling of
personal data across members outside an explicit user request (R16).
