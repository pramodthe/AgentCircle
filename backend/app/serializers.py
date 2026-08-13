from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId


def serialize(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        # Every timestamp leaves here with an explicit offset, even though everything
        # written was UTC-aware. BSON has no timezone, so PyMongo hands back a *naive*
        # datetime on read, and `isoformat()` on that produces "2026-08-13T03:32:33"
        # with no suffix — which ECMAScript parses as the *viewer's* local time. The
        # symptom is silent and looks plausible: a browser at UTC-7 rendered every
        # feed post under seven hours old as "just now", and a 19-hour-old post as
        # "12h". Nothing errors, the number is just wrong by the reader's offset.
        #
        # Stamping it here rather than opening the client with `tz_aware=True` keeps
        # the fix to the boundary: in-process comparisons stay naive-vs-naive, so
        # nothing that currently subtracts two stored datetimes starts raising.
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, tuple):
        return [serialize(item) for item in value]
    return value
