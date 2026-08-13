from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient

from app.accounts import AccountStore
from app.agent_memory import AgentMemoryStore
from app.auth import assert_signing_key_is_safe
from app.community import CommunityStore
from app.community_agent import CommunityCommenter
from app.embeddings import build_embedding_client
from app.interview import InterviewAgent, InterviewStore
from app.llm import build_chat_model
from app.media import MediaStore, MultimodalEmbedder
from app.memory_graph import MemoryGraphStore
from app.memory_log import MemoryLog
from app.messages import MessageStore
from app.outcomes import OutcomeStore
from app.persona import PersonaBuilder
from app.profile_media import ProfileMediaStore
from app.rerank import build_reranker
from app.research import ExaClient, ResearchStore
from app.routers import auth as auth_router
from app.routers import community as community_router
from app.routers import discovery as discovery_router
from app.routers import interviews as interviews_router
from app.routers import media as media_router
from app.routers import messages as messages_router
from app.routers import outcomes as outcomes_router
from app.routers import persona as persona_router
from app.routers import profile as profile_router
from app.routers import research as research_router
from app.routers import social as social_router
from app.search import PeopleSearch
from app.settings import get_settings
from app.social import ConnectionStore, FeedStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Fail before serving a single request rather than after.
    assert_signing_key_is_safe(settings)
    if settings.use_mock_mongodb:
        from app.mock_mongo import create_mock_client

        client = create_mock_client()
    else:
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")

    database = client[settings.mongodb_database]
    accounts = AccountStore(database)
    accounts.ensure_indexes()
    community = CommunityStore(database)
    community.ensure_indexes()
    outcomes = OutcomeStore(database)
    outcomes.ensure_indexes()
    interviews = InterviewStore(database)
    interviews.ensure_indexes()
    connections = ConnectionStore(database)
    connections.ensure_indexes()
    feed = FeedStore(database)
    feed.ensure_indexes()
    media = MediaStore(database)
    media.ensure_indexes()
    # Separate store from MediaStore on purpose — see app/profile_media.py. Avatars are
    # presentation and must never reach a retrieval path.
    profile_media = ProfileMediaStore(database)
    profile_media.ensure_indexes()
    messages = MessageStore(database)
    messages.ensure_indexes()
    agent_memory = AgentMemoryStore(database)
    agent_memory.ensure_indexes()
    memory_graph = MemoryGraphStore(database)
    memory_graph.ensure_indexes()
    memory_log = MemoryLog(database)
    memory_log.ensure_indexes()
    research = ResearchStore(database)
    research.ensure_indexes()

    embeddings = build_embedding_client(settings)
    chat = build_chat_model(settings)
    persona_builder = PersonaBuilder(embeddings=embeddings, chat=chat, settings=settings)
    reranker = build_reranker(settings)
    # PeopleSearch detects real index availability at startup rather than trusting a
    # config flag, because $search against a missing index returns an empty result set
    # instead of raising. USE_MOCK_MONGODB is the one case where probing is pointless.
    people_search = PeopleSearch(
        database,
        embeddings=embeddings,
        atlas_enabled=not settings.use_mock_mongodb,
        reranker=reranker,
        rerank_candidates=settings.rerank_candidates,
    )

    app.state.mongo_client = client
    app.state.accounts = accounts
    app.state.community = community
    app.state.community_commenter = CommunityCommenter(chat)
    app.state.outcomes = outcomes
    app.state.interviews = interviews
    app.state.interview_agent = InterviewAgent(chat)
    app.state.connections = connections
    app.state.feed = feed
    app.state.media = media
    app.state.profile_media = profile_media
    app.state.messages = messages
    app.state.agent_memory = agent_memory
    app.state.memory_graph = memory_graph
    app.state.memory_log = memory_log
    app.state.research = research
    app.state.exa = ExaClient(
        api_key=settings.exa_api_key.get_secret_value() if settings.exa_api_key else None
    )
    # Photo search needs Voyage's multimodal endpoint. MongoDB AI does not cover
    # multimodal (ai.mongodb.com has no /multimodalembeddings), so this always uses
    # VOYAGE_API_KEY — independent of EMBEDDING_PROVIDER. With no key the surface
    # reports itself off rather than guessing.
    voyage_key = (
        settings.voyage_api_key.get_secret_value() if settings.voyage_api_key else None
    )
    app.state.multimodal = MultimodalEmbedder(
        api_key=voyage_key,
        endpoint="https://api.voyageai.com/v1/multimodalembeddings",
    )
    app.state.people_search = people_search
    app.state.embeddings = embeddings
    app.state.chat = chat
    app.state.reranker = reranker
    app.state.persona_builder = persona_builder
    yield
    client.close()


settings = get_settings()


def allowed_origins(raw: str) -> list[str]:
    """Expand FRONTEND_ORIGIN into every spelling a dev server actually uses.

    `npm run dev` binds 127.0.0.1 while the configured origin usually says localhost,
    and the browser treats those as different origins. Accept both, plus any extra
    comma-separated origins, so a port change is a config edit rather than a CORS bug.
    """
    origins: list[str] = []
    for origin in raw.split(","):
        origin = origin.strip().rstrip("/")
        if not origin:
            continue
        origins.append(origin)
        if "localhost" in origin:
            origins.append(origin.replace("localhost", "127.0.0.1"))
        elif "127.0.0.1" in origin:
            origins.append(origin.replace("127.0.0.1", "localhost"))
    return list(dict.fromkeys(origins))


def local_dev_origin_regex(raw: str) -> str | None:
    """Vite hops to 5174+ when 5173 is taken; those origins are not a config edit.

    Only when FRONTEND_ORIGIN itself is loopback — a production origin must stay
    an exact allowlist, not a regex that would accept any local tab.
    """
    if not any(host in raw for host in ("localhost", "127.0.0.1")):
        return None
    return r"https?://(localhost|127\.0\.0\.1)(:\d+)?"


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(settings.frontend_origin),
    allow_origin_regex=local_dev_origin_regex(settings.frontend_origin),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router.router)
app.include_router(profile_router.router)
app.include_router(persona_router.router)
app.include_router(community_router.router)
app.include_router(outcomes_router.router)
app.include_router(discovery_router.router)
app.include_router(interviews_router.router)
app.include_router(social_router.router)
app.include_router(media_router.router)
app.include_router(messages_router.router)
app.include_router(research_router.router)


def _runtime(request: Request) -> dict:
    """Which model and retrieval path are actually live.

    Every layer here has a working degraded mode and the app looks identical either way,
    so the only thing stopping a fallback from passing as the real system is saying so.
    """
    chat = request.app.state.chat
    reranker = request.app.state.reranker
    return {
        "model": {
            "configured": chat.configured,
            "provider": chat.provider,
            "model": chat.model_name if chat.configured else None,
            "mode": "live" if chat.configured else "deterministic_fallback",
            "warnings": list(chat.warnings),
        },
        "embeddings": request.app.state.embeddings.describe(),
        "rerank": reranker.describe(),
        "research": request.app.state.exa.describe(),
    }


@app.get("/health")
def health(request: Request) -> dict:
    request.app.state.mongo_client.admin.command("ping")
    return {"status": "ok", "database": "mongodb", **_runtime(request)}


@app.get("/api/runtime/status")
def runtime_status(request: Request) -> dict:
    return _runtime(request)
