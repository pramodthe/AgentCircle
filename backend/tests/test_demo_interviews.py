from app.accounts import AccountStore
from app.agent_memory import AgentMemoryStore
from app.auth import hash_password
from app.community import CommunityStore
from app.embeddings import EmbeddingClient
from app.ingestion import ExtractedSource
from app.interview import InterviewAgent, InterviewStore, safe_interview_settings
from app.llm import ChatModelBundle
from app.memory_graph import MemoryGraphStore
from app.mock_mongo import create_mock_client
from app.persona import PersonaBuilder
from app.settings import Settings
from scripts.demo_interviews import INTERVIEW_PLAN, seed_interviews

PASSWORD = hash_password("agentcircle")
EMBEDDINGS = EmbeddingClient(provider="local", model="local", dimensions=128, api_key=None)


def _world():
    database = create_mock_client()["demo-interviews"]
    accounts = AccountStore(database)
    community = CommunityStore(database)
    interviews = InterviewStore(database)
    memory = AgentMemoryStore(database)
    graph = MemoryGraphStore(database)
    accounts.ensure_indexes()
    community.ensure_indexes()
    interviews.ensure_indexes()
    memory.ensure_indexes()
    graph.ensure_indexes()
    agent = InterviewAgent(ChatModelBundle(model=None, provider="test", model_name="none"))
    return database, accounts, community, interviews, memory, graph, agent


def _register(accounts: AccountStore, email: str, name: str) -> dict:
    return accounts.create_user(email=email, password_hash=PASSWORD, display_name=name)


def _ingest(accounts: AccountStore, user_id: str, text: str) -> None:
    builder = PersonaBuilder(
        embeddings=EMBEDDINGS,
        chat=ChatModelBundle(model=None, provider="test", model_name="none"),
        settings=Settings(chunk_characters=300, chunk_overlap_characters=40),
    )
    source = ExtractedSource(
        title="background.txt",
        text=text,
        kind="upload",
        detail="seeded background document",
    )
    accounts.add_source(
        user_id=user_id,
        title=source.title,
        kind=source.kind,
        detail=source.detail,
        text=source.text,
        chunks=builder.prepare_chunks(source),
    )


def _seed(database, accounts, community, interviews, memory, graph, agent):
    return seed_interviews(
        database=database,
        accounts=accounts,
        community=community,
        embeddings=EMBEDDINGS,
        interviews=interviews,
        agent=agent,
        memory=memory,
        graph=graph,
        atlas=False,
    )


def test_seed_interviews_completes_with_unanswered_rows_when_no_model() -> None:
    """No LLM: InterviewAgent declines rather than inventing biography."""
    database, accounts, community, interviews, memory, graph, agent = _world()
    first = INTERVIEW_PLAN[0]
    _register(accounts, first["asker"], "Maya Chen")
    subject = _register(accounts, first["subject"], "Kenji Sato")
    accounts.update_member_settings(
        subject["_id"],
        safe_interview_settings({"interview_enabled": True, "interview_topics": ["hiring"]}),
    )
    _ingest(
        accounts,
        subject["_id"],
        "Kenji builds real-time dispatch systems for distributed energy.",
    )

    summary = _seed(database, accounts, community, interviews, memory, graph, agent)

    assert summary["ran"] == 1
    assert summary["failed"] == 0
    assert summary["skipped"] == len(INTERVIEW_PLAN) - 1
    assert summary["answered_rows"] == 0

    docs = list(database.interviews.find({}))
    assert len(docs) == 1
    doc = docs[0]
    assert doc["asker_id"] != doc["subject_id"]
    assert doc["runtime_mode"] is not None
    assert doc["runtime_mode"] == "deterministic_fallback"
    assert doc["rows"], "the agent records a row per question even when it cannot answer"
    assert all(not row["answered"] for row in doc["rows"])
    assert all(row.get("answer") == "" for row in doc["rows"])
    assert all(row["decline_kind"] == "no_model" for row in doc["rows"])
    # complete-with-unanswered, not a crash: status is complete and a verdict was stored.
    assert doc["status"] == "complete"
    assert (doc.get("verdict") or {}).get("recommendation") == "pass"

    again = _seed(database, accounts, community, interviews, memory, graph, agent)
    assert again["ran"] == 0
    assert again["failed"] == 0
    assert again["skipped"] == len(INTERVIEW_PLAN)
    assert database.interviews.count_documents({}) == 1


def test_seed_interviews_skips_when_subject_has_not_consented() -> None:
    database, accounts, community, interviews, memory, graph, agent = _world()
    first = INTERVIEW_PLAN[0]
    _register(accounts, first["asker"], "Maya Chen")
    subject = _register(accounts, first["subject"], "Kenji Sato")
    accounts.update_member_settings(
        subject["_id"],
        safe_interview_settings({"interview_enabled": False}),
    )

    summary = _seed(database, accounts, community, interviews, memory, graph, agent)

    assert summary["ran"] == 0
    assert summary["failed"] == 0
    assert summary["skipped"] == len(INTERVIEW_PLAN)
    assert database.interviews.count_documents({}) == 0
