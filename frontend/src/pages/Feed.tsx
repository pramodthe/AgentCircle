import {
  ChevronRight,
  Heart,
  Image,
  MapPin,
  MessageCircle,
  Plus,
  Send,
  Sparkles,
  Video,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { socialApi } from "../api";
import { CircleNav, PageHeader } from "../AppShell";
import { useAuth } from "../auth";
import { Avatar } from "../components/Avatar";
import { SkeletonList } from "../components/Skeleton";
import { useToast } from "../components/Toast";
import type { FeedPost, FeedResponse, SocialPerson } from "../types";
type ComposerAttachment = {
  id: string;
  mediaType: string;
  kind: "post" | "clip";
  previewUrl: string;
};

function initials(person?: SocialPerson | null | { display_name?: string }) {
  return (person?.display_name || "?")
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function relativeTime(value: string) {
  const elapsed = Math.max(0, Date.now() - new Date(value).getTime());
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function headlineFor(person?: SocialPerson | null) {
  return person?.headline || "Builder";
}

function StoryViewer({ post, onClose }: { post: FeedPost; onClose: () => void }) {
  const person = post.author;
  const image = post.image_media_id ? socialApi.storySrc(post.image_media_id) : null;
  return (
    <div
      className="story-viewer-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Story"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <article className={`story-viewer ${image ? "has-image" : ""} tone-${person?.accent || "violet"}`}>
        <header>
          <Avatar
            name={person?.display_name}
            mediaId={person?.avatar_media_id}
            accent={person?.accent || "violet"}
            size="md"
            aiGenerated={person?.avatar_ai_generated}
          />
          <span>
            <b>{person?.display_name || "Member"}</b>
            <small>{relativeTime(post.created_at)} ago</small>
          </span>
          <button autoFocus onClick={onClose} aria-label="Close story"><X size={19} /></button>
        </header>
        {image ? (
          <div className="story-viewer-media">
            <img src={image} alt="" />
            {post.body && post.body !== "Shared a story" && <p>{post.body}</p>}
          </div>
        ) : (
          <div className="story-viewer-copy">
            <Sparkles size={22} />
            <p>{post.body}</p>
          </div>
        )}
        {person?.handle && <Link to={`/u/${person.handle}`}>View {person.display_name.split(" ")[0]}'s profile</Link>}
      </article>
    </div>
  );
}

function PostCard({
  post,
  myInitials,
  accent,
  localComments,
  commenting,
  commentDraft,
  liked,
  onToggleLike,
  onToggleComment,
  onCommentChange,
  onAddComment,
  onShare,
}: {
  post: FeedPost;
  liked: boolean;
  myInitials: string;
  accent: string;
  localComments: string[];
  commenting: boolean;
  commentDraft: string;
  onToggleLike: () => void;
  onToggleComment: () => void;
  onCommentChange: (value: string) => void;
  onAddComment: () => void;
  onShare: () => void;
}) {
  const person = post.author;
  const likeCount = (post.reaction_counts.like || 0);
  const commentCount = localComments.length;
  const mediaUrl = post.image_media_id ? socialApi.mediaSrc(post.image_media_id) : null;
  const isVideo = Boolean(post.image_media_type?.startsWith("video/"));

  return (
    <article className={post.kind === "agent" ? "feed-post agent" : "feed-post"}>
      <header>
        <Avatar
          name={person?.display_name}
          mediaId={person?.avatar_media_id}
          accent={person?.accent || "violet"}
          size="md"
          aiGenerated={person?.avatar_ai_generated}
        />
        <div>
          <b>
            {person?.handle ? <Link to={`/u/${person.handle}`}>{person.display_name}</Link> : "Member"}
            {post.kind === "agent" && <em> · agent</em>}
          </b>
          <small>
            {headlineFor(person)} · {relativeTime(post.created_at)}
            {post.location ? ` · ${post.location}` : ""}
            {post.from_connection ? " · connection" : ""}
          </small>
        </div>
      </header>

      {post.kind === "agent" && post.body.includes(".") ? (
        <>
          <h3>{post.body.split(/[.!?]/)[0].trim()}.</h3>
          <p>{post.body}</p>
        </>
      ) : (
        <p>{post.body}</p>
      )}

      {mediaUrl && (
        <div className={`post-media ${isVideo ? "is-video" : ""}`}>
          {isVideo ? (
            <video src={mediaUrl} controls playsInline preload="metadata" />
          ) : (
            <img src={mediaUrl} alt="" loading="lazy" />
          )}
        </div>
      )}

      <footer>
        <span>{likeCount} like{likeCount === 1 ? "" : "s"}</span>
        <button
          type="button"
          className={liked ? "selected" : ""}
          aria-pressed={liked}
          onClick={onToggleLike}
        >
          <Heart size={15} fill={liked ? "currentColor" : "none"} /> Like
        </button>
        <button type="button" onClick={onToggleComment}>
          <MessageCircle size={15} />
          {commentCount === 1 ? "1 comment" : `${commentCount} comments`}
        </button>
        <button type="button" onClick={onShare}>
          <Send size={15} /> Share
        </button>
        <Link className="feed-find-link" to="/find">
          Find people <ChevronRight size={14} />
        </Link>
      </footer>

      {localComments.map((item, index) => (
        <p className="local-comment" key={`${post._id}-${index}`}>
          <b>You</b>
          {item}
          <small>Not saved</small>
        </p>
      ))}

      {commenting && (
        <form
          className="comment-box"
          onSubmit={(event) => {
            event.preventDefault();
            onAddComment();
          }}
        >
          <span className={`avatar avatar-sm tone-${accent}`}>{myInitials}</span>
          <input
            autoFocus
            aria-label="Write a comment"
            placeholder="Write a comment — saved only on this device"
            value={commentDraft}
            onChange={(event) => onCommentChange(event.target.value)}
          />
          <button type="submit" disabled={!commentDraft.trim()} aria-label="Post comment">
            <Send size={15} />
          </button>
        </form>
      )}
    </article>
  );
}

export default function Feed() {
  const { user, profile } = useAuth();
  const navigate = useNavigate();
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const storyFileRef = useRef<HTMLInputElement>(null);
  const photoFileRef = useRef<HTMLInputElement>(null);
  const clipFileRef = useRef<HTMLInputElement>(null);
  const [feed, setFeed] = useState<FeedResponse>();
  const [composer, setComposer] = useState("");
  const [location, setLocation] = useState("");
  const [showLocation, setShowLocation] = useState(false);
  const [attachment, setAttachment] = useState<ComposerAttachment | null>(null);
  const [busy, setBusy] = useState(false);
  const [storyBusy, setStoryBusy] = useState(false);
  const [draftBusy, setDraftBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [activeStory, setActiveStory] = useState<FeedPost>();
  const [commenting, setCommenting] = useState<string>();
  const [commentDraft, setCommentDraft] = useState("");
  const [comments, setComments] = useState<Record<string, string[]>>({});
  const { toast } = useToast();

  const load = useCallback(async () => {
    setFeed(await socialApi.feed());
  }, []);

  useEffect(() => {
    void load().catch((caught) => setError(caught.message));
  }, [load]);

  useEffect(() => {
    if (!activeStory) return;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setActiveStory(undefined);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [activeStory]);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  /** Only real 24h stories from the API — never pad with ordinary posts. */
  const stories = useMemo(() => {
    const seen = new Set<string>();
    return (feed?.posts || [])
      .filter((post) => post.story_active)
      .filter((post) => {
        if (!post.author_id || seen.has(post.author_id)) return false;
        seen.add(post.author_id);
        return true;
      })
      .slice(0, 8);
  }, [feed]);

  const suggestions = useMemo(() => {
    const seen = new Set<string>();
    return (feed?.posts || [])
      .map((post) => post.author)
      .filter((person): person is SocialPerson => Boolean(person && person.user_id !== user?._id))
      .filter((person) => {
        if (seen.has(person.user_id)) return false;
        seen.add(person.user_id);
        return true;
      })
      .slice(0, 4);
  }, [feed, user?._id]);

  const visiblePosts = useMemo(
    () => (feed?.posts || []).filter((post) => post.presentation !== "story"),
    [feed],
  );

  const myInitials = initials({ display_name: user?.display_name });
  const accent = profile?.theme?.accent || "violet";

  const focusComposer = () => {
    requestAnimationFrame(() => composerRef.current?.focus());
  };

  const clearAttachment = () => {
    setAttachment((current) => {
      if (current?.previewUrl.startsWith("blob:")) URL.revokeObjectURL(current.previewUrl);
      return null;
    });
  };

  const submitPost = (event?: FormEvent) => {
    event?.preventDefault();
    const value = composer.trim();
    if ((!value && !attachment) || busy) return;
    void run(async () => {
      const post = await socialApi.post(value || "Shared an update", "post", {
        image_media_id: attachment?.id,
        location: location.trim() || undefined,
      });
      setComposer("");
      setLocation("");
      setShowLocation(false);
      clearAttachment();
      setNotice(
        post.ingested
          ? "Posted — your agent can now use this as grounded context."
          : "Posted to your circle.",
      );
    });
  };

  const onCreateStoryClick = () => {
    storyFileRef.current?.click();
  };

  const uploadComposerFile = async (file: File, kind: "post" | "clip") => {
    setBusy(true);
    setError("");
    try {
      const uploaded = await socialApi.uploadMedia(file, kind);
      clearAttachment();
      setAttachment({
        id: uploaded._id,
        mediaType: uploaded.media_type,
        kind,
        previewUrl: URL.createObjectURL(file),
      });
      setNotice(kind === "clip" ? "Clip attached — add a caption and hit Post." : "Photo attached — add a caption and hit Post.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not upload file");
    } finally {
      setBusy(false);
    }
  };

  const onPhotoFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Photos need an image file (PNG, JPEG, WebP, or GIF).");
      return;
    }
    void uploadComposerFile(file, "post");
  };

  const onClipFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("video/")) {
      setError("Clips need a video file (MP4, WebM, or MOV).");
      return;
    }
    void uploadComposerFile(file, "clip");
  };

  const askAgentHelp = async () => {
    const notes = composer.trim();
    if (!notes) {
      setError("Write a few rough notes first — your agent needs something to draft from.");
      composerRef.current?.focus();
      return;
    }
    setDraftBusy(true);
    setError("");
    try {
      const draft = await socialApi.draftPost(notes);
      setComposer(draft.body);
      setNotice(
        draft.runtime_mode === "live"
          ? "Agent drafted this — edit anything, then Post when you’re happy."
          : "Draft ready (offline polish) — edit anything, then Post.",
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Agent could not draft right now");
    } finally {
      setDraftBusy(false);
    }
  };

  const onStoryFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Stories need an image (PNG, JPEG, WebP, or GIF).");
      return;
    }
    setStoryBusy(true);
    setError("");
    void (async () => {
      try {
        await socialApi.createStory(file);
        await load();
        toast("Story posted — it stays in the strip for 24 hours.", "ok");
      } catch (caught) {
        toast(caught instanceof Error ? caught.message : "Could not upload story", "error");
      } finally {
        setStoryBusy(false);
      }
    })();
  };

  const toggleLike = (post: FeedPost) => {
    const mine = feed?.my_reactions[post._id];
    void run(() => socialApi.react(post._id, mine === "like" ? null : "like"));
  };

  const addComment = (postId: string) => {
    const value = commentDraft.trim();
    if (!value) return;
    setComments((current) => ({
      ...current,
      [postId]: [...(current[postId] || []), value],
    }));
    setCommentDraft("");
    setCommenting(undefined);
    toast("Comment added locally — not saved to the server yet.", "info");
  };

  const sharePost = async (post: FeedPost) => {
    const text = post.body.slice(0, 120);
    // Transient results go to the toast channel, not into the composer's notice slot —
    // sharing a post has nothing to do with the thing you are drafting.
    try {
      await navigator.clipboard.writeText(`${text} — ${window.location.origin}/feed`);
      toast("Post link copied", "ok");
    } catch {
      toast("Could not reach the clipboard — copy the address bar instead", "error");
    }
  };

  return (
    <div className="feed-layout">
      <main>
        <div className="feed-title">
          <span>SF BUILDERS CIRCLE</span>
          <h1>Social feed</h1>
          <div role="group" aria-label="Feed filter">
            {(["Recents", "Friends", "Popular"] as FeedFilter[]).map((item) => (
              <button
                key={item}
                type="button"
                className={filter === item ? "active" : ""}
                aria-pressed={filter === item}
                onClick={() => setFilter(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </div>

        <div className="stories" aria-label="Stories">
          <input
            ref={storyFileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            hidden
            onChange={onStoryFile}
          />
          <button
            type="button"
            className="create-story"
            disabled={storyBusy}
            onClick={onCreateStoryClick}
          >
            <Plus size={18} />
            <small>{storyBusy ? "Uploading…" : "Create story"}</small>
          </button>
          {stories.map((post, index) => {
            const image = post.image_media_id ? socialApi.storySrc(post.image_media_id) : null;
            return (
              <button
                type="button"
                className={`story-chip story-tone-${index % 5}${image ? " has-photo" : ""}`}
                key={post._id}
                aria-label={`Open ${post.author?.display_name || "member"}'s story`}
                onClick={() => setActiveStory(post)}
                style={image ? { backgroundImage: `url(${image})` } : undefined}
              >
                <span className={`avatar avatar-sm tone-${post.author?.accent || "violet"}`}>
                  {initials(post.author)}
                </span>
                <span className="story-chip-shade" />
                <small>{post.author?.display_name?.split(" ")[0] || "Member"}</small>
              </button>
            );
          })}
          {stories.length === 0 && (
            <p className="stories-empty">No active stories yet — tap Create story to upload a photo.</p>
          )}
        </div>

        <Link className="approval-banner" to="/find">
          <span className="banner-icon"><Send size={17} /></span>
          <span>
            <b>Find your next introduction</b>
            <small>Tell Discover who you need — your agent drafts, you approve.</small>
          </span>
          <ChevronRight size={18} />
        </Link>

        <form className="composer open" onSubmit={submitPost}>
          <div className="composer-main">
            <span className={`avatar tone-${accent}`}>{myInitials}</span>
            <textarea
              ref={composerRef}
              aria-label="Write an update"
              placeholder="Share an update, ask, or win…"
              value={composer}
              rows={composer.trim() || attachment ? 3 : 2}
              maxLength={4000}
              onChange={(event) => setComposer(event.target.value)}
              onFocus={focusComposer}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                  event.preventDefault();
                  submitPost();
                }
              }}
            />
            <button
              type="button"
              className="composer-emoji"
              aria-label="Insert smile"
              onClick={() => {
                setComposer((current) => `${current}${current && !current.endsWith(" ") ? " " : ""}🙂`);
                composerRef.current?.focus();
              }}
            >
              <Smile size={18} />
            </button>
          </div>

          {attachment && (
            <div className="composer-attach-preview">
              {attachment.mediaType.startsWith("video/") ? (
                <video src={attachment.previewUrl} controls playsInline />
              ) : (
                <img src={attachment.previewUrl} alt="" />
              )}
              <button type="button" onClick={clearAttachment} aria-label="Remove attachment">
                <X size={14} />
              </button>
            </div>
          )}

          {showLocation && (
            <label className="composer-location">
              <MapPin size={14} />
              <input
                value={location}
                onChange={(event) => setLocation(event.target.value)}
                placeholder="Add a location"
                maxLength={80}
              />
            </label>
          )}

          {error && <p className="auth-error" role="alert">{error}</p>}
          {notice && <p className="thread-notice">{notice}</p>}

          <footer>
            <input
              ref={photoFileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              hidden
              onChange={onPhotoFile}
            />
            <input
              ref={clipFileRef}
              type="file"
              accept="video/mp4,video/webm,video/quicktime"
              hidden
              onChange={onClipFile}
            />
            <button type="button" className="composer-tool" onClick={() => photoFileRef.current?.click()} disabled={busy}>
              <Image size={15} /> Photo
            </button>
            <button type="button" className="composer-tool" onClick={() => clipFileRef.current?.click()} disabled={busy}>
              <Video size={15} /> Clip
            </button>
            <button
              type="button"
              className={`composer-tool ${showLocation ? "on" : ""}`}
              onClick={() => setShowLocation((current) => !current)}
            >
              <MapPin size={15} /> Location
            </button>
            <button
              type="button"
              className="composer-tool agent-help"
              onClick={() => void askAgentHelp()}
              disabled={draftBusy || busy}
            >
              <Sparkles size={15} /> {draftBusy ? "Drafting…" : "Agent help"}
            </button>
            <button
              type="submit"
              className="composer-submit"
              disabled={busy || (!composer.trim() && !attachment)}
            >
              {busy ? "Posting…" : "Post"}
            </button>
          </footer>
        </form>

        {visiblePosts.map((post) => (
          <PostCard
            key={post._id}
            post={post}
            liked={feed?.my_reactions[post._id] === "like"}
            myInitials={myInitials}
            accent={accent}
            localComments={comments[post._id] || []}
            commenting={commenting === post._id}
            commentDraft={commenting === post._id ? commentDraft : ""}
            onToggleLike={() => toggleLike(post)}
            onToggleComment={() => {
              setCommenting((current) => (current === post._id ? undefined : post._id));
              setCommentDraft("");
            }}
            onCommentChange={setCommentDraft}
            onAddComment={() => addComment(post._id)}
            onShare={() => void sharePost(post)}
            onWarmIntro={() => navigate("/find")}
          />
        ))}

        {!feed && <SkeletonList count={3} lines={3} media label="Loading your feed…" />}

        {feed && visiblePosts.length === 0 && (
          <div className="social-empty feed-post">
            <Sparkles size={22} />
            <h2>Your circle is ready for its first update.</h2>
            <p>Share what you are building or <Link to="/find">discover people</Link>.</p>
          </div>
        )}
      </main>

      <aside className="feed-rail">
        <section className="live-now">
          <span className="live-label"><i /> Discover</span>
          <div />
          <strong>Find people worth meeting</strong>
          <small>Ask in plain English. Matches come from what people wrote — not job titles.</small>
          <button type="button" onClick={() => navigate("/find")}>
            Open Discover <ChevronRight size={14} />
          </button>
        </section>

        <h2>
          Suggestions
          <button type="button" onClick={() => navigate("/find")}>See all</button>
        </h2>
        {suggestions.map((person) => (
          <Link className="suggestion" to={`/u/${person.handle}`} key={person.user_id}>
            <span className={`avatar avatar-sm tone-${person.accent || "violet"}`}>
              {initials(person)}
            </span>
            <span>
              <b>{person.display_name}</b>
              <small>{headlineFor(person)}</small>
            </span>
            <span className="suggestion-action">View</span>
          </Link>
        ))}

        <h2>Recommendations</h2>
        <div className="recommend-grid">
          {interests.map((topic) => (
            <button
              key={topic}
              type="button"
              onClick={() => navigate("/find")}
            >
              <Sparkles size={16} />
              <b>{topic}</b>
            </button>
          ))}
        </div>
      </aside>

      {activeStory && <StoryViewer post={activeStory} onClose={() => setActiveStory(undefined)} />}
    </div>
  );
}
