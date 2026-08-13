import { Camera, ImageOff, Loader2, Trash2, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { mediaApi } from "../api";
import type { MediaStatus, MemberPhoto } from "../types";

/**
 * Photo management, written to make the constraint visible rather than only enforced.
 *
 * A caption is required before the file dialog opens, because the caption is what the
 * photo is matched on and what a searcher is shown as evidence. Asking for it afterwards
 * would make it feel like a formality; asking first makes it the point.
 */
export default function Photos({
  onChanged,
  composer = false,
}: {
  onChanged?: () => void;
  /** Caption + upload only. The profile mosaic is the gallery, so this must not draw a second one. */
  composer?: boolean;
}) {
  const [photos, setPhotos] = useState<MemberPhoto[]>([]);
  const [status, setStatus] = useState<MediaStatus>();
  const [caption, setCaption] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const [rows, health] = await Promise.all([mediaApi.mine(), mediaApi.status()]);
    setPhotos(rows);
    setStatus(health);
  }, []);

  useEffect(() => {
    void load().catch((caught) => setError(caught.message));
  }, [load]);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      await load();
      onChanged?.();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That did not work");
    } finally {
      setBusy(false);
    }
  };

  const ready = caption.trim().length >= 12;

  const body = (
    <>
      {!composer && (
        <>
          <span className="consent-label"><Camera size={12} /> Photos</span>
          <p className="panel-sub">
            Photos are found by what they show you <em>doing</em> — a workshop, a build, a
            talk. Never by how anyone looks.
          </p>
        </>
      )}

      {status && !status.available && (
        <p className="thread-notice">
          <ImageOff size={13} /> Photo search is off right now, so new photos are stored
          but not searchable.
        </p>
      )}
      {error && <p className="auth-error" role="alert"><TriangleAlert size={14} /> {error}</p>}

      <div className="photo-add">
        <input
          value={caption}
          maxLength={300}
          onChange={(event) => setCaption(event.target.value)}
          placeholder="What is happening in the photo? e.g. running a grid-simulation workshop"
        />
        <button
          className="ghost"
          disabled={busy || !ready}
          onClick={() => fileInput.current?.click()}
          title={ready ? "Choose a photo" : "Describe the photo first"}
        >
          {busy ? <Loader2 size={15} className="spin" /> : <Camera size={15} />} Add photo
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              void run(async () => {
                await mediaApi.upload(file, caption);
                setCaption("");
              });
            }
            event.target.value = "";
          }}
        />
      </div>

      {!composer && photos.length > 0 && (
        <ul className="photo-grid">
          {photos.map((photo) => (
            <li key={photo._id}>
              <img src={mediaApi.src(photo._id)} alt={photo.caption} loading="lazy" />
              <div>
                <p>{photo.caption}</p>
                {!photo.indexed && (
                  <small className="photo-unindexed">
                    <ImageOff size={11} /> stored, not searchable
                  </small>
                )}
              </div>
              <button
                className="icon-button"
                disabled={busy}
                onClick={() => run(() => mediaApi.remove(photo._id))}
                aria-label={`Remove photo: ${photo.caption}`}
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {!composer && !photos.length && <p className="source-empty">No photos yet.</p>}
    </>
  );

  if (composer) return <div className="photo-composer">{body}</div>;
  return <section className="panel">{body}</section>;
}
