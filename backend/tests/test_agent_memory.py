"""Memory must not cross between relationships.

The failure this guards against is concrete: Kenji's agent remembers what Maya's agent
told it, then repeats it while Kenji is talking to Priya. That leaks a private exchange
between two other people through a third, and no amount of good ranking makes it
acceptable. These tests assert the boundary holds at the store, which is where it is
enforced — not in whichever caller happens to read it.
"""

import pytest

from app.agent_memory import AgentMemoryStore, memories_from_interview
from app.mock_mongo import create_mock_client
from app.social import pair_id

SPACE = "test:test:4"

KENJI, MAYA, PRIYA = "u_kenji", "u_maya", "u_priya"


@pytest.fixture()
def memory() -> AgentMemoryStore:
    store = AgentMemoryStore(create_mock_client()["testdb"])
    store.ensure_indexes()
    return store


def write(store: AgentMemoryStore, owner: str, counterparty: str, text: str, vector=None):
    return store.remember(
        owner_id=owner,
        counterparty_id=counterparty,
        kind="interview_asked",
        text=text,
        embedding=vector or [1.0, 0.0, 0.0, 0.0],
        space=SPACE,
    )


def test_recall_never_returns_another_counterpartys_memory(memory):
    """The core guarantee. Same owner, different edge — must not surface."""
    write(memory, KENJI, MAYA, "Maya said she writes seed checks in climate hardware")
    write(memory, KENJI, PRIYA, "Priya said she is hiring backend engineers")

    recalled = memory.recall(
        owner_id=KENJI,
        counterparty_id=PRIYA,
        query_vector=[1.0, 0.0, 0.0, 0.0],
        space=SPACE,
        limit=10,
    )

    texts = " ".join(row["text"] for row in recalled)
    assert "Priya" in texts
    assert "Maya" not in texts, "memory from another relationship leaked into this one"


def test_recall_never_returns_another_owners_memory(memory):
    """Same edge, different owner. Each side's view of a conversation is its own."""
    write(memory, KENJI, MAYA, "what Kenji privately noted")
    write(memory, MAYA, KENJI, "what Maya privately noted")

    kenjis = memory.recall(
        owner_id=KENJI, counterparty_id=MAYA,
        query_vector=[1.0, 0.0, 0.0, 0.0], space=SPACE, limit=10,
    )

    assert [row["text"] for row in kenjis] == ["what Kenji privately noted"]


def test_an_edge_with_no_memory_recalls_nothing(memory):
    write(memory, KENJI, MAYA, "something about Maya")

    assert memory.recall(
        owner_id=KENJI, counterparty_id=PRIYA,
        query_vector=[1.0, 0.0, 0.0, 0.0], space=SPACE, limit=10,
    ) == []


def test_the_edge_id_is_order_independent(memory):
    """Both parties key the same relationship, so neither can create a second edge."""
    assert pair_id(KENJI, MAYA) == pair_id(MAYA, KENJI)
    row = write(memory, KENJI, MAYA, "x")
    assert row["edge_id"] == pair_id(MAYA, KENJI)


def test_memory_from_a_stale_embedding_space_is_ignored(memory):
    """Same rule as persona chunks: never compare vectors across incompatible spaces."""
    memory.remember(
        owner_id=KENJI, counterparty_id=MAYA, kind="message", text="old vector",
        embedding=[1.0, 0.0, 0.0, 0.0], space="old:model:4",
    )

    assert memory.recall(
        owner_id=KENJI, counterparty_id=MAYA,
        query_vector=[1.0, 0.0, 0.0, 0.0], space=SPACE, limit=10,
    ) == []


def test_forgetting_a_chunk_removes_the_memory_it_supported(memory):
    """A memory may not outlive the evidence it cites."""
    memory.remember(
        owner_id=KENJI, counterparty_id=MAYA, kind="interview_asked",
        text="grounded in a chunk", embedding=[1.0, 0.0, 0.0, 0.0],
        space=SPACE, chunk_id="chk_gone",
    )

    assert memory.forget_chunks({"chk_gone"}) == 1
    assert memory.recall(
        owner_id=KENJI, counterparty_id=MAYA,
        query_vector=[1.0, 0.0, 0.0, 0.0], space=SPACE, limit=10,
    ) == []


def test_counterparties_lists_only_the_owners_own_relationships(memory):
    write(memory, KENJI, MAYA, "a")
    write(memory, KENJI, PRIYA, "b")
    write(memory, MAYA, PRIYA, "not Kenji's business")

    ids = {row["_id"] for row in memory.counterparties(KENJI)}

    assert ids == {MAYA, PRIYA}


def test_an_interview_gives_each_side_its_own_memory():
    """One exchange, two owners, two different points of view."""
    rows = [
        {
            "question": "Have you shipped a payments system?",
            "answer": "Yes — a settlement reconciliation pipeline.",
            "answered": True,
            "citations": [{"chunk_id": "chk_1", "source_title": "resume.txt"}],
        }
    ]

    pending = memories_from_interview(
        asker_id=KENJI, subject_id=MAYA, goal="find a payments person", rows=rows
    )

    owners = {row["owner_id"] for row in pending}
    assert owners == {KENJI, MAYA}

    asker_row = next(r for r in pending if r["owner_id"] == KENJI)
    assert asker_row["counterparty_id"] == MAYA
    assert asker_row["chunk_id"] == "chk_1", "the asker's memory keeps its citation"

    subject_row = next(r for r in pending if r["owner_id"] == MAYA)
    assert subject_row["counterparty_id"] == KENJI


def test_a_declined_answer_does_not_become_a_remembered_claim():
    """A decline means "not in profile". Remembering it as knowledge inverts it."""
    rows = [
        {
            "question": "What are their salary expectations?",
            "answer": "",
            "answered": False,
            "citations": [],
        }
    ]

    pending = memories_from_interview(asker_id=KENJI, subject_id=MAYA, goal="", rows=rows)

    assert all(row["owner_id"] != KENJI for row in pending), (
        "the asker must not remember an answer they never got"
    )
    # The subject still learns they were asked — that is the demand signal.
    assert any(row["owner_id"] == MAYA for row in pending)


def test_an_unknown_memory_kind_is_rejected(memory):
    with pytest.raises(ValueError):
        memory.remember(
            owner_id=KENJI, counterparty_id=MAYA, kind="speculation",
            text="x", embedding=[1.0, 0.0, 0.0, 0.0], space=SPACE,
        )
