import pytest

from app.accounts import AccountStore
from app.auth import DEV_JWT_SECRET, assert_signing_key_is_safe
from app.community import DEFAULT_COMMUNITY_SETTINGS, safe_community_settings
from app.mock_mongo import create_mock_client
from app.settings import Settings

# ------------------------------------------------------------- signing key


def test_dev_secret_is_allowed_against_a_local_database() -> None:
    """The default exists so local development is frictionless — keep it working."""
    assert_signing_key_is_safe(
        Settings(jwt_secret=DEV_JWT_SECRET, mongodb_uri="mongodb://localhost:27017")
    )
    assert_signing_key_is_safe(Settings(jwt_secret=DEV_JWT_SECRET, use_mock_mongodb=True))


def test_dev_secret_against_a_remote_database_refuses_to_start() -> None:
    """Anyone who has read the repo could forge a session — a warning is not enough."""
    with pytest.raises(RuntimeError, match="public example value"):
        assert_signing_key_is_safe(
            Settings(
                jwt_secret=DEV_JWT_SECRET,
                mongodb_uri="mongodb+srv://user:pw@cluster0.example.mongodb.net/",
                # Explicit: conftest sets USE_MOCK_MONGODB for the suite, and the
                # guard correctly reads mock mongo as local.
                use_mock_mongodb=False,
            )
        )


def test_a_short_custom_secret_is_rejected_everywhere() -> None:
    with pytest.raises(RuntimeError, match="bytes"):
        assert_signing_key_is_safe(
            Settings(jwt_secret="too-short", mongodb_uri="mongodb://localhost:27017")
        )


def test_a_strong_secret_passes_against_a_remote_database() -> None:
    assert_signing_key_is_safe(
        Settings(
            jwt_secret="x" * 48,
            mongodb_uri="mongodb+srv://user:pw@cluster0.example.mongodb.net/",
            use_mock_mongodb=False,
        )
    )


def test_a_short_secret_is_rejected_even_remotely() -> None:
    with pytest.raises(RuntimeError, match="bytes"):
        assert_signing_key_is_safe(
            Settings(
                jwt_secret="short",
                mongodb_uri="mongodb+srv://user:pw@cluster0.example.mongodb.net/",
                use_mock_mongodb=False,
            )
        )


# ----------------------------------------------------------- discoverability


def test_members_are_discoverable_by_default() -> None:
    assert DEFAULT_COMMUNITY_SETTINGS["discoverable"] is True
    assert safe_community_settings({})["discoverable"] is True


def test_opting_out_of_discovery_is_recorded_and_queryable() -> None:
    accounts = AccountStore(create_mock_client()["hardening-test"])
    accounts.ensure_indexes()
    accounts.update_member_settings("hidden", safe_community_settings({"discoverable": False}))
    accounts.update_member_settings("visible", safe_community_settings({"discoverable": True}))

    hidden = accounts.undiscoverable_ids()
    assert hidden == {"hidden"}
    assert "visible" not in hidden


def test_a_member_who_never_touched_settings_stays_discoverable() -> None:
    accounts = AccountStore(create_mock_client()["hardening-test-2"])
    accounts.ensure_indexes()
    assert accounts.undiscoverable_ids() == set()


# ------------------------------------------------------- async interviews


def test_a_pending_interview_from_a_dead_process_reports_failed() -> None:
    """Nothing resumes a background job, so pending forever is the wrong answer."""
    from datetime import UTC, datetime, timedelta

    from app.interview import STALE_AFTER_SECONDS, InterviewStore

    store = InterviewStore(create_mock_client()["stale-test"])
    store.ensure_indexes()
    row = store.create_pending(
        asker_id="ada", subject_id="bo", goal="a goal", questions=["Q?"]
    )
    assert store.get(row["_id"], "ada")["status"] == "pending"

    store.db.interviews.update_one(
        {"_id": row["_id"]},
        {"$set": {"created_at": datetime.now(UTC) - timedelta(seconds=STALE_AFTER_SECONDS + 60)}},
    )
    stale = store.get(row["_id"], "ada")
    assert stale["status"] == "failed"
    assert "restarted" in stale["error"]


def test_naive_timestamps_from_mongo_do_not_break_stale_detection() -> None:
    """BSON round-trips datetimes without a timezone; utcnow() is aware."""
    from datetime import datetime, timedelta

    from app.interview import InterviewStore

    store = InterviewStore(create_mock_client()["stale-test-2"])
    store.ensure_indexes()
    row = store.create_pending(asker_id="ada", subject_id="bo", goal="g", questions=["Q?"])
    store.db.interviews.update_one(
        {"_id": row["_id"]},
        {"$set": {"created_at": datetime.utcnow() - timedelta(seconds=10)}},  # naive
    )
    assert store.get(row["_id"], "ada")["status"] == "pending"


def test_a_completed_interview_carries_its_counts() -> None:
    from app.interview import InterviewStore

    store = InterviewStore(create_mock_client()["complete-test"])
    store.ensure_indexes()
    row = store.create_pending(
        asker_id="ada", subject_id="bo", goal="a goal", questions=["Q1?", "Q2?", "Q3?"]
    )
    done = store.complete(
        row["_id"],
        rows=[
            {"answered": True, "decline_kind": None},
            {"answered": False, "decline_kind": "not_in_profile"},
            {"answered": False, "decline_kind": "permission"},
        ],
        verdict={"recommendation": "maybe"},
        offer="",
        runtime_mode="live",
        model="m",
    )
    assert done["status"] == "complete"
    assert done["answered_count"] == 1
    assert done["blocked_count"] == 1
    assert done["question_count"] == 3


def test_a_failed_background_job_records_why() -> None:
    from app.interview import InterviewStore

    store = InterviewStore(create_mock_client()["fail-test"])
    store.ensure_indexes()
    row = store.create_pending(asker_id="ada", subject_id="bo", goal="g", questions=["Q?"])
    store.fail(row["_id"], "RuntimeError: provider exploded")

    failed = store.get(row["_id"], "ada")
    assert failed["status"] == "failed"
    assert "provider exploded" in failed["error"]


# ------------------------------------------------------------- timestamp offsets


def test_serialized_timestamps_always_carry_an_offset() -> None:
    """A naive timestamp is read by the browser as *local* time, not UTC.

    BSON stores no timezone, so PyMongo hands back naive datetimes and
    `isoformat()` would emit "2026-08-13T03:32:33" — which `new Date()` parses in
    the viewer's zone. It shipped that way: a browser at UTC-7 showed every post
    under seven hours old as "just now". The offset is the whole fix.
    """
    from datetime import UTC, datetime, timedelta

    from app.serializers import serialize

    naive = serialize({"created_at": datetime(2026, 8, 13, 3, 32, 33)})["created_at"]
    assert naive.endswith("+00:00"), naive

    aware = serialize({"created_at": datetime(2026, 8, 13, 3, 32, 33, tzinfo=UTC)})
    assert aware["created_at"] == naive, "an already-aware timestamp must not shift"

    # The round trip a client actually performs must land back on the same instant.
    parsed = datetime.fromisoformat(naive)
    assert parsed - datetime(2026, 8, 13, 3, 32, 33, tzinfo=UTC) == timedelta(0)


def test_naive_timestamps_survive_nesting_and_lists() -> None:
    """Feed posts carry timestamps inside nested evidence, not just at the top level."""
    from datetime import datetime

    from app.serializers import serialize

    payload = serialize(
        {"posts": [{"created_at": datetime(2026, 1, 1, 12, 0, 0), "evidence": []}]}
    )
    assert payload["posts"][0]["created_at"].endswith("+00:00")


# ----------------------------------------------------------------- CORS


def test_loopback_frontend_origin_accepts_both_spellings() -> None:
    from app.main import allowed_origins, local_dev_origin_regex

    origins = allowed_origins("http://localhost:5173")
    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:5173" in origins
    assert local_dev_origin_regex("http://localhost:5173") is not None


def test_production_frontend_origin_is_not_a_localhost_regex() -> None:
    from app.main import allowed_origins, local_dev_origin_regex

    origins = allowed_origins("https://app.example.com")
    assert origins == ["https://app.example.com"]
    assert local_dev_origin_regex("https://app.example.com") is None
