import {
  ExternalLink,
  Loader2,
  ScrollText,
  ShieldAlert,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { researchApi } from "../api";
import { PageHeader } from "../AppShell";
import type { ResearchBrief, ResearchStatus } from "../types";

const GOALS = [
  "What have they built or shipped publicly?",
  "What have they written or spoken about?",
  "What are they working on right now?",
];

/**
 * The brief.
 *
 * Findings lead with the claim and carry the source next to it, never underneath a
 * summary that the reader has to take on trust. A claim whose source did not resolve was
 * already dropped server-side — `dropped_claims` says how many, because silently
 * discarding a model's output and silently keeping it look identical from here.
 */
function Brief({ brief }: { brief: ResearchBrief }) {
  if (brief.status === "pending") {
    return (
      <p className="thread-loading">
        <Loader2 size={15} className="spin" /> Searching and reading sources…
      </p>
    );
  }
  if (brief.status === "failed") {
    return (
      <p className="auth-error"><TriangleAlert size={14} /> {brief.error || "That run failed."}</p>
    );
  }
  if (brief.declined) {
    return (
      <div className="panel">
        <p className="thread-notice photo-refusal">
          <ShieldAlert size={14} /> {brief.decline_reason}
        </p>
        {(brief.unconfirmed_sources?.length ?? 0) > 0 && (
          <>
            <span className="consent-label">
              Pages with that name on them — none confirmed to be this member
            </span>
            <ul className="source-list">
              {(brief.unconfirmed_sources ?? []).map((s) => (
                <li key={s.url}>
                  <span className="source-body">
                    <a href={s.url} target="_blank" rel="noreferrer noopener">{s.title}</a>
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    );
  }

  return (
    <>
      {brief.summary && (
        <section className="panel">
          <span className="consent-label">Summary</span>
          <p className="persona-summary">{brief.summary}</p>
        </section>
      )}

      <section className="panel">
        <span className="consent-label">Findings — every one carries its source</span>
        <ul className="finding-list">
          {brief.findings.map((f, i) => (
            <li key={`${f.source_url}-${i}`}>
              <p>{f.claim}</p>
              <a href={f.source_url} target="_blank" rel="noreferrer noopener">
                <ExternalLink size={11} /> {new URL(f.source_url).hostname}
              </a>
            </li>
          ))}
        </ul>
        {!!brief.dropped_claims && (
          <p className="panel-sub">
            {brief.dropped_claims} claim{brief.dropped_claims === 1 ? " was" : "s were"} dropped
            for citing a source the search never returned.
          </p>
        )}
      </section>

      {brief.open_questions.length > 0 && (
        <section className="panel">
          <span className="consent-label">Worth asking them directly</span>
          <ul className="demand-list">
            {brief.open_questions.map((q) => <li key={q}>{q}</li>)}
          </ul>
        </section>
      )}

      <p className="panel-sub">
        {brief.sources.length} sources · {brief.queries.length} searches · cost $
        {brief.cost_usd.toFixed(4)}
      </p>
    </>
  );
}

export default function Research() {
  const { subjectId = "" } = useParams();
  const [status, setStatus] = useState<ResearchStatus>();
  const [goal, setGoal] = useState(GOALS[0]);
  const [brief, setBrief] = useState<ResearchBrief>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    void researchApi.status().then(setStatus).catch(() => undefined);
  }, []);

  // Stop polling if the page unmounts mid-run, or the timer outlives the component.
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const poll = useCallback((id: string) => {
    timer.current = window.setTimeout(async () => {
      try {
        const next = await researchApi.get(id);
        setBrief(next);
        if (next.status === "pending") poll(id);
        else setBusy(false);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Lost track of that run");
        setBusy(false);
      }
    }, 2000);
  }, []);

  const start = async () => {
    setBusy(true);
    setError("");
    setBrief(undefined);
    try {
      const started = await researchApi.start(subjectId, goal);
      setBrief(started);
      poll(started._id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start that");
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        icon={ScrollText}
        title="Deep research"
        blurb="Public professional context on one person, with a source next to every claim. They have to have turned this on."
      />

      {status && !status.available && (
        <p className="thread-notice">
          <ShieldAlert size={13} /> Deep research is off — no search provider is configured.
        </p>
      )}
      {error && <p className="auth-error" role="alert"><TriangleAlert size={14} /> {error}</p>}

      <section className="panel">
        <span className="consent-label">What do you want to know?</span>
        <p className="panel-sub">
          Public professional work only. Questions about protected or private attributes
          are refused before any search runs.
        </p>
        <div className="topic-grid">
          {GOALS.map((option) => (
            <button
              key={option}
              className={`topic-chip sentence${goal === option ? " on" : ""}`}
              onClick={() => setGoal(option)}
            >
              {option}
            </button>
          ))}
        </div>
        <label className="field">
          <span>Or ask your own</span>
          <input value={goal} maxLength={300} onChange={(e) => setGoal(e.target.value)} />
        </label>
        <div className="panel-actions">
          <button className="primary" onClick={start} disabled={busy || goal.trim().length < 8}>
            {busy ? <Loader2 size={15} className="spin" /> : <ScrollText size={15} />} Research
          </button>
        </div>
      </section>

      {brief && <Brief brief={brief} />}
    </>
  );
}
