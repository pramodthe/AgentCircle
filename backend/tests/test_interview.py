import pytest

from app.interview import (
    DEFAULT_INTERVIEW_SETTINGS,
    InterviewAgent,
    InterviewResponse,
    InterviewStore,
    Verdict,
    classify_question,
    safe_interview_settings,
)
from app.llm import ChatModelBundle
from app.mock_mongo import create_mock_client

OPEN = {"interview_enabled": True, "interview_topics": [], "disclose_personal": True}
PROFESSIONAL_ONLY = {"interview_enabled": True, "disclose_personal": False}


class Scripted:
    def __init__(self, result):
        self.result = result

    def invoke(self, _messages):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class ScriptedModel:
    """Returns a different scripted object per schema, so answers and verdicts differ."""

    def __init__(self, by_schema):
        self.by_schema = by_schema

    def with_structured_output(self, schema):
        return Scripted(self.by_schema[schema.__name__])


def agent(by_schema=None):
    if by_schema is None:
        return InterviewAgent(ChatModelBundle(model=None, provider="t", model_name="t"))
    return InterviewAgent(
        ChatModelBundle(model=ScriptedModel(by_schema), provider="test", model_name="scripted")
    )


def chunks(*texts):
    return [
        {"_id": f"c{i}", "text": text, "source_title": "cv.txt", "source_id": "s1"}
        for i, text in enumerate(texts)
    ]


# ------------------------------------------------------------------ consent


def test_interviews_are_off_by_default() -> None:
    assert DEFAULT_INTERVIEW_SETTINGS["interview_enabled"] is False
    assert DEFAULT_INTERVIEW_SETTINGS["disclose_personal"] is False


def test_question_classification_separates_contact_and_personal() -> None:
    assert classify_question("What's your email address?") == "contact"
    assert classify_question("What are your hobbies?") == "personal"
    assert classify_question("What have you shipped in production?") == "professional"
    assert classify_question("What salary are you looking for?") == "personal"


def test_settings_reject_unknown_topics() -> None:
    safe = safe_interview_settings(
        {"interview_enabled": True, "interview_topics": ["hiring", "nonsense"]}
    )
    assert safe["interview_topics"] == ["hiring"]


def test_contact_questions_are_refused_even_when_everything_is_enabled() -> None:
    result = agent().run(
        questions=["What is your email address?"],
        subject_name="Kenji",
        chunks_per_question=[chunks("Kenji builds streaming systems.")],
        settings={**OPEN, "disclose_personal": True},
    )
    row = result["rows"][0]
    assert row["answered"] is False
    assert row["decline_kind"] == "permission"
    assert "never shared" in row["decline_reason"]


def test_personal_questions_respect_the_subjects_setting() -> None:
    result = agent().run(
        questions=["What are your hobbies?"],
        subject_name="Kenji",
        chunks_per_question=[chunks("Kenji cycles and does woodworking.")],
        settings=PROFESSIONAL_ONLY,
    )
    assert result["rows"][0]["decline_kind"] == "permission"
    assert result["runtime_mode"] == "permission_blocked"


# ------------------------------------------------------------------ answering


def test_no_model_declines_rather_than_improvising() -> None:
    result = agent().run(
        questions=["What have you shipped?"],
        subject_name="Kenji",
        chunks_per_question=[chunks("Kenji owns the dispatch service.")],
        settings=OPEN,
    )
    row = result["rows"][0]
    assert row["answered"] is False
    assert row["decline_kind"] == "no_model"
    assert row["answer"] == "", "a keyless agent must not answer for a real person"


def test_answers_keep_only_resolvable_citations() -> None:
    scripted = agent(
        {
            "InterviewResponse": InterviewResponse(
                answers=[
                    {
                        "question_index": 0,
                        "answered": True,
                        "answer": "Kenji owns an exactly-once dispatch path at 400k events/min.",
                        "chunk_indexes": [0, 99],
                        "confidence": 0.9,
                    }
                ],
                offer="a walkthrough of the replay design",
            )
        }
    )
    result = scripted.run(
        questions=["What have you shipped?"],
        subject_name="Kenji",
        chunks_per_question=[chunks("Exactly-once at 400k events/min.")],
        settings=OPEN,
    )
    row = result["rows"][0]
    assert row["answered"] is True
    assert [c["chunk_id"] for c in row["citations"]] == ["c0"]
    assert result["offer"] == "a walkthrough of the replay design"


def test_an_answer_with_no_surviving_citation_becomes_unanswered() -> None:
    scripted = agent(
        {
            "InterviewResponse": InterviewResponse(
                answers=[
                    {
                        "question_index": 0,
                        "answered": True,
                        "answer": "Confident but unsourced.",
                        "chunk_indexes": [],
                        "confidence": 0.9,
                    }
                ]
            )
        }
    )
    row = scripted.run(
        questions=["What have you shipped?"],
        subject_name="Kenji",
        chunks_per_question=[chunks("Some text.")],
        settings=OPEN,
    )["rows"][0]
    assert row["answered"] is False
    assert row["decline_kind"] == "not_in_profile"


def test_a_question_the_model_skipped_is_unanswered_not_dropped() -> None:
    scripted = agent({"InterviewResponse": InterviewResponse(answers=[])})
    rows = scripted.run(
        questions=["Q one?", "Q two?"],
        subject_name="Kenji",
        chunks_per_question=[chunks("a"), chunks("b")],
        settings=OPEN,
    )["rows"]
    assert len(rows) == 2
    assert all(row["answered"] is False for row in rows)
    assert all(row["decline_kind"] == "not_in_profile" for row in rows)


def test_model_failure_degrades_instead_of_raising() -> None:
    broken = agent({"InterviewResponse": RuntimeError("boom")})
    result = broken.run(
        questions=["What have you shipped?"],
        subject_name="Kenji",
        chunks_per_question=[chunks("text")],
        settings=OPEN,
    )
    assert result["runtime_mode"] == "fallback_after_error"
    assert result["rows"][0]["decline_kind"] == "error"


# ------------------------------------------------------------------- verdict


def _rows(answered: int, total: int) -> list[dict]:
    return [
        {
            "question": f"Q{i}",
            "kind": "professional",
            "answered": i < answered,
            "answer": "an answer" if i < answered else "",
            "citations": [{"source_title": "cv.txt"}] if i < answered else [],
            "confidence": 0.8 if i < answered else 0.0,
            "decline_kind": None if i < answered else "not_in_profile",
            "decline_reason": None if i < answered else "not in profile",
        }
        for i in range(total)
    ]


def test_permission_declines_do_not_count_against_coverage() -> None:
    """Otherwise an asker could depress anyone's verdict by asking for their email."""
    rows = _rows(2, 2) + [
        {
            "question": "What is your email address?",
            "kind": "contact",
            "answered": False,
            "answer": "",
            "citations": [],
            "confidence": 0.0,
            "decline_kind": "permission",
            "decline_reason": "Contact details are never shared through an agent.",
        }
    ]
    assert InterviewAgent.coverage(rows) == 1.0, "2 of 2 answerable questions were answered"

    with_gap = rows + [
        {
            "question": "Have you done X?",
            "kind": "professional",
            "answered": False,
            "answer": "",
            "citations": [],
            "confidence": 0.0,
            "decline_kind": "not_in_profile",
            "decline_reason": "not in profile",
        }
    ]
    # A profile gap still counts — that one really is missing context.
    assert InterviewAgent.coverage(with_gap) == pytest.approx(2 / 3)


def test_coverage_is_zero_when_every_question_was_blocked() -> None:
    blocked = [
        {
            "question": "What is your email?",
            "kind": "contact",
            "answered": False,
            "answer": "",
            "citations": [],
            "confidence": 0.0,
            "decline_kind": "permission",
            "decline_reason": "never shared",
        }
    ]
    assert InterviewAgent.coverage(blocked) == 0.0


def test_a_confident_verdict_on_a_mostly_empty_table_is_downgraded() -> None:
    scripted = agent(
        {
            "Verdict": Verdict(
                recommendation="connect",
                rationale="They seem like a strong fit for what you described.",
                met=["Q0"],
                missing=["Q1", "Q2", "Q3"],
                confidence=0.95,
            )
        }
    )
    verdict = scripted.verdict(
        goal="find a streaming engineer", subject_name="Kenji", rows=_rows(1, 4), offer=""
    )
    assert verdict["recommendation"] == "maybe", "1 of 4 answered cannot support 'connect'"
    assert "Downgraded" in verdict["rationale"]
    assert verdict["confidence"] <= verdict["coverage"]


def test_a_well_covered_verdict_is_left_alone() -> None:
    scripted = agent(
        {
            "Verdict": Verdict(
                recommendation="connect",
                rationale="Four of four answered with specifics from their own documents.",
                met=["Q0", "Q1", "Q2", "Q3"],
                missing=[],
                confidence=0.9,
            )
        }
    )
    verdict = scripted.verdict(
        goal="find a streaming engineer", subject_name="Kenji", rows=_rows(4, 4), offer=""
    )
    assert verdict["recommendation"] == "connect"
    assert verdict["coverage"] == 1.0


def test_verdict_without_a_model_reports_a_count_not_a_judgement() -> None:
    verdict = agent().verdict(
        goal="find someone", subject_name="Kenji", rows=_rows(2, 4), offer=""
    )
    assert verdict["recommendation"] == "maybe"
    assert verdict["confidence"] == 0.0
    assert "not a judgement" in verdict["rationale"]


def test_verdict_with_nothing_answered_is_a_pass() -> None:
    verdict = agent().verdict(
        goal="find someone", subject_name="Kenji", rows=_rows(0, 3), offer=""
    )
    assert verdict["recommendation"] == "pass"


def test_recommendations_are_limited_to_contact_decisions() -> None:
    """The schema itself prevents 'hire' / 'date' style verdicts."""
    assert set(Verdict.model_fields["recommendation"].annotation.__args__) == {
        "connect",
        "maybe",
        "pass",
    }


# --------------------------------------------------------------------- store


def test_interviews_are_private_to_the_asker() -> None:
    store = InterviewStore(create_mock_client()["interview-test"])
    store.ensure_indexes()
    saved = store.save(
        asker_id="asker-1", subject_id="subject-1", goal="find someone",
        rows=_rows(2, 3), verdict={"recommendation": "maybe"}, offer="",
        runtime_mode="live", model="m",
    )

    assert store.get(saved["_id"], "asker-1") is not None
    assert store.get(saved["_id"], "someone-else") is None, (
        "an interview must not be readable by anyone but the asker"
    )
    assert saved["answered_count"] == 2
    assert saved["question_count"] == 3
    assert store.list_for_asker("someone-else") == []


def test_store_records_counts_for_the_list_view() -> None:
    store = InterviewStore(create_mock_client()["interview-test-2"])
    store.ensure_indexes()
    for answered in (0, 3):
        store.save(
            asker_id="asker-1", subject_id=f"s{answered}", goal="goal here",
            rows=_rows(answered, 3), verdict={"recommendation": "maybe"}, offer="",
            runtime_mode="live", model="m",
        )
    rows = store.list_for_asker("asker-1")
    assert {row["answered_count"] for row in rows} == {0, 3}


@pytest.mark.parametrize("question", ["what is your phone number", "share your linkedin"])
def test_contact_markers_are_caught_case_insensitively(question: str) -> None:
    assert classify_question(question.upper()) == "contact"
