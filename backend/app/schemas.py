from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field

from app.search import DEFAULT_MIN_MATCH_PERCENT


class RegisterRequest(BaseModel):
    email: EmailStr
    # 72 bytes is bcrypt's hard limit; longer passwords would be silently truncated.
    password: str = Field(min_length=8, max_length=72)
    display_name: str = Field(min_length=1, max_length=80)
    handle: str | None = Field(default=None, max_length=24)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]
    onboarding: dict[str, Any]


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    headline: str | None = Field(default=None, max_length=160)
    bio: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=120)
    pronouns: str | None = Field(default=None, max_length=40)
    organization: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=300)
    availability: str | None = Field(default=None, max_length=120)
    skills: list[str] | None = Field(default=None, max_length=25)
    interests: list[str] | None = Field(default=None, max_length=25)
    looking_for: list[str] | None = Field(default=None, max_length=10)
    likes: list[str] | None = Field(default=None, max_length=25)
    dislikes: list[str] | None = Field(default=None, max_length=25)
    hobbies: list[str] | None = Field(default=None, max_length=25)
    theme: dict[str, str] | None = None


class SourceLinkCreate(BaseModel):
    url: str = Field(min_length=3, max_length=500)


class PostCreate(BaseModel):
    title: str = Field(min_length=6, max_length=200)
    body: str = Field(min_length=20, max_length=6000)
    topics: list[str] | None = Field(default=None, max_length=8)


class VoteCreate(BaseModel):
    value: int = Field(ge=-1, le=1)


class GapResolve(BaseModel):
    gap_ids: list[str] = Field(min_length=1, max_length=50)


class ConnectionRequest(BaseModel):
    recipient_id: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=400)
    source: str = Field(default="direct", max_length=24)
    context_id: str | None = Field(default=None, max_length=64)


class ConnectionRespond(BaseModel):
    accept: bool


class DirectMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class PostCreateFeed(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    presentation: Literal["post", "story"] = "post"
    image_media_id: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=80)


class PostDraftRequest(BaseModel):
    """Rough notes the member wants their agent to turn into a post draft."""

    notes: str = Field(min_length=3, max_length=2000)


class ReactionCreate(BaseModel):
    reaction: str | None = Field(default=None, max_length=24)


class InterviewCreate(BaseModel):
    subject_id: str = Field(min_length=1, max_length=64)
    goal: str = Field(min_length=8, max_length=400)
    questions: list[str] = Field(min_length=1, max_length=8)


class InterviewSettingsUpdate(BaseModel):
    interview_enabled: bool | None = None
    interview_topics: list[str] | None = Field(default=None, max_length=8)
    disclose_personal: bool | None = None


class DiscoverySearch(BaseModel):
    query: str = Field(min_length=8, max_length=500)
    limit: int = Field(default=8, ge=1, le=25)
    # An absolute similarity floor, not a rank cutoff. 50 is an orthogonal vector, so
    # the default hides people who share vocabulary with the query but nothing else.
    min_match_percent: int = Field(default=DEFAULT_MIN_MATCH_PERCENT, ge=0, le=100)

    # Narrowing filters. `None` means "no constraint"; an empty string would otherwise
    # read as "match the empty value" and quietly return nobody. Applied to the
    # candidate universe before ranking, never to the result list after it.
    location: str | None = Field(default=None, max_length=80)
    goal: str | None = Field(default=None, max_length=120)
    # "Has the member actually supplied evidence", which is the only membership claim
    # this product can back. There is no identity-verification signal anywhere in the
    # data model, so a "verified" filter would be asserting something nobody checked.
    evidence_only: bool = False


class OutcomeCreate(BaseModel):
    subject_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=24)
    context: str = Field(default="community", max_length=32)
    context_id: str = Field(min_length=1, max_length=64)
    # Advisory only: the server prefers the score the agent actually predicted.
    predicted_score: float | None = Field(default=None, ge=0.0, le=1.0)
    note: str | None = Field(default=None, max_length=400)


class CommunitySettingsUpdate(BaseModel):
    comment_enabled: bool | None = None
    comment_topics: list[str] | None = Field(default=None, max_length=8)
    review_before_publish: bool | None = None
    discoverable: bool | None = None
    photo_search_enabled: bool | None = None
    research_enabled: bool | None = None


class APIMessage(BaseModel):
    message: str
    data: dict[str, Any] | None = None


class ResearchCreate(BaseModel):
    subject_id: str = Field(min_length=1, max_length=64)
    goal: str = Field(min_length=8, max_length=300)
