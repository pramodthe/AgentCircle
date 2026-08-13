"""Deep research: a sourced brief on one member, gathered from the public web.

This is the most dangerous feature in the product, because it is the one that compiles.
Anyone can search a name; an agent that fans out across sources and assembles the results
into a dossier is a different act, and the NFR in spec §10 names it directly — no
compiling of personal data across members outside an explicit user request.

So the shape is deliberately narrow:

- **Opt-in by the subject.** `research_enabled` defaults False. Being findable is the
  deal a member signed up for; being profiled is not, and they get to refuse it.
- **One member at a time, user-triggered.** No batch endpoint exists, on purpose. The
  funnel in the spec (10 discovered -> 5 selected -> 3 researched) is a cost gate and a
  restraint gate at once.
- **Every claim cites a URL that was actually returned.** A claim whose source does not
  resolve is dropped, and a brief with nothing left becomes a decline. Same rule the
  persona and interview layers already run on.
- **Protected-attribute questions are refused before a search is issued**, the way
  `media.appearance_query_reason` refuses phenotype queries.
- **Contact details are stripped**, never surfaced. Spec §9: agents never share them.
- **Cost is recorded per brief** from Exa's own accounting, so the funnel is auditable
  rather than aspirational.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.database import Database

from app.llm import ChatModelBundle
from app.serializers import serialize

logger = logging.getLogger(__name__)

EXA_SEARCH_URL = "https://api.exa.ai/search"
# "auto" lets Exa pick neural or keyword. Cheap and adequate for a handful of queries
# about one person; the deep-* modes cost materially more per call.
EXA_SEARCH_TYPE = "auto"
EXA_CATEGORY = None

# Cost gates. A brief is a bounded number of searches over a bounded number of results,
# so the ceiling per brief is knowable before anyone runs one.
MAX_QUERIES = 4
RESULTS_PER_QUERY = 5
MAX_HIGHLIGHT_CHARACTERS = 900
STALE_AFTER_SECONDS = 420

# Attributes nobody may research through this product. Same reasoning as the photo
# guard: the capability is identical either way, so the framing has to be enforced.
PROTECTED_TERMS = {
    "race", "racial", "ethnicity", "ethnic", "religion", "religious", "church",
    "mosque", "synagogue", "sexuality", "sexual", "gay", "lesbian", "orientation",
    "disability", "disabled", "illness", "diagnosis", "medical", "health",
    "pregnant", "pregnancy", "immigration", "visa", "citizenship", "criminal",
    "arrest", "conviction", "lawsuit", "divorce", "salary", "compensation",
    "political", "politics", "voted", "party",
}

# Contact details are stripped from anything that reaches a brief.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d\-.\s()]{7,}\d)(?!\d)")
_WORD = re.compile(r"[a-z][a-z-]*")


def utcnow() -> datetime:
    return datetime.now(UTC)


def protected_goal_reason(goal: str) -> str | None:
    """Refuse a research goal that targets a protected attribute.

    Returns a reason rather than results, so the refusal is an answer the asker can read
    rather than an empty brief they will read as "nothing found".
    """
    hits = sorted(PROTECTED_TERMS.intersection(_WORD.findall(goal.lower())))
    if hits:
        return (
            f"“{hits[0]}” is a protected or private attribute. Research here covers "
            "public professional work — what someone has built, written, or shipped."
        )
    return None


def strip_contact_details(text: str) -> str:
    """Remove emails and phone numbers. Agents never surface contact details (§9)."""
    text = _EMAIL.sub("[email removed]", text)
    return _PHONE.sub("[number removed]", text)


# Words too common to identify anyone. An anchor has to be distinguishing.
ANCHOR_STOPWORDS = {
    "the", "and", "for", "with", "engineer", "engineering", "developer", "founder",
    "manager", "director", "lead", "senior", "staff", "head", "chief", "officer",
    "designer", "researcher", "consultant", "analyst", "specialist", "systems",
    "software", "technology", "technologies", "company", "inc", "llc", "ltd",
    "work", "working", "works", "team", "product", "products", "at", "of", "in",
}
MIN_ANCHOR_LENGTH = 4


def identity_anchors(*, profile: dict[str, Any], name: str = "", handle: str = "") -> set[str]:
    """Distinguishing terms that tie a source to *this* person rather than a namesake.

    Drawn only from what the member declared — employer, location, website domain, and
    the distinctive words of their headline and role.

    **Nothing derived from the name may be an anchor.** The name is what caused the
    collision, so a page containing it proves nothing. That includes the handle: handles
    are usually auto-generated from the display name, and `kenji_tanaka` appearing in a
    URL confirmed a namesake's paper in testing — the guard confirming exactly what it
    existed to reject.
    """
    name_parts = {w for w in _WORD.findall(name.lower()) if w}

    def usable(word: str) -> bool:
        if len(word) < MIN_ANCHOR_LENGTH or word in ANCHOR_STOPWORDS:
            return False
        # Reject the name itself and any token containing it ("kenji_tanaka" -> kenji).
        return not any(part in word or word in part for part in name_parts)

    # Organization, location and website only — never role or headline. Those describe
    # what someone does, not who they are, and a namesake in the same field shares them.
    # Observed: with "infrastructure" and "energy" admitted as anchors, five of a rival
    # Kenji Tanaka's papers were "confirmed" because he also works on energy
    # infrastructure. Topic overlap is the most likely kind of collision, not the least.
    anchors: set[str] = set()
    for key in ("organization", "location"):
        anchors.update(w for w in _WORD.findall(str(profile.get(key) or "").lower()) if usable(w))
    website = str(profile.get("website") or "").lower()
    domain = re.sub(r"^https?://(www\.)?", "", website).split("/")[0]
    if usable(domain):
        anchors.add(domain)
    if usable(handle.lower()):
        anchors.add(handle.lower())
    return anchors


def corroborate(sources: list[dict], anchors: set[str]) -> tuple[list[dict], list[dict]]:
    """Split sources into those that mention something identifying, and those that don't.

    This exists because citation-checking is not identity-checking, and conflating the
    two is how you get a confident dossier about a stranger. Measured on this codebase:
    a search for a member named "Kenji Tanaka" returned eighteen genuine, correctly
    cited sources about a *different* Kenji Tanaka — a real researcher at another
    company — and every claim passed the URL check because every URL was real.

    A source that corroborates nothing the member declared is not weaker evidence about
    them; it is evidence about somebody else. It never becomes a finding.
    """
    if not anchors:
        # Nothing declared to match against, so nothing can be confirmed. Refusing to
        # guess is the whole point.
        return [], sources
    confirmed, unconfirmed = [], []
    for source in sources:
        haystack = f"{source.get('title', '')} {source.get('snippet', '')} {source['url']}".lower()
        hits = sorted(a for a in anchors if a in haystack)
        if hits:
            confirmed.append({**source, "matched_on": hits[:4]})
        else:
            unconfirmed.append(source)
    return confirmed, unconfirmed


def build_queries(*, name: str, headline: str, organization: str, goal: str) -> list[str]:
    """A small fixed fan-out, anchored on the name so results are about this person.

    Bounded and deterministic rather than model-chosen: a model that writes its own
    queries is a model that can be talked into researching something else.
    """
    name = name.strip()
    queries = [f'"{name}" {goal}'.strip()]
    if organization.strip():
        queries.append(f'"{name}" {organization.strip()}')
    if headline.strip():
        queries.append(f'"{name}" {headline.strip()[:80]}')
    queries.append(f'"{name}" projects OR writing OR talks')
    return queries[:MAX_QUERIES]


@dataclass
class ExaClient:
    """Exa search, or an honest `unavailable` when there is no key."""

    api_key: str | None
    timeout: float = 30.0
    endpoint: str = EXA_SEARCH_URL

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def describe(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "provider": "exa" if self.available else None,
            "search_type": EXA_SEARCH_TYPE,
        }

    def search(self, query: str, *, num_results: int = RESULTS_PER_QUERY) -> dict[str, Any]:
        """One search. Returns `{results, cost}`; raises nothing the caller must handle."""
        if not self.available:
            return {"results": [], "cost": 0.0}
        payload = {
            "query": query,
            "type": EXA_SEARCH_TYPE,
            "numResults": num_results,
            "contents": {
                "highlights": {"query": query, "maxCharacters": MAX_HIGHLIGHT_CHARACTERS},
                "summary": {"query": f"What does this say about the person? {query}"},
            },
        }
        try:
            response = httpx.post(
                self.endpoint,
                json=payload,
                headers={"x-api-key": self.api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            # One failed query does not sink a brief: the others may still ground it,
            # and a partial brief that says what it found beats no answer.
            logger.warning("exa search failed for %r: %s", query[:60], exc)
            return {"results": [], "cost": 0.0}

        cost = float((body.get("costDollars") or {}).get("total") or 0.0)
        results = []
        for row in body.get("results", []):
            url = (row.get("url") or "").strip()
            if not url:
                continue
            snippet = " ".join(row.get("highlights") or []) or (row.get("summary") or "")
            results.append(
                {
                    "url": url,
                    "title": (row.get("title") or url)[:200],
                    "author": (row.get("author") or "")[:120],
                    "published": row.get("publishedDate"),
                    "snippet": strip_contact_details(snippet)[:MAX_HIGHLIGHT_CHARACTERS],
                }
            )
        return {"results": results, "cost": cost}


# ----------------------------------------------------------------- the brief itself


class Finding(BaseModel):
    claim: str = Field(description="One specific, checkable statement about this person")
    source_url: str = Field(description="The URL this claim came from, copied exactly")


class Brief(BaseModel):
    summary: str = Field(default="", description="Two or three sentences, or empty")
    findings: list[Finding] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


@dataclass
class ResearchAgent:
    """Turns search results into a brief where every claim carries a live source."""

    chat: ChatModelBundle
    _unused: tuple = field(default=(), repr=False)

    def run(
        self,
        *,
        name: str,
        goal: str,
        sources: list[dict],
        unconfirmed: list[dict] | None = None,
    ) -> dict[str, Any]:
        unconfirmed = unconfirmed or []
        if not sources:
            if unconfirmed:
                # The honest answer to "we found pages with this name on them but cannot
                # show any of them are this person".
                return self._declined(
                    f"Found {len(unconfirmed)} pages mentioning that name, but none "
                    "mention anything on their profile — so none can be confirmed to be "
                    "them. Common names collide; guessing would attribute a stranger's "
                    "work to a member.",
                    "unconfirmed_identity",
                    unconfirmed=unconfirmed,
                )
            return self._declined("Nothing public turned up for that.", "no_results")
        if not self.chat.configured:
            # No model: report the sources found and refuse to characterise them. A
            # templated summary of someone's public life is exactly the fabrication this
            # product refuses everywhere else.
            return self._declined(
                "Found sources but no model is configured to read them.", "no_model", sources
            )

        allowed = {source["url"] for source in sources}
        catalogue = "\n\n".join(
            f"[{i + 1}] {s['title']}\nURL: {s['url']}\n{s['snippet']}"
            for i, s in enumerate(sources)
        )
        prompt = (
            f"Research goal: {goal}\nPerson: {name}\n\n"
            f"Sources:\n{catalogue}\n\n"
            "Write a short brief about this person's public professional work. Every "
            "finding must state one specific fact and copy the exact URL it came from. "
            "Every source below already mentions something from this person's own "
            "profile, which is why it is here. Use only these sources. "
            "Never include contact details. Never state anything about protected or "
            "private attributes. If the sources do not support a claim, leave it out."
        )
        try:
            drafted = self.chat.model.with_structured_output(Brief).invoke(prompt)
        except Exception as exc:  # noqa: BLE001 - any model failure degrades the same way
            logger.warning("research synthesis failed: %s", exc)
            return self._declined("The model could not read those sources.", "model_error", sources)

        # The grounding rule, applied after the fact because a model will cheerfully
        # cite a URL it invented. A finding whose source was not actually returned is
        # not a weaker finding, it is a fabricated one.
        findings = [
            {"claim": strip_contact_details(f.claim.strip())[:400], "source_url": f.source_url}
            for f in drafted.findings
            if f.claim.strip() and f.source_url in allowed
        ]
        dropped = len(drafted.findings) - len(findings)
        if not findings:
            return self._declined(
                "Nothing in those sources grounded a claim about this person.",
                "ungrounded",
                sources,
            )
        return {
            "declined": False,
            "summary": strip_contact_details(drafted.summary.strip())[:800],
            "findings": findings,
            "open_questions": [q.strip()[:200] for q in drafted.open_questions if q.strip()][:5],
            "sources": sources,
            "unconfirmed_sources": unconfirmed,
            "dropped_claims": dropped,
            "runtime_mode": "live",
            "model": self.chat.model_name,
        }

    @staticmethod
    def _declined(
        reason: str,
        kind: str,
        sources: list[dict] | None = None,
        unconfirmed: list[dict] | None = None,
    ) -> dict[str, Any]:
        # `sources` means "confirmed to be about this member" everywhere, including here.
        # Putting unconfirmed pages in it during a decline would make one field mean two
        # things depending on status, which is how a caller ends up presenting a
        # stranger's pages as this member's.
        return {
            "declined": True,
            "decline_reason": reason,
            "decline_kind": kind,
            "summary": "",
            "findings": [],
            "open_questions": [],
            "sources": sources or [],
            "unconfirmed_sources": unconfirmed or [],
            "dropped_claims": 0,
            "runtime_mode": "deterministic_fallback" if kind == "no_model" else kind,
            "model": None,
        }


# ---------------------------------------------------------------------- the store


class ResearchStore:
    """Briefs, readable only by the person who asked for them."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def ensure_indexes(self) -> None:
        self.db.research_briefs.create_index(
            [("asker_id", ASCENDING), ("created_at", DESCENDING)]
        )
        self.db.research_briefs.create_index([("subject_id", ASCENDING)])

    def create_pending(self, *, asker_id: str, subject_id: str, goal: str) -> dict:
        now = utcnow()
        document = {
            "_id": f"res_{uuid4().hex[:16]}",
            "asker_id": asker_id,
            "subject_id": subject_id,
            "goal": goal,
            "status": "pending",
            "summary": "",
            "findings": [],
            "open_questions": [],
            "sources": [],
            "declined": False,
            "cost_usd": 0.0,
            "queries": [],
            "created_at": now,
            "updated_at": now,
        }
        self.db.research_briefs.insert_one(document)
        return serialize(document)

    def complete(self, brief_id: str, *, result: dict[str, Any], cost: float,
                 queries: list[str]) -> dict | None:
        return serialize(
            self.db.research_briefs.find_one_and_update(
                {"_id": brief_id},
                {
                    "$set": {
                        "status": "complete",
                        "summary": result.get("summary", ""),
                        "findings": result.get("findings", []),
                        "open_questions": result.get("open_questions", []),
                        "sources": result.get("sources", []),
                        "unconfirmed_sources": result.get("unconfirmed_sources", []),
                        "declined": result.get("declined", False),
                        "decline_reason": result.get("decline_reason", ""),
                        "decline_kind": result.get("decline_kind", ""),
                        "dropped_claims": result.get("dropped_claims", 0),
                        "runtime_mode": result.get("runtime_mode"),
                        "model": result.get("model"),
                        "cost_usd": round(cost, 6),
                        "queries": queries,
                        "updated_at": utcnow(),
                    }
                },
                return_document=ReturnDocument.AFTER,
            )
        )

    def fail(self, brief_id: str, reason: str) -> None:
        self.db.research_briefs.update_one(
            {"_id": brief_id},
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
        # BSON returns naive datetimes; utcnow() is aware. Comparing them raises.
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if (utcnow() - created).total_seconds() > STALE_AFTER_SECONDS:
            row["status"] = "failed"
            row["error"] = "The research did not finish — the server restarted mid-run."
        return row

    def get(self, brief_id: str, asker_id: str) -> dict | None:
        """Filtered on asker_id: a brief is private to whoever requested it."""
        return self._resolve_stale(
            serialize(self.db.research_briefs.find_one({"_id": brief_id, "asker_id": asker_id}))
        )

    def list_for_asker(self, asker_id: str, limit: int = 20) -> list[dict]:
        rows = (
            self.db.research_briefs.find({"asker_id": asker_id}, {"sources": 0})
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        return [self._resolve_stale(row) for row in serialize(list(rows))]

    def spend_since(self, asker_id: str, since: datetime) -> float:
        """What this member has spent on research recently, for the cost gate."""
        rows = self.db.research_briefs.find(
            {"asker_id": asker_id, "created_at": {"$gte": since}}, {"cost_usd": 1}
        )
        return round(sum(float(row.get("cost_usd") or 0.0) for row in rows), 6)
