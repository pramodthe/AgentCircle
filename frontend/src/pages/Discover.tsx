import {
  ArrowRight,
  Camera,
  Compass,
  Database,
  FileText,
  Loader2,
  MapPin,
  MessagesSquare,
  RotateCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Target,
  TriangleAlert,
  UserRound,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { discoveryApi, mediaApi } from "../api";
import { PageHeader } from "../AppShell";
import type {
  DiscoveryFacets,
  DiscoveryFilters,
  DiscoveryResponse,
  DiscoveryResult,
  PhotoSearchResponse,
  RetrievalStatus,
} from "../types";

const EXAMPLES = [
  "Who can help with backpressure and replay in a streaming pipeline?",
  "Someone who has been the first designer at a startup",
  "A clinical operations person who will pressure-test a prototype",
  "Who is hiring senior backend engineers right now?",
];

// Activities and settings, never people. The examples teach the constraint faster than
// the explanation underneath them does.
const PHOTO_EXAMPLES = [
  "Speaking at a conference",
  "Working in a woodshop or makerspace",
  "Whiteboarding a system design",
  "Out on a long cycling route",
];

/** Says exactly which retrieval path served the query — never implies more than it has. */
function RetrievalBadge({ retrieval }: { retrieval: RetrievalStatus }) {
  const degraded = !retrieval.semantic;
  return (
    <details className={degraded ? "retrieval-badge warn" : "retrieval-badge"} open={degraded}>
      <summary>
        {degraded ? <Database size={13} /> : <ShieldCheck size={13} />}
        <span>{degraded ? "Search is running in limited mode" : "Search quality is live"}</span>
        <small>How results were ranked</small>
      </summary>
      <p>
        Semantic: <b>{retrieval.vector === "atlas" ? "Atlas Vector Search" : "local fallback"}</b>
        {" · "}Keyword: <b>{retrieval.keyword === "atlas" ? "Atlas Search" : "local fallback"}</b>
        {" · "}Rerank: <b>{retrieval.rerank === "skipped" ? "skipped (rate limit)" : retrieval.rerank}</b>
      </p>
      {degraded && <small>These results currently match shared vocabulary more than meaning.</small>}
    </details>
  );
}

function MatchCard({
  match,
  goal,
  index,
}: {
  match: DiscoveryResult;
  goal: string;
  index: number;
}) {
  const [showEvidence, setShowEvidence] = useState(false);
  const both = match.vector_rank !== null && match.keyword_rank !== null;
  const firstName = match.member?.display_name?.split(" ")[0] || "them";
  const rawSummary = match.persona_summary.trim();
  const summary = rawSummary && !/[.!?…]$/.test(rawSummary)
    ? `${rawSummary.replace(/\s+\S*$/, "")}…`
    : rawSummary;
  const reasons = match.why_it_clicks
    .filter((reason) => !/mentions\s+[a-z]{1,3}$/i.test(reason.trim()))
    .slice(0, 3);
  const fitLabel = index === 0 ? "Top match" : match.match_percent >= 85 ? "Strong match" : "Possible match";

  return (
    <article className="social-match-card">
      <div className={`social-match-cover story-tone-${index % 5}`}>
        <span className={`avatar avatar-lg tone-${match.member ? "violet" : "blue"}`}>
          {(match.member?.display_name || "M").split(/\s+/).map((part) => part[0]).join("").slice(0, 2)}
        </span>
        <span className="social-match-score"><b>{match.match_percent}</b><small>relative fit</small></span>
      </div>
      <header className="social-match-identity-row">
        <div className="match-identity">
          <strong>{match.member?.display_name || "Member"}</strong>
          {match.headline && <span className="match-headline">{match.headline}</span>}
          {match.location && (
            <span className="match-location"><MapPin size={12} /> {match.location}</span>
          )}
        </div>
        <span className={index === 0 ? "fit-label top" : "fit-label"}><Zap size={12} /> {fitLabel}</span>
      </header>

      {summary && <p className="social-match-summary">{summary}</p>}

      <div className="why-it-clicks">
        <span><Sparkles size={13} /> Why it clicks</span>
        <ul>
        {(reasons.length ? reasons : ["Their grounded profile overlaps with what you asked for"]).map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
        </ul>
      </div>

      {(match.skills.length > 0 || match.looking_for.length > 0) && (
        <div className="match-tags">
          {match.skills.slice(0, 4).map((skill) => (
            <span className="chip" key={`s-${skill}`}>{skill}</span>
          ))}
          {match.looking_for.slice(0, 2).map((item) => (
            <span className="chip seeking" key={`l-${item}`}>seeking: {item}</span>
          ))}
        </div>
      )}

      <footer className="social-match-footer">
        <span className="retrieval-note">
          {both
            ? "Found by both semantic and keyword search"
            : match.vector_rank !== null
              ? "Found by semantic search"
              : "Found by keyword search"}
        </span>
        <span className="social-match-actions">
          {match.evidence.length > 0 && (
            <button className="link-button" onClick={() => setShowEvidence((value) => !value)}>
              <FileText size={12} /> {showEvidence ? "Hide" : "Show"} evidence
            </button>
          )}
          <Link
            className="match-primary-action"
            to={`/interview/${match.user_id}?goal=${encodeURIComponent(goal)}`}
            state={{ subject: match.member, headline: match.headline }}
          >
            <MessagesSquare size={13} /> Ask {firstName}'s agent <ArrowRight size={13} />
          </Link>
          {match.member?.handle && (
            <Link className="link-button" to={`/u/${match.member.handle}`}>
              <UserRound size={12} /> Profile
            </Link>
          )}
        </span>
      </footer>

      {showEvidence && (
        <div className="match-evidence social-match-evidence">
          {match.evidence.map((item) => (
            <blockquote key={item.text.slice(0, 40)}>
              <p>{item.text}</p>
              <cite>{item.source_title || "their own documents"}</cite>
            </blockquote>
          ))}
        </div>
      )}
    </article>
  );
}

/**
 * Photo results.
 *
 * The caption leads and the image supports it, not the other way round. A photo match is
 * only ever "this person said they were doing this" — presenting the picture as the
 * finding would invite exactly the reading of the feature that spec §9 rules out.
 */
function PhotoMatches({ response }: { response: PhotoSearchResponse }) {
  if (response.refused) {
    return (
      <p className="thread-notice photo-refusal">
        <ShieldAlert size={14} /> {response.reason}
      </p>
    );
  }
  if (response.available === false) {
    return <p className="thread-empty">{response.reason}</p>;
  }
  if (!response.results.length) {
    return (
      <p className="thread-empty">
        No photos matched. Only members who turned photo sharing on appear here.
      </p>
    );
  }
  return (
    <div className="photo-results">
      {response.results.map((photo) => (
        <article key={photo._id}>
          <img src={mediaApi.src(photo._id)} alt={photo.caption} loading="lazy" />
          <p>{photo.caption}</p>
          <footer>
            {photo.member ? (
              <Link to={`/u/${photo.member.handle}`}>{photo.member.display_name}</Link>
            ) : (
              <span>Member</span>
            )}
          </footer>
        </article>
      ))}
    </div>
  );
}

export default function Discover() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"people" | "photos">("people");
  const [result, setResult] = useState<DiscoveryResponse>();
  const [photos, setPhotos] = useState<PhotoSearchResponse>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [location, setLocation] = useState("");
  const [goal, setGoal] = useState("");
  const [evidenceOnly, setEvidenceOnly] = useState(false);
  const [facets, setFacets] = useState<DiscoveryFacets>();

  // Options come from live profiles so the pickers can never offer a city nobody is
  // in. A failure here leaves the filters usable as free text rather than blocking
  // the page — they are a convenience over the query, not a prerequisite for it.
  useEffect(() => {
    void discoveryApi.facets().then(setFacets).catch(() => undefined);
  }, []);

  const filters: DiscoveryFilters = { location, goal, evidenceOnly };
  const anyFilter = Boolean(location || goal || evidenceOnly);

  const run = async (value: string, override?: DiscoveryFilters) => {
    if (value.trim().length < 8) {
      setError("Say a bit more — a vague query gets vague matches.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (mode === "photos") {
        setPhotos(await mediaApi.search(value));
      } else {
        setResult(await discoveryApi.search(value, override ?? filters));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Search failed");
    } finally {
      setBusy(false);
    }
  };

  /** Re-run immediately on a filter change, but only once there is a query to narrow. */
  const applyFilter = (next: Partial<DiscoveryFilters>) => {
    const merged = { ...filters, ...next };
    if (next.location !== undefined) setLocation(next.location);
    if (next.goal !== undefined) setGoal(next.goal);
    if (next.evidenceOnly !== undefined) setEvidenceOnly(next.evidenceOnly);
    if (result && query.trim().length >= 8) void run(query, merged);
  };

  const clearFilters = () => {
    setLocation("");
    setGoal("");
    setEvidenceOnly(false);
    if (result && query.trim().length >= 8) {
      void run(query, { location: "", goal: "", evidenceOnly: false });
    }
  };

  const switchMode = (next: "people" | "photos") => {
    setMode(next);
    setError("");
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run(query);
  };

  return (
    <>
      <PageHeader
        variant="hero"
        eyebrow={<><Compass size={13} /> Discover inside your builder circle</>}
        title="Find people worth meeting this week."
        blurb="Search by what you need, not by job title. Your agent ranks people from what they actually shared and keeps every introduction approval-gated."
        aside={
          <>
            <b><Zap size={18} /> {result?.matches.length || "—"}</b>
            <span>ranked matches</span>
            <small><ShieldCheck size={13} /> Human approval required</small>
          </>
        }
      />

      <div className="discover social-discover">
        <div className="mode-tabs" role="tablist" aria-label="What to search">
          <button
            role="tab"
            aria-selected={mode === "people"}
            className={mode === "people" ? "on" : ""}
            onClick={() => switchMode("people")}
          >
            <UserRound size={14} /> People
          </button>
          <button
            role="tab"
            aria-selected={mode === "photos"}
            className={mode === "photos" ? "on" : ""}
            onClick={() => switchMode("photos")}
          >
            <Camera size={14} /> Photos
          </button>
        </div>

        <form className="discover-form social-discover-form" onSubmit={submit}>
          <label className="discover-form-label"><Sparkles size={14} /> Tell your agent who would be useful right now</label>
          <div className="discover-input">
            <Search size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={
                mode === "photos"
                  ? "What were they doing? A workshop, a build, a talk…"
                  : "Who are you looking for, and why?"
              }
              maxLength={500}
            />
            <button className="primary" type="submit" disabled={busy}>
              {busy ? <Loader2 size={15} className="spin" /> : <Search size={15} />} Search
            </button>
          </div>
          <div className="discover-examples">
            {(mode === "photos" ? PHOTO_EXAMPLES : EXAMPLES).map((example) => (
              <button
                key={example}
                type="button"
                className="example-chip"
                onClick={() => {
                  setQuery(example);
                  void run(example);
                }}
              >
                {example}
              </button>
            ))}
          </div>

          {mode === "people" && (
            <div className="discover-filters" role="group" aria-label="Narrow the results">
              <div className="discover-filter">
                <MapPin size={15} />
                {/* Free text with suggestions rather than a fixed dropdown: members
                    write a location freehand, and a city nobody has typed yet still
                    has to be searchable the day they arrive. */}
                <input
                  list="discover-locations"
                  value={location}
                  onChange={(event) => setLocation(event.target.value)}
                  onBlur={() => applyFilter({ location })}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      applyFilter({ location });
                    }
                  }}
                  placeholder="Anywhere"
                  aria-label="Filter by location"
                  maxLength={80}
                />
                <datalist id="discover-locations">
                  {(facets?.locations || []).map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.count} {item.count === 1 ? "member" : "members"}
                    </option>
                  ))}
                </datalist>
              </div>

              <div className="discover-filter">
                <Target size={15} />
                <select
                  value={goal}
                  onChange={(event) => applyFilter({ goal: event.target.value })}
                  aria-label="Filter by what they are looking for"
                >
                  <option value="">Any goal</option>
                  {(facets?.goals || []).map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.value}
                    </option>
                  ))}
                </select>
              </div>

              {/* Not "verified": nothing in this product verifies an identity, and a
                  badge saying otherwise would be the one claim it must never make.
                  What it can prove is whether the member supplied evidence at all. */}
              <label className="discover-toggle" title="Only members whose agent has documents behind it">
                <input
                  type="checkbox"
                  checked={evidenceOnly}
                  onChange={(event) => applyFilter({ evidenceOnly: event.target.checked })}
                />
                <span className="discover-toggle-track" aria-hidden="true"><i /></span>
                Evidence-backed only
              </label>

              {anyFilter && (
                <button type="button" className="discover-filter-clear" onClick={clearFilters}>
                  <X size={13} /> Clear
                </button>
              )}

              <button
                type="submit"
                className="discover-refresh"
                disabled={busy || query.trim().length < 8}
              >
                {busy ? <Loader2 size={14} className="spin" /> : <RotateCw size={14} />} Refresh
              </button>
            </div>
          )}
        </form>

        {error && <p className="auth-error" role="alert"><TriangleAlert size={14} /> {error}</p>}

        {mode === "photos" && photos && <PhotoMatches response={photos} />}

        {mode === "people" && result && (
          <>
            <RetrievalBadge retrieval={result.retrieval} />
            {result.matches.length === 0 ? (
              /* Three different situations render as an empty list, and telling them
                 apart is the difference between "widen the filter" and "the search is
                 broken". `candidates` is how many people survived filtering, before
                 the query ranked any of them. */
              result.filters.candidates === 0 && anyFilter ? (
                <p className="thread-empty">
                  No member matches those filters yet
                  {result.filters.location ? ` — nobody lists ${result.filters.location}` : ""}.
                  <button type="button" className="link-button" onClick={clearFilters}>
                    Clear filters
                  </button>
                </p>
              ) : anyFilter ? (
                <p className="thread-empty">
                  {result.filters.candidates}{" "}
                  {result.filters.candidates === 1 ? "member fits" : "members fit"} these
                  filters, but none of them match this query. Try a broader ask, or
                  <button type="button" className="link-button" onClick={clearFilters}>
                    clear the filters
                  </button>
                  .
                </p>
              ) : (
                <p className="thread-empty">
                  Nobody matched that. Either no member's background covers it, or their
                  profiles are still thin.
                </p>
              )
            ) : (
              <div className="match-list social-match-grid">
                {result.matches.map((match, index) => (
                  <MatchCard key={match.user_id} match={match} goal={result.query} index={index} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
