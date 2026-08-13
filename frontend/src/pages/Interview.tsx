import {
  ArrowRight,
  Check,
  FileText,
  Loader2,
  Lock,
  MessagesSquare,
  Minus,
  Plus,
  ShieldAlert,
  Sparkles,
  TriangleAlert,
  UserPlus,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import { interviewApi, outcomeApi, socialApi } from "../api";
import { PageHeader } from "../AppShell";
import { OUTCOME_LABELS } from "../types";
import type { Interview, InterviewRow, InterviewPresets, SocialPerson } from "../types";

const VERDICT_COPY: Record<string, { label: string; blurb: string }> = {
  connect: { label: "Worth reaching out", blurb: "The answers support it" },
  maybe: { label: "Maybe", blurb: "Partial evidence — read the gaps" },
  pass: { label: "Probably not", blurb: "The answers point away from it" },
};

const DECLINE_COPY: Record<string, { label: string; icon: typeof Lock }> = {
  permission: { label: "Boundary", icon: Lock },
  not_in_profile: { label: "Not in profile", icon: Minus },
  no_model: { label: "No model", icon: ShieldAlert },
  error: { label: "Agent error", icon: TriangleAlert },
};

function AnswerRow({ row }: { row: InterviewRow }) {
  const [open, setOpen] = useState(false);
  const decline = row.decline_kind ? DECLINE_COPY[row.decline_kind] : null;
  const DeclineIcon = decline?.icon;

  return (
    // Namespaced: a bare `permission` class collides with the legacy stylesheet's
    // `.permission { display: flex }`, which drops the row out of the table layout.
    <tr className={row.answered ? "" : `unanswered decline-${row.decline_kind}`}>
      <td className="q-cell">{row.question}</td>
      <td className="a-cell">
        {row.answered ? (
          row.answer
        ) : (
          <span className="decline">
            {DeclineIcon && <DeclineIcon size={12} />} {row.decline_reason}
          </span>
        )}
      </td>
      <td className="src-cell">
        {row.citations.length > 0 ? (
          <button className="link-button" onClick={() => setOpen((v) => !v)}>
            <FileText size={11} /> {row.citations[0].source_title}
          </button>
        ) : (
          <span className="muted">{decline?.label || "—"}</span>
        )}
        {open && (
          <div className="src-excerpt">
            {row.citations.map((c) => (
              <blockquote key={c.chunk_id}>{c.excerpt}</blockquote>
            ))}
          </div>
        )}
      </td>
      <td className="conf-cell">
        {row.answered ? `${Math.round(row.confidence * 100)}%` : "—"}
      </td>
    </tr>
  );
}

function Result({ interview, onOutcome }: { interview: Interview; onOutcome: (l: string) => void }) {
  const v = interview.verdict;
  const copy = VERDICT_COPY[v.recommendation];
  const answerable = interview.question_count - interview.blocked_count;

  return (
    <>
      <section className={`verdict verdict-${v.recommendation}`}>
        <div className="verdict-head">
          <div>
            <strong>{copy.label}</strong>
            <small>{copy.blurb}</small>
          </div>
          <div className="verdict-stats">
            <span><b>{interview.answered_count}</b>/{answerable} answered</span>
            {interview.blocked_count > 0 && (
              <span className="muted">{interview.blocked_count} out of bounds</span>
            )}
          </div>
        </div>
        <p>{v.rationale}</p>
        {v.met.length > 0 && (
          <div className="verdict-list">
            <span className="consent-label">Supported by the answers</span>
            <ul>{v.met.map((m) => <li key={m}><Check size={12} /> {m}</li>)}</ul>
          </div>
        )}
        {v.missing.length > 0 && (
          <div className="verdict-list">
            <span className="consent-label">Still unknown</span>
            <ul>{v.missing.map((m) => <li key={m}><X size={12} /> {m}</li>)}</ul>
          </div>
        )}
        {interview.runtime_mode !== "live" && (
          <p className="persona-flag">
            <TriangleAlert size={13} /> Ran in {interview.runtime_mode.replace(/_/g, " ")} —
            not a live agent response.
          </p>
        )}
      </section>

      <table className="evidence-table">
        <thead>
          <tr><th>Question</th><th>Answer</th><th>Source</th><th>Conf.</th></tr>
        </thead>
        <tbody>
          {interview.rows.map((row) => <AnswerRow key={row.question} row={row} />)}
        </tbody>
      </table>

      {interview.offer && (
        <p className="interview-offer"><Sparkles size={13} /> {interview.offer}</p>
      )}

      <div className="outcome-row">
        <span className="outcome-label">Reached out? Record what happened</span>
        <div className="outcome-buttons">
          {OUTCOME_LABELS.map((o) => (
            <button key={o.id} className="outcome-chip" title={o.hint} onClick={() => onOutcome(o.id)}>
              {o.label}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

export default function InterviewPage() {
  const { subjectId = "" } = useParams();
  const location = useLocation();
  const [params] = useSearchParams();
  const routeState = location.state as { subject?: SocialPerson | null; headline?: string } | null;
  const [presets, setPresets] = useState<InterviewPresets>();
  const [goal, setGoal] = useState(params.get("goal") || "");
  const [questions, setQuestions] = useState<string[]>([""]);
  const [interview, setInterview] = useState<Interview>();
  const [polling, setPolling] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const subject = interview?.subject || routeState?.subject;
  const subjectName = subject?.display_name || "this member";
  const subjectHandle = subject?.handle || routeState?.subject?.handle;

  useEffect(() => {
    void interviewApi.presets().then(setPresets).catch(() => undefined);
  }, []);

  // Poll while the background job runs. Cleared on unmount so navigating away
  // mid-interview does not leave a timer firing against a dead component.
  useEffect(() => {
    if (!polling) return;
    let active = true;
    const timer = window.setInterval(async () => {
      try {
        const row = await interviewApi.get(polling);
        if (!active) return;
        setInterview(row);
        if (row.status !== "pending") {
          setPolling(undefined);
          setBusy(false);
          if (row.status === "failed") {
            setError(row.error || "The interview did not finish.");
          }
        }
      } catch {
        if (!active) return;
        setPolling(undefined);
        setBusy(false);
        setError("Lost track of the interview.");
      }
    }, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [polling]);

  const setQuestion = (index: number, value: string) =>
    setQuestions((all) => all.map((q, i) => (i === index ? value : q)));

  const usePreset = useCallback((key: string) => {
    if (!presets) return;
    setQuestions(presets.presets[key].slice(0, presets.max_questions));
  }, [presets]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const asked = questions.map((q) => q.trim()).filter(Boolean);
    if (goal.trim().length < 8 || !asked.length) {
      setError("Give a goal and at least one question.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      // The server answers immediately with a pending interview and does the agent
      // work in the background; poll until it settles.
      const started = await interviewApi.run(subjectId, goal, asked);
      setInterview(started);
      setPolling(started.status === "pending" ? started._id : undefined);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Interview failed");
      setBusy(false);
    }
  };

  const record = async (label: string) => {
    if (!interview) return;
    try {
      const result = await outcomeApi.record({
        subjectId, label, context: "interview", contextId: interview._id,
      });
      setNotice(
        `Recorded. Your agent now rates them ${Math.round(result.trust.value * 100)}.`,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not record that");
    }
  };

  const connect = async () => {
    try {
      const row = await socialApi.connect(
        subjectId,
        `Reached out after an agent interview about: ${goal}`,
        "interview",
        interview?._id,
      );
      setNotice(row.status === "accepted" ? `You and ${subjectName} are connected.` : `Connection request sent to ${subjectName}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not send that request");
    }
  };

  const subjectHeadline =
    routeState?.headline ||
    routeState?.subject?.headline ||
    "Answers stay grounded in what this member shared.";
  const subjectAccent = routeState?.subject?.accent || "violet";

  return (
    <>
      <PageHeader
        icon={MessagesSquare}
        title="Agent interview"
        blurb="Your agent asks; theirs answers only from what its user actually wrote, and says so when it can't. Every answer keeps its source."
      />

      <div className="thread">
        {subject && (
          <section className="interview-subject-card">
            <span className={`avatar avatar-md tone-${subjectAccent}`}>
              {subjectName.split(/\s+/).map((part) => part[0]).join("").slice(0, 2)}
            </span>
            <span>
              <small>YOU ARE ASKING</small>
              <b>{subjectName}'s agent</b>
              <p>{subjectHeadline}</p>
            </span>
            {subjectHandle && <Link to={`/u/${subjectHandle}`}>View profile <ArrowRight size={13} /></Link>}
          </section>
        )}

        {!interview && (
          <form className="composer-card" onSubmit={submit}>
            <label className="field">
              <span>What are you trying to find out?</span>
              <input
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="I need someone who has run real-time pipelines in production"
                maxLength={400}
              />
            </label>

            {presets && (
              <div className="discover-examples">
                {Object.keys(presets.presets).map((key) => (
                  <button type="button" key={key} className="example-chip" onClick={() => usePreset(key)}>
                    {key.replace(/_/g, " ")} questions
                  </button>
                ))}
              </div>
            )}

            <div className="question-list">
              {questions.map((q, index) => (
                <div className="question-row" key={index}>
                  <input
                    value={q}
                    onChange={(e) => setQuestion(index, e.target.value)}
                    placeholder={`Question ${index + 1}`}
                    maxLength={300}
                  />
                  {questions.length > 1 && (
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => setQuestions((all) => all.filter((_, i) => i !== index))}
                      aria-label="Remove question"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>
              ))}
            </div>

            {presets && questions.length < presets.max_questions && (
              <button type="button" className="ghost small" onClick={() => setQuestions((a) => [...a, ""])}>
                <Plus size={13} /> Add question
              </button>
            )}

            {error && <p className="auth-error" role="alert"><TriangleAlert size={14} /> {error}</p>}

            <div className="panel-actions">
              <button className="primary" type="submit" disabled={busy}>
                {busy ? <Loader2 size={15} className="spin" /> : <Sparkles size={15} />}
                {busy ? "Agents are talking…" : "Run the interview"}
              </button>
            </div>
          </form>
        )}

        {interview?.status === "pending" && (
          <section className="panel pending-interview">
            <Loader2 size={18} className="spin" />
            <div>
              <strong>The agents are talking</strong>
              <p>
                Their agent is answering {interview.question_count} question
                {interview.question_count === 1 ? "" : "s"} from its own documents. This
                usually takes under a minute — you can leave this page and come back.
              </p>
            </div>
          </section>
        )}

        {interview && interview.status !== "pending" && (
          <>
            {notice && <p className="thread-notice">{notice}</p>}
            {error && <p className="auth-error" role="alert">{error}</p>}
            {interview.status === "complete" && (
              <>
                <Result interview={interview} onOutcome={record} />
                <section className="interview-next-step">
                  <div>
                    <small>READY FOR THE HUMAN STEP?</small>
                    <h2>Turn the evidence into a real conversation.</h2>
                    <p>Your agent has done the screening. You stay in control of whether anything is sent.</p>
                  </div>
                  <div>
                    {subjectHandle && <Link className="ghost" to={`/u/${subjectHandle}`}>View profile</Link>}
                    <button className="primary" onClick={connect}><UserPlus size={15} /> Connect with {subjectName.split(" ")[0]}</button>
                  </div>
                </section>
              </>
            )}
            <div className="panel-actions">
              <button
                className="ghost"
                onClick={() => { setInterview(undefined); setNotice(""); setError(""); }}
              >
                Ask something else
              </button>
            </div>
          </>
        )}
      </div>
    </>
  );
}
