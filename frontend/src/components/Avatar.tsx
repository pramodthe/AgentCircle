import { profileMediaApi } from "../api";

/**
 * A member's face, or their initials — never a stand-in for a person.
 *
 * This exists because the previous design rendered hard-coded stock photographs as
 * member identity: a story card labelled "Kenji" showed a photograph of a stranger,
 * and search results carried pictures of unrelated people as their covers. On a
 * product whose claim is that what you see about someone is grounded in what they
 * supplied, an unrelated photograph presented as a person is a fabricated visual
 * claim — the visual equivalent of an uncited answer.
 *
 * So there are exactly two states: the member's own image, or initials. There is no
 * decorative third option, because a decorative third option is what went wrong.
 */
export function Avatar({
  name,
  mediaId,
  accent = "violet",
  size = "md",
  aiGenerated = false,
}: {
  name?: string | null;
  mediaId?: string | null;
  accent?: string;
  size?: "sm" | "md" | "lg";
  aiGenerated?: boolean;
}) {
  const initials = (name || "?")
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  if (!mediaId) {
    return (
      <span className={`avatar avatar-${size} tone-${accent}`} aria-hidden="true">
        {initials}
      </span>
    );
  }

  return (
    <span className={`avatar avatar-${size} avatar-photo`}>
      <img src={profileMediaApi.src(mediaId)} alt={name ? `${name}` : "Member"} loading="lazy" />
      {/* Labelled, not forbidden. A member may choose a generated portrait; presenting
          one as a photograph without saying so is the failure this component exists
          to prevent. */}
      {aiGenerated && <i className="avatar-ai" title="AI-generated image">AI</i>}
    </span>
  );
}
