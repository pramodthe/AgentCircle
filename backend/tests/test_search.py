from app.accounts import AccountStore
from app.auth import hash_password
from app.embeddings import EmbeddingClient
from app.ingestion import ExtractedSource
from app.llm import ChatModelBundle
from app.mock_mongo import create_mock_client
from app.outcomes import OutcomeStore
from app.persona import PersonaBuilder
from app.search import RRF_K, Candidate, PeopleSearch, tokenize
from app.settings import Settings

EMBEDDINGS = EmbeddingClient(provider="local", model="local", dimensions=128, api_key=None)

PEOPLE = {
    "kenji": {
        "name": "Kenji Tanaka",
        "profile": {
            "headline": "Infrastructure engineer working on energy systems",
            "location": "Oakland",
            "skills": ["distributed systems", "kubernetes", "go"],
            "looking_for": ["senior backend engineers"],
        },
        "source": (
            "Kenji Tanaka builds distributed streaming infrastructure and real-time "
            "dispatch systems.\n\nOwns the exactly-once delivery path handling 400k "
            "events per minute, and wrote the backpressure and replay logic."
        ),
    },
    "elena": {
        "name": "Elena Rossi",
        "profile": {
            "headline": "Clinical operations lead",
            "location": "San Francisco",
            "skills": ["care coordination", "clinical workflows"],
            "looking_for": ["healthcare founders"],
        },
        "source": (
            "Elena Rossi runs clinical operations for outpatient clinics.\n\nFifteen "
            "years in healthcare operations, reviewing discharge workflows."
        ),
    },
    "priya": {
        "name": "Priya Raman",
        "profile": {
            "headline": "Design lead for early-stage product",
            "location": "San Francisco",
            "skills": ["interface design", "typography"],
            "looking_for": ["founding design roles"],
        },
        "source": (
            "Priya Raman designs early-stage products.\n\nTen years of interface design "
            "and typography; has been the first designer at three startups."
        ),
    },
}


def build_world():
    client = create_mock_client()
    database = client["agentcircle-search-test"]
    accounts = AccountStore(database)
    accounts.ensure_indexes()
    outcomes = OutcomeStore(database)
    outcomes.ensure_indexes()
    builder = PersonaBuilder(
        embeddings=EMBEDDINGS,
        chat=ChatModelBundle(model=None, provider="test", model_name="test-model"),
        settings=Settings(chunk_characters=400, chunk_overlap_characters=40),
    )
    # atlas_enabled=False: mongomock has no $vectorSearch, so this exercises the
    # fallback path that free-tier and offline development also run on.
    search = PeopleSearch(database, embeddings=EMBEDDINGS, atlas_enabled=False)

    members = {}
    for key, spec in PEOPLE.items():
        user = accounts.create_user(
            email=f"{key}@example.com",
            password_hash=hash_password("a good password"),
            display_name=spec["name"],
        )
        accounts.update_profile(user["_id"], spec["profile"])
        source = ExtractedSource(
            title=f"{key}.txt", text=spec["source"], kind="upload", detail="seed"
        )
        accounts.add_source(
            user_id=user["_id"], title=source.title, kind=source.kind,
            detail=source.detail, text=source.text, chunks=builder.prepare_chunks(source),
        )
        persona = builder.extract(
            chunks=accounts.list_chunks(user["_id"], with_embedding=False),
            extras=spec["profile"],
        )
        accounts.save_persona(user["_id"], persona)
        members[key] = user

    viewer = accounts.create_user(
        email="viewer@example.com",
        password_hash=hash_password("a good password"),
        display_name="Viewer",
    )
    accounts.update_profile(viewer["_id"], {"headline": "Just looking"})
    return accounts, outcomes, search, members, viewer


def run(search, accounts, viewer, query, *, trust=None, limit=8, min_match=0):
    """Defaults to no threshold so ranking tests see the whole ordering.

    The API default is 50; tests that care about filtering pass it explicitly.
    """
    profiles = {
        row["_id"]: row for row in search.db.profiles.find({"_id": {"$ne": viewer["_id"]}})
    }
    personas = {row["_id"]: row for row in search.db.personas.find({})}
    return search.search(
        query=query, viewer_id=viewer["_id"], profiles=profiles, personas=personas,
        trust=trust or {}, limit=limit, min_match_percent=min_match,
    )


# ------------------------------------------------------------------- primitives


def test_tokenize_drops_stopwords_and_keeps_technical_terms() -> None:
    tokens = tokenize("I am looking for someone who knows C++ and node.js")
    assert "c++" in tokens
    assert "node.js" in tokens
    assert "looking" not in tokens
    assert "for" not in tokens


def test_rrf_rewards_appearing_in_both_result_lists() -> None:
    both = Candidate(user_id="a", vector_rank=3, keyword_rank=3)
    vector_only = Candidate(user_id="b", vector_rank=1)
    assert both.rrf() > vector_only.rrf(), "agreement across retrievers should win"
    assert Candidate(user_id="c").rrf() == 0.0
    assert Candidate(user_id="d", vector_rank=1).rrf() == 1 / (RRF_K + 1)


# --------------------------------------------------------------------- ranking


def test_search_finds_the_right_person_for_a_semantic_query() -> None:
    accounts, _, search, members, viewer = build_world()
    result = run(search, accounts, viewer, "who can help with backpressure and replay?")

    assert result["matches"], "expected at least one match"
    assert result["matches"][0]["user_id"] == members["kenji"]["_id"]
    assert result["retrieval"]["fusion"] == "reciprocal_rank"


def test_keyword_only_query_still_matches_a_declared_field() -> None:
    accounts, _, search, members, viewer = build_world()
    result = run(search, accounts, viewer, "anyone doing typography work right now")

    top = result["matches"][0]
    assert top["user_id"] == members["priya"]["_id"]
    assert top["keyword_rank"] is not None
    assert "typography" in top["matched_terms"]


def test_the_searcher_is_never_in_their_own_results() -> None:
    accounts, _, search, members, viewer = build_world()
    accounts.update_profile(viewer["_id"], {"skills": ["distributed systems"]})
    result = run(search, accounts, viewer, "distributed systems and streaming")
    assert all(row["user_id"] != viewer["_id"] for row in result["matches"])


def test_match_percent_is_an_absolute_similarity_not_a_rank() -> None:
    """The old scale normalised against the top hit, so it moved when the pool did.

    That made it useless as a filter — a person's number depended on who else showed
    up — and its floor was 50, so "hide anything under 50%" could never hide anything.
    """
    accounts, _, search, _, viewer = build_world()
    result = run(search, accounts, viewer, "streaming infrastructure and clinical workflows")

    percents = [row["match_percent"] for row in result["matches"]]
    assert percents == sorted(percents, reverse=True)
    assert all(0 <= value <= 100 for value in percents)
    assert percents[0] != 99 or len(set(percents)) > 1, "not pinned to the top result"
    assert all(row["similarity_basis"] in {"rerank", "vector", "keyword_only"}
               for row in result["matches"])


def test_the_same_person_scores_the_same_in_a_smaller_pool() -> None:
    """The property the relative scale could not offer, and the reason to change it.

    A similarity that shifts when a stronger candidate appears cannot be compared
    across queries, so no fixed threshold means anything.
    """
    accounts, _, search, _, viewer = build_world()
    query = "backpressure and replay in streaming pipelines"

    everyone = run(search, accounts, viewer, query, limit=8)
    top = everyone["matches"][0]
    just_one = run(search, accounts, viewer, query, limit=1)

    assert just_one["matches"][0]["user_id"] == top["user_id"]
    assert just_one["matches"][0]["match_percent"] == top["match_percent"]


def test_the_threshold_hides_weak_matches_and_says_how_many() -> None:
    accounts, _, search, _, viewer = build_world()
    query = "streaming infrastructure and clinical workflows"

    everything = run(search, accounts, viewer, query, min_match=0)
    assert everything["threshold"]["hidden_below_threshold"] == 0

    strict = run(search, accounts, viewer, query, min_match=100)
    assert strict["matches"] == []
    # "no matches" and "no matches above your bar" must not look the same.
    assert strict["threshold"]["hidden_below_threshold"] == len(everything["matches"])
    assert strict["threshold"]["min_match_percent"] == 100


def test_raising_the_bar_never_reorders_what_survives() -> None:
    """The threshold filters; it does not rank. Ordering still comes from fusion."""
    accounts, _, search, _, viewer = build_world()
    query = "streaming infrastructure and clinical workflows"

    loose = [row["user_id"] for row in run(search, accounts, viewer, query, min_match=0)["matches"]]
    tight = run(search, accounts, viewer, query, min_match=60)["matches"]

    assert [row["user_id"] for row in tight] == [uid for uid in loose if uid in
                                                 {row["user_id"] for row in tight}]


def test_a_keyword_only_match_never_borrows_a_similarity_it_never_had() -> None:
    """No vector hit means nothing measured similarity. Reporting one would invent it."""
    from app.search import PeopleSearch

    percent, basis = PeopleSearch._similarity(
        {"vector_rank": None, "keyword_rank": 2, "vector_score": 0.0, "keyword_score": 9.9}
    )
    assert (percent, basis) == (0, "keyword_only")


def test_a_reranked_row_reports_the_reranker_not_the_cosine() -> None:
    from app.search import PeopleSearch

    percent, basis = PeopleSearch._similarity(
        {"rerank_score": 0.83, "vector_rank": 0, "vector_score": 0.61}
    )
    assert (percent, basis) == (83, "rerank")


def test_reasons_are_human_readable_and_leak_no_internals() -> None:
    accounts, _, search, _, viewer = build_world()
    result = run(search, accounts, viewer, "who knows about backpressure and replay?")

    for row in result["matches"]:
        assert row["why_it_clicks"], "every match must explain itself"
        joined = " ".join(row["why_it_clicks"]).lower()
        for leaked in ("embedding", "vector", "cosine", "rrf", "chunk_id"):
            assert leaked not in joined


# ----------------------------------------------------------- outcomes feed back


def test_a_recorded_bad_outcome_demotes_someone_in_discovery() -> None:
    accounts, outcomes, search, members, viewer = build_world()
    query = "who can help with streaming infrastructure?"

    before = run(search, accounts, viewer, query)
    before_scores = {row["user_id"]: row["score"] for row in before["matches"]}
    assert before["matches"][0]["user_id"] == members["kenji"]["_id"]

    for round_index in range(3):
        outcomes.record(
            reporter_id=viewer["_id"], subject_id=members["kenji"]["_id"], label="waste",
            context="discovery", context_id=f"met-{round_index}",
        )

    after = run(
        search, accounts, viewer, query,
        trust=outcomes.trust_map(viewer["_id"], [m["_id"] for m in members.values()]),
    )
    after_scores = {row["user_id"]: row["score"] for row in after["matches"]}

    assert after_scores[members["kenji"]["_id"]] < before_scores[members["kenji"]["_id"]]
    demoted = next(r for r in after["matches"] if r["user_id"] == members["kenji"]["_id"])
    assert "previous outcome" in " ".join(demoted["why_it_clicks"]).lower()


def test_trust_cannot_promote_an_irrelevant_person_above_a_relevant_one() -> None:
    """RRF scores are nearly flat, so an upward trust multiplier would dominate them.

    Trust is capped at no-op for this reason: liking someone is not expertise.
    """
    accounts, outcomes, search, members, viewer = build_world()
    query = "backpressure replay and exactly-once delivery"
    baseline = run(search, accounts, viewer, query)
    baseline_scores = {row["user_id"]: row["score"] for row in baseline["matches"]}

    for round_index in range(5):
        outcomes.record(
            reporter_id=viewer["_id"], subject_id=members["elena"]["_id"], label="great",
            context="discovery", context_id=f"loved-{round_index}",
        )

    trust = outcomes.trust_map(viewer["_id"], [m["_id"] for m in members.values()])
    assert trust[members["elena"]["_id"]] > 0.7, "she really is well-trusted"

    result = run(search, accounts, viewer, query, trust=trust)
    ids = [row["user_id"] for row in result["matches"]]
    assert ids.index(members["kenji"]["_id"]) < ids.index(members["elena"]["_id"]), (
        "loving someone must not make them the streaming expert"
    )
    # High trust is a no-op, not a boost.
    after = {row["user_id"]: row["score"] for row in result["matches"]}
    assert after[members["elena"]["_id"]] == baseline_scores[members["elena"]["_id"]]


def test_retrieval_status_reports_the_path_actually_used() -> None:
    accounts, _, search, _, viewer = build_world()
    result = run(search, accounts, viewer, "streaming infrastructure")

    # mongomock cannot serve $vectorSearch, so both retrievers must report local
    # rather than silently claiming Atlas.
    assert result["retrieval"]["vector"] == "local"
    assert result["retrieval"]["keyword"] == "local"
    assert result["retrieval"]["semantic"] is False
    assert result["retrieval"]["embedding_space"] == EMBEDDINGS.space()


def test_missing_indexes_are_detected_up_front_not_inferred_from_empty_results() -> None:
    """A missing index must degrade to local, never silently return nothing.

    `$search` against a nonexistent index returns an empty result set rather than
    raising, so availability has to be probed. Without this the API would report
    "atlas" while every keyword result quietly vanished.
    """
    accounts, _, _, _, viewer = build_world()
    client = create_mock_client()
    optimistic = PeopleSearch(
        _clone_into(client, accounts), embeddings=EMBEDDINGS, atlas_enabled=True
    )

    assert optimistic._probed is True
    assert optimistic._atlas_vector_ok is False
    assert optimistic._atlas_text_ok is False

    profiles = {row["_id"]: row for row in optimistic.db.profiles.find({})}
    personas = {row["_id"]: row for row in optimistic.db.personas.find({})}
    result = optimistic.search(
        query="streaming infrastructure and backpressure",
        viewer_id=viewer["_id"], profiles=profiles, personas=personas,
    )

    assert result["retrieval"]["vector"] == "local"
    assert result["retrieval"]["keyword"] == "local"
    assert result["matches"], "fallback must still return results"


def test_kill_switch_forces_local_even_when_indexes_exist() -> None:
    accounts, _, _, _, _ = build_world()
    client = create_mock_client()
    disabled = PeopleSearch(
        _clone_into(client, accounts), embeddings=EMBEDDINGS, atlas_enabled=False
    )
    assert disabled.probe() == {"vector": False, "keyword": False}


def _clone_into(client, accounts):
    """Copy the seeded fixture into a fresh mongomock database."""
    target = client["atlas-probe"]
    for name in ("users", "profiles", "personas", "persona_chunks", "persona_sources"):
        rows = list(accounts.db[name].find({}))
        if rows:
            target[name].insert_many(rows)
    return target
