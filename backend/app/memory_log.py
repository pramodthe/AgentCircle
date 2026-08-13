"""What the agent learned, when — and what looks wrong with it.

Two halves of the same idea, and both exist because extraction is not deterministic.

The **log** is append-only. Once the persona compounds rather than being rebuilt, "why
does my agent think this?" stops having an answer you can get by re-running anything —
the current state is the sum of every pass that ever ran. So each pass records what it
did. It is also the only way to tell a model that read a source badly from one that never
saw it.

The **lint** reports problems and never fixes them. Picking a winner between "six years"
and "eight years" would be manufacturing a fact, which is the one thing this product
does not do anywhere else either. It flags, a person decides — the same shape as
`context_gaps`, which records what an agent could not answer instead of inventing an
answer.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from app.persona import ITEM_FIELDS, _norm, _support_of
from app.serializers import serialize

KINDS = (
    "source_added",
    "source_removed",
    "persona_learned",
    "memory_written",
    "edge_recorded",
)

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class MemoryLog:
    def __init__(self, db: Database) -> None:
        self.db = db

    def ensure_indexes(self) -> None:
        self.db.memory_log.create_index(
            [("user_id", ASCENDING), ("seq", DESCENDING)]
        )

    def record(
        self,
        *,
        user_id: str,
        kind: str,
        summary: str,
        detail: dict[str, Any] | None = None,
    ) -> dict:
        if kind not in KINDS:
            raise ValueError(f"unknown log kind: {kind}")
        # Two entries written in the same tick sort arbitrarily by timestamp alone, and
        # an append-only log with an unstable order is not much of a record. Same
        # per-conversation sequence trick MessageStore uses.
        document = {
            "_id": f"log_{uuid4().hex[:20]}",
            "user_id": user_id,
            "seq": self.db.memory_log.count_documents({"user_id": user_id}),
            "kind": kind,
            "summary": summary[:300],
            "detail": detail or {},
            "created_at": utcnow(),
        }
        self.db.memory_log.insert_one(document)
        return serialize(document)

    def timeline(self, user_id: str, *, limit: int = 50) -> list[dict]:
        return serialize(
            list(
                self.db.memory_log.find({"user_id": user_id})
                .sort([("seq", DESCENDING)])
                .limit(max(1, min(limit, 200)))
            )
        )


def _numbers_in(value: str) -> list[float]:
    """Digits and the small number words that actually appear in a CV."""
    text = value.lower()
    found = [float(match) for match in re.findall(r"\d+(?:\.\d+)?", text)]
    found.extend(
        float(NUMBER_WORDS[word])
        for word in re.findall(r"[a-z]+", text)
        if word in NUMBER_WORDS
    )
    return found


def _skeleton(value: str) -> str:
    """The claim with its numbers removed, so two versions of it can be compared."""
    text = _norm(value)
    text = re.sub(r"\d+(?:\.\d+)?", "#", text)
    return " ".join("#" if word in NUMBER_WORDS else word for word in text.split())


def lint_persona(
    persona: dict[str, Any] | None,
    *,
    known_chunk_ids: set[str],
    source_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Everything that looks wrong, stated as a question for a human.

    Deterministic on purpose — no model is consulted, so a lint run costs nothing and
    cannot itself hallucinate a problem.
    """
    if not persona:
        return []
    findings: list[dict[str, Any]] = []

    for field in ITEM_FIELDS:
        items = persona.get(field) or []

        # 1. A claim whose evidence is gone. Should be impossible after prune_persona,
        #    so seeing one means something wrote a persona without going through it.
        for item in items:
            support = _support_of(item)
            live = [row for row in support if row.get("chunk_id") in known_chunk_ids]
            if support and not live:
                findings.append(
                    {
                        "kind": "orphaned_claim",
                        "field": field,
                        "value": item.get("value"),
                        "message": (
                            f"“{item.get('value')}” cites a source that no longer exists. "
                            "Your agent should stop saying it."
                        ),
                    }
                )
            elif not support:
                findings.append(
                    {
                        "kind": "uncited_claim",
                        "field": field,
                        "value": item.get("value"),
                        "message": (
                            f"“{item.get('value')}” has no source behind it at all."
                        ),
                    }
                )

        # 2. Two versions of one claim that differ only in a number.
        by_skeleton: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            value = str(item.get("value") or "")
            if _numbers_in(value):
                by_skeleton.setdefault(_skeleton(value), []).append(item)
        for group in by_skeleton.values():
            if len(group) < 2:
                continue
            variants = {str(row.get("value")) for row in group}
            if len({tuple(_numbers_in(v)) for v in variants}) < 2:
                continue
            findings.append(
                {
                    "kind": "contradiction",
                    "field": field,
                    "values": sorted(variants),
                    "sources": sorted(
                        {
                            row.get("source_title")
                            for item in group
                            for row in _support_of(item)
                            if row.get("source_title")
                        }
                    ),
                    "message": (
                        "Two of your sources disagree: "
                        + " vs ".join(f"“{v}”" for v in sorted(variants))
                        + ". Your agent will cite whichever it retrieves."
                    ),
                }
            )

    # 3. A source that was ingested but produced nothing.
    if source_ids:
        used = {
            row.get("source_id")
            for field in ITEM_FIELDS
            for item in persona.get(field) or []
            for row in _support_of(item)
        }
        for source_id in sorted(source_ids - used):
            findings.append(
                {
                    "kind": "unused_source",
                    "source_id": source_id,
                    "message": (
                        "Your agent has not drawn anything from this source. It may be "
                        "the wrong kind of document, or the extraction may have missed it."
                    ),
                }
            )

    return findings
