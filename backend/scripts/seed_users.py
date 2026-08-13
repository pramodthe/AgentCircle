"""Create demo accounts with real personas built from real ingested text.

These are ordinary users created through the same code path as a signup: password
hashing, source ingestion, chunking, embedding, persona extraction. Nothing here is a
special case the product does not otherwise support, so anything that works for a
seeded account works for a real one.

    uv run python -m scripts.seed_users            # add missing accounts
    uv run python -m scripts.seed_users --reset    # delete and recreate them
"""

from __future__ import annotations

import argparse

from pymongo import MongoClient

from app.accounts import AccountStore
from app.auth import hash_password
from app.embeddings import build_embedding_client
from app.ingestion import ExtractedSource
from app.llm import build_chat_model
from app.persona import PersonaBuilder
from app.settings import get_settings

DEMO_PASSWORD = "agentcircle"

PEOPLE = [
    {
        "email": "maya@example.com",
        "display_name": "Maya Chen",
        "profile": {
            "headline": "Founder at Lumen AI — AI onboarding for B2B products",
            "bio": (
                "I build onboarding experiences that adapt to the person using them. "
                "Happiest talking to other founders about activation, churn, and the "
                "unglamorous parts of product work."
            ),
            "location": "San Francisco",
            "role": "Founder",
            "organization": "Lumen AI",
            "interests": ["activation metrics", "developer tools", "design systems"],
            "hobbies": ["bouldering", "film photography"],
            "looking_for": ["design partners", "early enterprise pilots"],
            "likes": ["direct feedback", "small teams", "written specs"],
            "dislikes": ["cold pitches", "meetings without an agenda"],
            "theme": {"accent": "coral", "layout": "classic"},
        },
        "source": (
            "Maya Chen — Founder, Lumen AI (San Francisco)\n\n"
            "Founded Lumen AI in 2024 to fix B2B onboarding. Lumen personalizes the first "
            "session of a product based on what a user is actually trying to accomplish. "
            "Used by 40 B2B SaaS teams; median activation lift of 22 percent.\n\n"
            "Before Lumen: product lead at a developer tools company for four years, where "
            "she owned the self-serve funnel and rebuilt the trial experience end to end.\n\n"
            "Speaks regularly about activation metrics, onboarding instrumentation, and why "
            "most product analytics dashboards go unread.\n\n"
            "Studied cognitive science. Writes a small newsletter about product decisions "
            "that did not work.\n\n"
            "Outside work: bouldering several times a week, and shoots film photography."
        ),
    },
    {
        "email": "sofia@example.com",
        "display_name": "Sofia Alvarez",
        "profile": {
            "headline": "Research engineer — evidence, citations, and verification systems",
            "bio": (
                "I care about whether a claim is actually supported. I build retrieval and "
                "verification tooling, and I am good at telling you when your data does not "
                "say what you think it says."
            ),
            "location": "San Francisco",
            "role": "Research engineer",
            "interests": ["retrieval systems", "evaluation", "scientific tooling"],
            "hobbies": ["long-distance running", "crossword construction"],
            "looking_for": ["research collaborators", "hard evaluation problems"],
            "likes": ["citations", "reproducible benchmarks"],
            "dislikes": ["confident claims without sources"],
            "theme": {"accent": "blue", "layout": "classic"},
        },
        "source": (
            "Sofia Alvarez — Research engineer (San Francisco)\n\n"
            "Builds evidence and verification systems: retrieval pipelines that attach a "
            "source to every claim, and evaluation harnesses that catch unsupported output.\n\n"
            "Previously spent three years on search quality, where she built the citation "
            "coverage metric her team still uses to gate releases.\n\n"
            "Published work on retrieval evaluation and on measuring citation faithfulness "
            "in generated summaries.\n\n"
            "Known for structured, heavily-sourced handoffs. Prefers a slower answer with "
            "references over a fast one without.\n\n"
            "Runs long distances and constructs crosswords, badly."
        ),
    },
    {
        "email": "elena@example.com",
        "display_name": "Elena Rossi",
        "profile": {
            "headline": "Clinical operations lead at CareLoop",
            "bio": (
                "Fifteen years inside healthcare operations. I can tell you in ten minutes "
                "whether a clinical workflow prototype will survive contact with an actual "
                "nursing shift."
            ),
            "location": "San Francisco",
            "role": "Clinical operations lead",
            "organization": "CareLoop",
            "interests": ["clinical workflows", "care coordination", "health policy"],
            "hobbies": ["cooking", "open-water swimming"],
            "looking_for": ["healthcare founders to pressure-test prototypes"],
            "likes": ["prototypes over decks", "frontline input"],
            "dislikes": ["health tech built without clinicians"],
            "theme": {"accent": "teal", "layout": "classic"},
        },
        "source": (
            "Elena Rossi — Clinical operations lead, CareLoop (San Francisco)\n\n"
            "Fifteen years in healthcare operations, the last four at CareLoop building "
            "care coordination workflows for outpatient clinics.\n\n"
            "Started as a registered nurse and moved into operations, which is why she "
            "evaluates every tool by whether it survives a real shift.\n\n"
            "Has run prototype reviews for a dozen early healthcare startups. Typical "
            "feedback session is twenty minutes and ends with three specific changes.\n\n"
            "Interested in care coordination, discharge workflows, and health policy as it "
            "affects small clinics.\n\n"
            "Cooks seriously and swims in open water year round."
        ),
    },
    {
        "email": "kenji@example.com",
        "display_name": "Kenji Tanaka",
        "profile": {
            "headline": "Infrastructure engineer at GridPilot — energy systems",
            "bio": (
                "I work on the software that keeps distributed energy systems balanced. "
                "Interested in climate infrastructure and in hiring people who like hard "
                "systems problems."
            ),
            "location": "Oakland",
            "role": "Infrastructure engineer",
            "organization": "GridPilot",
            "interests": ["distributed systems", "energy markets", "climate tech"],
            "hobbies": ["cycling", "woodworking"],
            "looking_for": ["senior backend engineers", "climate tech peers"],
            "likes": ["systems thinking", "clear postmortems"],
            "dislikes": ["premature abstraction"],
            "theme": {"accent": "gold", "layout": "classic"},
        },
        "source": (
            "Kenji Tanaka — Infrastructure engineer, GridPilot (Oakland)\n\n"
            "Builds the control and settlement systems that keep distributed energy "
            "resources balanced against grid demand. Owns the real-time dispatch service.\n\n"
            "Six years in distributed systems before moving into climate: previously worked "
            "on payments infrastructure, where he learned to care about exactly-once "
            "semantics and clear postmortems.\n\n"
            "Currently hiring senior backend engineers who are comfortable with real-time "
            "systems and are willing to learn energy market mechanics.\n\n"
            "Cycles long distances and does woodworking on weekends."
        ),
    },
    {
        "email": "priya@example.com",
        "display_name": "Priya Raman",
        "profile": {
            "headline": "Design lead — early-stage product and brand",
            "bio": (
                "I help early teams find the shape of their product before they scale it. "
                "Mostly interface design, some brand, a lot of arguing about naming."
            ),
            "location": "San Francisco",
            "role": "Design lead",
            "interests": ["interface design", "typography", "early-stage product"],
            "hobbies": ["ceramics", "cycling"],
            "looking_for": ["founding design roles", "startups pre product-market fit"],
            "likes": ["fast prototypes", "opinionated products"],
            "dislikes": ["design by committee"],
            "theme": {"accent": "violet", "layout": "retro"},
        },
        "source": (
            "Priya Raman — Design lead (San Francisco)\n\n"
            "Ten years designing early-stage products. Has been the first designer at three "
            "startups, twice before the product had a name.\n\n"
            "Works on interface design and product shape: what the thing is, what it is not, "
            "and what the first screen should do.\n\n"
            "Strong typography background. Built the design system currently used across two "
            "of her former companies.\n\n"
            "Looking for a founding design role at a team that already has users and knows "
            "what it does not know.\n\n"
            "Makes ceramics and cycles."
        ),
    },
]


def seed(*, reset: bool) -> None:
    settings = get_settings()
    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    database = client[settings.mongodb_database]
    accounts = AccountStore(database)
    accounts.ensure_indexes()

    embeddings = build_embedding_client(settings)
    chat = build_chat_model(settings)
    builder = PersonaBuilder(embeddings=embeddings, chat=chat, settings=settings)

    described = embeddings.describe()
    print(f"Embeddings: {described['space']} (semantic={described['semantic']})")
    print(f"Persona extraction: {'model ' + chat.model_name if chat.configured else 'heuristic'}")

    if reset:
        emails = [person["email"] for person in PEOPLE]
        existing = list(database.users.find({"email": {"$in": emails}}, {"_id": 1}))
        user_ids = [row["_id"] for row in existing]
        if user_ids:
            for collection in ("users", "profiles", "personas"):
                database[collection].delete_many({"_id": {"$in": user_ids}})
            for collection in ("persona_sources", "persona_chunks"):
                database[collection].delete_many({"user_id": {"$in": user_ids}})
            print(f"Removed {len(user_ids)} existing demo account(s)")

    for person in PEOPLE:
        if accounts.get_user_by_email(person["email"]):
            print(f"skip   {person['email']} (already exists)")
            continue

        user = accounts.create_user(
            email=person["email"],
            password_hash=hash_password(DEMO_PASSWORD),
            display_name=person["display_name"],
        )
        accounts.update_profile(user["_id"], person["profile"])

        source = ExtractedSource(
            title=f"{person['display_name'].split()[0].lower()}-background.txt",
            text=person["source"],
            kind="upload",
            detail="seeded background document",
        )
        accounts.add_source(
            user_id=user["_id"],
            title=source.title,
            kind=source.kind,
            detail=source.detail,
            text=source.text,
            chunks=builder.prepare_chunks(source),
        )

        profile = accounts.get_profile(user["_id"]) or {}
        extras = {
            key: profile[key]
            for key in (
                "headline", "location", "skills", "interests",
                "looking_for", "likes", "dislikes", "hobbies",
            )
            if profile.get(key)
        }
        persona = builder.extract(
            chunks=accounts.list_chunks(user["_id"], with_embedding=False), extras=extras
        )
        accounts.save_persona(user["_id"], persona)
        accounts.mark_onboarding_complete(user["_id"])

        coverage = persona["coverage"]
        print(
            f"create {person['email']:24} @{user['handle']:14} "
            f"{persona['chunk_count']} chunks  coverage {coverage['score']:.2f}"
        )

    print(f"\nSign in with any of these emails. Password: {DEMO_PASSWORD}")
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true", help="delete the demo accounts before recreating them"
    )
    seed(reset=parser.parse_args().reset)
