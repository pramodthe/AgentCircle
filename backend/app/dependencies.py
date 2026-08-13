from typing import Annotated

from fastapi import Depends, Request

from app.accounts import AccountStore
from app.agent_memory import AgentMemoryStore
from app.community import CommunityStore
from app.embeddings import EmbeddingClient
from app.interview import InterviewStore
from app.media import MediaStore, MultimodalEmbedder
from app.memory_graph import MemoryGraphStore
from app.memory_log import MemoryLog
from app.messages import MessageStore
from app.outcomes import OutcomeStore
from app.persona import PersonaBuilder
from app.profile_media import ProfileMediaStore
from app.research import ResearchStore
from app.social import ConnectionStore, FeedStore


def get_accounts(request: Request) -> AccountStore:
    return request.app.state.accounts


def get_community(request: Request) -> CommunityStore:
    return request.app.state.community


def get_outcomes(request: Request) -> OutcomeStore:
    return request.app.state.outcomes


def get_interviews(request: Request) -> InterviewStore:
    return request.app.state.interviews


def get_agent_memory(request: Request) -> AgentMemoryStore:
    return request.app.state.agent_memory


def get_memory_graph(request: Request) -> MemoryGraphStore:
    return request.app.state.memory_graph


def get_memory_log(request: Request) -> MemoryLog:
    return request.app.state.memory_log


def get_connections(request: Request) -> ConnectionStore:
    return request.app.state.connections


def get_feed(request: Request) -> FeedStore:
    return request.app.state.feed


def get_embeddings(request: Request) -> EmbeddingClient:
    return request.app.state.embeddings


def get_persona_builder(request: Request) -> PersonaBuilder:
    return request.app.state.persona_builder


def get_research(request: Request) -> ResearchStore:
    return request.app.state.research


def get_media(request: Request) -> MediaStore:
    return request.app.state.media


def get_multimodal(request: Request) -> MultimodalEmbedder:
    return request.app.state.multimodal


def get_profile_media(request: Request) -> ProfileMediaStore:
    return request.app.state.profile_media


def get_messages(request: Request) -> MessageStore:
    return request.app.state.messages


AccountsDependency = Annotated[AccountStore, Depends(get_accounts)]
CommunityDependency = Annotated[CommunityStore, Depends(get_community)]
OutcomesDependency = Annotated[OutcomeStore, Depends(get_outcomes)]
InterviewsDependency = Annotated[InterviewStore, Depends(get_interviews)]
AgentMemoryDependency = Annotated[AgentMemoryStore, Depends(get_agent_memory)]
MemoryGraphDependency = Annotated[MemoryGraphStore, Depends(get_memory_graph)]
MemoryLogDependency = Annotated[MemoryLog, Depends(get_memory_log)]
ConnectionsDependency = Annotated[ConnectionStore, Depends(get_connections)]
FeedDependency = Annotated[FeedStore, Depends(get_feed)]
EmbeddingsDependency = Annotated[EmbeddingClient, Depends(get_embeddings)]
PersonaBuilderDependency = Annotated[PersonaBuilder, Depends(get_persona_builder)]
MediaDependency = Annotated[MediaStore, Depends(get_media)]
ResearchDependency = Annotated[ResearchStore, Depends(get_research)]
MultimodalDependency = Annotated[MultimodalEmbedder, Depends(get_multimodal)]
ProfileMediaDependency = Annotated[ProfileMediaStore, Depends(get_profile_media)]
MessagesDependency = Annotated[MessageStore, Depends(get_messages)]
