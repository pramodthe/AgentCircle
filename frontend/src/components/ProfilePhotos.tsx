import { Loader2, Sparkles, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { profileMediaApi } from "../api";
import { Avatar } from "./Avatar";
import type { UserProfile } from "../types";

/**
 * Avatar and cover upload.
 *
 * Deliberately says what this does *not* buy. Every other field in this editor is
 * declared context that gets embedded and makes you findable, and the editor tells
 * members so. An image is the exception: it is presentation, like `theme`, and it
 * changes nothing about who finds you. Saying that here keeps the editor's central
 * promise true rather than leaving members to infer that a better photo ranks better.
 */
export function ProfilePhotos({
  profile,
  onChange,
}: {
  profile: UserProfile;
  onChange: () => Promise<void> | void;
}) {
  const [busy, setBusy] = useState<"" | "avatar" | "cover">("");
  const [error, setError] = useState("");
  const [aiGenerated, setAiGenerated] = useState(false);
  const avatarInput = useRef<HTMLInputElement>(null);
  const coverInput = useRef<HTMLInputElement>(null);

  const upload = async (file: File | undefined, kind: "avatar" | "cover") => {
    if (!file) return;
    setBusy(kind);
    setError("");
    try {
      await profileMediaApi.upload(file, kind, aiGenerated);
      await onChange();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed");
    } finally {
      setBusy("");
    }
  };

  const remove = async (kind: "avatar" | "cover") => {
    setBusy(kind);
    setError("");
    try {
      await profileMediaApi.remove(kind);
      await onChange();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not remove that");
    } finally {
      setBusy("");
    }
  };

  return (
    <section className="panel profile-photos">
      <span className="consent-label">Your photos</span>
      <p className="panel-note">
        Presentation only. Unlike everything else on this page, an image is never
        embedded and never affects who finds you.
      </p>

      <div className="photo-slots">
        <div className="photo-slot">
          <Avatar
            name={profile.display_name}
            mediaId={profile.avatar_media_id}
            accent={profile.theme?.accent}
            size="lg"
            aiGenerated={profile.avatar_ai_generated}
          />
          <div>
            <b>Profile photo</b>
            <small>Shown on your posts, matches, and profile.</small>
            <span className="photo-slot-actions">
              <button
                type="button"
                className="ghost small"
                disabled={busy === "avatar"}
                onClick={() => avatarInput.current?.click()}
              >
                {busy === "avatar" ? <Loader2 size={13} className="spin" /> : <Upload size={13} />}
                {profile.avatar_media_id ? " Replace" : " Upload"}
              </button>
              {profile.avatar_media_id && (
                <button
                  type="button"
                  className="link-button"
                  disabled={busy === "avatar"}
                  onClick={() => void remove("avatar")}
                >
                  <Trash2 size={12} /> Remove
                </button>
              )}
            </span>
          </div>
        </div>

        <div className="photo-slot">
          <span className="cover-preview">
            {profile.cover_media_id ? (
              <img src={profileMediaApi.src(profile.cover_media_id)} alt="" />
            ) : (
              <em>No cover yet</em>
            )}
          </span>
          <div>
            <b>Cover image</b>
            <small>The banner behind your card in search and stories.</small>
            <span className="photo-slot-actions">
              <button
                type="button"
                className="ghost small"
                disabled={busy === "cover"}
                onClick={() => coverInput.current?.click()}
              >
                {busy === "cover" ? <Loader2 size={13} className="spin" /> : <Upload size={13} />}
                {profile.cover_media_id ? " Replace" : " Upload"}
              </button>
              {profile.cover_media_id && (
                <button
                  type="button"
                  className="link-button"
                  disabled={busy === "cover"}
                  onClick={() => void remove("cover")}
                >
                  <Trash2 size={12} /> Remove
                </button>
              )}
            </span>
          </div>
        </div>
      </div>

      {/* An AI portrait is allowed — plenty of people prefer one. What is not allowed
          is presenting it as a photograph without saying so, which is the same
          fabricated visual claim as a stock photo of a stranger. */}
      <label className="ai-flag">
        <input
          type="checkbox"
          checked={aiGenerated}
          onChange={(event) => setAiGenerated(event.target.checked)}
        />
        <span>
          <Sparkles size={13} /> This is an AI-generated image
          <small>Adds a small "AI" mark so nobody reads it as a photograph.</small>
        </span>
      </label>

      {error && <p className="auth-error" role="alert">{error}</p>}

      <input
        ref={avatarInput}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        hidden
        onChange={(event) => void upload(event.target.files?.[0], "avatar")}
      />
      <input
        ref={coverInput}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        hidden
        onChange={(event) => void upload(event.target.files?.[0], "cover")}
      />
    </section>
  );
}
