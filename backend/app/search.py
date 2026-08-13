"""Hybrid people search: Atlas Vector Search fused with Atlas Search.

Two retrievers, because they fail in opposite directions:

  $vectorSearch over `persona_chunks` finds people whose own writing *means* what the
  query means, even with no shared vocabulary. It is weak on proper nouns — a query
  naming a city, a tool, or a company can drift.

  $search over `profiles` (Lucene) nails exactly those literal terms, with fuzziness
  for typos, and is useless at "someone who has done the 0-to-1 part before".

Fused with reciprocal rank fusion, which combines *ranks* rather than scores. That
matters: cosine similarity and Lucene's BM25 are not on a comparable scale, so adding
them directly lets whichever happens to have the wider range dominate. RRF only asks
"how near the top of its own list did this person appear".

Every path here has a local fallback so the product runs without Atlas indexes (free
tiers cap how many you get) and so tests never need a network. The fallback reproduces
the same fusion, so ranking semantics stay identical — only recall quality changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pymongo.database import Database

from app.embeddings import EmbeddingClient, cosine_similarity
from app.rerank import Reranker

# Standard RRF damping. Larger values flatten the advantage of rank 1 over rank 5.
RRF_K = 60
VECTOR_INDEX = "persona_chunks_vector"
PROFILE_INDEX = "profiles_text"

# Below this, a "match" is shared vocabulary rather than fit. Chosen against the
# (1 + cos) / 2 scale, where 50 is an orthogonal vector — literally no relationship
# between the query and what the member wrote. Callers may raise or lower it.
DEFAULT_MIN_MATCH_PERCENT = 50

PROFILE_SEARCH_FIELDS = [
    "headline",
    "bio",
    "skills",
    "interests",
    "looking_for",
    "hobbies",
    "role",
    "organization",
    "location",
    "display_name",
]

STOPWORDS = {
    "a", "an", "and", "any", "anyone", "are", "as", "at", "be", "been", "can", "could",
    "find", "for", "from", "has", "have", "help", "how", "i", "in", "into", "is", "it",
    "looking", "me", "my", "need", "of", "on", "or", "someone", "that", "the", "their",
    "them", "they", "this", "to", "want", "was", "we", "what", "who", "with", "would",
}


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9+#.-]*", text.lower())
        if token not in STOPWORDS and len(token) > 1
    ]


@dataclass
class Candidate:
    user_id: str
    vector_rank: int | None = None
    keyword_rank: int | None = None
    vector_score: float = 0.0
    keyword_score: float = 0.0
    evidence: list[dict[str, Any]] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)

    def rrf(self) -> float:
        total = 0.0
        if self.vector_rank is not None:
            total += 1.0 / (RRF_K + self.vector_rank)
        if self.keyword_rank is not None:
            total += 1.0 / (RRF_K + self.keyword_rank)
        return total


class PeopleSearch:
    def __init__(
        self,
        db: Database,
        *,
        embeddings: EmbeddingClient,
        atlas_enabled: bool = True,
        reranker: Reranker | None = None,
        rerank_candidates: int = 20,
    ) -> None:
        """`atlas_enabled=False` is a kill switch, not the enable path.

        Availability is *detected* rather than configured: an index that exists and is
        READY gets used. A boolean in .env drifts out of step with the cluster, and the
        failure mode is silent — the app quietly runs on the fallback while the index
        it needs sits there unused.
        """
        self.db = db
        self.embeddings = embeddings
        self.atlas_enabled = atlas_enabled
        self.reranker = reranker
        self.rerank_candidates = rerank_candidates
        self._probed = False
        self._atlas_vector_ok = False
        self._atlas_text_ok = False
        if atlas_enabled:
            self.probe()

    def probe(self) -> dict[str, bool]:
        """Ask the cluster which indexes actually exist and are queryable.

        Necessary because `$search` against a missing index returns an empty result
        set rather than raising. Inferring availability from behaviour would let the
        API report "atlas" while silently returning nothing — a status that lies is
        worse than one that says it fell back.
        """
        if not self.atlas_enabled:
            self._atlas_vector_ok = self._atlas_text_ok = False
            self._probed = True
            return {"vector": False, "keyword": False}
        self._atlas_vector_ok = self._index_ready(self.db.persona_chunks, VECTOR_INDEX)
        self._atlas_text_ok = self._index_ready(self.db.profiles, PROFILE_INDEX)
        self._probed = True
        return {"vector": self._atlas_vector_ok, "keyword": self._atlas_text_ok}

    @staticmethod
    def _index_ready(collection, name: str) -> bool:
        try:
            for index in collection.list_search_indexes():
                if index.get("name") == name:
                    return index.get("status") == "READY"
        except Exception:
            # Not Atlas, or the command is unsupported (mongomock).
            return False
        return False

    # ------------------------------------------------------------------ retrieval

    def _vector_atlas(
        self, query_vector: list[float], viewer_id: str, pool: int
    ) -> list[dict[str, Any]] | None:
        try:
            return list(
                self.db.persona_chunks.aggregate(
                    [
                        {
                            "$vectorSearch": {
                                "index": VECTOR_INDEX,
                                "path": "embedding",
                                "queryVector": query_vector,
                                "numCandidates": max(100, pool * 10),
                                "limit": pool,
                                "filter": {
                                    "user_id": {"$ne": viewer_id},
                                    "space": self.embeddings.space(),
                                },
                            }
                        },
                        {
                            "$project": {
                                "user_id": 1,
                                "text": 1,
                                "source_title": 1,
                                "source_id": 1,
                                "score": {"$meta": "vectorSearchScore"},
                            }
                        },
                    ]
                )
            )
        except Exception:
            # Missing or still-building index, or a tier without Atlas Search.
            self._atlas_vector_ok = False
            return None

    def _vector_local(
        self, query_vector: list[float], viewer_id: str, pool: int
    ) -> list[dict[str, Any]]:
        rows = []
        for chunk in self.db.persona_chunks.find(
            {"user_id": {"$ne": viewer_id}, "space": self.embeddings.space()}
        ):
            rows.append(
                {
                    "user_id": chunk["user_id"],
                    "text": chunk["text"],
                    "source_title": chunk.get("source_title"),
                    "source_id": chunk.get("source_id"),
                    # Rescaled to Atlas's `vectorSearchScore` convention, (1 + cos) / 2.
                    # Raw cosine here and normalized cosine on Atlas meant the same
                    # person scored 0.64 locally and 0.82 on the cluster — invisible
                    # while the number was only ever compared against its own query,
                    # and a real discrepancy now that it is reported as a similarity.
                    "score": (
                        1.0 + cosine_similarity(query_vector, chunk.get("embedding", []))
                    )
                    / 2.0,
                }
            )
        rows.sort(key=lambda row: row["score"], reverse=True)
        return rows[:pool]

    def _keyword_atlas(self, query: str, viewer_id: str, pool: int) -> list[dict] | None:
        try:
            rows = list(
                self.db.profiles.aggregate(
                    [
                        {
                            "$search": {
                                "index": PROFILE_INDEX,
                                "compound": {
                                    "should": [
                                        {
                                            "text": {
                                                "query": query,
                                                "path": PROFILE_SEARCH_FIELDS,
                                                # One edit of slack absorbs typos without
                                                # matching unrelated words.
                                                "fuzzy": {"maxEdits": 1, "prefixLength": 2},
                                            }
                                        },
                                        {
                                            "text": {
                                                "query": query,
                                                "path": ["skills", "looking_for", "headline"],
                                                "score": {"boost": {"value": 2}},
                                            }
                                        },
                                    ],
                                    "minimumShouldMatch": 1,
                                },
                                # Lucene knows which terms actually hit; without asking
                                # for highlights that information is lost and matches
                                # can no longer explain themselves to the user.
                                "highlight": {"path": PROFILE_SEARCH_FIELDS},
                            }
                        },
                        {"$match": {"_id": {"$ne": viewer_id}}},
                        {"$limit": pool},
                        {
                            "$project": {
                                "score": {"$meta": "searchScore"},
                                "highlights": {"$meta": "searchHighlights"},
                            }
                        },
                    ]
                )
            )
            for row in rows:
                row["matched"] = self._highlight_terms(row.pop("highlights", []))
            return rows
        except Exception:
            self._atlas_text_ok = False
            return None

    @staticmethod
    def _highlight_terms(highlights: list[dict]) -> list[str]:
        """Pull the actually-matched words out of Atlas Search highlight spans."""
        terms: list[str] = []
        for entry in highlights:
            for span in entry.get("texts", []):
                if span.get("type") != "hit":
                    continue
                for token in tokenize(span.get("value", "")):
                    if token not in terms:
                        terms.append(token)
        return terms[:6]

    def _keyword_local(self, query: str, viewer_id: str, pool: int) -> list[dict]:
        """Token-overlap stand-in for Lucene, with the same field weighting."""
        terms = set(tokenize(query))
        if not terms:
            return []
        weights = {"skills": 2.0, "looking_for": 2.0, "headline": 2.0}
        rows: list[dict] = []
        for profile in self.db.profiles.find({"_id": {"$ne": viewer_id}}):
            score = 0.0
            matched: set[str] = set()
            for field_name in PROFILE_SEARCH_FIELDS:
                value = profile.get(field_name)
                if not value:
                    continue
                text = " ".join(value) if isinstance(value, list) else str(value)
                hits = terms & set(tokenize(text))
                if hits:
                    score += len(hits) * weights.get(field_name, 1.0)
                    matched |= hits
            if score > 0:
                rows.append({"_id": profile["_id"], "score": score, "matched": sorted(matched)})
        rows.sort(key=lambda row: row["score"], reverse=True)
        return rows[:pool]

    # -------------------------------------------------------------------- fusion

    def _collect(self, query: str, viewer_id: str, pool: int) -> dict[str, Candidate]:
        query_vector = self.embeddings.embed(query)

        vector_rows = None
        if self._atlas_vector_ok:
            vector_rows = self._vector_atlas(query_vector, viewer_id, pool)
        if vector_rows is None:
            vector_rows = self._vector_local(query_vector, viewer_id, pool)

        keyword_rows = None
        if self._atlas_text_ok:
            keyword_rows = self._keyword_atlas(query, viewer_id, pool)
        if keyword_rows is None:
            keyword_rows = self._keyword_local(query, viewer_id, pool)

        candidates: dict[str, Candidate] = {}

        # Rank per *person*, not per chunk: someone with five decent chunks should not
        # outrank someone with one excellent one just by occupying more result slots.
        seen_rank = 0
        for row in vector_rows:
            user_id = row["user_id"]
            candidate = candidates.setdefault(user_id, Candidate(user_id=user_id))
            if candidate.vector_rank is None:
                seen_rank += 1
                candidate.vector_rank = seen_rank
                candidate.vector_score = round(float(row.get("score", 0.0)), 4)
            if len(candidate.evidence) < 2:
                candidate.evidence.append(
                    {
                        "text": row["text"][:280],
                        "source_title": row.get("source_title"),
                        "source_id": row.get("source_id"),
                        "score": round(float(row.get("score", 0.0)), 4),
                    }
                )

        for rank, row in enumerate(keyword_rows, start=1):
            user_id = row["_id"]
            candidate = candidates.setdefault(user_id, Candidate(user_id=user_id))
            candidate.keyword_rank = rank
            candidate.keyword_score = round(float(row.get("score", 0.0)), 4)
            candidate.matched_terms = row.get("matched", [])

        return candidates

    # -------------------------------------------------------------------- ranking

    def search(
        self,
        *,
        query: str,
        viewer_id: str,
        profiles: dict[str, dict],
        personas: dict[str, dict],
        trust: dict[str, float] | None = None,
        limit: int = 8,
        pool: int = 60,
        min_match_percent: int = DEFAULT_MIN_MATCH_PERCENT,
    ) -> dict[str, Any]:
        trust = trust or {}
        candidates = self._collect(query, viewer_id, pool)

        ranked: list[dict[str, Any]] = []
        for candidate in candidates.values():
            profile = profiles.get(candidate.user_id)
            if profile is None:
                continue
            base = candidate.rrf()
            if base <= 0:
                continue
            trust_value = trust.get(candidate.user_id, 0.5)
            # Trust demotes; it never promotes. Capped at 1.0 rather than allowed to
            # boost because RRF scores are deliberately flat — rank 1 and rank 2 differ
            # by ~1.6% — so any meaningful upward multiplier would let "people you like"
            # outrank "people who know the answer". Liking someone is not expertise.
            trust_factor = min(1.0, 0.55 + trust_value * 0.9)
            ranked.append(
                {
                    "user_id": candidate.user_id,
                    "score": round(base * trust_factor, 6),
                    "fusion_score": round(base, 6),
                    "vector_rank": candidate.vector_rank,
                    "keyword_rank": candidate.keyword_rank,
                    "vector_score": candidate.vector_score,
                    "keyword_score": candidate.keyword_score,
                    "trust": round(trust_value, 4),
                    "evidence": candidate.evidence,
                    "matched_terms": candidate.matched_terms,
                }
            )

        ranked.sort(key=lambda row: row["score"], reverse=True)
        reranked = self._rerank(query, ranked[: self.rerank_candidates], profiles, personas)
        ranked = reranked if reranked is not None else ranked

        for row in ranked:
            row["match_percent"], row["similarity_basis"] = self._similarity(row)

        # Thresholding happens before the limit, so raising the bar surfaces the next
        # candidate down rather than shortening the page.
        threshold = max(0, min(100, min_match_percent))
        kept = [row for row in ranked if row["match_percent"] >= threshold]
        hidden = len(ranked) - len(kept)
        matches = kept[: max(1, limit)]

        for row in matches:
            row["why_it_clicks"] = self._reasons(row, personas.get(row["user_id"]))

        return {
            "matches": matches,
            "retrieval": {
                "vector": "atlas" if self._atlas_vector_ok else "local",
                "keyword": "atlas" if self._atlas_text_ok else "local",
                "fusion": "reciprocal_rank",
                "rerank": self._rerank_status(reranked is not None),
                "embedding_space": self.embeddings.space(),
                "semantic": self.embeddings.describe()["semantic"],
                # What produced match_percent for this result set. Callers that present
                # the number need to know whether it is a reranked relevance or a raw
                # cosine — they are both honest similarities and they are not the same
                # measurement.
                "similarity": (
                    matches[0]["similarity_basis"] if matches else "none"
                ),
            },
            "threshold": {
                "min_match_percent": threshold,
                # Never a silent cut. A caller that hides people has to be able to say
                # how many, or "no matches" and "no matches above your bar" look alike.
                "hidden_below_threshold": hidden,
            },
        }

    def _rerank_status(self, ran: bool) -> str:
        """Three outcomes, not two.

        "off" and "skipped" both mean this result set was not reranked, but they call for
        opposite responses: "off" is a configuration fact that will hold until someone
        changes it, while "skipped" is one query losing a race with a per-minute quota
        and the next one will probably be fine. Reporting a rate-limited query as "off"
        sends you looking for a broken key.
        """
        if ran:
            return self.reranker.model
        if self.reranker is None or not self.reranker.available:
            return "off"
        return "skipped"

    def _rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        profiles: dict[str, dict],
        personas: dict[str, dict],
    ) -> list[dict[str, Any]] | None:
        """Re-score the survivors of fusion by reading query and candidate together.

        Returns None when reranking did not run, so the caller reports the honest
        retrieval path rather than implying a rerank that never happened.
        """
        if self.reranker is None or not candidates:
            return None

        documents = [self._candidate_text(row, profiles, personas) for row in candidates]
        scores = self.reranker.rank(query, documents, top_k=len(documents))
        if scores is None:
            return None

        for row, score in zip(candidates, scores, strict=True):
            row["rerank_score"] = round(score, 4)
            # Trust still applies after reranking, and still only downward — the
            # reranker judges relevance, not whether this person wasted your time.
            row["score"] = round(score * min(1.0, 0.55 + row["trust"] * 0.9), 6)
        candidates.sort(key=lambda row: row["score"], reverse=True)
        return candidates

    @staticmethod
    def _candidate_text(
        row: dict[str, Any], profiles: dict[str, dict], personas: dict[str, dict]
    ) -> str:
        """What the reranker reads. Their own words first, declared fields after."""
        profile = profiles.get(row["user_id"], {})
        persona = personas.get(row["user_id"], {})
        parts = [
            profile.get("headline", ""),
            " ".join(profile.get("skills", [])[:8]),
            " ".join(profile.get("looking_for", [])[:4]),
            persona.get("summary", "")[:400],
            *[item["text"] for item in row.get("evidence", [])],
        ]
        return "\n".join(part for part in parts if part).strip()

    @staticmethod
    def _similarity(row: dict[str, Any]) -> tuple[int, str]:
        """An absolute similarity in [0, 100], plus what measured it.

        This used to be `50 + 49 * sqrt(score / top)` — a rank *within one query*,
        normalised against whatever happened to come first. Two consequences made it
        unusable as a filter: the same person scored differently depending on who else
        matched, and the formula's floor was 50, so "hide anything under 50%" could
        never hide anything.

        So the number is now sourced from a measurement that means the same thing in
        every query, in preference order:

          `rerank`  — the cross-encoder read the query and the candidate together and
                      returned a calibrated relevance. This is the best answer we have.
          `vector`  — cosine similarity between the query and the member's nearest
                      chunk, on Atlas's (1 + cos) / 2 scale.

        RRF is deliberately *not* a source. It combines ranks, not scores, and is flat
        by construction — rank 1 and rank 2 differ by about 1.6% — so a percentage
        derived from it would vary with pool size rather than with fit.

        Ordering still comes from fusion and reranking. This only decides what number
        is shown and what the threshold cuts, which is why a keyword-only row returns
        0 and `keyword_only` rather than borrowing a similarity it never had.
        """
        if "rerank_score" in row:
            return int(round(100 * max(0.0, min(1.0, row["rerank_score"])))), "rerank"
        if row.get("vector_rank") is not None:
            return int(round(100 * max(0.0, min(1.0, row["vector_score"])))), "vector"
        return 0, "keyword_only"

    @staticmethod
    def _reasons(row: dict[str, Any], persona: dict | None) -> list[str]:
        """User-readable explanation. Never exposes raw vectors or internal scores."""
        reasons: list[str] = []
        if row["vector_rank"] is not None and row["keyword_rank"] is not None:
            reasons.append("Matches both what you asked for and how they describe themselves")
        elif row["vector_rank"] is not None:
            reasons.append("Their own writing covers what you're asking about")
        elif row["keyword_rank"] is not None:
            reasons.append("Their profile names exactly what you asked for")

        if row["matched_terms"]:
            reasons.append(f"Profile mentions {', '.join(row['matched_terms'][:3])}")

        if persona:
            looking = [item["value"] for item in persona.get("looking_for", [])][:2]
            if looking:
                reasons.append(f"Currently looking for {', '.join(looking)}")

        if row["trust"] > 0.6:
            reasons.append("Past interactions with them went well")
        elif row["trust"] < 0.45:
            reasons.append("Ranked lower because of a previous outcome you recorded")

        if row["evidence"]:
            source = row["evidence"][0].get("source_title")
            if source:
                reasons.append(f"Evidence from {source}")
        return reasons
