import {
  Clock,
  Database,
  FileText,
  Lock,
  Sparkles,
  TriangleAlert,
  Waypoints,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { brainApi } from "../api";
import type { LearningEntry, LintFinding, NetworkPath } from "../types";

/**
 * What the agent has learned, what looks wrong with it, and who it can reach.
 *
 * The one thing this panel must communicate, because it is the thing a member would
 * otherwise reasonably fear: conversations are walled off from each other. It says so
 * plainly rather than leaving it to be inferred from an absence.
 */

const KIND_COPY: Record<string, string> = {
  source_added: "Added a source",
  source_removed: "Removed a source",
  persona_learned: "Learned",
  memory_written: "Remembered a conversation",
  edge_recorded: "Recorded a connection",
};

function when(value: string) {
  const elapsed = Math.max(0, Date.now() - new Date(value).getTime());
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function AgentMemory() {
  const [log, setLog] = useState<LearningEntry[]>();
  const [findings, setFindings] = useState<LintFinding[]>();
  const [paths, setPaths] = useState<NetworkPath[]>();

  useEffect(() => {
    void brainApi.log(20).then(setLog).catch(() => setLog([]));
    void brainApi.lint().then((r) => setFindings(r.findings)).catch(() => setFindings([]));
    void brainApi.paths().then((r) => setPaths(r.paths)).catch(() => setPaths([]));
  }, []);

  return (
    <section className="profile-surface" id="memory">
      <header className="profile-surface-heading">
        <h2><Sparkles size={16} /> What your agent remembers</h2>
        <small>Only you can see this</small>
      </header>

      <p className="brain-wall">
        <Lock size={14} />
        <span>
          Each conversation is kept on its own. What one person's agent told yours is
          recalled only when you are talking to <em>that</em> person — never repeated to
          anyone else.
        </span>
      </p>

      {findings === undefined ? (
        <div className="skeleton skeleton-text" />
      ) : findings.length > 0 ? (
        <div className="brain-lint">
          <span className="consent-label"><TriangleAlert size={12} /> Worth a look</span>
          <ul>
            {findings.map((finding, index) => (
              <li key={`${finding.kind}-${index}`}>
                <b>{finding.kind.replace(/_/g, " ")}</b>
                <span>{finding.message}</span>
                {finding.sources && finding.sources.length > 0 && (
                  <small><FileText size={10} /> {finding.sources.join(" · ")}</small>
                )}
              </li>
            ))}
          </ul>
          <small className="brain-lint-note">
            Flagged, not resolved — picking a winner between two of your own sources
            would be inventing a fact.
          </small>
        </div>
      ) : (
        <p className="brain-clean"><Database size={13} /> Nothing looks contradictory.</p>
      )}

      {paths !== undefined && paths.length > 0 && (
        <div className="brain-paths">
          <span className="consent-label"><Waypoints size={12} /> Two hops away</span>
          <ul>
            {paths.map((path) => (
              <li key={path.user_id}>
                <b>
                  {path.member?.handle ? (
                    <Link to={`/u/${path.member.handle}`}>{path.member.display_name}</Link>
                  ) : (
                    "A member"
                  )}
                </b>
                <small>
                  through {path.through.map((p) => p.display_name).join(", ") || "your network"}
                  {path.via.length > 0 && ` · both mention ${path.via.join(", ")}`}
                </small>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="brain-log">
        <span className="consent-label"><Clock size={12} /> What it learned, and when</span>
        {log === undefined ? (
          <div className="skeleton skeleton-text" />
        ) : log.length === 0 ? (
          <p className="brain-clean">Nothing yet — add a document and build your agent.</p>
        ) : (
          <ol>
            {log.map((entry) => (
              <li key={entry._id}>
                <i />
                <span>
                  <b>{KIND_COPY[entry.kind] || entry.kind}</b>
                  <small>{entry.summary} · {when(entry.created_at)}</small>
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
