from pathlib import Path

from app.mock_mongo import create_mock_client
from scripts.demo_catalog import FEATURED_EMAILS, PEOPLE, catalog_emails
from scripts.seed_users import DEMO_AVATARS, seed, wipe_catalog


def test_catalog_has_at_least_fifty_distinct_members() -> None:
    emails = catalog_emails()
    assert len(emails) >= 50
    assert len(emails) == len(set(emails))
    names = [person["display_name"] for person in PEOPLE]
    assert len(names) == len(set(names))
    for person in PEOPLE:
        assert person["source"].strip()
        assert person["profile"]["bio"].strip()
        assert person["cluster"]
        assert "@example.com" in person["email"]
    featured = {person["email"] for person in PEOPLE if person.get("featured")}
    assert featured == set(FEATURED_EMAILS)


def test_consent_is_not_uniform() -> None:
    comment = {bool((person.get("settings") or {}).get("comment_enabled")) for person in PEOPLE}
    interview = {bool((person.get("settings") or {}).get("interview_enabled")) for person in PEOPLE}
    discoverable = {
        (person.get("settings") or {}).get("discoverable", True) for person in PEOPLE
    }
    assert comment == {True, False}
    assert interview == {True, False}
    assert discoverable == {True, False}

    kenji = next(person for person in PEOPLE if person["email"] == "kenji@example.com")
    assert kenji["settings"]["comment_enabled"] is False
    assert kenji["settings"]["interview_enabled"] is True
    assert kenji["settings"]["research_enabled"] is True

    maya = next(person for person in PEOPLE if person["email"] == "maya@example.com")
    assert maya["settings"]["comment_enabled"] is True
    assert "product" in maya["settings"]["comment_topics"]


def test_seed_builds_a_populated_network() -> None:
    database = create_mock_client()["seed-network"]
    summary = seed(reset=False, skip_agents=True, database=database)
    assert summary["users_total"] >= 50
    assert summary["users_created"] == summary["users_total"]
    assert summary["connections_accepted"] > 40
    assert summary["feed_posts"] > 40
    assert summary["community_posts"] >= 8
    assert summary["message_threads"] >= 5
    assert summary["chunks"] > 50
    assert database.users.count_documents({"email": "maya@example.com"}) == 1
    assert database.users.find_one({"email": "maya@example.com"})["onboarding_complete"] is True

    again = seed(reset=False, skip_agents=True, database=database)
    assert again["users_created"] == 0
    assert again["users_total"] == summary["users_total"]
    assert again["feed_posts"] == 0


def test_seed_attaches_demo_avatars_for_main_accounts() -> None:
    """Maya / Sofia / Priya get profile_media avatars; Kenji does not (no matching photo)."""
    database = create_mock_client()["seed-avatars"]
    for email, spec in DEMO_AVATARS.items():
        path = Path(__file__).resolve().parents[1] / "scripts" / "demo_avatars" / spec["file"]
        assert path.is_file(), f"missing demo avatar {path}"

    summary = seed(reset=False, skip_agents=True, database=database)
    assert summary["avatars"] == len(DEMO_AVATARS)

    maya = database.users.find_one({"email": "maya@example.com"})
    assert maya is not None
    avatar = database.profile_media.find_one({"_id": f"pm_avatar_{maya['_id']}"})
    assert avatar is not None
    assert avatar["kind"] == "avatar"
    assert "embedding" not in avatar
    assert database.media_blobs.find_one({"_id": avatar["_id"]}) is not None

    priya = database.users.find_one({"email": "priya@example.com"})
    assert database.profile_media.find_one({"_id": f"pm_avatar_{priya['_id']}"})["ai_generated"] is True

    kenji = database.users.find_one({"email": "kenji@example.com"})
    assert database.profile_media.find_one({"user_id": kenji["_id"]}) is None


def test_reset_removes_catalog_accounts_and_their_network() -> None:
    database = create_mock_client()["seed-reset"]
    seed(reset=False, skip_agents=True, database=database)
    removed = wipe_catalog(database, catalog_emails())
    assert removed >= 50
    assert database.users.count_documents({}) == 0
    assert database.feed_posts.count_documents({}) == 0
    assert database.connections.count_documents({}) == 0
    assert database.direct_messages.count_documents({}) == 0
