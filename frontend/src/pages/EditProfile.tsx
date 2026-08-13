import { Check, Eye, Loader2, Palette, TriangleAlert, UserRound, X } from "lucide-react";
import { useCallback, useEffect, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { profileApi } from "../api";
import { PageHeader } from "../AppShell";
import { ProfilePhotos } from "../components/ProfilePhotos";
import { useAuth } from "../auth";
import type { UserProfile } from "../types";

/**
 * Theme is presentation only.
 *
 * The agent layer never reads `profiles.theme` — restyling a page must not change who
 * gets found, or customization becomes an SEO surface. Everything on this screen is
 * either something the member says about themselves (which *is* retrieval input) or
 * something purely visual. Keep that line where it is.
 */
const ACCENTS = ["violet", "coral", "blue", "teal", "gold", "green"] as const;

const LAYOUTS = [
  { id: "classic", label: "Classic", blurb: "Clean and current" },
  { id: "retro", label: "Retro", blurb: "Monospace, double border, stripes" },
] as const;

const FONTS = [
  { id: "", label: "Default" },
  { id: '"Courier New", monospace', label: "Typewriter" },
  { id: "Georgia, serif", label: "Serif" },
  { id: '"Comic Sans MS", cursive', label: "Unserious" },
] as const;

const BACKGROUNDS = [
  { id: "", label: "None" },
  { id: "linear-gradient(120deg,#fde7f3,#e6f0ff)", label: "Soft" },
  { id: "linear-gradient(120deg,#0d1114,#2b1f4a)", label: "Midnight" },
  { id: "repeating-linear-gradient(45deg,#fff 0 14px,#f3ecff 14px 28px)", label: "Stripes" },
] as const;

function ChipField({
  label,
  values,
  onChange,
  placeholder,
}: {
  label: string;
  values: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
}) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    const value = draft.trim();
    if (value && !values.some((item) => item.toLowerCase() === value.toLowerCase())) {
      onChange([...values, value.slice(0, 80)]);
    }
    setDraft("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commit();
    } else if (event.key === "Backspace" && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  };

  return (
    <div className="chip-field">
      <span className="chip-label">{label}</span>
      <div className="chip-box">
        {values.map((value) => (
          <span className="chip" key={value}>
            {value}
            <button type="button" onClick={() => onChange(values.filter((v) => v !== value))}
              aria-label={`Remove ${value}`}>
              <X size={12} />
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          onBlur={commit}
          placeholder={values.length ? "" : placeholder}
        />
      </div>
    </div>
  );
}

type EditProfileProps = {
  embedded?: boolean;
  onClose?: () => void;
  onSaved?: () => void | Promise<void>;
};

export default function EditProfile({
  embedded = false,
  onClose,
  onSaved,
}: EditProfileProps = {}) {
  const { user, refresh } = useAuth();
  const [profile, setProfile] = useState<UserProfile>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<"" | "yes" | "unindexed">("");

  const load = useCallback(async () => {
    setProfile(await profileApi.get());
  }, []);

  useEffect(() => {
    void load().catch((caught) => setError(caught.message));
  }, [load]);

  const set = <K extends keyof UserProfile>(key: K, value: UserProfile[K]) =>
    setProfile((current) => (current ? { ...current, [key]: value } : current));

  const setTheme = (patch: Record<string, string>) =>
    setProfile((current) =>
      current ? { ...current, theme: { ...current.theme, ...patch } } : current,
    );

  const save = async () => {
    if (!profile) return;
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const next = await profileApi.update({
        display_name: profile.display_name,
        headline: profile.headline,
        bio: profile.bio,
        location: profile.location,
        role: profile.role,
        organization: profile.organization,
        skills: profile.skills,
        interests: profile.interests,
        looking_for: profile.looking_for,
        hobbies: profile.hobbies,
        theme: profile.theme as Record<string, string>,
      });
      setProfile(next);
      await refresh();
      setSaved(next.retrieval_synced === false ? "unindexed" : "yes");
      void onSaved?.();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!embedded) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [embedded, onClose]);

  const frame = (content: ReactNode) =>
    embedded ? (
      <div
        className="profile-edit-modal-backdrop"
        role="presentation"
        onMouseDown={(event) => event.target === event.currentTarget && onClose?.()}
      >
        <section
          className="profile-edit-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="profile-edit-title"
        >
          {content}
        </section>
      </div>
    ) : (
      <>{content}</>
    );

  if (!profile) {
    return frame(
      <>
        {embedded && (
          <EditProfileHeader embedded onClose={onClose} />
        )}
        {error ? (
          <p className="auth-error"><TriangleAlert size={14} /> {error}</p>
        ) : (
          <p className="thread-loading">Loading…</p>
        )}
      </>,
    );
  }

  const theme = (profile.theme || {}) as Record<string, string>;
  const accent = theme.accent || "violet";

  return frame(
    <>
      {embedded ? (
        <EditProfileHeader embedded onClose={onClose} />
      ) : (
        <PageHeader
          icon={UserRound}
          title="Edit profile"
          blurb="What people see, and what your agent treats as things you said about yourself."
          action={
            user?.handle ? (
              <Link to="/me" className="ghost small"><Eye size={13} /> View page</Link>
            ) : undefined
          }
        />
      )}

      {error && <p className="auth-error" role="alert"><TriangleAlert size={14} /> {error}</p>}

      <ProfilePhotos profile={profile} onChange={load} />

      <section className="panel">
        <span className="consent-label">About you</span>
        <label className="field">
          <span>Name</span>
          <input value={profile.display_name || ""} maxLength={80}
            onChange={(e) => set("display_name", e.target.value)} />
        </label>
        <label className="field">
          <span>Headline</span>
          <input value={profile.headline || ""} maxLength={160}
            placeholder="Founder building onboarding analytics for B2B SaaS"
            onChange={(e) => set("headline", e.target.value)} />
        </label>
        <label className="field">
          <span>About</span>
          <textarea value={profile.bio || ""} rows={4} maxLength={2000}
            onChange={(e) => set("bio", e.target.value)} />
        </label>
        <div className="field-row">
          <label className="field">
            <span>Location</span>
            <input value={profile.location || ""} maxLength={120}
              onChange={(e) => set("location", e.target.value)} />
          </label>
          <label className="field">
            <span>Role</span>
            <input value={profile.role || ""} maxLength={120}
              onChange={(e) => set("role", e.target.value)} />
          </label>
          <label className="field">
            <span>Organization</span>
            <input value={profile.organization || ""} maxLength={120}
              onChange={(e) => set("organization", e.target.value)} />
          </label>
        </div>
      </section>

      <section className="panel">
        <span className="consent-label">What you do and want</span>
        <p className="panel-sub">
          Unlike the theme below, these feed retrieval — they are things you said about
          yourself, so your agent can be found for them.
        </p>
        <ChipField label="Skills" values={profile.skills || []}
          onChange={(v) => set("skills", v)} placeholder="distributed systems, typography…" />
        <ChipField label="Interests" values={profile.interests || []}
          onChange={(v) => set("interests", v)} placeholder="climate tech, developer tools…" />
        <ChipField label="Looking for" values={profile.looking_for || []}
          onChange={(v) => set("looking_for", v)} placeholder="design partners, a technical cofounder…" />
        <ChipField label="Outside work" values={profile.hobbies || []}
          onChange={(v) => set("hobbies", v)} placeholder="climbing, ceramics…" />
      </section>

      <section className="panel">
        <span className="consent-label"><Palette size={12} /> Make it yours</span>
        <p className="panel-sub">
          Purely how your page looks. Your agent never reads any of this, so styling your
          page can't change who finds you.
        </p>

        <div className="theme-field">
          <span className="chip-label">Accent</span>
          <div className="swatch-row">
            {ACCENTS.map((value) => (
              <button
                key={value}
                className={`swatch tone-${value} ${accent === value ? "on" : ""}`}
                type="button"
                onClick={() => setTheme({ accent: value })}
                aria-label={value}
                title={value}
              >
                {accent === value && <Check size={13} />}
              </button>
            ))}
          </div>
        </div>

        <div className="theme-field">
          <span className="chip-label">Layout</span>
          <div className="topic-grid">
            {LAYOUTS.map((option) => (
              <button
                key={option.id}
                className={(theme.layout || "classic") === option.id ? "topic-chip on" : "topic-chip"}
                type="button"
                onClick={() => setTheme({ layout: option.id })}
                title={option.blurb}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="theme-field">
          <span className="chip-label">Background</span>
          <div className="topic-grid">
            {BACKGROUNDS.map((option) => (
              <button
                key={option.label}
                className={(theme.background || "") === option.id ? "topic-chip on" : "topic-chip"}
                type="button"
                onClick={() => setTheme({ background: option.id })}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="theme-field">
          <span className="chip-label">Font</span>
          <div className="topic-grid">
            {FONTS.map((option) => (
              <button
                key={option.label}
                className={(theme.font || "") === option.id ? "topic-chip on" : "topic-chip"}
                type="button"
                onClick={() => setTheme({ font: option.id })}
                style={option.id ? { fontFamily: option.id } : undefined}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <label className="field">
          <span>Song link</span>
          <input value={theme.song_url || ""} maxLength={300}
            placeholder="https://…  (every good profile page had one)"
            onChange={(e) => setTheme({ song_url: e.target.value })} />
        </label>

        {/*
          Structured exactly like PublicProfile — backdrop behind, white card on top.
          A preview that paints the background under the text would show a dark theme as
          unreadable when the real page is fine, and a preview that can lie is worse than
          no preview.
        */}
        <div className="theme-preview-shell" style={{ background: theme.background || undefined }}>
          <div
            className={`theme-preview layout-${theme.layout || "classic"} tone-${accent}`}
            style={{ fontFamily: theme.font || undefined }}
          >
            <div className="profile-banner" />
            <strong>{profile.display_name || user?.display_name}</strong>
            <small>@{user?.handle}</small>
            {profile.headline && <p>{profile.headline}</p>}
          </div>
        </div>
      </section>

      <div className="panel-actions">
        {saved === "yes" && <span className="saved-pip"><Check size={13} /> Saved</span>}
        {/* Saving and being findable are different things, so they get different words. */}
        {saved === "unindexed" && (
          <span className="saved-pip warn">
            <TriangleAlert size={13} /> Saved, but not searchable yet — retry shortly
          </span>
        )}
        <button className="primary" onClick={save} disabled={busy}>
          {busy ? <Loader2 size={15} className="spin" /> : <Check size={15} />} Save profile
        </button>
      </div>
    </>,
  );
}

function EditProfileHeader({
  embedded,
  onClose,
}: {
  embedded: boolean;
  onClose?: () => void;
}) {
  if (!embedded) return null;
  return (
    <header className="profile-edit-modal-head">
      <div>
        <span className="consent-label">Edit profile</span>
        <h2 id="profile-edit-title">Make your profile feel like you</h2>
        <p>Changes appear on your profile as soon as you save.</p>
      </div>
      <button
        type="button"
        className="profile-edit-close"
        onClick={onClose}
        aria-label="Close edit profile"
      >
        <X size={18} />
      </button>
    </header>
  );
}
