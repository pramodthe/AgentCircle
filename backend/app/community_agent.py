"""The agent that answers a community post on behalf of one member.

The failure mode this file exists to prevent: twelve agents leaving twelve paragraphs
of generic encouragement. Three defences, in order of how much they do:

  1. Grounding.  The model sees only excerpts from the responder's own persona chunks
     and is required to cite the excerpt number behind each claim. Citations that do
     not resolve to a supplied excerpt are dropped in `_finalize`, so an unverifiable
     attribution cannot survive into the thread.

  2. Permission to decline.  `declined` is a normal outcome, not an error. An agent
     with nothing grounded to say says so, and that decline is recorded as demand
     signal against the responder's persona.

  3. No keyless invention.  With no model configured this returns a decline rather
     than a templated opinion. A fabricated opinion attributed to a real person is
     worse than silence.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.llm import ChatModelBundle

COMMENT_SYSTEM_PROMPT = (
    "You are commenting on a community post on behalf of one specific person, using "
    "only the excerpts from their own documents that you are given.\n\n"
    "Rules:\n"
    "- Every substantive claim about this person's experience must cite the excerpt "
    "number that supports it.\n"
    "- Never invent employers, titles, numbers, projects, or opinions that the "
    "excerpts do not support.\n"
    "- If the excerpts do not give this person genuine, specific standing to help with "
    "this post, set declined to true and say briefly why. Declining is the correct "
    "answer far more often than not. Do not stretch a loose connection.\n"
    "- No generic encouragement, no 'great idea', no restating the post back.\n"
    "- Write as this person's representative, in plain third person, 2-5 sentences. "
    "Lead with the specific thing they know that bears on the post.\n"
    "- Where useful, say what the person could offer or would want to know — this is "
    "the start of a conversation between two humans, not a verdict."
)


class CommentDraft(BaseModel):
    declined: bool = Field(
        description="True when the excerpts do not support a specific, useful response."
    )
    decline_reason: str = Field(default="", max_length=280)
    body: str = Field(default="", max_length=1200)
    chunk_indexes: list[int] = Field(default_factory=list, max_length=6)
    offer: str = Field(default="", max_length=240)


class CommunityCommenter:
    def __init__(self, chat: ChatModelBundle) -> None:
        self.chat = chat

    @property
    def configured(self) -> bool:
        return self.chat.configured

    def draft(
        self,
        *,
        post_title: str,
        post_body: str,
        responder_name: str,
        chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not chunks:
            return self._decline(
                "This member has no ingested background to answer from.",
                runtime_mode="no_grounding",
            )
        if self.chat.model is None:
            # Deliberately a decline, not a template. See module docstring.
            return self._decline(
                "No language model is configured, so this agent will not speak for its "
                "user. Configure an LLM key to enable community comments.",
                runtime_mode="deterministic_fallback",
            )

        window = chunks[:6]
        excerpts = "\n\n".join(
            f"[{index}] (from {chunk.get('source_title', 'source')})\n{chunk['text']}"
            for index, chunk in enumerate(window)
        )
        try:
            structured = self.chat.model.with_structured_output(CommentDraft)
            result = structured.invoke(
                [
                    {"role": "system", "content": COMMENT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"POST TITLE: {post_title}\n\nPOST BODY:\n{post_body}\n\n"
                            f"You are representing {responder_name}. Excerpts from their "
                            f"own documents:\n\n{excerpts}\n\n"
                            "Comment on this post, or decline."
                        ),
                    },
                ]
            )
            if not isinstance(result, CommentDraft):
                result = CommentDraft.model_validate(result)
        except Exception as exc:
            return self._decline(
                f"The commenting agent failed: {type(exc).__name__}",
                runtime_mode="fallback_after_error",
            )

        return self._finalize(result, window)

    def _finalize(self, draft: CommentDraft, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        if draft.declined or not draft.body.strip():
            return self._decline(
                draft.decline_reason or "Not enough grounded expertise on this topic.",
                runtime_mode="live",
            )

        citations: list[dict[str, Any]] = []
        for index in draft.chunk_indexes:
            if index < 0 or index >= len(chunks):
                continue
            chunk = chunks[index]
            citations.append(
                {
                    "chunk_id": chunk["_id"],
                    "source_id": chunk.get("source_id"),
                    "source_title": chunk.get("source_title"),
                    "excerpt": chunk["text"][:220],
                }
            )

        # A substantive claim with no surviving citation violates the grounding rule,
        # so it is demoted to a decline rather than published uncited.
        if not citations:
            return self._decline(
                "The response could not be tied back to this member's own documents.",
                runtime_mode="live",
            )

        body = draft.body.strip()
        if draft.offer.strip():
            body = f"{body}\n\nCould help with: {draft.offer.strip()}"
        return {
            "declined": False,
            "decline_reason": None,
            "body": body,
            "citations": citations,
            "runtime_mode": "live",
            "model": self.chat.model_name,
        }

    def _decline(self, reason: str, *, runtime_mode: str) -> dict[str, Any]:
        return {
            "declined": True,
            "decline_reason": reason,
            "body": "",
            "citations": [],
            "runtime_mode": runtime_mode,
            "model": self.chat.model_name if self.chat.configured else None,
        }
