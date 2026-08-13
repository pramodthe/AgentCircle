import {
  Check,
  FileText,
  Link2,
  Loader2,
  Sparkles,
  Trash2,
  TriangleAlert,
  Upload,
  UserRound,
} from "lucide-react";
import { useRef, useState } from "react";
import type { GapDemand, PersonaSource } from "../types";

function sourceIcon(kind: PersonaSource["kind"]) {
  if (kind === "link") return <Link2 size={14} />;
  if (kind === "declared") return <UserRound size={14} />;
  return <FileText size={14} />;
}

function sourceKind(kind: PersonaSource["kind"]) {
  if (kind === "link") return "Link";
  if (kind === "declared") return "From this page";
  return "File";
}

/**
 * The resume and the rest of the evidence — not another copy of skills or about.
 * Those already appear once on the profile. This is where they came from.
 */
export default function AgentDocuments({
  sources,
  demand,
  busy,
  error,
  notice,
  onUpload,
  onAddLink,
  onDelete,
  onRebuild,
  onResolveGaps,
}: {
  sources: PersonaSource[];
  demand?: GapDemand;
  busy: boolean;
  error?: string;
  notice?: string;
  onUpload: (file: File) => void;
  onAddLink: (url: string) => void;
  onDelete: (id: string) => void;
  onRebuild: () => void;
  onResolveGaps: (ids: string[]) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [linkDraft, setLinkDraft] = useState("");

  return (
    <div className="profile-stack" id="documents">
      <section className="profile-surface">
        <header className="profile-surface-heading">
          <span>Documents</span>
          <small>What your agent can cite</small>
        </header>
        <p className="profile-about-copy">
          Resumes, sites, and posts. Skills and about on this page already count —
          they are not listed again here.
        </p>
        {error && <p className="auth-error" role="alert"><TriangleAlert size={14} /> {error}</p>}
        {notice && <p className="thread-notice">{notice}</p>}
        <div className="source-actions">
          <button className="ghost" onClick={() => fileInput.current?.click()} disabled={busy}>
            <Upload size={15} /> Upload resume or file
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx,.txt,.md,.markdown"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onUpload(file);
              event.target.value = "";
            }}
          />
          <div className="link-row">
            <input
              value={linkDraft}
              onChange={(event) => setLinkDraft(event.target.value)}
              placeholder="yoursite.com, a blog post, LinkedIn…"
            />
            <button
              className="ghost"
              disabled={busy || !linkDraft.trim()}
              onClick={() => {
                onAddLink(linkDraft);
                setLinkDraft("");
              }}
            >
              <Link2 size={15} /> Add
            </button>
          </div>
        </div>
        <ul className="source-list">
          {sources.map((source) => (
            <li key={source._id}>
              <span className="source-icon">{sourceIcon(source.kind)}</span>
              <span className="source-body">
                <strong>{source.title}</strong>
                <small>
                  {source.chunk_count} passage{source.chunk_count === 1 ? "" : "s"} ·{" "}
                  {sourceKind(source.kind)}
                </small>
              </span>
              {source.kind !== "declared" && (
                <button
                  className="icon-button"
                  onClick={() => onDelete(source._id)}
                  disabled={busy}
                  aria-label={`Remove ${source.title}`}
                >
                  <Trash2 size={14} />
                </button>
              )}
            </li>
          ))}
          {!sources.length && <li className="source-empty">No documents yet — upload a resume to ground your agent.</li>}
        </ul>
        <div className="panel-actions">
          <button className="ghost" disabled={busy || !sources.length} onClick={onRebuild}>
            {busy ? <Loader2 size={14} className="spin" /> : <Sparkles size={14} />} Rebuild from documents
          </button>
        </div>
      </section>

      {demand && demand.demand.length > 0 && (
        <section className="profile-surface">
          <header className="profile-surface-heading">
            <span>Still unanswered</span>
            <small>{demand.total_unanswered} question{demand.total_unanswered === 1 ? "" : "s"}</small>
          </header>
          <p className="profile-about-copy">
            People asked these and your documents did not cover them. Add the answer
            above, then mark it covered.
          </p>
          <ul className="demand-list">
            {demand.demand.map((row) => (
              <li key={row.key}>
                <span className="demand-count">×{row.count}</span>
                <span className="demand-body">
                  <b>{row.question}</b>
                  <small>via {row.sources.join(", ")}</small>
                </span>
                <button
                  className="link-button"
                  title="Mark as covered"
                  onClick={() => onResolveGaps(row.ids)}
                >
                  <Check size={13} />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
