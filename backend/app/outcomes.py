"""What actually happened, and what the network does differently because of it.

Everything upstream of this file is the forward path: discover, recruit, comment,
recommend. None of it records whether the agent was *right*. This is where that
closes, and it is the difference between a good matchmaker and a network that learns.

Three mechanisms:

  Direct trust.  Your own outcomes with someone move your agent's opinion of them,
  with an exponential update so one bad meeting does not erase a good history.

  Propagated trust.  Other members' outcomes with the same person move your agent's
  opinion too — weighted by how reliable *those reporters* are, and bounded so a
  stranger can never move you as far as your own experience. This is the part a pure
  search product cannot do: one member's bad experience protects everyone else.

  Calibration.  Your agent predicted a match score; you recorded what happened. The
  gap between those two, accumulated, is persistent context about your own agent
  rather than about other people. An agent that runs optimistic gets damped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.database import Database

from app.serializers import serialize

NEUTRAL_TRUST = 0.5

# What a member can report, the score it implies, and how hard it moves trust.
# "passed" is deliberately weak: not pursuing someone says something about relevance,
# not about the person, so it should not damage them the way a wasted meeting does.
OUTCOME_LABELS: dict[str, dict[str, float]] = {
    "great": {"score": 0.95, "weight": 0.30},
    "useful": {"score": 0.75, "weight": 0.25},
    "neutral": {"score": 0.50, "weight": 0.15},
    "waste": {"score": 0.15, "weight": 0.30},
    "passed": {"score": 0.35, "weight": 0.08},
}

# How far the network's opinion can pull you from neutral when you have no direct
# experience. Tuned against a hard invariant, asserted in the tests: *no amount* of
# propagated signal may move you further than a single first-hand outcome would.
# Without that bound, a coordinated group outweighs your own experience, which is
# both wrong and cheap to attack.
PROPAGATION_CEILING = 0.28
# Reliability-weight at which propagation reaches full strength. Requiring roughly
# three established reporters means propagation reflects consensus, not one loud voice.
CONSENSUS_AT = 3.0
# How far the network can shift you when you *do* have direct experience.
PROPAGATION_WITH_DIRECT = 0.20
# Reporters need a track record before their signal counts fully.
FULL_RELIABILITY_AT = 5


def utcnow() -> datetime:
    return datetime.now(UTC)


def trust_id(reporter_id: str, subject_id: str) -> str:
    """Directional: A's view of B is a different document from B's view of A."""
    return f"{reporter_id}:{subject_id}"


class OutcomeStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def ensure_indexes(self) -> None:
        # One outcome per reporter per thing. Changing your mind updates the record
        # rather than stacking a second vote on the same interaction.
        self.db.outcomes.create_index(
            [("reporter_id", ASCENDING), ("context_id", ASCENDING), ("subject_id", ASCENDING)],
            unique=True,
        )
        self.db.outcomes.create_index([("subject_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.outcomes.create_index([("reporter_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.member_trust.create_index([("reporter_id", ASCENDING), ("updated_at", DESCENDING)])
        self.db.member_trust.create_index("subject_id")
        self.db.agent_calibration.create_index([("updated_at", DESCENDING)])

    # ----------------------------------------------------------------- recording

    def record(
        self,
        *,
        reporter_id: str,
        subject_id: str,
        label: str,
        context: str,
        context_id: str,
        predicted_score: float | None = None,
        note: str | None = None,
    ) -> dict:
        if label not in OUTCOME_LABELS:
            raise ValueError(f"Unknown outcome label: {label}")
        if reporter_id == subject_id:
            raise PermissionError("You cannot record an outcome about yourself")

        spec = OUTCOME_LABELS[label]
        now = utcnow()
        outcome_id = f"out_{uuid4().hex[:16]}"
        key = {
            "reporter_id": reporter_id,
            "context_id": context_id,
            "subject_id": subject_id,
        }
        self.db.outcomes.update_one(
            key,
            {
                "$set": {
                    "label": label,
                    "score": spec["score"],
                    "weight": spec["weight"],
                    "context": context,
                    "predicted_score": predicted_score,
                    "note": (note or "")[:400],
                    "updated_at": now,
                },
                "$setOnInsert": {"_id": outcome_id, "created_at": now},
            },
            upsert=True,
        )
        stored = self.db.outcomes.find_one(key)

        self._apply_trust(
            reporter_id=reporter_id, subject_id=subject_id, score=spec["score"],
            weight=spec["weight"], now=now,
        )
        if predicted_score is not None:
            self._apply_calibration(
                reporter_id=reporter_id,
                predicted=predicted_score,
                actual=spec["score"],
                now=now,
            )
        return serialize(stored)

    def _apply_trust(
        self, *, reporter_id: str, subject_id: str, score: float, weight: float, now: datetime
    ) -> None:
        """Exponential update, so history matters and one datapoint cannot swing it."""
        row = self.db.member_trust.find_one({"_id": trust_id(reporter_id, subject_id)})
        current = float(row["trust"]) if row else NEUTRAL_TRUST
        updated = current * (1 - weight) + score * weight
        self.db.member_trust.update_one(
            {"_id": trust_id(reporter_id, subject_id)},
            {
                "$set": {
                    "reporter_id": reporter_id,
                    "subject_id": subject_id,
                    "trust": round(max(0.0, min(1.0, updated)), 4),
                    "last_score": score,
                    "updated_at": now,
                },
                "$inc": {"interactions": 1},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    def _apply_calibration(
        self, *, reporter_id: str, predicted: float, actual: float, now: datetime
    ) -> None:
        """Track how far this member's agent's predictions land from reality.

        `bias` is signed: positive means the agent runs optimistic — it predicted a
        better match than the member actually got.
        """
        row = self.db.agent_calibration.find_one({"_id": reporter_id}) or {
            "samples": 0,
            "total_error": 0.0,
            "total_abs_error": 0.0,
        }
        samples = int(row.get("samples", 0)) + 1
        total_error = float(row.get("total_error", 0.0)) + (predicted - actual)
        total_abs = float(row.get("total_abs_error", 0.0)) + abs(predicted - actual)
        self.db.agent_calibration.update_one(
            {"_id": reporter_id},
            {
                "$set": {
                    "samples": samples,
                    "total_error": round(total_error, 6),
                    "total_abs_error": round(total_abs, 6),
                    "bias": round(total_error / samples, 4),
                    "mean_error": round(total_abs / samples, 4),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    # -------------------------------------------------------------------- reading

    def list_for_reporter(self, reporter_id: str, *, limit: int = 50) -> list[dict]:
        return serialize(
            list(
                self.db.outcomes.find({"reporter_id": reporter_id})
                .sort("updated_at", DESCENDING)
                .limit(limit)
            )
        )

    def outcomes_for_context(self, reporter_id: str, context_id: str) -> dict[str, dict]:
        rows = self.db.outcomes.find({"reporter_id": reporter_id, "context_id": context_id})
        return {row["subject_id"]: serialize(row) for row in rows}

    def calibration(self, reporter_id: str) -> dict:
        row = self.db.agent_calibration.find_one({"_id": reporter_id})
        if not row:
            return {"samples": 0, "bias": 0.0, "mean_error": 0.0, "confidence_multiplier": 1.0}
        return {
            "samples": row["samples"],
            "bias": row["bias"],
            "mean_error": row["mean_error"],
            "confidence_multiplier": self.confidence_multiplier(reporter_id),
        }

    def confidence_multiplier(self, reporter_id: str) -> float:
        """Damp an agent that has been over-promising; leave a calibrated one alone.

        Only applies once there is enough history to distinguish bias from noise.
        """
        row = self.db.agent_calibration.find_one({"_id": reporter_id})
        if not row or row.get("samples", 0) < 3:
            return 1.0
        bias = float(row.get("bias", 0.0))
        if bias <= 0:
            return 1.0
        return round(max(0.6, 1.0 - bias), 4)

    def reporter_reliability(self, reporter_id: str) -> float:
        """How much this member's reports should count for other people.

        Grows with track record so a brand-new account cannot cheaply poison the
        network's view of someone, and shrinks if their own agent is badly calibrated.
        """
        reported = self.db.outcomes.count_documents({"reporter_id": reporter_id})
        if reported == 0:
            return 0.0
        history = min(1.0, reported / FULL_RELIABILITY_AT)
        calibration_row = self.db.agent_calibration.find_one({"_id": reporter_id})
        accuracy = 1.0
        if calibration_row and calibration_row.get("samples", 0) >= 3:
            accuracy = max(0.4, 1.0 - float(calibration_row.get("mean_error", 0.0)))
        return round(history * accuracy, 4)

    def direct_trust(self, reporter_id: str, subject_id: str) -> float | None:
        row = self.db.member_trust.find_one({"_id": trust_id(reporter_id, subject_id)})
        return float(row["trust"]) if row else None

    def propagated_trust(self, reporter_id: str, subject_id: str) -> dict[str, Any]:
        """What everyone *else* has learned about this person, reliability-weighted."""
        rows = list(
            self.db.member_trust.find(
                {"subject_id": subject_id, "reporter_id": {"$ne": reporter_id}}
            )
        )
        weighted_sum = 0.0
        weight_total = 0.0
        contributors = 0
        for row in rows:
            reliability = self.reporter_reliability(row["reporter_id"])
            if reliability <= 0:
                continue
            weighted_sum += float(row["trust"]) * reliability
            weight_total += reliability
            contributors += 1
        if weight_total == 0:
            return {"value": None, "contributors": 0, "weight": 0.0}
        return {
            "value": round(weighted_sum / weight_total, 4),
            "contributors": contributors,
            # Saturates on accumulated reliability, not on a single reporter, so one
            # established member never speaks for the whole network.
            "weight": round(min(1.0, weight_total / CONSENSUS_AT), 4),
        }

    def effective_trust(self, reporter_id: str, subject_id: str) -> dict[str, Any]:
        """The number ranking actually uses, with the reasoning kept alongside it.

        Your own experience dominates when you have it. Without it, the network's
        view can only pull you `PROPAGATION_CEILING` of the way from neutral —
        informative, never authoritative.
        """
        direct = self.direct_trust(reporter_id, subject_id)
        propagated = self.propagated_trust(reporter_id, subject_id)
        reasons: list[str] = []

        if direct is not None and propagated["value"] is not None:
            # Your own experience is the base; the network can shift it by at most
            # PROPAGATION_WITH_DIRECT, and only in proportion to its consensus weight.
            blend = PROPAGATION_WITH_DIRECT * propagated["weight"]
            value = direct * (1 - blend) + propagated["value"] * blend
            reasons.append("your own past outcomes")
            reasons.append(f"{propagated['contributors']} other member(s)' outcomes")
        elif direct is not None:
            value = direct
            reasons.append("your own past outcomes")
        elif propagated["value"] is not None:
            pull = PROPAGATION_CEILING * propagated["weight"]
            value = NEUTRAL_TRUST + (propagated["value"] - NEUTRAL_TRUST) * pull
            reasons.append(
                f"{propagated['contributors']} other member(s)' outcomes "
                "(you have none of your own yet)"
            )
        else:
            value = NEUTRAL_TRUST
            reasons.append("no outcomes recorded yet")

        return {
            "value": round(max(0.0, min(1.0, value)), 4),
            "direct": direct,
            "propagated": propagated["value"],
            "contributors": propagated["contributors"],
            "reasons": reasons,
        }

    def trust_map(self, reporter_id: str, subject_ids: list[str]) -> dict[str, float]:
        """Effective trust for many subjects at once, for ranking."""
        return {
            subject_id: self.effective_trust(reporter_id, subject_id)["value"]
            for subject_id in subject_ids
        }

    def set_trust(self, reporter_id: str, subject_id: str, trust: float) -> dict:
        """Test and seeding helper. Not exposed through the API."""
        now = utcnow()
        self.db.member_trust.update_one(
            {"_id": trust_id(reporter_id, subject_id)},
            {
                "$set": {
                    "reporter_id": reporter_id,
                    "subject_id": subject_id,
                    "trust": round(max(0.0, min(1.0, trust)), 4),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now, "interactions": 0},
            },
            upsert=True,
        )
        return serialize(self.db.member_trust.find_one({"_id": trust_id(reporter_id, subject_id)}))

    def find_and_clear(self, reporter_id: str, context_id: str, subject_id: str) -> dict | None:
        return serialize(
            self.db.outcomes.find_one_and_update(
                {
                    "reporter_id": reporter_id,
                    "context_id": context_id,
                    "subject_id": subject_id,
                },
                {"$set": {"cleared_at": utcnow()}},
                return_document=ReturnDocument.AFTER,
            )
        )
