"""Create a demo network through the ordinary signup path.

Featured accounts (EnterAs) plus a crowd of members, connections, feed posts,
community threads, and a few DMs — enough that Discover, Feed, and Community look
like a live product rather than five empty profiles.

    uv run python -m scripts.seed_users              # add anything missing
    uv run python -m scripts.seed_users --reset      # delete catalog accounts and recreate
    uv run python -m scripts.seed_users --extract-all  # LLM-extract every persona (slow)
    uv run python -m scripts.seed_users --skip-agents  # skip recruitment / interviews

Nothing here is a special case the product does not otherwise support. Seeding is a
script, never a boot path (C4). Chunks are embedded in batches (C3). Consent is not
uniform — some agents comment, some refuse interviews, a few have stepped off discovery.
"""

from __future__ import annotations

import argparse
import hashlib
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

from app.accounts import AccountStore
from app.agent_memory import AgentMemoryStore
from app.auth import hash_password
from app.community import CommunityStore, safe_community_settings
from app.community_agent import CommunityCommenter
from app.embeddings import build_embedding_client
from app.ingestion import ExtractedSource, chunk_text
from app.interview import InterviewAgent, InterviewStore, safe_interview_settings
from app.llm import build_chat_model
from app.memory_graph import MemoryGraphStore
from app.messages import MessageStore
from app.persona import PersonaBuilder
from app.profile_media import ProfileMediaStore
from app.search import PeopleSearch
from app.settings import get_settings
from app.social import (
    ConnectionStore,
    FeedStore,
    episodic_title,
    pair_id,
    should_ingest,
)
from scripts.demo_catalog import (
    COMMUNITY_POSTS,
    DEMO_PASSWORD,
    FEATURED_EMAILS,
    MESSAGES,
    PEOPLE,
    catalog_emails,
)
from scripts.demo_community import seed_community_agents
from scripts.demo_interviews import seed_interviews

EMBED_BATCH = 32
# Spread join dates across the last 90 days so the network does not look like it
# appeared this afternoon.
JOIN_SPAN_HOURS = 24 * 90

# Portraits that match the person. Every source file is a woman, so Kenji and the
# other men stay initials — an unmatched face is a fabricated visual claim.
AVATAR_DIR = Path(__file__).resolve().parent / "demo_avatars"
DEMO_AVATARS: dict[str, dict[str, Any]] = {
    "maya@example.com": {"file": "maya.jpg", "ai_generated": False},
    "sofia@example.com": {"file": "sofia.jpg", "ai_generated": False},
    "priya@example.com": {"file": "priya.jpg", "ai_generated": True},
}

WIPE_BY_ID = ("users", "profiles", "personas", "member_settings", "agent_calibration")
WIPE_BY_FIELD = (
    ("persona_sources", "user_id"),
    ("persona_chunks", "user_id"),
    ("feed_posts", "author_id"),
    ("feed_reactions", "user_id"),
    ("feed_media", "user_id"),
    ("story_media", "user_id"),
    ("media_blobs", "user_id"),
    ("persona_media", "user_id"),
    ("profile_media", "user_id"),
    ("community_posts", "author_id"),
    ("community_comments", "responder_id"),
    ("comment_votes", "voter_id"),
    ("context_gaps", "user_id"),
    ("outcomes", "reporter_id"),
    ("research_briefs", "asker_id"),
    ("interviews", "asker_id"),
    ("agent_memory", "owner_id"),
    ("memory_log", "user_id"),
    ("memory_edges", "owner_id"),
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _hours_for(key: str, span: int) -> int:
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:2], "big") % max(1, span)


def _stamp(collection: Any, query: dict, when: datetime) -> None:
    collection.update_many(query, {"$set": {"created_at": when, "updated_at": when}})


def wipe_catalog(database: Database, emails: list[str]) -> int:
    existing = list(database.users.find({"email": {"$in": emails}}, {"_id": 1}))
    ids = [row["_id"] for row in existing]
    if not ids:
        return 0
    for name in WIPE_BY_ID:
        database[name].delete_many({"_id": {"$in": ids}})
    for name, field in WIPE_BY_FIELD:
        database[name].delete_many({field: {"$in": ids}})
    database.outcomes.delete_many({"subject_id": {"$in": ids}})
    database.interviews.delete_many({"subject_id": {"$in": ids}})
    database.research_briefs.delete_many({"subject_id": {"$in": ids}})
    database.memory_edges.delete_many({"counterparty_id": {"$in": ids}})
    database.connections.delete_many({"members": {"$in": ids}})
    database.direct_messages.delete_many({"participants": {"$in": ids}})
    database.member_trust.delete_many(
        {"$or": [{"reporter_id": {"$in": ids}}, {"subject_id": {"$in": ids}}]}
    )
    return len(ids)


def apply_settings(accounts: AccountStore, user_id: str, raw: dict[str, Any]) -> None:
    accounts.update_member_settings(
        user_id,
        {**safe_community_settings(raw), **safe_interview_settings(raw)},
    )


def seed_avatars(profile_media: ProfileMediaStore, roster: dict[str, dict[str, Any]]) -> int:
    """Attach demo portraits through the ordinary profile_media path (C25).

    Re-runs replace rather than skip, so a later seed can refresh the photos without
    wiping the network. Missing files print and continue — tests without binaries
    should not fail the rest of the seed.
    """
    profile_media.ensure_indexes()
    attached = 0
    for email, spec in DEMO_AVATARS.items():
        row = roster.get(email)
        if not row:
            continue
        path = AVATAR_DIR / spec["file"]
        if not path.is_file():
            print(f"avatar missing {path.name}")
            continue
        profile_media.set(
            user_id=row["user"]["_id"],
            kind="avatar",
            image=path.read_bytes(),
            media_type="image/jpeg",
            ai_generated=bool(spec["ai_generated"]),
        )
        attached += 1
        label = " (AI)" if spec["ai_generated"] else ""
        print(f"avatar {email:28} {spec['file']}{label}")
    return attached


def connection_plan(
    people: list[dict[str, Any]],
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    featured = [person["email"] for person in people if person.get("featured")]
    by_cluster: dict[str, list[str]] = defaultdict(list)
    for person in people:
        by_cluster[person["cluster"]].append(person["email"])

    accepted: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(left: str, right: str, source: str) -> None:
        if left == right:
            return
        key = tuple(sorted((left, right)))
        if key in seen:
            return
        seen.add(key)
        accepted.append((left, right, source))

    for index, left in enumerate(featured):
        for right in featured[index + 1 :]:
            add(left, right, "direct")

    for emails in by_cluster.values():
        count = len(emails)
        if count < 2:
            continue
        for index, email in enumerate(emails):
            add(email, emails[(index + 1) % count], "discovery")
            if count >= 4:
                add(email, emails[(index + 2) % count], "community")
            if count >= 7:
                add(email, emails[(index + 3) % count], "feed")

    clusters = sorted(by_cluster)
    for index, cluster in enumerate(clusters):
        nxt = clusters[(index + 1) % len(clusters)]
        left_members = by_cluster[cluster]
        right_members = by_cluster[nxt]
        if left_members and right_members:
            add(left_members[0], right_members[-1], "interview")

    for thread in MESSAGES:
        left, right = thread["participants"]
        add(left, right, "direct")

    pending: list[tuple[str, str, str]] = []
    for person in people:
        if person.get("featured"):
            continue
        for target in featured:
            key = tuple(sorted((person["email"], target)))
            if key in seen:
                continue
            digest = hashlib.sha256(f"{person['email']}:{target}".encode()).digest()
            if digest[0] < 20:
                pending.append((person["email"], target, "direct"))
                seen.add(key)
                break
    return accepted, pending


def _embed_jobs(
    *,
    embeddings: Any,
    settings: Any,
    jobs: list[tuple[str, ExtractedSource]],
) -> list[tuple[str, ExtractedSource, list[dict[str, Any]]]]:
    """Chunk every source, then embed all pieces in batches (C3)."""
    prepared: list[tuple[str, ExtractedSource, list[str]]] = []
    pieces: list[str] = []
    for user_id, source in jobs:
        chunks = chunk_text(
            source.text,
            size=settings.chunk_characters,
            overlap=settings.chunk_overlap_characters,
        )
        prepared.append((user_id, source, chunks))
        pieces.extend(chunks)

    vectors: list[list[float]] = []
    for start in range(0, len(pieces), EMBED_BATCH):
        vectors.extend(embeddings.embed_batch(pieces[start : start + EMBED_BATCH]))

    space = embeddings.space()
    cursor = 0
    result: list[tuple[str, ExtractedSource, list[dict[str, Any]]]] = []
    for user_id, source, chunks in prepared:
        rows = []
        for ordinal, text in enumerate(chunks):
            rows.append(
                {
                    "text": text,
                    "ordinal": ordinal,
                    "embedding": vectors[cursor],
                    "space": space,
                    "characters": len(text),
                }
            )
            cursor += 1
        result.append((user_id, source, rows))
    return result


def seed(
    *,
    reset: bool,
    extract_all: bool = False,
    skip_agents: bool = False,
    database: Database | None = None,
) -> dict[str, int]:
    settings = get_settings()
    client = None
    if database is None:
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
        database = client[settings.mongodb_database]

    accounts = AccountStore(database)
    connections = ConnectionStore(database)
    feed = FeedStore(database)
    messages = MessageStore(database)
    community = CommunityStore(database)
    profile_media = ProfileMediaStore(database)
    accounts.ensure_indexes()
    connections.ensure_indexes()
    feed.ensure_indexes()
    messages.ensure_indexes()
    community.ensure_indexes()
    profile_media.ensure_indexes()

    embeddings = build_embedding_client(settings)
    chat = build_chat_model(settings)
    builder = PersonaBuilder(embeddings=embeddings, chat=chat, settings=settings)

    described = embeddings.describe()
    print(f"Embeddings: {described['space']} (semantic={described['semantic']})")
    print(
        "Persona extraction: "
        + (
            f"model {chat.model_name} on featured"
            + (" + crowd" if extract_all else ", heuristic on crowd")
            if chat.configured
            else "heuristic"
        )
    )

    emails = catalog_emails()
    if reset:
        removed = wipe_catalog(database, emails)
        if removed:
            print(f"Removed {removed} existing demo account(s) and their network")

    password_hash = hash_password(DEMO_PASSWORD)
    roster: dict[str, dict[str, Any]] = {}
    created = 0
    skipped = 0

    for person in PEOPLE:
        existing = accounts.get_user_by_email(person["email"])
        if existing:
            apply_settings(accounts, existing["_id"], person.get("settings") or {})
            roster[person["email"]] = {"user": existing, "person": person, "new": False}
            skipped += 1
            print(f"skip   {person['email']:28} (already exists)")
            continue
        user = accounts.create_user(
            email=person["email"],
            password_hash=password_hash,
            display_name=person["display_name"],
        )
        accounts.update_profile(user["_id"], person["profile"])
        apply_settings(accounts, user["_id"], person.get("settings") or {})
        joined = utcnow() - timedelta(hours=_hours_for(person["email"], JOIN_SPAN_HOURS))
        _stamp(database.users, {"_id": user["_id"]}, joined)
        _stamp(database.profiles, {"_id": user["_id"]}, joined)
        roster[person["email"]] = {"user": user, "person": person, "new": True}
        created += 1

    avatars_attached = seed_avatars(profile_media, roster)

    source_jobs: list[tuple[str, ExtractedSource]] = []
    ingest_posts: list[tuple[str, str]] = []  # (user_id, post_id)
    posts_created = 0

    for row in roster.values():
        user_id = row["user"]["_id"]
        person = row["person"]
        needs_background = not accounts.list_sources(user_id)
        if needs_background:
            first = person["display_name"].split()[0].lower()
            source_jobs.append(
                (
                    user_id,
                    ExtractedSource(
                        title=f"{first}-background.txt",
                        text=person["source"],
                        kind="upload",
                        detail="seeded background document",
                    ),
                )
            )

        if database.feed_posts.count_documents({"author_id": user_id}, limit=1):
            continue
        for spec in person.get("posts") or []:
            post = feed.create(
                author_id=user_id,
                body=spec["body"],
                kind="human",
                presentation=spec["presentation"],
                location=spec.get("location"),
            )
            when = utcnow() - timedelta(hours=float(spec["hours_ago"]))
            database.feed_posts.update_one(
                {"_id": post["_id"]},
                {"$set": {"created_at": when, "updated_at": when}},
            )
            posts_created += 1
            stamp = when.isoformat()
            if should_ingest(spec["body"], spec["presentation"]):
                title = (
                    episodic_title(stamp)
                    if spec["presentation"] == "story"
                    else f"Post · {stamp[:10]}"
                )
                source_jobs.append(
                    (
                        user_id,
                        ExtractedSource(
                            title=title,
                            text=spec["body"],
                            kind="episodic" if spec["presentation"] == "story" else "post",
                            detail=post["_id"],
                        ),
                    )
                )
                ingest_posts.append((user_id, post["_id"]))

    embedded = _embed_jobs(embeddings=embeddings, settings=settings, jobs=source_jobs)
    chunk_count = 0
    for user_id, source, chunks in embedded:
        if not chunks:
            continue
        accounts.add_source(
            user_id=user_id,
            title=source.title,
            kind=source.kind,
            detail=source.detail,
            text=source.text,
            chunks=chunks,
        )
        chunk_count += len(chunks)

    ingested_by_post: dict[str, int] = defaultdict(int)
    for _user_id, source, chunks in embedded:
        if source.kind in {"post", "episodic"} and source.detail:
            ingested_by_post[source.detail] += len(chunks)
    for _user_id, post_id in ingest_posts:
        feed.mark_ingested(post_id, ingested_by_post.get(post_id, 0))

    for email, row in roster.items():
        user_id = row["user"]["_id"]
        if accounts.get_persona(user_id):
            continue
        profile = accounts.get_profile(user_id) or {}
        extras = {
            key: profile[key]
            for key in (
                "headline",
                "location",
                "skills",
                "interests",
                "looking_for",
                "likes",
                "dislikes",
                "hobbies",
            )
            if profile.get(key)
        }
        chunks = accounts.list_chunks(user_id, with_embedding=False)
        live = extract_all or row["person"].get("featured")
        if live:
            persona = builder.extract(chunks=chunks, extras=extras)
        else:
            persona = (
                builder._heuristic_persona(chunks, extras)
                if chunks
                else builder._empty_persona(extras)
            )
        accounts.save_persona(user_id, persona)
        accounts.mark_onboarding_complete(user_id)
        coverage = persona.get("coverage") or {}
        score = float(coverage.get("score") or 0)
        print(
            f"create {email:28} @{row['user']['handle']:16} "
            f"{persona.get('chunk_count', len(chunks))} chunks  "
            f"coverage {score:.2f}"
        )

    accepted_plan, pending_plan = connection_plan(PEOPLE)
    accepted_count = 0
    pending_count = 0
    for requester_email, recipient_email, source in accepted_plan:
        requester = roster[requester_email]["user"]["_id"]
        recipient = roster[recipient_email]["user"]["_id"]
        existing = connections.status_between(requester, recipient)
        if existing and existing.get("status") == "accepted":
            continue
        row = connections.request(
            requester_id=requester,
            recipient_id=recipient,
            source=source,
            note="",
        )
        if row["status"] != "accepted":
            connections.respond(pair=row["_id"], recipient_id=recipient, accept=True)
        when = utcnow() - timedelta(
            hours=_hours_for(f"{requester_email}:{recipient_email}", 24 * 40)
        )
        database.connections.update_one(
            {"_id": pair_id(requester, recipient)},
            {"$set": {"created_at": when, "updated_at": when, "responded_at": when}},
        )
        accepted_count += 1

    for requester_email, recipient_email, source in pending_plan:
        requester = roster[requester_email]["user"]["_id"]
        recipient = roster[recipient_email]["user"]["_id"]
        existing = connections.status_between(requester, recipient)
        if existing and existing.get("status") not in {None, "none"}:
            continue
        cluster = roster[requester_email]["person"]["cluster"]
        note = f"Saw your profile — would like to connect about {cluster}."
        connections.request(
            requester_id=requester,
            recipient_id=recipient,
            source=source,
            note=note,
        )
        pending_count += 1

    threads_created = 0
    for thread in MESSAGES:
        left_email, right_email = thread["participants"]
        left = roster[left_email]["user"]["_id"]
        right = roster[right_email]["user"]["_id"]
        if database.direct_messages.count_documents(
            {"conversation_id": pair_id(left, right)}, limit=1
        ):
            continue
        start = utcnow() - timedelta(hours=float(thread["hours_ago"]))
        for offset, (sender_email, body) in enumerate(thread["bodies"]):
            sender = roster[sender_email]["user"]["_id"]
            recipient = right if sender == left else left
            document = messages.send(sender_id=sender, recipient_id=recipient, body=body)
            when = start + timedelta(minutes=offset * 12)
            database.direct_messages.update_one(
                {"_id": document["_id"]},
                {"$set": {"created_at": when}},
            )
        threads_created += 1

    community_created = 0
    existing_titles = {
        row["title"] for row in database.community_posts.find({}, {"title": 1})
    }
    for spec in COMMUNITY_POSTS:
        if spec["title"] in existing_titles:
            continue
        author_id = roster[spec["author"]]["user"]["_id"]
        post = community.create_post(
            author_id=author_id, title=spec["title"], body=spec["body"]
        )
        when = utcnow() - timedelta(hours=float(spec["hours_ago"]))
        _stamp(database.community_posts, {"_id": post["_id"]}, when)
        community_created += 1

    agent_comments = {"posts": 0, "commented": 0, "declined": 0, "skipped": 0}
    interview_stats = {"ran": 0, "skipped": 0, "failed": 0, "answered_rows": 0}
    if not skip_agents:
        people_search = PeopleSearch(
            database,
            embeddings=embeddings,
            atlas_enabled=not settings.use_mock_mongodb,
        )
        atlas = people_search._atlas_vector_ok
        print("\nRecruiting community agents…")
        agent_comments = seed_community_agents(
            database=database,
            accounts=accounts,
            community=community,
            embeddings=embeddings,
            commenter=CommunityCommenter(chat),
            atlas=atlas,
        )
        interviews = InterviewStore(database)
        memory = AgentMemoryStore(database)
        graph = MemoryGraphStore(database)
        interviews.ensure_indexes()
        memory.ensure_indexes()
        graph.ensure_indexes()
        print("Running agent interviews…")
        interview_stats = seed_interviews(
            database=database,
            accounts=accounts,
            community=community,
            embeddings=embeddings,
            interviews=interviews,
            agent=InterviewAgent(chat),
            memory=memory,
            graph=graph,
            atlas=atlas,
        )

    reaction_count = 0
    reaction_kinds = ("like", "insightful", "same")
    for post in database.feed_posts.find({}, {"_id": 1, "author_id": 1}):
        author_id = post["author_id"]
        peers = connections.connected_ids(author_id)
        for peer_id in peers[:14]:
            digest = hashlib.sha256(f"{post['_id']}:{peer_id}".encode()).digest()
            if digest[0] >= 150:
                continue
            if database.feed_reactions.find_one(
                {"post_id": post["_id"], "user_id": peer_id}
            ):
                continue
            feed.react(
                post_id=post["_id"],
                user_id=peer_id,
                reaction=reaction_kinds[digest[1] % len(reaction_kinds)],
            )
            reaction_count += 1

    summary = {
        "users_created": created,
        "users_skipped": skipped,
        "users_total": len(roster),
        "avatars": avatars_attached,
        "chunks": chunk_count,
        "feed_posts": posts_created,
        "connections_accepted": accepted_count,
        "connections_pending": pending_count,
        "community_posts": community_created,
        "community_commented": agent_comments["commented"],
        "community_declined": agent_comments["declined"],
        "interviews_ran": interview_stats["ran"],
        "interview_answers": interview_stats["answered_rows"],
        "message_threads": threads_created,
        "reactions": reaction_count,
    }
    print(
        f"\nNetwork  {summary['users_total']} members  "
        f"{summary['connections_accepted']} connections  "
        f"{summary['feed_posts']} posts  "
        f"{summary['community_posts']} community threads  "
        f"{summary['message_threads']} DMs  "
        f"{summary['avatars']} avatars"
    )
    if not skip_agents:
        print(
            f"Agents   {summary['community_commented']} comments  "
            f"{summary['community_declined']} declines  "
            f"{summary['interviews_ran']} interviews  "
            f"{summary['interview_answers']} grounded answers"
        )
    print(f"Sign in with any featured email. Password: {DEMO_PASSWORD}")
    print("Featured: " + ", ".join(FEATURED_EMAILS))
    if client is not None:
        client.close()
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete catalog accounts and their network before recreating them",
    )
    parser.add_argument(
        "--extract-all",
        action="store_true",
        help="run live persona extraction on every member (slow, billed)",
    )
    parser.add_argument(
        "--skip-agents",
        action="store_true",
        help="skip community recruitment and interviews",
    )
    args = parser.parse_args()
    seed(reset=args.reset, extract_all=args.extract_all, skip_agents=args.skip_agents)
