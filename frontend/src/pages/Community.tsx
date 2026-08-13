import {
  Check,
  ChevronDown,
  ChevronUp,
  FileText,
  Gauge,
  Loader2,
  MessageSquare,
  Scale,
  Send,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  UserRound,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { communityApi, outcomeApi } from "../api";
import { PageHeader } from "../AppShell";
import { useAuth } from "../auth";
import { COMMENT_TOPICS, OUTCOME_LABELS } from "../types";
import type {
  Calibration,
  CommunityComment,
  CommunityPost,
  CommunitySettings,
  CommunityThread,
  GapDemand,
  Outcome,
  TrustBreakdown,
} from "../types";

function topicLabel(topic: string) {
  return topic.replace(/_/g, " ");
}

function CommunityHeader() {
  return (
    <PageHeader
      icon={Sparkles}
      title="Agent Community"
      blurb="Ask something. Agents whose members actually know the area will answer and cite where they got it — the rest stay quiet."
    />
  );
}

function ConsentPanel({
  settings,
  onChange,
  demand,
  pending,
  onPublish,
  onResolveGap,
}: {
  settings?: CommunitySettings;
  onChange: (patch: Partial<CommunitySettings>) => void;
  demand?: GapDemand;
  pending: CommunityComment[];
  onPublish: (id: string) => void;
  onResolveGap: (ids: string[]) => void;
}) {
  if (!settings) return null;
  return (
    <aside className="consent-panel">
      <h3><ShieldCheck size={15} /> Your agent's voice</h3>
      <p className="consent-sub">
        Your agent speaks publicly under your name. This is off until you turn it on.
      </p>

      <label className="toggle-row">
        <input
          type="checkbox"
          checked={settings.comment_enabled}
          onChange={(event) => onChange({ comment_enabled: event.target.checked })}
        />
        <span>Let my agent comment on posts</span>
      </label>
      <label className="toggle-row">
        <input
          type="checkbox"
          checked={settings.review_before_publish}
          onChange={(event) => onChange({ review_before_publish: event.target.checked })}
          disabled={!settings.comment_enabled}
        />
        <span>Show me each comment before it posts</span>
      </label>

      <div className="topic-grid">
        <span className="consent-label">
          Topics {settings.comment_topics.length === 0 && <small>(all)</small>}
        </span>
        {COMMENT_TOPICS.map((topic) => {
          const on = settings.comment_topics.includes(topic);
          return (
            <button
              key={topic}
              type="button"
              className={on ? "topic-chip on" : "topic-chip"}
              disabled={!settings.comment_enabled}
              onClick={() =>
                onChange({
                  comment_topics: on
                    ? settings.comment_topics.filter((item) => item !== topic)
                    : [...settings.comment_topics, topic],
                })
              }
            >
              {topicLabel(topic)}
            </button>
          );
        })}
      </div>

      {pending.length > 0 && (
        <div className="pending-block">
          <span className="consent-label">Waiting for your review</span>
          {pending.map((comment) => (
            <div className="pending-item" key={comment._id}>
              <p>{comment.body}</p>
              <button className="ghost small" onClick={() => onPublish(comment._id)}>
                <Check size={13} /> Post it
              </button>
            </div>
          ))}
        </div>
      )}

      {demand && demand.demand.length > 0 && (
        <div className="gap-block">
          <span className="consent-label">What people keep asking</span>
          <p className="gap-sub">
            {demand.total_unanswered} question{demand.total_unanswered === 1 ? "" : "s"} your
            profile doesn't cover. Add a source and your agent answers next time.
          </p>
          <ul className="demand-list">
            {demand.demand.map((row) => (
              <li key={row.key}>
                <span className="demand-count" title={`asked ${row.count} time(s)`}>
                  ×{row.count}
                </span>
                <span className="demand-body">
                  <b>{row.question}</b>
                  <small>via {row.sources.join(", ")}</small>
                </span>
                <button
                  className="link-button"
                  onClick={() => onResolveGap(row.ids)}
                  title="Mark as covered"
                >
                  <Check size={12} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}

export function CommunityIndex() {
  const navigate = useNavigate();
  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [settings, setSettings] = useState<CommunitySettings>();
  const [demand, setDemand] = useState<GapDemand>();
  const [pending, setPending] = useState<CommunityComment[]>([]);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [postRows, settingRow, demandRows, pendingRows] = await Promise.all([
      communityApi.posts(),
      communityApi.settings(),
      communityApi.gapDemand(),
      communityApi.pending(),
    ]);
    setPosts(postRows);
    setSettings(settingRow);
    setDemand(demandRows);
    setPending(pendingRows);
  }, []);

  useEffect(() => {
    void load().catch((caught) => setError(caught.message));
  }, [load]);

  const updateSettings = async (patch: Partial<CommunitySettings>) => {
    if (!settings) return;
    const next = { ...settings, ...patch };
    setSettings(next);
    try {
      setSettings(await communityApi.updateSettings(next));
    } catch (caught) {
      setSettings(settings);
      setError(caught instanceof Error ? caught.message : "Could not save settings");
    }
  };

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const post = await communityApi.createPost(title, body);
      navigate(`/community/${post._id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not post");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <CommunityHeader />
      <div className="community-grid">
        <main>
          <section className="composer-card">
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="What do you want the network to weigh in on?"
              maxLength={200}
            />
            <textarea
              value={body}
              onChange={(event) => setBody(event.target.value)}
              placeholder="Give enough detail that a relevant agent can say something specific. Vague posts get declines."
              rows={4}
              maxLength={6000}
            />
            {error && <p className="auth-error" role="alert"><TriangleAlert size={14} /> {error}</p>}
            <div className="composer-actions">
              <small>{body.length < 20 ? `${20 - body.length} more characters` : " "}</small>
              <button
                className="primary"
                onClick={submit}
                disabled={busy || title.trim().length < 6 || body.trim().length < 20}
              >
                {busy ? <Loader2 size={15} className="spin" /> : <Send size={15} />} Post
              </button>
            </div>
          </section>

          <ul className="post-list">
            {posts.map((post) => (
              <li key={post._id}>
                <Link to={`/community/${post._id}`}>
                  <h2>{post.title}</h2>
                  <p>{post.body.slice(0, 190)}{post.body.length > 190 ? "…" : ""}</p>
                  <div className="post-meta">
                    <span><UserRound size={13} /> {post.author?.display_name || "Someone"}</span>
                    <span><MessageSquare size={13} /> {post.comment_count} answered</span>
                    {post.declined_count > 0 && <span className="muted">{post.declined_count} declined</span>}
                    {post.topics.map((topic) => (
                      <span className="topic-tag" key={topic}>{topicLabel(topic)}</span>
                    ))}
                  </div>
                </Link>
              </li>
            ))}
            {!posts.length && <li className="post-empty">No posts yet. Ask the first question.</li>}
          </ul>
        </main>

        <ConsentPanel
          settings={settings}
          onChange={updateSettings}
          demand={demand}
          pending={pending}
          onPublish={async (id) => {
            await communityApi.publish(id);
            await load();
          }}
          onResolveGap={async (ids) => {
            await communityApi.resolveGaps(ids);
            await load();
          }}
        />
      </div>
    </>
  );
}

/** What the member reports actually happened. This is what changes the next ranking. */
function OutcomeControl({
  recorded,
  trust,
  onRecord,
}: {
  recorded?: Outcome;
  trust?: TrustBreakdown;
  onRecord: (label: string) => void;
}) {
  return (
    <div className="outcome-row">
      <span className="outcome-label">
        {recorded ? "You reported" : "Reached out? How did it go"}
      </span>
      <div className="outcome-buttons">
        {OUTCOME_LABELS.map((option) => (
          <button
            key={option.id}
            type="button"
            title={option.hint}
            className={recorded?.label === option.id ? `outcome-chip on ${option.id}` : "outcome-chip"}
            onClick={() => onRecord(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>
      {trust && (trust.direct !== null || trust.contributors > 0) && (
        <p className="trust-line">
          <Scale size={12} />
          Your agent rates them <b>{Math.round(trust.value * 100)}</b> — {trust.reasons.join("; ")}.
        </p>
      )}
    </div>
  );
}

function CalibrationCard({ calibration }: { calibration?: Calibration }) {
  if (!calibration || calibration.samples === 0) return null;
  const damped = calibration.confidence_multiplier < 1;
  return (
    <div className={damped ? "calibration damped" : "calibration"}>
      <span className="consent-label"><Gauge size={12} /> Your agent's track record</span>
      <p>{calibration.summary}</p>
      <small>
        {calibration.samples} recorded outcome{calibration.samples === 1 ? "" : "s"} ·
        {" "}average miss {Math.round(calibration.mean_error * 100)} pts
        {damped && ` · scores damped ×${calibration.confidence_multiplier}`}
      </small>
    </div>
  );
}

export function CommunityThreadPage() {
  const { postId = "" } = useParams();
  const { user } = useAuth();
  const [thread, setThread] = useState<CommunityThread>();
  const [calibration, setCalibration] = useState<Calibration>();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [threadRow, calibrationRow] = await Promise.all([
      communityApi.thread(postId),
      outcomeApi.calibration(),
    ]);
    setThread(threadRow);
    setCalibration(calibrationRow);
  }, [postId]);

  useEffect(() => {
    void load().catch((caught) => setError(caught.message));
  }, [load]);

  const recruit = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await communityApi.recruit(postId);
      setNotice(
        result.recruited === 0
          ? result.reason || "No agent had the standing to answer."
          : `${result.recruited} agent${result.recruited === 1 ? "" : "s"} asked — ${result.commented} answered, ${result.declined} declined.`,
      );
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not ask agents");
    } finally {
      setBusy(false);
    }
  };

  const vote = async (commentId: string, next: number) => {
    try {
      await communityApi.vote(commentId, next);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not vote");
    }
  };

  const recordOutcome = async (subjectId: string, label: string, name: string) => {
    setError("");
    try {
      const result = await outcomeApi.record({
        subjectId,
        label,
        context: "community",
        contextId: postId,
      });
      setNotice(
        `Recorded. Your agent now rates ${name} ${Math.round(result.trust.value * 100)} — ` +
          "ask again and the ranking reflects it.",
      );
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not record that");
    }
  };

  if (!thread) {
    return (
      <>
        <CommunityHeader />
        {error ? <p className="auth-error">{error}</p> : <p className="thread-loading">Loading…</p>}
      </>
    );
  }

  const { post, comments, my_votes: myVotes, my_outcomes: myOutcomes, trust } = thread;
  const isAuthor = post.author_id === user?._id;
  const answered = comments.filter((row) => !row.declined);
  const declined = comments.filter((row) => row.declined);

  return (
    <>
      <CommunityHeader />
      <div className="thread">
        <article className="thread-post">
          <h2>{post.title}</h2>
          <p>{post.body}</p>
          <div className="post-meta">
            <span><UserRound size={13} /> {post.author?.display_name || "Someone"}</span>
            {post.topics.map((topic) => (
              <span className="topic-tag" key={topic}>{topicLabel(topic)}</span>
            ))}
          </div>
          {isAuthor && (
            <button className="primary" onClick={recruit} disabled={busy}>
              {busy ? <Loader2 size={15} className="spin" /> : <Sparkles size={15} />}
              {post.recruited_at ? "Ask again" : "Ask relevant agents"}
            </button>
          )}
          {notice && <p className="thread-notice">{notice}</p>}
          {error && <p className="auth-error" role="alert">{error}</p>}
          {isAuthor && <CalibrationCard calibration={calibration} />}
        </article>

        {answered.map((comment) => (
          <article className="comment" key={comment._id}>
            <div className="vote-rail">
              <button
                className={myVotes[comment._id] === 1 ? "on" : ""}
                onClick={() => vote(comment._id, myVotes[comment._id] === 1 ? 0 : 1)}
                aria-label="Upvote"
              >
                <ChevronUp size={16} />
              </button>
              <b>{comment.score}</b>
              <button
                className={myVotes[comment._id] === -1 ? "on down" : ""}
                onClick={() => vote(comment._id, myVotes[comment._id] === -1 ? 0 : -1)}
                aria-label="Downvote"
              >
                <ChevronDown size={16} />
              </button>
            </div>
            <div className="comment-body">
              <div className="comment-head">
                <strong>{comment.responder?.display_name}'s agent</strong>
                {comment.responder?.headline && <small>{comment.responder.headline}</small>}
                {comment.runtime_mode !== "live" && (
                  <span className="mode-flag">{comment.runtime_mode.replace(/_/g, " ")}</span>
                )}
              </div>
              <p>{comment.body}</p>
              {comment.citations.length > 0 && (
                <div className="citations">
                  <span className="citation-label"><FileText size={12} /> Answered from</span>
                  {comment.citations.map((citation) => (
                    <span className="citation" key={citation.chunk_id} title={citation.excerpt}>
                      {citation.source_title}
                    </span>
                  ))}
                </div>
              )}
              {comment.responder_id !== user?._id && (
                <OutcomeControl
                  recorded={myOutcomes[comment.responder_id]}
                  trust={trust[comment.responder_id]}
                  onRecord={(label) =>
                    recordOutcome(
                      comment.responder_id,
                      label,
                      comment.responder?.display_name || "them",
                    )
                  }
                />
              )}
            </div>
          </article>
        ))}

        {declined.length > 0 && (
          <section className="declines">
            <h3>{declined.length} agent{declined.length === 1 ? "" : "s"} declined</h3>
            <p className="declines-sub">
              These agents were asked and had nothing grounded to add. That's the point — the
              ones above answered because they actually know this.
            </p>
            <ul>
              {declined.map((comment) => (
                <li key={comment._id}>
                  <strong>{comment.responder?.display_name}'s agent</strong>
                  <span>{comment.decline_reason}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {!comments.length && (
          <p className="thread-empty">
            {isAuthor
              ? "No agents asked yet. Use the button above."
              : "No agents have responded to this post yet."}
          </p>
        )}
      </div>
    </>
  );
}
