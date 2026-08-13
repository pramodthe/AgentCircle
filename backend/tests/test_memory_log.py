"""The log records, the lint reports. Neither invents or resolves anything."""

import pytest

from app.memory_log import MemoryLog, lint_persona
from app.mock_mongo import create_mock_client

USER = "u_kenji"


def item(value: str, chunk_id: str, source_id="src_a", title="resume.txt") -> dict:
    return {
        "value": value,
        "chunk_id": chunk_id,
        "source_id": source_id,
        "source_title": title,
        "support": [
            {"chunk_id": chunk_id, "source_id": source_id, "source_title": title}
        ],
    }


@pytest.fixture()
def log() -> MemoryLog:
    store = MemoryLog(create_mock_client()["testdb"])
    store.ensure_indexes()
    return store


def test_the_log_is_newest_first(log):
    log.record(user_id=USER, kind="source_added", summary="added resume.txt")
    log.record(user_id=USER, kind="persona_learned", summary="learned 4 items")

    entries = log.timeline(USER)

    assert [row["kind"] for row in entries] == ["persona_learned", "source_added"]


def test_the_log_is_scoped_to_its_owner(log):
    log.record(user_id=USER, kind="source_added", summary="mine")
    log.record(user_id="u_maya", kind="source_added", summary="hers")

    assert [row["summary"] for row in log.timeline(USER)] == ["mine"]


def test_an_unknown_log_kind_is_rejected(log):
    with pytest.raises(ValueError):
        log.record(user_id=USER, kind="vibes", summary="x")


def test_lint_flags_a_claim_whose_source_is_gone():
    persona = {"skills": [item("idempotency keys", "chk_gone")]}

    findings = lint_persona(persona, known_chunk_ids={"chk_live"})

    assert [f["kind"] for f in findings] == ["orphaned_claim"]


def test_lint_flags_a_claim_with_no_source_at_all():
    persona = {"skills": [{"value": "invented skill"}]}

    findings = lint_persona(persona, known_chunk_ids=set())

    assert [f["kind"] for f in findings] == ["uncited_claim"]


def test_lint_flags_two_sources_that_disagree_on_a_number():
    """The example from the plan: resume says six years, a post says eight."""
    persona = {
        "skills": [
            item("six years in distributed systems", "chk_1", "src_a", "resume.txt"),
            item("eight years in distributed systems", "chk_2", "src_b", "post.txt"),
        ]
    }

    findings = lint_persona(persona, known_chunk_ids={"chk_1", "chk_2"})

    contradiction = next(f for f in findings if f["kind"] == "contradiction")
    assert contradiction["values"] == [
        "eight years in distributed systems",
        "six years in distributed systems",
    ]
    assert contradiction["sources"] == ["post.txt", "resume.txt"]


def test_lint_does_not_resolve_the_contradiction():
    """It reports both. Choosing one would be manufacturing a fact."""
    persona = {
        "skills": [
            item("six years shipping payments", "chk_1"),
            item("eight years shipping payments", "chk_2", "src_b", "post.txt"),
        ]
    }

    findings = lint_persona(persona, known_chunk_ids={"chk_1", "chk_2"})

    assert len(findings[0]["values"]) == 2, "both readings survive"
    assert "winner" not in findings[0] and "resolved" not in findings[0]


def test_the_same_claim_stated_identically_is_not_a_contradiction():
    persona = {
        "skills": [
            item("six years in payments", "chk_1"),
            item("six years in payments", "chk_2", "src_b"),
        ]
    }

    assert lint_persona(persona, known_chunk_ids={"chk_1", "chk_2"}) == []


def test_claims_without_numbers_are_never_contradictions():
    persona = {
        "skills": [
            item("distributed systems", "chk_1"),
            item("payments infrastructure", "chk_2"),
        ]
    }

    assert lint_persona(persona, known_chunk_ids={"chk_1", "chk_2"}) == []


def test_lint_flags_a_source_the_agent_learned_nothing_from():
    persona = {"skills": [item("payments", "chk_1", "src_a")]}

    findings = lint_persona(
        persona, known_chunk_ids={"chk_1"}, source_ids={"src_a", "src_ignored"}
    )

    unused = [f for f in findings if f["kind"] == "unused_source"]
    assert [f["source_id"] for f in unused] == ["src_ignored"]


def test_a_healthy_persona_lints_clean():
    persona = {"skills": [item("payments", "chk_1", "src_a")]}

    assert lint_persona(persona, known_chunk_ids={"chk_1"}, source_ids={"src_a"}) == []
