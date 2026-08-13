import { ArrowLeft, CheckCheck, MessageCircle, Send, Sparkles, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { messagesApi } from "../api";
import { PageHeader } from "../AppShell";
import { Avatar } from "../components/Avatar";
import { useAuth } from "../auth";
import type { MessageConversation, MessageThread as MessageThreadData, SocialPerson } from "../types";

function initials(person?: SocialPerson | null) {
  return (person?.display_name || "?")
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function timeLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(
    new Date(value),
  );
}

function ConversationRow({
  conversation,
  active,
  onClick,
}: {
  conversation: MessageConversation;
  active: boolean;
  onClick: () => void;
}) {
  const { member, last_message: lastMessage } = conversation;
  return (
    <button type="button" className={active ? "message-conversation active" : "message-conversation"} onClick={onClick}>
      <Avatar
        name={member.display_name}
        mediaId={member.avatar_media_id}
        accent={member.accent}
        size="md"
        aiGenerated={member.avatar_ai_generated}
      />
      <span className="message-conversation-copy">
        <b>{member.display_name}</b>
        <small>{lastMessage.body}</small>
      </span>
      <span className="message-conversation-meta">
        <time>{timeLabel(lastMessage.created_at)}</time>
        {conversation.unread_count > 0 && <i>{conversation.unread_count}</i>}
      </span>
    </button>
  );
}

export default function Messages() {
  const { user } = useAuth();
  const { userId } = useParams();
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<MessageConversation[]>([]);
  const [thread, setThread] = useState<MessageThreadData>();
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadConversations = useCallback(async () => {
    const rows = await messagesApi.conversations();
    setConversations(rows);
    return rows;
  }, []);

  const loadThread = useCallback(async (otherId: string) => {
    setThread(await messagesApi.thread(otherId));
    await loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    void loadConversations()
      .then((rows) => {
        if (!userId && rows[0]) navigate(`/messages/${rows[0].member_id}`, { replace: true });
      })
      .catch((caught) => setError(caught.message));
  }, [loadConversations, navigate, userId]);

  useEffect(() => {
    if (!userId) {
      setThread(undefined);
      return;
    }
    void loadThread(userId).catch((caught) => {
      setThread(undefined);
      setError(caught.message);
    });
  }, [loadThread, userId]);

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.member_id === userId),
    [conversations, userId],
  );

  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (!userId || !body.trim()) return;
    setBusy(true);
    setError("");
    try {
      const message = await messagesApi.send(userId, body);
      setBody("");
      setThread((current) => current ? { ...current, messages: [...current.messages, message] } : current);
      await loadConversations();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not send message");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="messages-page">
      <PageHeader
        variant="feature"
        eyebrow="Your builder circle"
        title="Messages"
        blurb="Talk directly with people you are connected to. Every conversation starts after both sides accept."
        aside={<span className="messages-heading-badge"><Sparkles size={13} /> Connection-first messaging</span>}
      />

      {error && <p className="auth-error" role="alert"><TriangleAlert size={14} /> {error}</p>}

      <div className="messages-layout">
        <aside className="message-inbox">
          <header>
            <span><MessageCircle size={15} /> Inbox</span>
            <small>{conversations.length} conversation{conversations.length === 1 ? "" : "s"}</small>
          </header>
          <div className="message-conversation-list">
            {conversations.map((conversation) => (
              <ConversationRow
                key={conversation.conversation_id}
                conversation={conversation}
                active={conversation.member_id === userId}
                onClick={() => navigate(`/messages/${conversation.member_id}`)}
              />
            ))}
            {!conversations.length && (
              <div className="message-inbox-empty">
                <MessageCircle size={20} />
                <b>No conversations yet</b>
                <p>Connect with someone first, then message them here.</p>
                <Link to="/connections" className="ghost small">View connections</Link>
              </div>
            )}
          </div>
        </aside>

        <main className="message-thread-panel">
          {thread ? (
            <>
              <header className="message-thread-header">
                <Link to="/messages" className="message-mobile-back" aria-label="Back to messages"><ArrowLeft size={16} /></Link>
                <Avatar
                  name={thread.member.display_name}
                  mediaId={thread.member.avatar_media_id}
                  accent={thread.member.accent}
                  size="md"
                  aiGenerated={thread.member.avatar_ai_generated}
                />
                <span>
                  <b>{thread.member.display_name}</b>
                  <small>{thread.member.headline || "Connected member"}</small>
                </span>
                <span className="connected-pill"><i /> Connected</span>
              </header>

              <div className="message-list" aria-live="polite">
                <div className="message-thread-intro">
                  <Sparkles size={18} />
                  <b>You are connected with {thread.member.display_name.split(" ")[0]}.</b>
                  <small>Say hello and continue the conversation.</small>
                </div>
                {thread.messages.map((message) => {
                  const mine = message.sender_id === user?._id;
                  return (
                    <div key={message._id} className={mine ? "message-bubble-row mine" : "message-bubble-row"}>
                      {!mine && <Avatar name={thread.member.display_name} mediaId={thread.member.avatar_media_id} accent={thread.member.accent} size="sm" />}
                      <span className="message-bubble">
                        {message.body}
                        <small>{timeLabel(message.created_at)} {mine && <CheckCheck size={11} />}</small>
                      </span>
                    </div>
                  );
                })}
              </div>

              <form className="message-composer" onSubmit={send}>
                <textarea
                  value={body}
                  onChange={(event) => setBody(event.target.value)}
                  placeholder={`Message ${thread.member.display_name.split(" ")[0]}…`}
                  rows={1}
                  maxLength={2000}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                />
                <button className="composer-submit" disabled={busy || !body.trim()}><Send size={14} /> Send</button>
              </form>
            </>
          ) : (
            <div className="message-thread-empty">
              <MessageCircle size={28} />
              <h2>{activeConversation ? "Open the conversation" : "Choose a conversation"}</h2>
              <p>Select a connected person from your inbox to start messaging.</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
