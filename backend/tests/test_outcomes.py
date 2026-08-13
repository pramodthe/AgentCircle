import pytest

from app.accounts import AccountStore
from app.auth import hash_password
from app.community import DEFAULT_COMMUNITY_SETTINGS, CommunityStore, rank_responders
from app.embeddings import EmbeddingClient
from app.ingestion import ExtractedSource
from app.llm import ChatModelBundle
from app.mock_mongo import create_mock_client
from app.outcomes import NEUTRAL_TRUST, OutcomeStore
from app.persona import PersonaBuilder
from app.settings import Settings

EMBEDDINGS = EmbeddingClient(provider="local", model="local", dimensions=128, api_key=None)
OPEN = {"comment_enabled": True, "comment_topics": [], "review_before_publish": False}


def build_world():
    client = create_mock_client()
    database = client["agentcircle-outcomes-test"]
    accounts = AccountStore(database)
    accounts.ensure_indexes()
    community = CommunityStore(database)
    community.ensure_indexes()
    outcomes = OutcomeStore(database)
    outcomes.ensure_indexes()
    builder = PersonaBuilder(
        embeddings=EMBEDDINGS,
        chat=ChatModelBundle(model=None, provider="test", model_name="test-model"),
        settings=Settings(chunk_characters=400, chunk_overlap_characters=40),
    )
    return accounts, community, outcomes, builder


def add_member(accounts, builder, email, name, text, *, settings=None):
    user = accounts.create_user(
        email=email, password_hash=hash_password("a good password"), display_name=name
    )
    source = ExtractedSource(title=f"{name}.txt", text=text, kind="upload", detail="seed")
    accounts.add_source(
        user_id=user["_id"], title=source.title, kind=source.kind, detail=source.detail,
        text=source.text, chunks=builder.prepare_chunks(source),
    )
    if settings is not None:
        accounts.update_member_settings(user["_id"], settings)
    return user


def report(outcomes, reporter, subject, label, *, context_id="ctx-1", predicted=None):
    return outcomes.record(
        reporter_id=reporter["_id"], subject_id=subject["_id"], label=label,
        context="community", context_id=context_id, predicted_score=predicted,
    )


# ------------------------------------------------------------------- recording


def test_outcome_is_idempotent_per_interaction() -> None:
    accounts, _, outcomes, builder = build_world()
    ada = add_member(accounts, builder, "ada@example.com", "Ada", "Ada bio.")
    bo = add_member(accounts, builder, "bo@example.com", "Bo", "Bo bio.")

    report(outcomes, ada, bo, "great")
    report(outcomes, ada, bo, "waste")  # changed their mind about the same meeting

    rows = outcomes.list_for_reporter(ada["_id"])
    assert len(rows) == 1, "re-reporting the same interaction must update, not stack"
    assert rows[0]["label"] == "waste"


def test_you_cannot_record_an_outcome_about_yourself() -> None:
    accounts, _, outcomes, builder = build_world()
    ada = add_member(accounts, builder, "ada@example.com", "Ada", "Ada bio.")
    with pytest.raises(PermissionError):
        report(outcomes, ada, ada, "great")


def test_unknown_label_is_rejected() -> None:
    accounts, _, outcomes, builder = build_world()
    ada = add_member(accounts, builder, "ada@example.com", "Ada", "Ada bio.")
    bo = add_member(accounts, builder, "bo@example.com", "Bo", "Bo bio.")
    with pytest.raises(ValueError):
        report(outcomes, ada, bo, "amazing")


# ---------------------------------------------------------------- direct trust


def test_direct_trust_moves_toward_the_outcome_without_overshooting() -> None:
    accounts, _, outcomes, builder = build_world()
    ada = add_member(accounts, builder, "ada@example.com", "Ada", "Ada bio.")
    bo = add_member(accounts, builder, "bo@example.com", "Bo", "Bo bio.")

    assert outcomes.direct_trust(ada["_id"], bo["_id"]) is None
    report(outcomes, ada, bo, "waste", context_id="c1")
    after_one = outcomes.direct_trust(ada["_id"], bo["_id"])

    assert after_one < NEUTRAL_TRUST
    assert after_one > 0.15, "one bad meeting must not collapse trust to the raw score"

    report(outcomes, ada, bo, "waste", context_id="c2")
    assert outcomes.direct_trust(ada["_id"], bo["_id"]) < after_one


def test_passing_on_someone_is_a_weaker_signal_than_a_wasted_meeting() -> None:
    accounts, _, outcomes, builder = build_world()
    ada = add_member(accounts, builder, "ada@example.com", "Ada", "Ada bio.")
    passed_on = add_member(accounts, builder, "p@example.com", "Pat", "Pat bio.")
    wasted = add_member(accounts, builder, "w@example.com", "Wes", "Wes bio.")

    report(outcomes, ada, passed_on, "passed")
    report(outcomes, ada, wasted, "waste")

    assert outcomes.direct_trust(ada["_id"], passed_on["_id"]) > outcomes.direct_trust(
        ada["_id"], wasted["_id"]
    )


def test_trust_is_directional() -> None:
    accounts, _, outcomes, builder = build_world()
    ada = add_member(accounts, builder, "ada@example.com", "Ada", "Ada bio.")
    bo = add_member(accounts, builder, "bo@example.com", "Bo", "Bo bio.")

    report(outcomes, ada, bo, "waste")
    assert outcomes.direct_trust(ada["_id"], bo["_id"]) < NEUTRAL_TRUST
    assert outcomes.direct_trust(bo["_id"], ada["_id"]) is None


# ------------------------------------------------------------ propagated trust


def test_another_members_outcome_moves_you_but_less_than_your_own_would() -> None:
    accounts, _, outcomes, builder = build_world()
    ada = add_member(accounts, builder, "ada@example.com", "Ada", "Ada bio.")
    subject = add_member(accounts, builder, "s@example.com", "Sam", "Sam bio.")
    reporters = [
        add_member(accounts, builder, f"r{i}@example.com", f"R{i}", "bio.") for i in range(5)
    ]
    # Each reporter builds a real track record so their signal counts.
    for index, reporter in enumerate(reporters):
        for other in range(5):
            report(outcomes, reporter, subject, "waste", context_id=f"warm-{index}-{other}")

    propagated = outcomes.effective_trust(ada["_id"], subject["_id"])
    assert propagated["direct"] is None
    assert propagated["contributors"] == 5
    assert propagated["value"] < NEUTRAL_TRUST, "the network's experience should reach Ada"

    # Ada's own equivalent experience must move her further than hearsay does.
    solo_accounts, _, solo_outcomes, solo_builder = build_world()
    solo_ada = add_member(solo_accounts, solo_builder, "ada@example.com", "Ada", "bio.")
    solo_subject = add_member(solo_accounts, solo_builder, "s@example.com", "Sam", "bio.")
    report(solo_outcomes, solo_ada, solo_subject, "waste")
    direct = solo_outcomes.effective_trust(solo_ada["_id"], solo_subject["_id"])

    assert direct["value"] < propagated["value"]


def test_no_amount_of_hearsay_outweighs_one_first_hand_outcome() -> None:
    """The invariant that keeps the trust channel from being worth attacking.

    A coordinated group with real track records still must not move a member further
    than a single meeting of their own would.
    """
    accounts, _, outcomes, builder = build_world()
    ada = add_member(accounts, builder, "ada@example.com", "Ada", "Ada bio.")
    subject = add_member(accounts, builder, "s@example.com", "Sam", "Sam bio.")

    mob = [add_member(accounts, builder, f"m{i}@example.com", f"M{i}", "bio.") for i in range(12)]
    for index, member in enumerate(mob):
        for other in range(8):
            report(outcomes, member, subject, "waste", context_id=f"mob-{index}-{other}")

    hearsay = outcomes.effective_trust(ada["_id"], subject["_id"])["value"]

    solo_accounts, _, solo_outcomes, solo_builder = build_world()
    solo_ada = add_member(solo_accounts, solo_builder, "ada@example.com", "Ada", "bio.")
    solo_subject = add_member(solo_accounts, solo_builder, "s@example.com", "Sam", "bio.")
    report(solo_outcomes, solo_ada, solo_subject, "waste")
    first_hand = solo_outcomes.effective_trust(solo_ada["_id"], solo_subject["_id"])["value"]

    assert hearsay < NEUTRAL_TRUST, "the network's experience should still reach Ada"
    assert hearsay > first_hand, (
        f"12 strangers ({hearsay}) moved Ada further than her own meeting ({first_hand})"
    )


def test_a_brand_new_account_cannot_poison_the_network() -> None:
    accounts, _, outcomes, builder = build_world()
    ada = add_member(accounts, builder, "ada@example.com", "Ada", "Ada bio.")
    subject = add_member(accounts, builder, "s@example.com", "Sam", "Sam bio.")
    attacker = add_member(accounts, builder, "bad@example.com", "Mal", "bio.")

    report(outcomes, attacker, subject, "waste")

    view = outcomes.effective_trust(ada["_id"], subject["_id"])
    # One report from a zero-history account carries almost no weight.
    assert view["value"] > 0.45, f"a single new account moved trust too far: {view}"
    assert outcomes.reporter_reliability(attacker["_id"]) < 0.5


def test_your_own_experience_outweighs_the_networks() -> None:
    accounts, _, outcomes, builder = build_world()
    ada = add_member(accounts, builder, "ada@example.com", "Ada", "Ada bio.")
    subject = add_member(accounts, builder, "s@example.com", "Sam", "Sam bio.")
    crowd = [add_member(accounts, builder, f"c{i}@example.com", f"C{i}", "bio.") for i in range(4)]

    # The crowd had a bad time with Sam; Ada repeatedly had a great one.
    for index, member in enumerate(crowd):
        for other in range(5):
            report(outcomes, member, subject, "waste", context_id=f"crowd-{index}-{other}")
    for round_index in range(4):
        report(outcomes, ada, subject, "great", context_id=f"ada-{round_index}")

    view = outcomes.effective_trust(ada["_id"], subject["_id"])
    assert view["direct"] > 0.7
    assert view["value"] > NEUTRAL_TRUST, "Ada's own repeated experience should win"
    assert view["contributors"] == 4


def test_effective_trust_explains_itself() -> None:
    accounts, _, outcomes, builder = build_world()
    ada = add_member(accounts, builder, "ada@example.com", "Ada", "Ada bio.")
    subject = add_member(accounts, builder, "s@example.com", "Sam", "Sam bio.")

    fresh = outcomes.effective_trust(ada["_id"], subject["_id"])
    assert fresh["value"] == NEUTRAL_TRUST
    assert "no outcomes recorded yet" in fresh["reasons"][0]

    report(outcomes, ada, subject, "great")
    after = outcomes.effective_trust(ada["_id"], subject["_id"])
    assert "your own past outcomes" in after["reasons"]


# ------------------------------------------------------------------ calibration


def test_an_over_promising_agent_gets_damped() -> None:
    accounts, _, outcomes, builder = build_world()
    ada = add_member(accounts, builder, "ada@example.com", "Ada", "Ada bio.")
    subjects = [
        add_member(accounts, builder, f"s{i}@example.com", f"S{i}", "bio.") for i in range(4)
    ]

    assert outcomes.confidence_multiplier(ada["_id"]) == 1.0

    # The agent kept predicting strong matches; every one was a waste.
    for index, subject in enumerate(subjects):
        report(outcomes, ada, subject, "waste", context_id=f"c{index}", predicted=0.9)

    record = outcomes.calibration(ada["_id"])
    assert record["samples"] == 4
    assert record["bias"] > 0.5, "predicted far above what actually happened"
    assert record["confidence_multiplier"] < 1.0
    assert record["confidence_multiplier"] >= 0.6, "damping must stay bounded"


def test_a_well_calibrated_agent_is_left_alone() -> None:
    accounts, _, outcomes, builder = build_world()
    ada = add_member(accounts, builder, "ada@example.com", "Ada", "Ada bio.")
    subjects = [
        add_member(accounts, builder, f"s{i}@example.com", f"S{i}", "bio.") for i in range(4)
    ]
    for index, subject in enumerate(subjects):
        report(outcomes, ada, subject, "great", context_id=f"c{index}", predicted=0.95)

    assert outcomes.calibration(ada["_id"])["confidence_multiplier"] == 1.0


# --------------------------------------------------- the loop actually closing


def test_a_recorded_outcome_changes_who_gets_recruited_next_time() -> None:
    """The whole point of F10: same question, different answer, because of what happened."""
    accounts, community, outcomes, builder = build_world()
    author = add_member(accounts, builder, "author@example.com", "Author", "Author bio.")
    text = "Builds distributed streaming infrastructure and real-time dispatch systems."
    first = add_member(accounts, builder, "a@example.com", "Ana", text, settings=OPEN)
    second = add_member(accounts, builder, "b@example.com", "Ben", text, settings=OPEN)

    common = {
        "query_vector": EMBEDDINGS.embed("real-time streaming infrastructure"),
        "space": EMBEDDINGS.space(),
        "chunks_by_user": accounts.chunks_by_user(
            exclude_user_id=author["_id"], space=EMBEDDINGS.space()
        ),
        "reputation": {},
        "topics": [],
        "settings_by_user": {
            user_id: {**DEFAULT_COMMUNITY_SETTINGS, **row}
            for user_id, row in accounts.all_member_settings().items()
        },
    }

    before = rank_responders(
        trust=outcomes.trust_map(author["_id"], [first["_id"], second["_id"]]), **common
    )
    assert {row["trust"] for row in before} == {NEUTRAL_TRUST}, "no history yet"
    before_scores = {row["user_id"]: row["recruit_score"] for row in before}
    assert before_scores[first["_id"]] == before_scores[second["_id"]]

    # The author met Ana twice and it was a waste both times.
    for round_index in range(2):
        report(outcomes, author, first, "waste", context_id=f"met-{round_index}")

    after = rank_responders(
        trust=outcomes.trust_map(author["_id"], [first["_id"], second["_id"]]), **common
    )
    after_scores = {row["user_id"]: row["recruit_score"] for row in after}

    assert after[0]["user_id"] == second["_id"], "the better outcome should now rank first"
    assert after_scores[first["_id"]] < before_scores[first["_id"]]
    assert after_scores[second["_id"]] == before_scores[second["_id"]], (
        "someone with no recorded outcomes should be unaffected"
    )


def test_trust_demotes_but_never_promotes_an_irrelevant_person() -> None:
    accounts, community, outcomes, builder = build_world()
    author = add_member(accounts, builder, "author@example.com", "Author", "Author bio.")
    relevant = add_member(
        accounts, builder, "rel@example.com", "Rel",
        "Builds distributed streaming infrastructure and real-time dispatch systems.",
        settings=OPEN,
    )
    irrelevant = add_member(
        accounts, builder, "irr@example.com", "Irr",
        "Runs clinical operations for outpatient nursing clinics.", settings=OPEN,
    )

    # The author adores the irrelevant member and dislikes the relevant one.
    for round_index in range(4):
        report(outcomes, author, irrelevant, "great", context_id=f"good-{round_index}")
        report(outcomes, author, relevant, "waste", context_id=f"bad-{round_index}")

    ranked = rank_responders(
        query_vector=EMBEDDINGS.embed("real-time streaming infrastructure backpressure"),
        space=EMBEDDINGS.space(),
        chunks_by_user=accounts.chunks_by_user(
            exclude_user_id=author["_id"], space=EMBEDDINGS.space()
        ),
        reputation={},
        topics=[],
        settings_by_user={
            user_id: {**DEFAULT_COMMUNITY_SETTINGS, **row}
            for user_id, row in accounts.all_member_settings().items()
        },
        trust=outcomes.trust_map(author["_id"], [relevant["_id"], irrelevant["_id"]]),
    )

    selected = [row["user_id"] for row in ranked]
    if irrelevant["_id"] in selected and relevant["_id"] in selected:
        scores = {row["user_id"]: row["semantic_score"] for row in ranked}
        assert scores[relevant["_id"]] > scores[irrelevant["_id"]], (
            "trust must not rewrite what someone actually knows"
        )
