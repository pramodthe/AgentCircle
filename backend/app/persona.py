"""Build an agent persona from a user's own documents.

Two layers, deliberately separate:

  persona_chunks  — verbatim text from what the user gave us, embedded, with the
                    source it came from. This is the evidence.
  personas        — a structured summary (headline, skills, interests, looking_for)
                    with each item pointing at the chunk that supports it.

Nothing here invents biographical facts. When a model is configured it extracts and
attributes; when one is not, a heuristic pass produces a smaller persona that is
explicitly labelled as unextracted rather than pretending to be model output. The
downstream rule that an agent must answer "not in profile" instead of guessing only
works if this layer never manufactures the profile.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.embeddings import EmbeddingClient
from app.ingestion import ExtractedSource, chunk_text
from app.llm import ChatModelBundle
from app.settings import Settings

EXTRACTION_SYSTEM_PROMPT = (
    "You build a professional persona from a person's own documents. Use only the "
    "provided excerpts. Never invent employers, titles, dates, schools, or claims that "
    "are not present. Every list item must be supported by an excerpt, and you must "
    "cite the excerpt number that supports it. If the excerpts do not support a field, "
    "return an empty list for it rather than guessing. Write in third person, plainly, "
    "with no marketing language."
)


class PersonaItem(BaseModel):
    value: str = Field(min_length=1, max_length=160)
    chunk_index: int = Field(ge=0)


class PersonaExtraction(BaseModel):
    headline: str = Field(default="", max_length=160)
    summary: str = Field(default="", max_length=1200)
    skills: list[PersonaItem] = Field(default_factory=list, max_length=20)
    interests: list[PersonaItem] = Field(default_factory=list, max_length=20)
    looking_for: list[PersonaItem] = Field(default_factory=list, max_length=10)
    notable: list[PersonaItem] = Field(default_factory=list, max_length=10)


class PersonaBuilder:
    def __init__(
        self,
        *,
        embeddings: EmbeddingClient,
        chat: ChatModelBundle,
        settings: Settings,
    ) -> None:
        self.embeddings = embeddings
        self.chat = chat
        self.settings = settings

    def prepare_chunks(self, source: ExtractedSource) -> list[dict[str, Any]]:
        """Chunk and embed one source. Returns rows ready for the store."""
        pieces = chunk_text(
            source.text,
            size=self.settings.chunk_characters,
            overlap=self.settings.chunk_overlap_characters,
        )
        if not pieces:
            return []
        vectors = self.embeddings.embed_batch(pieces)
        return [
            {
                "text": text,
                "ordinal": index,
                "embedding": vector,
                "space": self.embeddings.space(),
                "characters": len(text),
            }
            for index, (text, vector) in enumerate(zip(pieces, vectors, strict=True))
        ]

    def extract(
        self,
        *,
        chunks: list[dict[str, Any]],
        extras: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        extras = extras or {}
        if not chunks:
            return self._empty_persona(extras)
        if self.chat.model is None:
            return self._heuristic_persona(chunks, extras)
        try:
            return self._model_persona(chunks, extras)
        except Exception as exc:
            persona = self._heuristic_persona(chunks, extras)
            persona["extraction_error"] = f"{type(exc).__name__}: {exc}"[:400]
            return persona

    def extract_incremental(
        self,
        *,
        new_chunks: list[dict[str, Any]],
        existing: dict[str, Any] | None,
        extras: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract from newly added chunks and merge into what is already known.

        The rebuild path (`extract`) re-derives the whole persona from one bounded
        window, which means a long source is truncated and — because extraction is not
        deterministic — a second run can quietly *lose* a fact the first run found. That
        is the wrong shape for something a member is told their agent knows about them.

        Here each source contributes its own passes and the result is unioned into the
        stored persona, so knowledge accumulates instead of being re-derived. Nothing is
        removed except by `prune_persona`, which only ever drops a claim whose evidence
        is gone.
        """
        extras = extras or {}
        base = dict(existing or {})
        if not new_chunks:
            # Still refresh the parts derived from declared fields, without touching items.
            return _recompute(base, extras, self._coverage)

        merged = base
        for start in range(0, min(len(new_chunks), WINDOW * MAX_WINDOWS), WINDOW):
            window = new_chunks[start : start + WINDOW]
            if not window:
                break
            if self.chat.model is None:
                addition = self._heuristic_persona(window, extras)
            else:
                try:
                    addition = self._finalize(
                        self._extract_window(window, extras), window, extras, mode="model"
                    )
                except Exception as exc:
                    addition = self._heuristic_persona(window, extras)
                    addition["extraction_error"] = f"{type(exc).__name__}: {exc}"[:400]
            merged = merge_persona(merged, addition)

        merged["chunks_seen"] = int(base.get("chunks_seen") or 0) + len(new_chunks)
        return _recompute(merged, extras, self._coverage)

    def _model_persona(
        self, chunks: list[dict[str, Any]], extras: dict[str, Any]
    ) -> dict[str, Any]:
        # Bound the prompt: early chunks of a resume or bio carry the identity content.
        window = chunks[:WINDOW]
        return self._finalize(self._extract_window(window, extras), window, extras, mode="model")

    def _extract_window(
        self, window: list[dict[str, Any]], extras: dict[str, Any]
    ) -> PersonaExtraction:
        excerpts = "\n\n".join(
            f"[{index}] (from {chunk.get('source_title', 'source')})\n{chunk['text']}"
            for index, chunk in enumerate(window)
        )
        declared = json.dumps(extras, ensure_ascii=False) if extras else "{}"
        structured = self.chat.model.with_structured_output(PersonaExtraction)
        result = structured.invoke(
            [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Excerpts from this person's own documents:\n\n{excerpts}\n\n"
                        f"Details they entered themselves (already trusted, use for "
                        f"context but still cite excerpts for extracted claims):\n{declared}\n\n"
                        "Produce the persona."
                    ),
                },
            ]
        )
        if not isinstance(result, PersonaExtraction):
            result = PersonaExtraction.model_validate(result)
        return result

    def _heuristic_persona(
        self, chunks: list[dict[str, Any]], extras: dict[str, Any]
    ) -> dict[str, Any]:
        """No-model path: use what the user typed, plus the opening of their documents.

        Deliberately thin. It is better for the persona to be visibly sparse than for
        it to look complete while being guessed at.
        """
        first = chunks[0]["text"] if chunks else ""
        summary = first[:600].strip()
        extraction = PersonaExtraction(
            headline=str(extras.get("headline") or "")[:160],
            summary=summary,
            skills=[
                PersonaItem(value=str(value)[:160], chunk_index=0)
                for value in (extras.get("skills") or [])[:20]
            ],
            interests=[
                PersonaItem(value=str(value)[:160], chunk_index=0)
                for value in (extras.get("interests") or [])[:20]
            ],
            looking_for=[
                PersonaItem(value=str(value)[:160], chunk_index=0)
                for value in (extras.get("looking_for") or [])[:10]
            ],
        )
        return self._finalize(extraction, chunks, extras, mode="heuristic")

    def _empty_persona(self, extras: dict[str, Any]) -> dict[str, Any]:
        return {
            "headline": str(extras.get("headline") or "")[:160],
            "summary": "",
            "skills": [],
            "interests": [],
            "looking_for": [],
            "notable": [],
            "extraction_mode": "empty",
            "extraction_model": None,
            "source_count": 0,
            "chunk_count": 0,
            "coverage": self._coverage([], [], [], extras),
        }

    def _finalize(
        self,
        extraction: PersonaExtraction,
        chunks: list[dict[str, Any]],
        extras: dict[str, Any],
        *,
        mode: str,
    ) -> dict[str, Any]:
        def attach(items: list[PersonaItem]) -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for item in items:
                # A citation pointing at a chunk we did not send is dropped, not kept:
                # an unverifiable attribution is worse than no attribution.
                if item.chunk_index >= len(chunks):
                    continue
                chunk = chunks[item.chunk_index]
                rows.append(
                    {
                        "value": item.value,
                        "chunk_id": chunk.get("_id"),
                        "source_id": chunk.get("source_id"),
                        "source_title": chunk.get("source_title"),
                    }
                )
            return rows

        skills = attach(extraction.skills)
        interests = attach(extraction.interests)
        looking_for = attach(extraction.looking_for)
        source_ids = {chunk.get("source_id") for chunk in chunks if chunk.get("source_id")}
        return {
            "headline": extraction.headline or str(extras.get("headline") or "")[:160],
            "summary": extraction.summary,
            "skills": skills,
            "interests": interests,
            "looking_for": looking_for,
            "notable": attach(extraction.notable),
            "extraction_mode": mode,
            "extraction_model": self.chat.model_name if mode == "model" else None,
            "source_count": len(source_ids),
            "chunk_count": len(chunks),
            "coverage": self._coverage(skills, interests, looking_for, extras),
        }

    @staticmethod
    def _coverage(
        skills: list[dict[str, Any]],
        interests: list[dict[str, Any]],
        looking_for: list[dict[str, Any]],
        extras: dict[str, Any],
    ) -> dict[str, Any]:
        """What the persona still can't answer.

        Surfaced to the user as onboarding prompts, and later as the "your agent was
        asked this and had nothing" signal.
        """
        missing: list[str] = []
        if not skills:
            missing.append("skills")
        if not interests:
            missing.append("interests")
        if not looking_for:
            missing.append("what you're looking for")
        if not extras.get("location"):
            missing.append("location")
        if not extras.get("headline"):
            missing.append("headline")
        filled = 5 - len(missing)
        return {
            "missing": missing,
            "score": round(max(0.0, min(1.0, filled / 5)), 2),
        }


ITEM_FIELDS = ("skills", "interests", "looking_for", "notable")
WINDOW = 24
MAX_WINDOWS = 4


def _norm(value: str) -> str:
    return " ".join(str(value).lower().split())


def _support_of(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Every chunk backing this item, tolerating rows written before `support` existed."""
    support = [row for row in (item.get("support") or []) if row.get("chunk_id")]
    if support:
        return support
    if item.get("chunk_id"):
        return [
            {
                "chunk_id": item.get("chunk_id"),
                "source_id": item.get("source_id"),
                "source_title": item.get("source_title"),
            }
        ]
    return []


def _promote(value: str, support: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep the flat citation fields the API and UI already read, plus the full support."""
    head = support[0]
    return {
        "value": value,
        "chunk_id": head.get("chunk_id"),
        "source_id": head.get("source_id"),
        "source_title": head.get("source_title"),
        "support": support,
    }


def merge_persona(existing: dict[str, Any], addition: dict[str, Any]) -> dict[str, Any]:
    """Union two personas. Additive and idempotent.

    Items are keyed by their normalised value, and each keeps *every* chunk that supports
    it rather than only the first. That matters for deletion: if two sources both back a
    skill, removing one of them must not strip the claim.
    """
    merged: dict[str, Any] = {**existing}
    for field in ITEM_FIELDS:
        by_key: dict[str, dict[str, Any]] = {}
        for item in [*(existing.get(field) or []), *(addition.get(field) or [])]:
            value = str(item.get("value") or "").strip()
            support = _support_of(item)
            if not value or not support:
                continue
            row = by_key.setdefault(_norm(value), {"value": value, "support": []})
            seen = {entry.get("chunk_id") for entry in row["support"]}
            row["support"].extend(e for e in support if e.get("chunk_id") not in seen)
        merged[field] = [_promote(row["value"], row["support"]) for row in by_key.values()]

    # Prose is the one part that genuinely supersedes rather than accumulates — a newer
    # source describes a more current person. The evidence-bearing items never do this.
    for key in ("headline", "summary"):
        if str(addition.get(key) or "").strip():
            merged[key] = addition[key]
        else:
            merged.setdefault(key, existing.get(key, ""))

    for key in ("extraction_mode", "extraction_model"):
        if addition.get(key):
            merged[key] = addition[key]
    if addition.get("extraction_error"):
        merged["extraction_error"] = addition["extraction_error"]
    return merged


def prune_persona(
    persona: dict[str, Any], removed_chunk_ids: set[str]
) -> dict[str, Any]:
    """Drop support that no longer exists, and any claim left with none.

    A persona item outliving the chunk it cites would be exactly the uncited claim the
    rest of the product refuses to publish.
    """
    if not persona or not removed_chunk_ids:
        return persona
    pruned = {**persona}
    for field in ITEM_FIELDS:
        rows: list[dict[str, Any]] = []
        for item in persona.get(field) or []:
            support = [
                entry
                for entry in _support_of(item)
                if entry.get("chunk_id") not in removed_chunk_ids
            ]
            if support:
                rows.append(_promote(str(item.get("value") or ""), support))
        pruned[field] = rows
    return pruned


def _recompute(
    persona: dict[str, Any], extras: dict[str, Any], coverage: Any
) -> dict[str, Any]:
    """Refresh the derived fields after items change."""
    result = {**persona}
    result.setdefault("headline", str(extras.get("headline") or "")[:160])
    result.setdefault("summary", "")
    for field in ITEM_FIELDS:
        result.setdefault(field, [])
    result["coverage"] = coverage(
        result["skills"], result["interests"], result["looking_for"], extras
    )
    sources = {
        entry.get("source_id")
        for field in ITEM_FIELDS
        for item in result[field]
        for entry in _support_of(item)
        if entry.get("source_id")
    }
    result["source_count"] = len(sources)
    result["chunk_count"] = int(result.get("chunks_seen") or result.get("chunk_count") or 0)
    return result


def safe_extras(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Whitelist the self-declared persona fields a client may set."""
    payload = payload or {}
    allowed_text = {"headline", "location", "pronouns", "availability", "website"}
    allowed_lists = {"skills", "interests", "looking_for", "likes", "dislikes", "hobbies"}
    extras: dict[str, Any] = {}
    for key in allowed_text:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            extras[key] = value.strip()[:160]
    for key in allowed_lists:
        value = payload.get(key)
        if isinstance(value, list):
            items = [str(item).strip()[:80] for item in value if str(item).strip()]
            if items:
                extras[key] = items[:25]
    return extras


def validate_extraction(payload: dict[str, Any]) -> PersonaExtraction | None:
    try:
        return PersonaExtraction.model_validate(payload)
    except ValidationError:
        return None
