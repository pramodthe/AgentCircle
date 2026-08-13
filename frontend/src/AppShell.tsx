import {
  Compass,
  Database,
  Home,
  LogOut,
  MessagesSquare,
  Radio,
  ShieldCheck,
  Sparkles,
  UserRound,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { discoveryApi } from "./api";
import { useAuth } from "./auth";
import { Avatar } from "./components/Avatar";
import type { RetrievalHealth } from "./types";

const NAV = [
  { to: "/feed", label: "News Feed", icon: Home, end: true },
  { to: "/find", label: "Discover", icon: Compass },
  { to: "/community", label: "Community", icon: Radio },
  { to: "/messages", label: "Messages", icon: MessagesSquare },
  { to: "/connections", label: "Connections", icon: Users },
  { to: "/me", label: "You", icon: UserRound },
];

/**
 * What is actually running underneath, stated plainly.
 *
 * Every retrieval and model path in this product has a working degraded mode, which
 * means the app looks identical whether it is running on real infrastructure or a
 * local stand-in. Showing the truth in the chrome is the only thing that stops a
 * fallback from quietly passing as the real system.
 */
function StackStatus() {
  const [health, setHealth] = useState<RetrievalHealth>();

  useEffect(() => {
    void discoveryApi.status().then(setHealth).catch(() => undefined);
  }, []);

  if (!health) return null;
  const semantic = health.embeddings.semantic;
  const atlas = health.atlas_vector || health.atlas_text;
  const degraded = !semantic || !atlas;

  const detail = [
    atlas ? "Atlas Search" : "local retrieval",
    semantic ? health.embeddings.model : "hash embeddings",
    health.rerank?.enabled ? health.rerank.model : null,
  ].filter(Boolean).join(" · ");

  return (
    <div className={degraded ? "stack-status warn" : "stack-status"} title={detail}>
      {degraded ? <Database size={13} /> : <ShieldCheck size={13} />}
      <span>{degraded ? "Limited search mode" : "Agent is grounded"}</span>
    </div>
  );
}

export default function AppShell() {
  const { user, profile, signOut } = useAuth();
  const accent = profile?.theme?.accent || "violet";
  const avatar = (
    <Avatar
      name={user?.display_name}
      mediaId={profile?.avatar_media_id}
      accent={accent}
      size="md"
      aiGenerated={profile?.avatar_ai_generated}
    />
  );

  return (
    <div className="shell">
      <aside className="shell-nav">
        <div className="shell-brand-wrap">
          <div className="shell-brand">
            <span><Sparkles size={16} /></span>
            <strong>AgentCircle</strong>
          </div>
          <small>SF Builders</small>
        </div>

        <NavLink to="/me" className={({ isActive }) => (isActive ? "shell-me active" : "shell-me")}>
          {avatar}
          <span>
            <b>{user?.display_name}</b>
            <small>@{user?.handle}</small>
          </span>
        </NavLink>

        <nav aria-label="Primary">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => (isActive ? "active" : "")}
            >
              <Icon size={17} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="shell-foot">
          <div className="agent-online-card">
            <span><Sparkles size={20} /></span>
            <div>
              <b>Your agent is online</b>
              <small>Grounded answers. You approve every connection.</small>
            </div>
          </div>
          <StackStatus />
          <button onClick={signOut} className="shell-signout">
            <LogOut size={14} /> Switch person
          </button>
        </div>
      </aside>

      <section className="shell-workspace">
        <header className="shell-topbar">
          <div className="topbar-actions">
            <Link to="/connections" aria-label="Connections"><Users size={17} /></Link>
            <Link to="/me#documents" aria-label="Agent documents"><Sparkles size={17} /></Link>
            <Link to={`/u/${user?.handle ?? ""}`} className="topbar-avatar" aria-label="View public profile">
              <Avatar
                name={user?.display_name}
                mediaId={profile?.avatar_media_id}
                accent={accent}
                size="sm"
                aiGenerated={profile?.avatar_ai_generated}
              />
            </Link>
          </div>
        </header>
        <main className="shell-main">
          <Outlet />
        </main>
      </section>
    </div>
  );
}

/**
 * The one page heading.
 *
 * There were five of these — a plain header, two dark hero banners (Connections and
 * Discover), a light heading on Messages and another on Feed — and the two heroes were
 * the same design drawn twice under different class names, so they had already drifted
 * apart in padding and eyebrow colour. Three variants cover every real case:
 *
 *   plain   — a title over a body of panels. The default, and what most pages want.
 *   feature — a titled surface with its own toolbar (Feed's filters, Messages' badge).
 *   hero    — the dark photographic banner reserved for the two discovery surfaces.
 *
 * Anything that needs a fourth should be a variant here, not a sixth header.
 */
export function PageHeader({
  icon: Icon,
  title,
  blurb,
  eyebrow,
  action,
  aside,
  variant = "plain",
}: {
  icon?: typeof UserRound;
  title: string;
  blurb?: string;
  /** Small uppercase kicker above the title. */
  eyebrow?: React.ReactNode;
  /** Controls that belong to the page — filters, a primary action. */
  action?: React.ReactNode;
  /** A single stat or badge pinned to the trailing edge. */
  aside?: React.ReactNode;
  variant?: "plain" | "feature" | "hero";
}) {
  if (variant === "plain") {
    return (
      <header className="page-header">
        <div>
          {eyebrow && <span className="page-eyebrow">{eyebrow}</span>}
          <h1>{Icon && <Icon size={19} />} {title}</h1>
          {blurb && <p>{blurb}</p>}
        </div>
        {action}
        {aside}
      </header>
    );
  }

  return (
    <header className={variant === "hero" ? "page-hero" : "page-heading"}>
      <div>
        {eyebrow && <span className="page-eyebrow">{eyebrow}</span>}
        <h1>{variant === "feature" && Icon && <Icon size={19} />} {title}</h1>
        {blurb && <p>{blurb}</p>}
      </div>
      {action}
      {aside && <aside>{aside}</aside>}
    </header>
  );
}
