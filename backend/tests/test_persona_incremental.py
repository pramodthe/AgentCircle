"""The persona must accumulate, never quietly lose.

Extraction is not deterministic, so a rebuild-from-scratch persona can drop a fact it
found last time. These pin the opposite behaviour: adding a source adds to what is known,
running twice changes nothing, and the only thing that ever removes a claim is the
disappearance of the evidence behind it.
"""

from app.persona import merge_persona, prune_persona


def item(value: str, chunk_id: str, source_id: str = "src_a") -> dict:
    return {
        "value": value,
        "chunk_id": chunk_id,
        "source_id": source_id,
        "source_title": f"{source_id}.txt",
    }


def values(persona: dict, field: str = "skills") -> set[str]:
    return {row["value"] for row in persona.get(field, [])}


def test_merging_a_new_source_keeps_what_was_already_known():
    first = {"skills": [item("idempotency keys", "chk_1")]}
    second = {"skills": [item("replay semantics", "chk_2", "src_b")]}

    merged = merge_persona(first, second)

    assert values(merged) == {"idempotency keys", "replay semantics"}


def test_merging_is_idempotent():
    """Running build twice must not duplicate a claim."""
    persona = {"skills": [item("idempotency keys", "chk_1")]}

    once = merge_persona(persona, {"skills": [item("idempotency keys", "chk_1")]})
    twice = merge_persona(once, {"skills": [item("idempotency keys", "chk_1")]})

    assert len(twice["skills"]) == 1
    assert values(twice) == {"idempotency keys"}


def test_the_same_claim_from_two_sources_keeps_both_as_support():
    """Two sources backing one skill is one chip, but two receipts."""
    merged = merge_persona(
        {"skills": [item("distributed systems", "chk_1", "src_a")]},
        {"skills": [item("Distributed Systems", "chk_9", "src_b")]},
    )

    assert len(merged["skills"]) == 1
    support = merged["skills"][0]["support"]
    assert {row["chunk_id"] for row in support} == {"chk_1", "chk_9"}


def test_deleting_one_of_two_supporting_sources_keeps_the_claim():
    """The claim is still cited — by the source that remains."""
    persona = merge_persona(
        {"skills": [item("distributed systems", "chk_1", "src_a")]},
        {"skills": [item("distributed systems", "chk_9", "src_b")]},
    )

    pruned = prune_persona(persona, {"chk_1"})

    assert values(pruned) == {"distributed systems"}
    assert pruned["skills"][0]["chunk_id"] == "chk_9"
    assert pruned["skills"][0]["source_id"] == "src_b"


def test_deleting_the_only_supporting_source_drops_the_claim():
    """A persona item may not outlive the chunk it cites."""
    persona = {"skills": [item("idempotency keys", "chk_1")]}

    pruned = prune_persona(persona, {"chk_1"})

    assert pruned["skills"] == []


def test_prose_supersedes_but_items_never_do():
    """A newer source describes a more current person, so the summary updates —
    but it must not take the evidence-bearing items down with it."""
    existing = {
        "headline": "Payments engineer",
        "summary": "Old summary.",
        "skills": [item("idempotency keys", "chk_1")],
    }
    addition = {"headline": "Reliability engineer", "summary": "New summary.", "skills": []}

    merged = merge_persona(existing, addition)

    assert merged["headline"] == "Reliability engineer"
    assert merged["summary"] == "New summary."
    assert values(merged) == {"idempotency keys"}


def test_an_empty_extraction_pass_cannot_erase_the_persona():
    """A model returning nothing is the exact case where the old rebuild lost facts."""
    existing = {
        "headline": "Payments engineer",
        "summary": "A summary.",
        "skills": [item("idempotency keys", "chk_1")],
        "interests": [item("incident review", "chk_2")],
    }

    merged = merge_persona(existing, {"skills": [], "interests": [], "summary": ""})

    assert values(merged) == {"idempotency keys"}
    assert values(merged, "interests") == {"incident review"}
    assert merged["summary"] == "A summary."
