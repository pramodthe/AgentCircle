import {
  Compass,
  Database,
  LogOut,
  Radio,
  ShieldCheck,
  Sparkles,
  UserRound,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { discoveryApi } from "./api";
import { useAuth } from "./auth";
import { Avatar } from "./components/Avatar";
import type { RetrievalHealth } from "./types";

const NAV = [
  { to: "/find", label: "Find", icon: Compass },
  { to: "/feed", label: "Circle", icon: Users, circle: true },
  { to: "/community", label: "Community", icon: Radio },
  { to: "/me", label: "You", icon: UserRound },
];

const CIRCLE_TABS = [
  { to: "/feed", label: "Updates", end: true },
  { to: "/messages", label: "Messages" },
  { to: "/connections", label: "Connections" },
];

function onCircle(pathname: string) {
  return (
    pathname.startsWith("/feed") ||
    pathname.startsWith("/messages") ||
    pathname.startsWith("/connections")
  );
}

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
      <span>{degraded ? "Limited search" : "Search is live"}</span>
    </div>
  );
}

export function CircleNav() {
  return (
    <nav className="circle-nav" aria-label="Circle">
      {CIRCLE_TABS.map(({ to, label, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) => (isActive ? "active" : "")}
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

export default function AppShell() {
  const { user, profile, signOut } = useAuth();
  const location = useLocation();
  const accent = profile?.theme?.accent || "violet";

  return (
    <div className="shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <aside className="shell-nav">
        <div className="shell-brand-wrap">
          <div className="shell-brand">
            <span><Sparkles size={16} /></span>
            <strong>AgentCircle</strong>
          </div>
        </div>

        <NavLink to="/me" className={({ isActive }) => (isActive ? "shell-me active" : "shell-me")}>
          <Avatar
            name={user?.display_name}
            mediaId={profile?.avatar_media_id}
            accent={accent}
            size="md"
            aiGenerated={profile?.avatar_ai_generated}
          />
          <span>
            <b>{user?.display_name}</b>
            <small>@{user?.handle}</small>
          </span>
        </NavLink>

        <nav aria-label="Primary">
          {NAV.map(({ to, label, icon: Icon, circle }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => {
                const active = circle ? onCircle(location.pathname) : isActive;
                return active ? "active" : "";
              }}
            >
              <Icon size={17} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="shell-foot">
          <StackStatus />
          <button onClick={signOut} className="shell-signout">
            <LogOut size={14} /> Sign out
          </button>
        </div>
      </aside>

      <section className="shell-workspace">
        <main id="main" className="shell-main">
          <Outlet />
        </main>
      </section>
    </div>
  );
}

/**
 * The one page heading.
 *
 *   plain   — a title over a body of panels. The default.
 *   feature — a titled surface with its own toolbar.
 *   hero    — reserved; styled as solid ink, never a stock photograph.
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
  eyebrow?: React.ReactNode;
  action?: React.ReactNode;
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
