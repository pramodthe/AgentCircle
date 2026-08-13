from app.messages import MessageStore
from app.mock_mongo import create_mock_client
from app.social import pair_id


def store() -> MessageStore:
    messages = MessageStore(create_mock_client()["messages-test"])
    messages.ensure_indexes()
    return messages


def test_messages_are_ordered_into_conversations_with_unread_counts() -> None:
    messages = store()
    first = messages.send(sender_id="ada", recipient_id="bo", body="Hello Bo")
    messages.send(sender_id="bo", recipient_id="ada", body="Hello Ada")

    conversations = messages.list_conversations("ada")
    assert len(conversations) == 1
    assert conversations[0]["member_id"] == "bo"
    assert conversations[0]["last_message"]["body"] == "Hello Ada"
    assert conversations[0]["unread_count"] == 1
    assert first["conversation_id"] == pair_id("ada", "bo")


def test_incoming_messages_are_unread_until_the_thread_is_opened() -> None:
    messages = store()
    messages.send(sender_id="bo", recipient_id="ada", body="Can we chat?")

    assert messages.list_conversations("ada")[0]["unread_count"] == 1
    messages.mark_read(user_id="ada", other_id="bo")
    assert messages.list_conversations("ada")[0]["unread_count"] == 0


def test_thread_is_private_to_the_pair_and_keeps_chronological_order() -> None:
    messages = store()
    messages.send(sender_id="ada", recipient_id="bo", body="First")
    messages.send(sender_id="ada", recipient_id="cy", body="Not for Bo")
    messages.send(sender_id="bo", recipient_id="ada", body="Second")

    assert [row["body"] for row in messages.thread(user_id="ada", other_id="bo")] == [
        "First",
        "Second",
    ]


def test_blank_messages_are_rejected() -> None:
    messages = store()
    try:
        messages.send(sender_id="ada", recipient_id="bo", body="  ")
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("blank messages must not be stored")
