import { Check, Compass, MessageCircle, Sparkles, TriangleAlert, Users, X } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { socialApi } from "../api";
import { PageHeader } from "../AppShell";
import { SkeletonList } from "../components/Skeleton";
import { useToast } from "../components/Toast";
import type { ConnectionsResponse, SocialConnection } from "../types";

/** Where a connection came from — which part of the product actually works. */
const SOURCE_COPY: Record<string, string> = {
  discovery: "found in Discover",
  interview: "after an agent interview",
  community: "from a community thread",
  feed: "from the feed",
  direct: "direct request",
};

type ConnectionTab = "accepted" | "recommended" | "pending" | "rejected" | "saved";

const TABS: Array<{ id: ConnectionTab; label: string }> = [
  { id: "accepted", label: "Accepted" },
  { id: "recommended", label: "Agent-recommended" },
  { id: "pending", label: "Pending intros" },
  { id: "rejected", label: "Rejected" },
  { id: "saved", label: "Saved" },
];

function initials(name: string) {
  return name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
}

function ConnectionCard({
  connection,
  action,
}: {
  connection: SocialConnection;
  action?: ReactNode;
}) {
  const person = connection.member;
  const name = person?.display_name || "Unknown member";
  const accent = person?.accent || "violet";

  return (
    <article>
      <i className={`tone-${accent}`} aria-hidden="true" />
      <span className={`avatar avatar-sm tone-${accent}`} aria-hidden="true">{initials(name)}</span>
      <span>
        <b>
          {person?.handle ? <Link to={`/u/${person.handle}`}>{name}</Link> : name}
        </b>
        <small>{person?.headline || "Builder in your circle"}</small>
        <em><Sparkles size={11} /> Agent note · {SOURCE_COPY[connection.source] || connection.source}</em>
      </span>
      {action}
    </article>
  );
}

function EmptyConnections({ tab }: { tab: ConnectionTab }) {
  const copy: Record<ConnectionTab, { title: string; body: string; action?: string }> = {
    accepted: {
      title: "No accepted connections yet",
      body: "Discover people in your builder circle and ask your agent to find a warm path.",
      action: "Discover people",
    },
    recommended: {
      title: "Recommendations are still warming up",
      body: "Your agent will surface people here once it has enough grounded context to explain why the connection makes sense.",
      action: "Add sources",
    },
    pending: {
      title: "No pending introductions",
      body: "Approval-gated requests you send or receive will appear here.",
    },
    rejected: {
      title: "No rejected introductions",
      body: "Requests you pass on will be kept here for reference.",
    },
    saved: {
      title: "Nothing saved yet",
      body: "Save a promising profile from Discover to come back to it later.",
      action: "Discover people",
    },
  };
  const item = copy[tab];

  return (
    <div className="empty-state compact-empty">
      <Sparkles size={22} />
      <h3>{item.title}</h3>
      <p>{item.body}</p>
      {item.action && (
        <Link className="ghost small" to={item.action === "Add sources" ? "/me#documents" : "/find"}>
          {item.action}
        </Link>
      )}
    </div>
  );
}

export default function Connections() {
  const [data, setData] = useState<ConnectionsResponse>();
  const [tab, setTab] = useState<ConnectionTab>("accepted");
  const [error, setError] = useState("");
  const { toast } = useToast();

  const load = useCallback(async () => {
    setData(await socialApi.connections());
  }, []);

  useEffect(() => {
    void load().catch((caught) => setError(caught.message));
  }, [load]);

  // Accepting, ignoring and withdrawing all used to reload the list and say nothing, so
  // the only evidence the click landed was a row quietly moving tabs. Each one now
  // reports what it did.
  const run = async (action: () => Promise<unknown>, success?: string) => {
    setError("");
    try {
      await action();
      await load();
      if (success) toast(success, "ok");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Something went wrong";
      setError(message);
      toast(message, "error");
    }
  };

  const accepted = data?.accepted || [];
  const incoming = data?.incoming || [];
  const outgoing = data?.outgoing || [];
  const pendingCount = incoming.length + outgoing.length;

  return (
    <div className="page connections-page">
      <PageHeader
        variant="hero"
        eyebrow={<><Users size={13} /> Your network graph</>}
        title="Connections"
        blurb="See the relationships your agent is helping you build, and keep every introduction inside your control."
        aside={
          <>
            <b>{data ? accepted.length : "—"}</b>
            <span>accepted connections</span>
            <small><Sparkles size={12} /> Approval-gated paths</small>
          </>
        }
      />

      {error && <p className="auth-error" role="alert"><TriangleAlert size={14} /> {error}</p>}

      <nav className="connection-tabs" aria-label="Connection status">
        {TABS.map((item) => (
          <button
            type="button"
            key={item.id}
            className={tab === item.id ? "active" : ""}
            onClick={() => setTab(item.id)}
          >
            {item.label}
            {item.id === "pending" && pendingCount > 0 && <span className="tab-count">{pendingCount}</span>}
          </button>
        ))}
      </nav>

      {/* Until the fetch lands there is nothing to be empty about — showing the empty
          state here claimed "no connections" for data that had not arrived. */}
      {!data && <SkeletonList count={4} lines={1} label="Loading your connections…" />}

      {data && tab === "accepted" && (
        accepted.length > 0 ? (
          <div className="connection-grid">
            {accepted.map((row) => (
              <ConnectionCard
                key={row._id}
                connection={row}
                action={<Link className="connection-message-action" to={`/messages/${row.member?.user_id}`}><MessageCircle size={13} /> Message</Link>}
              />
            ))}
          </div>
        ) : <EmptyConnections tab="accepted" />
      )}

      {data && tab === "pending" && (
        pendingCount > 0 ? (
          <div className="connection-grid">
            {incoming.map((row) => (
              <ConnectionCard
                key={row._id}
                connection={row}
                action={
                  <span className="connection-card-actions">
                    <button type="button" className="icon-button ok" aria-label={`Accept ${row.member?.display_name || "request"}`} onClick={() => run(() => socialApi.respond(row.requester_id, true), `Connected with ${row.member?.display_name || "them"}.`)}><Check size={15} /></button>
                    <button type="button" className="icon-button" aria-label={`Ignore ${row.member?.display_name || "request"}`} onClick={() => run(() => socialApi.respond(row.requester_id, false), "Request ignored.")}><X size={15} /></button>
                  </span>
                }
              />
            ))}
            {outgoing.map((row) => (
              <ConnectionCard
                key={row._id}
                connection={row}
                action={<button type="button" className="link-button" onClick={() => run(() => socialApi.withdraw(row.recipient_id), "Request withdrawn.")}>Withdraw</button>}
              />
            ))}
          </div>
        ) : <EmptyConnections tab="pending" />
      )}

      {data && (tab === "recommended" || tab === "rejected" || tab === "saved") && <EmptyConnections tab={tab} />}

      {tab === "accepted" && data && Object.keys(data.provenance).length > 0 && (
        <section className="panel provenance-panel">
          <span className="consent-label">How your network grows</span>
          <p className="panel-sub">The product surfaces the path behind each connection.</p>
          <ul className="provenance-list">
            {Object.entries(data.provenance)
              .sort((a, b) => b[1] - a[1])
              .map(([source, count]) => (
                <li key={source}><b>{count}</b> {SOURCE_COPY[source] || source}</li>
              ))}
          </ul>
          <Link to="/find" className="ghost small"><Compass size={13} /> Discover people</Link>
        </section>
      )}
    </div>
  );
}
