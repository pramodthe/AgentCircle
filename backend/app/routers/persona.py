from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.auth import CurrentUser
from app.dependencies import (
    AccountsDependency,
    AgentMemoryDependency,
    EmbeddingsDependency,
    MemoryLogDependency,
    PersonaBuilderDependency,
)
from app.ingestion import IngestionError, extract_upload, fetch_url
from app.memory_log import lint_persona
from app.schemas import SourceLinkCreate
from app.settings import get_settings

router = APIRouter(prefix="/api/persona", tags=["persona"])


def _store_source(accounts, builder, user_id: str, extracted, log=None) -> dict:
    chunks = builder.prepare_chunks(extracted)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No usable text was found in that source.",
        )
    source = accounts.add_source(
        user_id=user_id,
        title=extracted.title,
        kind=extracted.kind,
        detail=extracted.detail,
        text=extracted.text,
        chunks=chunks,
    )
    if log is not None:
        log.record(
            user_id=user_id,
            kind="source_added",
            summary=f"Added {extracted.title}",
            detail={"source_id": source["_id"], "chunks": len(chunks)},
        )
    return source


@router.get("")
def get_persona(user: CurrentUser, accounts: AccountsDependency) -> dict:
    user_id = user["_id"]
    return {
        "persona": accounts.get_persona(user_id),
        "sources": accounts.list_sources(user_id),
        "onboarding": accounts.onboarding_state(user_id),
    }


@router.post("/sources/upload", status_code=status.HTTP_201_CREATED)
async def upload_source(
    user: CurrentUser,
    accounts: AccountsDependency,
    builder: PersonaBuilderDependency,
    log: MemoryLogDependency,
    file: Annotated[UploadFile, File()],
) -> dict:
    settings = get_settings()
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is larger than {settings.max_upload_bytes // (1024 * 1024)}MB",
        )
    try:
        extracted = extract_upload(
            file.filename or "upload",
            data,
            max_characters=settings.max_source_characters,
        )
    except IngestionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _store_source(accounts, builder, user["_id"], extracted, log)


@router.post("/sources/link", status_code=status.HTTP_201_CREATED)
def add_link_source(
    payload: SourceLinkCreate,
    user: CurrentUser,
    accounts: AccountsDependency,
    builder: PersonaBuilderDependency,
    log: MemoryLogDependency,
) -> dict:
    settings = get_settings()
    try:
        extracted = fetch_url(
            payload.url,
            timeout=settings.url_fetch_timeout_seconds,
            max_characters=settings.max_source_characters,
        )
    except IngestionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _store_source(accounts, builder, user["_id"], extracted, log)


@router.get("/sources")
def list_sources(user: CurrentUser, accounts: AccountsDependency) -> list[dict]:
    return accounts.list_sources(user["_id"])


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    source_id: str,
    user: CurrentUser,
    accounts: AccountsDependency,
    memory: AgentMemoryDependency,
    log: MemoryLogDependency,
) -> None:
    # Collected before the delete, because afterwards there is nothing left to ask.
    removed = accounts.chunk_ids_for_source(user["_id"], source_id)
    if not accounts.delete_source(user["_id"], source_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    # The persona is pruned inside delete_source; memory cites the same chunks and would
    # otherwise keep repeating a claim whose evidence the member just removed.
    memory.forget_chunks(removed)
    log.record(
        user_id=user["_id"],
        kind="source_removed",
        summary="Removed a source and everything that cited it",
        detail={"source_id": source_id, "chunks": len(removed)},
    )


@router.post("/build")
def build_persona(
    user: CurrentUser,
    accounts: AccountsDependency,
    builder: PersonaBuilderDependency,
    log: MemoryLogDependency,
    rebuild: bool = False,
) -> dict:
    """Learn from any source the persona has not already been built from.

    This compounds rather than re-deriving: sources already extracted are skipped, so
    running it twice is cheap and — more importantly — cannot lose a fact the previous
    run found. `?rebuild=true` forces a clean re-derivation for the rare case where the
    stored persona is genuinely wrong.
    """
    user_id = user["_id"]
    chunks = accounts.list_chunks(user_id, with_embedding=False)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Add a resume, link, or website first so your agent has "
                "something to learn from."
            ),
        )
    profile = accounts.get_profile(user_id) or {}
    extras = {
        key: profile[key]
        for key in (
            "headline", "location", "skills", "interests",
            "looking_for", "likes", "dislikes", "hobbies",
        )
        if profile.get(key)
    }

    existing = None if rebuild else accounts.get_persona(user_id)
    seen: set[str] = set() if rebuild else set(
        (existing or {}).get("extracted_source_ids") or []
    )
    fresh = [chunk for chunk in chunks if chunk.get("source_id") not in seen]

    persona = builder.extract_incremental(
        new_chunks=fresh, existing=existing, extras=extras
    )
    persona["extracted_source_ids"] = sorted(
        seen | {chunk["source_id"] for chunk in chunks if chunk.get("source_id")}
    )
    persona["learned_now"] = len(fresh)

    saved = accounts.save_persona(user_id, persona)
    log.record(
        user_id=user_id,
        kind="persona_learned",
        summary=(
            f"Learned from {len(fresh)} new passage{'' if len(fresh) == 1 else 's'}"
            if fresh
            else "Nothing new to learn"
        ),
        detail={"passages": len(fresh), "rebuild": rebuild},
    )
    accounts.mark_onboarding_complete(user_id)
    return {"persona": saved, "onboarding": accounts.onboarding_state(user_id)}


@router.get("/log")
def persona_log(user: CurrentUser, log: MemoryLogDependency, limit: int = 50) -> list[dict]:
    """What this agent learned and when. Owner only."""
    return log.timeline(user["_id"], limit=limit)


@router.get("/lint")
def persona_lint(user: CurrentUser, accounts: AccountsDependency) -> dict:
    """Everything that looks wrong with the persona, for a human to decide about.

    Deterministic and model-free, so it costs nothing and cannot invent a problem.
    """
    user_id = user["_id"]
    chunks = accounts.list_chunks(user_id, with_embedding=False)
    findings = lint_persona(
        accounts.get_persona(user_id),
        known_chunk_ids={chunk["_id"] for chunk in chunks},
        source_ids={s["_id"] for s in accounts.list_sources(user_id)},
    )
    return {"findings": findings, "clean": not findings}


@router.get("/search")
def search_persona(
    q: str,
    request: Request,
    user: CurrentUser,
    accounts: AccountsDependency,
    embeddings: EmbeddingsDependency,
    limit: int = 6,
) -> list[dict]:
    """Retrieve your own grounded chunks. This is what agent answers will cite."""
    if len(q.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Query is too short"
        )
    return accounts.search_chunks(
        user_id=user["_id"],
        query_vector=embeddings.embed(q),
        space=embeddings.space(),
        limit=min(max(1, limit), 20),
        atlas=request.app.state.people_search._atlas_vector_ok,
    )
