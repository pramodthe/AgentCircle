"""Traversal finds paths, and only paths.

The graph exists so an introduction can be explained ("Priya knows Maya, you both write
about payments"). It must never become a second route to the thing agent_memory is
carefully keeping private — the contents of someone else's conversation.
"""

import pytest

from app.memory_graph import MemoryGraphStore
from app.mock_mongo import create_mock_client

KENJI, MAYA, PRIYA, SOFIA = "u_kenji", "u_maya", "u_priya", "u_sofia"
EVERYONE = [KENJI, MAYA, PRIYA, SOFIA]


@pytest.fixture()
def graph() -> MemoryGraphStore:
    store = MemoryGraphStore(create_mock_client()["testdb"])
    store.ensure_indexes()
    return store


def link(graph, a, b, via=None, rel="INTERVIEWED"):
    """A relationship as both sides see it."""
    graph.record(owner_id=a, counterparty_id=b, rel=rel, via=via or [])
    graph.record(owner_id=b, counterparty_id=a, rel=rel, via=via or [])


def test_a_friend_of_a_friend_is_reachable(graph):
    link(graph, KENJI, MAYA, via=["payments"])
    link(graph, MAYA, PRIYA, via=["payments"])

    reached = graph.reachable(owner_id=KENJI, allowed_ids=EVERYONE)

    assert [row["user_id"] for row in reached] == [PRIYA]
    assert reached[0]["through"] == [MAYA]
    assert reached[0]["via"] == ["payments"], "the shared topic explains the path"


def test_people_you_already_know_are_not_introductions(graph):
    link(graph, KENJI, MAYA)
    link(graph, MAYA, PRIYA)
    link(graph, KENJI, PRIYA)

    reached = graph.reachable(owner_id=KENJI, allowed_ids=EVERYONE)

    assert [row["user_id"] for row in reached] == []


def test_you_are_never_your_own_suggestion(graph):
    link(graph, KENJI, MAYA)

    assert all(row["user_id"] != KENJI for row in graph.reachable(
        owner_id=KENJI, allowed_ids=EVERYONE
    ))


def test_traversal_never_walks_through_a_member_who_opted_out(graph):
    """Maya is not discoverable, so she is not a stepping stone to Priya either."""
    link(graph, KENJI, MAYA)
    link(graph, MAYA, PRIYA)

    reached = graph.reachable(owner_id=KENJI, allowed_ids=[KENJI, PRIYA, SOFIA])

    assert [row["user_id"] for row in reached] == []


def test_traversal_returns_paths_never_conversation_contents(graph):
    """The disclosure boundary: who and why, never what was said."""
    link(graph, KENJI, MAYA, via=["payments"])
    link(graph, MAYA, PRIYA, via=["payments"])

    reached = graph.reachable(owner_id=KENJI, allowed_ids=EVERYONE)

    assert reached, "sanity: a path exists"
    allowed_keys = {"user_id", "hops", "through", "via"}
    for row in reached:
        assert set(row) == allowed_keys, f"traversal leaked extra fields: {set(row) - allowed_keys}"


def test_recording_the_same_relationship_twice_strengthens_it(graph):
    graph.record(owner_id=KENJI, counterparty_id=MAYA, rel="INTERVIEWED", via=["payments"])
    edge = graph.record(
        owner_id=KENJI, counterparty_id=MAYA, rel="INTERVIEWED", via=["payments", "climate"]
    )

    assert edge["strength"] == 2
    assert sorted(edge["via"]) == ["climate", "payments"], "topics accumulate, not overwrite"


def test_evidence_without_a_chunk_is_not_stored(graph):
    """Same rule as citations: an untraceable link is not kept."""
    edge = graph.record(
        owner_id=KENJI,
        counterparty_id=MAYA,
        rel="INTERVIEWED",
        evidence=[{"source_title": "hearsay"}, {"chunk_id": "chk_1", "source_title": "resume"}],
    )

    assert [row["chunk_id"] for row in edge.get("evidence", [])] == ["chk_1"]


def test_an_edge_needs_two_different_people(graph):
    with pytest.raises(ValueError):
        graph.record(owner_id=KENJI, counterparty_id=KENJI, rel="CONNECTED")


def test_shared_topics_rank_a_path_above_a_bare_one(graph):
    link(graph, KENJI, MAYA, via=["payments"])
    link(graph, MAYA, PRIYA, via=["payments"])   # shares a topic with Kenji's edge
    link(graph, MAYA, SOFIA, via=["gardening"])  # connected, but nothing in common

    reached = graph.reachable(owner_id=KENJI, allowed_ids=EVERYONE)

    assert [row["user_id"] for row in reached][0] == PRIYA
