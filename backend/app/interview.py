"""One member's agent interviewing another's, on the record.

The failure mode this is built against: two models talking to each other produce
fluent, agreeable, unfalsifiable text. Nobody can tell whether "yes, they have deep
Kubernetes experience" came from the person's resume or from the model's sense of what
a backend engineer probably knows. A transcript of that is worse than nothing, because
it looks like evidence.

So this is not a conversation. It is a structured exchange that produces a table:

    question | answer | source | confidence

Every answer either resolves to a chunk of the subject's own documents or is marked
unanswered. There is no third state. Three distinct reasons an answer can be missing,
kept separate because they mean different things to the asker:

    not_in_profile  the documents do not cover it — recorded as a context gap so the
                    subject learns what people keep asking that they can't answer
    permission      the subject's consent settings do not allow this topic — a
                    deliberate boundary, not a shortcoming
    no_model        nothing is configured; the agent refuses to speak rather than
                    improvise on a real person's behalf

Contact details are never disclosed regardless of settings.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.database import Database

from app.llm import ChatModelBundle
from app.serializers import serialize

MAX_QUESTIONS = 8
MAX_CHUNKS_PER_QUESTION = 3

# Consent for being interviewed, separate from consent to comment publicly: answering
# one person's specific question is a different exposure from speaking to everyone.
DEFAULT_INTERVIEW_SETTINGS = {
    "interview_enabled": False,
    "interview_topics": [],
    "disclose_personal": False,
}

QUESTION_PRESETS: dict[str, list[str]] = {
    "collaboration": [
        "What are you working on right now?",
        "What kind of problem do you most want to be brought into?",
        "How do you prefer to work with people early on?",
    ],
    "hiring": [
        "What have you actually built end to end?",
        "What technical depth do you have in production systems?",
        "What kind of team and role are you looking for?",
    ],
    "feedback": [
        "What have you shipped that's closest to this problem?",
        "What would you want to know before giving feedback?",
        "Where has your advice been most useful before?",
    ],
    "founders": [
        "What are you building and why you?",
        "What stage are you at, concretely?",
        "What do you need help with that you can't solve yourself?",
    ],
}

# Topics a question can touch, matched against the subject's consent settings.
PERSONAL_MARKERS = (
    "hobby", "hobbies", "personal", "family", "married", "partner", "relationship",
    "age", "religion", "politics", "health", "salary", "compensation", "pay",
)
CONTACT_MARKERS = ("email", "phone", "number", "contact", "address", "linkedin", "handle")

ANSWER_SYSTEM_PROMPT = (
    "You answer questions on behalf of one specific person, using ONLY the excerpts "
    "from their own documents that you are given.\n\n"
    "Rules:\n"
    "- Answer only what the excerpts support. Cite the excerpt number(s) behind each "
    "answer.\n"
    "- If the excerpts do not answer a question, set answered=false and leave the "
    "answer empty. Do NOT guess, generalize from their job title, or say what someone "
    "like them would probably say. An unanswered question is a correct outcome.\n"
    "- Never invent employers, titles, dates, numbers, or opinions.\n"
    "- Write in third person, plainly, 1-3 sentences. No sales language.\n"
    "- confidence reflects how directly the excerpts answer the question, not how "
    "good the person sounds."
)

VERDICT_SYSTEM_PROMPT = (
    "You summarize an interview for the person who asked for it, using ONLY the "
    "answers in the table you are given.\n\n"
    "Rules:\n"
    "- Base the recommendation on what was actually answered. Unanswered questions are "
    "missing information, not implied negatives.\n"
    "- 'connect' means there is concrete evidence this is worth the asker's time. "
    "'maybe' means partial evidence. 'pass' means the evidence points away from it.\n"
    "- Recommend contact only. You are not deciding whether to hire, date, invest in, "
    "or trust this person, and you must not phrase it that way.\n"
    "- Reference specifics from the answers. Never introduce facts that are not there."
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class InterviewAnswer(BaseModel):
    question_index: int = Field(ge=0)
    answered: bool
    answer: str = Field(default="", max_length=700)
    chunk_indexes: list[int] = Field(default_factory=list, max_length=4)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class InterviewResponse(BaseModel):
    answers: list[InterviewAnswer] = Field(default_factory=list, max_length=MAX_QUESTIONS)
    offer: str = Field(default="", max_length=280)


class Verdict(BaseModel):
    recommendation: Literal["connect", "maybe", "pass"]
    rationale: str = Field(min_length=20, max_length=700)
    met: list[str] = Field(default_factory=list, max_length=6)
    missing: list[str] = Field(default_factory=list, max_length=6)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


def classify_question(question: str) -> str:
    """What consent a question needs. Cheap, and runs before any model call."""
    lowered = question.lower()
    if any(marker in lowered for marker in CONTACT_MARKERS):
        return "contact"
    if any(marker in lowered for marker in PERSONAL_MARKERS):
        return "personal"
    return "professional"


def safe_interview_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    topics = payload.get("interview_topics")
    return {
        "interview_enabled": bool(payload.get("interview_enabled", False)),
        "interview_topics": (
            [topic for topic in topics if topic in QUESTION_PRESETS]
            if isinstance(topics, list)
            else []
        ),
        "disclose_personal": bool(payload.get("disclose_personal", False)),
    }


class InterviewAgent:
    def __init__(self, chat: ChatModelBundle) -> None:
        self.chat = chat

    def run(
        self,
        *,
        questions: list[str],
        subject_name: str,
        chunks_per_question: list[list[dict[str, Any]]],
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        """Answer each question, or record precisely why it could not be answered."""
        rows: list[dict[str, Any]] = [
            {
                "question": question,
                "kind": classify_question(question),
                "answered": False,
                "answer": "",
                "citations": [],
                "confidence": 0.0,
                "decline_kind": None,
                "decline_reason": None,
            }
            for question in questions
        ]

        # Consent is resolved before the model sees anything, so a boundary is never
        # something the model can be talked out of.
        askable: list[int] = []
        for index, row in enumerate(rows):
            if row["kind"] == "contact":
                row["decline_kind"] = "permission"
                row["decline_reason"] = (
                    "Contact details are never shared through an agent."
                )
            elif row["kind"] == "personal" and not settings.get("disclose_personal"):
                row["decline_kind"] = "permission"
                row["decline_reason"] = (
                    f"{subject_name} has not enabled personal questions."
                )
            else:
                askable.append(index)

        if not askable:
            return {"rows": rows, "offer": "", "runtime_mode": "permission_blocked"}

        if self.chat.model is None:
            for index in askable:
                rows[index]["decline_kind"] = "no_model"
                rows[index]["decline_reason"] = (
                    "No language model is configured, so this agent will not answer "
                    "on its user's behalf."
                )
            return {"rows": rows, "offer": "", "runtime_mode": "deterministic_fallback"}

        # Excerpts are numbered globally so a citation maps to exactly one chunk.
        catalogue: list[dict[str, Any]] = []
        blocks: list[str] = []
        for index in askable:
            available = chunks_per_question[index][:MAX_CHUNKS_PER_QUESTION]
            numbers = []
            for chunk in available:
                catalogue.append(chunk)
                numbers.append(len(catalogue) - 1)
            excerpt = "\n".join(
                f"  [{number}] (from {catalogue[number].get('source_title','source')}) "
                f"{catalogue[number]['text'][:400]}"
                for number in numbers
            ) or "  (no excerpts available)"
            blocks.append(f"Q{index}: {rows[index]['question']}\n{excerpt}")

        try:
            structured = self.chat.model.with_structured_output(InterviewResponse)
            result = structured.invoke(
                [
                    {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"You represent {subject_name}. Answer each question using "
                            f"only its excerpts.\n\n" + "\n\n".join(blocks) + "\n\n"
                            "Return one entry per question, using the Q number as "
                            "question_index. Also give a short 'offer': what this person "
                            "could help the asker with, grounded in the excerpts."
                        ),
                    },
                ]
            )
            if not isinstance(result, InterviewResponse):
                result = InterviewResponse.model_validate(result)
        except Exception as exc:
            for index in askable:
                rows[index]["decline_kind"] = "error"
                rows[index]["decline_reason"] = f"The agent failed: {type(exc).__name__}"
            return {"rows": rows, "offer": "", "runtime_mode": "fallback_after_error"}

        answered_indexes = set()
        for answer in result.answers:
            if answer.question_index not in askable:
                continue
            row = rows[answer.question_index]
            citations = []
            for number in answer.chunk_indexes:
                # A citation that does not resolve is dropped; an answer left with
                # none is demoted to unanswered rather than published uncited.
                if 0 <= number < len(catalogue):
                    chunk = catalogue[number]
                    citations.append(
                        {
                            "chunk_id": chunk["_id"],
                            "source_id": chunk.get("source_id"),
                            "source_title": chunk.get("source_title"),
                            "excerpt": chunk["text"][:220],
                        }
                    )
            if not answer.answered or not answer.answer.strip() or not citations:
                row["decline_kind"] = "not_in_profile"
                row["decline_reason"] = (
                    f"Not in {subject_name}'s profile — their agent will ask them to add it."
                )
                continue
            row.update(
                {
                    "answered": True,
                    "answer": answer.answer.strip(),
                    "citations": citations,
                    "confidence": round(answer.confidence, 3),
                }
            )
            answered_indexes.add(answer.question_index)

        # A question the model simply omitted is unanswered, not silently dropped.
        for index in askable:
            if index not in answered_indexes and rows[index]["decline_kind"] is None:
                rows[index]["decline_kind"] = "not_in_profile"
                rows[index]["decline_reason"] = (
                    f"Not in {subject_name}'s profile — their agent will ask them to add it."
                )

        return {"rows": rows, "offer": result.offer.strip(), "runtime_mode": "live"}

    def verdict(
        self, *, goal: str, subject_name: str, rows: list[dict[str, Any]], offer: str
    ) -> dict[str, Any]:
        """Summarize the table. Never introduces facts the table does not contain."""
        answered = [row for row in rows if row["answered"]]
        coverage = self.coverage(rows)

        if self.chat.model is None or not answered:
            return self._deterministic_verdict(rows, coverage)

        table = "\n".join(
            f"Q: {row['question']}\n"
            + (
                f"A: {row['answer']} [source: "
                f"{', '.join(c['source_title'] or 'document' for c in row['citations'])}]"
                if row["answered"]
                else f"A: UNANSWERED ({row['decline_reason']})"
            )
            for row in rows
        )
        try:
            structured = self.chat.model.with_structured_output(Verdict)
            result = structured.invoke(
                [
                    {"role": "system", "content": VERDICT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"The asker's goal: {goal}\n"
                            f"Interview with {subject_name}:\n\n{table}\n\n"
                            + (f"What they offered: {offer}\n\n" if offer else "")
                            + "Recommend whether the asker should reach out."
                        ),
                    },
                ]
            )
            if not isinstance(result, Verdict):
                result = Verdict.model_validate(result)
        except Exception:
            return self._deterministic_verdict(rows, coverage)

        return self._guard(result.model_dump(), coverage)

    @staticmethod
    def coverage(rows: list[dict[str, Any]]) -> float:
        """Answered share of the questions the subject could legitimately answer.

        Permission declines are excluded from the denominator. They are a boundary the
        subject set, not a hole in their profile, and counting them would let an asker
        depress anyone's verdict just by including "what's your email" — punishing the
        subject for the asker's question list. A `not_in_profile` decline *does* count,
        because that genuinely is missing context.
        """
        answerable = [row for row in rows if row["decline_kind"] != "permission"]
        if not answerable:
            return 0.0
        return sum(1 for row in answerable if row["answered"]) / len(answerable)

    @staticmethod
    def _guard(verdict: dict[str, Any], coverage: float) -> dict[str, Any]:
        """Stop a confident recommendation resting on a mostly-empty table.

        The model sees the unanswered rows, but it optimizes for a helpful-sounding
        answer; coverage is the objective floor.
        """
        if coverage < 0.5 and verdict["recommendation"] == "connect":
            verdict["recommendation"] = "maybe"
            verdict["rationale"] = (
                "Downgraded: fewer than half the questions could be answered from "
                "their profile. " + verdict["rationale"]
            )
        verdict["confidence"] = round(min(verdict.get("confidence", 0.5), coverage), 3)
        verdict["coverage"] = round(coverage, 3)
        return verdict

    @staticmethod
    def _deterministic_verdict(rows: list[dict], coverage: float) -> dict[str, Any]:
        answered = [row for row in rows if row["answered"]]
        return {
            "recommendation": "maybe" if answered else "pass",
            "rationale": (
                f"{len(answered)} of {len(rows)} questions could be answered from their "
                "profile. No model was available to weigh them, so this is a count, "
                "not a judgement."
            ),
            "met": [row["question"] for row in answered][:6],
            "missing": [row["question"] for row in rows if not row["answered"]][:6],
            "confidence": 0.0,
            "coverage": round(coverage, 3),
        }


# A run that has been pending longer than this had its process die mid-flight. There
# is no worker to resume it, so surface it as failed instead of spinning forever.
STALE_AFTER_SECONDS = 300


class InterviewStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def ensure_indexes(self) -> None:
        self.db.interviews.create_index([("asker_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.interviews.create_index([("subject_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.interviews.create_index([("status", ASCENDING), ("created_at", DESCENDING)])

    def create_pending(
        self, *, asker_id: str, subject_id: str, goal: str, questions: list[str]
    ) -> dict:
        """Reserve the interview so the caller gets an id immediately."""
        now = utcnow()
        document = {
            "_id": f"int_{uuid4().hex[:16]}",
            "asker_id": asker_id,
            "subject_id": subject_id,
            "goal": goal,
            "questions": questions,
            "status": "pending",
            "rows": [],
            "verdict": {},
            "offer": "",
            "runtime_mode": None,
            "model": None,
            "answered_count": 0,
            "question_count": len(questions),
            "blocked_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        self.db.interviews.insert_one(document)
        return serialize(document)

    def complete(
        self,
        interview_id: str,
        *,
        rows: list[dict[str, Any]],
        verdict: dict[str, Any],
        offer: str,
        runtime_mode: str,
        model: str | None,
    ) -> dict | None:
        return serialize(
            self.db.interviews.find_one_and_update(
                {"_id": interview_id},
                {
                    "$set": {
                        "status": "complete",
                        "rows": rows,
                        "verdict": verdict,
                        "offer": offer,
                        "runtime_mode": runtime_mode,
                        "model": model,
                        "answered_count": sum(1 for row in rows if row["answered"]),
                        "blocked_count": sum(
                            1 for row in rows if row["decline_kind"] == "permission"
                        ),
                        "updated_at": utcnow(),
                    }
                },
                return_document=ReturnDocument.AFTER,
            )
        )

    def fail(self, interview_id: str, reason: str) -> None:
        self.db.interviews.update_one(
            {"_id": interview_id},
            {"$set": {"status": "failed", "error": reason[:300], "updated_at": utcnow()}},
        )

    @staticmethod
    def _resolve_stale(row: dict | None) -> dict | None:
        """Report a run whose process died as failed rather than eternally pending."""
        if row is None or row.get("status") != "pending":
            return row
        created = row.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        if not isinstance(created, datetime):
            return row
        # BSON round-trips datetimes without a timezone, so a value read back from
        # Mongo is naive while utcnow() is aware. Comparing them raises.
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if (utcnow() - created).total_seconds() > STALE_AFTER_SECONDS:
            row["status"] = "failed"
            row["error"] = "The interview did not finish — the server restarted mid-run."
        return row

    def save(
        self,
        *,
        asker_id: str,
        subject_id: str,
        goal: str,
        rows: list[dict[str, Any]],
        verdict: dict[str, Any],
        offer: str,
        runtime_mode: str,
        model: str | None,
    ) -> dict:
        now = utcnow()
        document = {
            "_id": f"int_{uuid4().hex[:16]}",
            "asker_id": asker_id,
            "subject_id": subject_id,
            "goal": goal,
            "rows": rows,
            "verdict": verdict,
            "offer": offer,
            "runtime_mode": runtime_mode,
            "model": model,
            "answered_count": sum(1 for row in rows if row["answered"]),
            "question_count": len(rows),
            # Separated so the UI can say "2 of 3 answerable" rather than "2 of 5",
            # which would read as a failing grade for questions that were out of bounds.
            "blocked_count": sum(1 for row in rows if row["decline_kind"] == "permission"),
            "created_at": now,
            "updated_at": now,
        }
        self.db.interviews.insert_one(document)
        return serialize(document)

    def get(self, interview_id: str, asker_id: str) -> dict | None:
        """Scoped to the asker: an interview is private to whoever requested it."""
        return self._resolve_stale(
            serialize(self.db.interviews.find_one({"_id": interview_id, "asker_id": asker_id}))
        )

    def list_for_asker(self, asker_id: str, *, limit: int = 30) -> list[dict]:
        rows = list(
            self.db.interviews.find({"asker_id": asker_id})
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        return [self._resolve_stale(row) for row in serialize(rows)]
