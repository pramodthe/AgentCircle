import {
  Briefcase,
  CalendarDays,
  Edit3,
  ExternalLink,
  Eye,
  Image as ImageIcon,
  Link as LinkIcon,
  MapPin,
  MessageCircle,
  Pencil,
  ShieldCheck,
  Sparkles,
  Trash2,
  UserPlus,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Avatar } from "./Avatar";
import { mediaApi, profileMediaApi } from "../api";
import type {
  MemberPhoto,
  Persona,
  PersonaItemRef,
  PublicProfile as PublicProfileData,
  SocialConnection,
} from "../types";

type Claim = { value: string; source?: string };

/** One row per value. Grounded citations win; declared fields fill gaps. Never both copies. */
function mergeClaims(
  grounded: PersonaItemRef[] | string[] | undefined,
  declared: string[] | undefined,
): Claim[] {
  const map = new Map<string, Claim>();
  for (const value of declared || []) {
    const trimmed = value.trim();
    if (trimmed) map.set(trimmed.toLowerCase(), { value: trimmed });
  }
  for (const item of grounded || []) {
    if (typeof item === "string") {
      const trimmed = item.trim();
      if (trimmed && !map.has(trimmed.toLowerCase())) {
        map.set(trimmed.toLowerCase(), { value: trimmed });
      }
      continue;
    }
    const trimmed = item.value.trim();
    if (!trimmed) continue;
    map.set(trimmed.toLowerCase(), { value: trimmed, source: item.source_title });
  }
  return [...map.values()];
}

export function ProfileView({
  data,
  photos,
  isMe,
  owner = false,
  persona,
  documents,
  permissions,
  memory,
  photoComposer,
  connection,
  busy = false,
  notice,
  error,
  onConnect,
  onEdit,
  onRemovePhoto,
}: {
  data: PublicProfileData;
  photos: MemberPhoto[];
  isMe: boolean;
  owner?: boolean;
  persona?: Persona | null;
  documents?: ReactNode;
  permissions?: ReactNode;
  memory?: ReactNode;
  photoComposer?: ReactNode;
  connection?: SocialConnection | { status: "none" };
  busy?: boolean;
  notice?: string;
  error?: string;
  onConnect?: () => void;
  onEdit?: () => void;
  onRemovePhoto?: (id: string) => void;
}) {
  const profile = data.profile;
  const theme = profile?.theme || {};
  const accent = theme.accent || "violet";
  const joined = data.user.created_at
    ? new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(new Date(data.user.created_at))
    : "Recently";

  const headline = profile?.headline || persona?.headline || data.persona.headline;
  const about = (profile?.bio || "").trim() || (persona?.summary || data.persona.summary || "").trim();
  const skills = mergeClaims(persona?.skills ?? data.persona.skills, profile?.skills);
  const interests = mergeClaims(persona?.interests ?? data.persona.interests, profile?.interests);
  const lookingFor = mergeClaims(persona?.looking_for ?? data.persona.looking_for, profile?.looking_for);
  const hobbies = (profile?.hobbies || []).filter(Boolean);
  const highlights = persona?.notable || [];
  const coverage = persona?.coverage;

  const roleLine = [profile?.role, profile?.organization].filter(Boolean).join(" at ");
  const edit = onEdit ? (
    <button type="button" className="profile-section-edit" onClick={onEdit} aria-label="Edit profile">
      <Pencil size={14} />
    </button>
  ) : isMe ? (
    <Link to="/me?edit=1" className="profile-section-edit" aria-label="Edit profile"><Pencil size={14} /></Link>
  ) : null;

  return (
    <div className="profile-linkedin">
      <section className="profile-linkedin-hero">
        <div className={`profile-linkedin-cover tone-${accent}`}>
          {profile?.cover_media_id && <img src={profileMediaApi.src(profile.cover_media_id)} alt="" />}
          {isMe && (onEdit ? (
            <button type="button" onClick={onEdit} className="profile-cover-edit"><Pencil size={13} /> Edit cover</button>
          ) : (
            <Link to="/me?edit=1" className="profile-cover-edit"><Pencil size={13} /> Edit cover</Link>
          ))}
        </div>

        <div className="profile-linkedin-identity">
          <Avatar
            name={data.user.display_name}
            mediaId={profile?.avatar_media_id}
            accent={accent}
            size="lg"
            aiGenerated={profile?.avatar_ai_generated}
          />
          <div className="profile-linkedin-copy">
            <h1>{data.user.display_name}</h1>
            {headline && <p className="profile-linkedin-headline">{headline}</p>}
            <p className="profile-linkedin-meta">
              {roleLine && <span><Briefcase size={13} /> {roleLine}</span>}
              {profile?.location && <span><MapPin size={13} /> {profile.location}</span>}
              <span><CalendarDays size={13} /> Joined {joined}</span>
              {profile?.website && (
                <a href={profile.website} target="_blank" rel="noreferrer"><LinkIcon size={13} /> {profile.website.replace(/^https?:\/\//, "")}</a>
              )}
            </p>
            <p className="profile-linkedin-handle">@{data.user.handle}</p>
          </div>
          <div className="profile-linkedin-actions">
            {isMe && owner ? (
              <>
                <button type="button" className="profile-action-primary" onClick={onEdit}>
                  <Edit3 size={14} /> Edit profile
                </button>
                <Link className="profile-action-secondary" to={`/u/${data.user.handle}`}>
                  <Eye size={14} /> Public view
                </Link>
              </>
            ) : isMe ? (
              <Link className="profile-action-primary" to="/me">
                <Sparkles size={14} /> Edit your profile
              </Link>
            ) : connection?.status === "accepted" ? (
              <Link className="profile-action-primary" to={`/messages/${data.user._id}`}>
                <MessageCircle size={14} /> Message
              </Link>
            ) : (
              <button className="profile-action-primary" onClick={onConnect} disabled={busy || connection?.status === "pending"}>
                <UserPlus size={14} /> {connection?.status === "pending" ? "Request pending" : "Connect"}
              </button>
            )}
          </div>
        </div>
      </section>

      {notice && <p className="thread-notice profile-notice">{notice}</p>}
      {error && <p className="auth-error profile-notice">{error}</p>}

      <div className="profile-linkedin-grid">
        <div className="profile-stack">
          {(about || owner) && (
            <section className="profile-surface" id="about">
              <header className="profile-surface-heading">
                <span>About</span>
                <div className="profile-surface-tools">
                  {owner && <small>Your words — the agent reads this</small>}
                  {edit}
                </div>
              </header>
              {about ? (
                <p className="profile-about-copy">{about}</p>
              ) : (
                <EmptyAdd onEdit={onEdit} label="Add an about" body="A short intro is one of the sources your agent answers from." />
              )}
            </section>
          )}

          {highlights.length > 0 && (
            <section className="profile-surface">
              <header className="profile-surface-heading">
                <span>Highlights</span>
                <small>From your documents</small>
              </header>
              <ul className="profile-highlight-list">
                {highlights.map((item) => (
                  <li key={item.value}>
                    <b>{item.value}</b>
                    {item.source_title && <small>{item.source_title}</small>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {(skills.length || owner) && (
            <ClaimSection
              id="skills"
              title="Skills"
              hint={owner ? "Each one is searchable" : undefined}
              claims={skills}
              edit={edit}
              empty={owner ? <EmptyAdd onEdit={onEdit} label="Add skills" body="These are what people find you for." /> : null}
            />
          )}

          {(lookingFor.length || interests.length || hobbies.length || owner) && (
            <section className="profile-surface" id="interests">
              <header className="profile-surface-heading">
                <span>Interests & looking for</span>
                {edit}
              </header>
              {lookingFor.length > 0 && <ClaimGroup label="Looking for" claims={lookingFor} />}
              {interests.length > 0 && <ClaimGroup label="Interests" claims={interests} />}
              {hobbies.length > 0 && (
                <ClaimGroup label="Outside work" claims={hobbies.map((value) => ({ value }))} />
              )}
              {!lookingFor.length && !interests.length && !hobbies.length && (
                <EmptyAdd onEdit={onEdit} label="Add interests" body="What you care about, and what you want next." />
              )}
            </section>
          )}

          {(photos.length || owner) && (
            <section className="profile-surface" id="photos">
              <header className="profile-surface-heading">
                <span><ImageIcon size={16} /> Photos</span>
                <small>{owner ? "Matched by caption, never by appearance" : `${photos.length} shared`}</small>
              </header>
              {photos.length ? (
                <div className="profile-photo-mosaic">
                  {photos.map((photo) => (
                    <figure key={photo._id}>
                      <img src={mediaApi.src(photo._id)} alt={photo.caption} />
                      <figcaption>
                        <span>{photo.caption}</span>
                        {owner && onRemovePhoto && (
                          <button type="button" className="icon-button" onClick={() => onRemovePhoto(photo._id)} aria-label={`Remove ${photo.caption}`}>
                            <Trash2 size={13} />
                          </button>
                        )}
                      </figcaption>
                    </figure>
                  ))}
                </div>
              ) : (
                <p className="profile-about-copy muted">No photos yet.</p>
              )}
              {owner && photoComposer}
            </section>
          )}

          {owner && documents}
          {owner && memory}
          {owner && permissions}
        </div>

        <aside className="profile-rail">
          <section className="profile-surface profile-agent-card">
            <span className="profile-agent-icon"><ShieldCheck size={18} /></span>
            <div>
              <b>{owner ? "Your agent" : "Grounded profile"}</b>
              <small>{owner ? "One page of context" : "Evidence-backed"}</small>
            </div>
            {owner && coverage ? (
              <div className="coverage">
                <div className="coverage-bar">
                  <span style={{ width: `${Math.round(coverage.score * 100)}%` }} />
                </div>
                <p>
                  {coverage.missing.length
                    ? `Still thin on ${coverage.missing.join(", ")}. Add it on this page — the agent will not guess.`
                    : "Covered across the areas we check."}
                </p>
              </div>
            ) : (
              <p>
                {isMe && !owner
                  ? "This is the public page. Edit the real profile to change what your agent knows."
                  : "This profile is based on what this member chose to share."}
              </p>
            )}
            {owner ? (
              <a href="#documents">Documents and sources <ExternalLink size={12} /></a>
            ) : isMe ? (
              <Link to="/me">Edit your profile <ExternalLink size={12} /></Link>
            ) : (
              <Link to="/find">Find people like this <ExternalLink size={12} /></Link>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}

function ClaimSection({
  id,
  title,
  hint,
  claims,
  edit,
  empty,
}: {
  id: string;
  title: string;
  hint?: string;
  claims: Claim[];
  edit: ReactNode;
  empty: ReactNode;
}) {
  return (
    <section className="profile-surface" id={id}>
      <header className="profile-surface-heading">
        <span>{title}</span>
        <div className="profile-surface-tools">
          {hint && <small>{hint}</small>}
          {edit}
        </div>
      </header>
      {claims.length ? <ClaimList claims={claims} /> : empty}
    </section>
  );
}

function ClaimGroup({ label, claims }: { label: string; claims: Claim[] }) {
  return (
    <div className="profile-claim-group">
      <span className="persona-group-label">{label}</span>
      <ClaimList claims={claims} />
    </div>
  );
}

function ClaimList({ claims }: { claims: Claim[] }) {
  return (
    <div className="profile-tag-list">
      {claims.map((claim) => (
        <span className={claim.source ? "profile-tag cited" : "profile-tag"} key={claim.value}>
          {claim.value}
          {claim.source && <small>{claim.source}</small>}
        </span>
      ))}
    </div>
  );
}

function EmptyAdd({
  onEdit,
  label,
  body,
}: {
  onEdit?: () => void;
  label: string;
  body: string;
}) {
  return (
    <div className="profile-empty-add">
      <p className="profile-about-copy muted">{body}</p>
      {onEdit && (
        <button type="button" className="ghost small" onClick={onEdit}>
          <Pencil size={13} /> {label}
        </button>
      )}
    </div>
  );
}
