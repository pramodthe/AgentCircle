/**
 * Placeholders that hold the shape of what is loading.
 *
 * Every list in this product used to render nothing until its fetch resolved, so the
 * page arrived in one jump and the layout moved under whatever the reader was already
 * looking at. A skeleton occupies the space the real content will take, which keeps
 * the jump from happening and — unlike a spinner — says what is coming.
 */

export function SkeletonText({ width = "medium" }: { width?: "short" | "medium" | "full" }) {
  return <div className={`skeleton skeleton-text ${width === "full" ? "" : width}`} />;
}

/** A card standing in for one feed post, connection, or search result. */
export function SkeletonCard({ lines = 2, media = false }: { lines?: number; media?: boolean }) {
  return (
    <div className="skeleton-card" aria-hidden="true">
      <header>
        <div className="skeleton skeleton-avatar" />
        <div>
          <SkeletonText width="short" />
          <SkeletonText width="medium" />
        </div>
      </header>
      {Array.from({ length: lines }, (_, index) => (
        <SkeletonText key={index} width={index === lines - 1 ? "medium" : "full"} />
      ))}
      {media && <div className="skeleton skeleton-block" />}
    </div>
  );
}

/**
 * `label` is what actually reaches a screen reader: the visual skeleton is decorative,
 * so it is hidden from the tree and this single polite message stands in for it.
 */
export function SkeletonList({
  count = 3,
  lines = 2,
  media = false,
  label = "Loading…",
}: {
  count?: number;
  lines?: number;
  media?: boolean;
  label?: string;
}) {
  return (
    <div className="skeleton-list" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: count }, (_, index) => (
        <SkeletonCard key={index} lines={lines} media={media} />
      ))}
    </div>
  );
}
