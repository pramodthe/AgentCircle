import type {
  AuthResponse,
  Calibration,
  CommunityComment,
  CommunityPost,
  CommunitySettings,
  CommunityThread,
  ConnectionsResponse,
  ContextGap,
  DiscoveryFacets,
  DiscoveryFilters,
  DiscoveryResponse,
  DirectMessage,
  FeedPost,
  FeedResponse,
  GapDemand,
  Interview,
  InterviewPresets,
  InterviewSettings,
  MediaStatus,
  MessageConversation,
  MessageThread,
  MemberPhoto,
  MeResponse,
  Outcome,
  PhotoSearchResponse,
  OutcomeResult,
  Persona,
  PersonaBuildResult,
  PersonaChunkHit,
  PersonaSource,
  ProfileImage,
  PublicProfile,
  ResearchBrief,
  ResearchStatus,
  RecruitResult,
  RetrievalHealth,
  StackStatusPayload,
  LearningEntry,
  LintFinding,
  NetworkPath,
  SocialConnection,
  TrustBreakdown,
  UserProfile,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const TOKEN_KEY = "agentcircle.token";

let authToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function loadStoredToken(): string | null {
  if (authToken === null) {
    try {
      authToken = window.localStorage.getItem(TOKEN_KEY);
    } catch {
      authToken = null;
    }
  }
  return authToken;
}

export function setAuthToken(token: string | null) {
  authToken = token;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Private browsing or disabled storage: the in-memory token still works
    // for this tab, the session just will not survive a reload.
  }
}

/** Called when the API rejects our token, so the app can drop back to sign-in. */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

function authHeaders(): Record<string, string> {
  const token = loadStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handle<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    onUnauthorized?.();
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = payload?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail) && detail[0]?.msg
          ? detail[0].msg
          : "AgentCircle request failed",
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(init?.headers || {}),
      },
    });
  } catch {
    throw new Error(`Can't reach the API at ${API_BASE}. Is the backend running?`);
  }
  return handle<T>(response);
}

async function upload<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  // No Content-Type here on purpose: the browser must set the multipart boundary.
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: authHeaders(),
    body,
  });
  return handle<T>(response);
}

export const auth = {
  register: (email: string, password: string, displayName: string) =>
    request<AuthResponse>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name: displayName }),
    }),
  login: (email: string, password: string) =>
    request<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<MeResponse>("/api/auth/me"),
};

export const profileApi = {
  get: () => request<UserProfile>("/api/profile"),
  update: (patch: Partial<UserProfile>) =>
    request<UserProfile>("/api/profile", { method: "PATCH", body: JSON.stringify(patch) }),
  public: (handle: string) => request<PublicProfile>(`/api/profile/${encodeURIComponent(handle)}`),
};

export const personaApi = {
  get: () =>
    request<{ persona: Persona | null; sources: PersonaSource[]; onboarding: MeResponse["onboarding"] }>(
      "/api/persona",
    ),
  sources: () => request<PersonaSource[]>("/api/persona/sources"),
  uploadSource: (file: File) => upload<PersonaSource>("/api/persona/sources/upload", file),
  addLink: (url: string) =>
    request<PersonaSource>("/api/persona/sources/link", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  deleteSource: (id: string) =>
    request<void>(`/api/persona/sources/${encodeURIComponent(id)}`, { method: "DELETE" }),
  build: () => request<PersonaBuildResult>("/api/persona/build", { method: "POST" }),
  search: (q: string) =>
    request<PersonaChunkHit[]>(`/api/persona/search?q=${encodeURIComponent(q)}`),
};

export const communityApi = {
  settings: () => request<CommunitySettings>("/api/community/settings"),
  updateSettings: (patch: Partial<CommunitySettings>) =>
    request<CommunitySettings>("/api/community/settings", {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  posts: () => request<CommunityPost[]>("/api/community/posts"),
  createPost: (title: string, body: string) =>
    request<CommunityPost>("/api/community/posts", {
      method: "POST",
      body: JSON.stringify({ title, body }),
    }),
  thread: (postId: string) =>
    request<CommunityThread>(`/api/community/posts/${encodeURIComponent(postId)}`),
  recruit: (postId: string) =>
    request<RecruitResult>(`/api/community/posts/${encodeURIComponent(postId)}/recruit`, {
      method: "POST",
    }),
  vote: (commentId: string, value: number) =>
    request<CommunityComment>(`/api/community/comments/${encodeURIComponent(commentId)}/vote`, {
      method: "POST",
      body: JSON.stringify({ value }),
    }),
  pending: () => request<CommunityComment[]>("/api/community/pending"),
  publish: (commentId: string) =>
    request<CommunityComment>(`/api/community/comments/${encodeURIComponent(commentId)}/publish`, {
      method: "POST",
    }),
  gaps: () => request<ContextGap[]>("/api/community/gaps"),
  gapDemand: () => request<GapDemand>("/api/community/gaps/demand"),
  resolveGaps: (gapIds: string[]) =>
    request<{ resolved: number }>("/api/community/gaps/resolve", {
      method: "POST",
      body: JSON.stringify({ gap_ids: gapIds }),
    }),
};

export const discoveryApi = {
  search: (
    query: string,
    filters: DiscoveryFilters = {},
    limit = 8,
    minMatchPercent = 50,
  ) =>
    request<DiscoveryResponse>("/api/discover", {
      method: "POST",
      body: JSON.stringify({
        query,
        limit,
        min_match_percent: minMatchPercent,
        // Send null, not "", for an unset filter: the server treats an empty string as
        // a real value to match against and would return nobody.
        location: filters.location?.trim() || null,
        goal: filters.goal?.trim() || null,
        evidence_only: filters.evidenceOnly ?? false,
      }),
    }),
  facets: () => request<DiscoveryFacets>("/api/discover/facets"),
  status: () => request<RetrievalHealth>("/api/discover/status"),
};

export const mediaApi = {
  status: () => request<MediaStatus>("/api/media/status"),
  mine: () => request<MemberPhoto[]>("/api/media"),
  forUser: (userId: string) => request<MemberPhoto[]>(`/api/media/user/${userId}`),
  /** The caption is required by the server — it is what the photo gets matched on. */
  upload: async (file: File, caption: string) => {
    const body = new FormData();
    body.append("file", file);
    body.append("caption", caption);
    const response = await fetch(`${API_BASE}/api/media`, {
      method: "POST",
      headers: authHeaders(),
      body,
    });
    return handle<MemberPhoto>(response);
  },
  remove: (mediaId: string) =>
    request<void>(`/api/media/${mediaId}`, { method: "DELETE" }),
  search: (query: string) =>
    request<PhotoSearchResponse>(`/api/media/search?q=${encodeURIComponent(query)}`),
  /** Photo bytes are a plain URL so the browser can cache them like any image. */
  src: (mediaId: string) => `${API_BASE}/api/media/${mediaId}/raw`,
};

/**
 * Avatars and covers. Deliberately separate from `mediaApi`, which handles searchable
 * persona photos under the consent rules in spec §9 — these are presentation only and
 * are never embedded, indexed, or reachable from any search endpoint.
 */
export const profileMediaApi = {
  upload: async (file: File, kind: "avatar" | "cover", aiGenerated = false) => {
    const body = new FormData();
    body.append("file", file);
    body.append("kind", kind);
    body.append("ai_generated", String(aiGenerated));
    const response = await fetch(`${API_BASE}/api/profile/photo`, {
      method: "POST",
      headers: authHeaders(),
      body,
    });
    return handle<ProfileImage>(response);
  },
  remove: (kind: "avatar" | "cover") =>
    request<void>(`/api/profile/photo/${kind}`, { method: "DELETE" }),
  /** Public URL — an avatar has to render on an unauthenticated profile page. */
  src: (mediaId: string) => `${API_BASE}/api/profile/photo/${mediaId}/raw`,
};

export const socialApi = {
  connections: () => request<ConnectionsResponse>("/api/social/connections"),
  status: (otherId: string) =>
    request<SocialConnection | { status: "none" }>(`/api/social/connections/${encodeURIComponent(otherId)}`),
  connect: (recipientId: string, note = "", source = "direct", contextId?: string) =>
    request<SocialConnection>("/api/social/connections", {
      method: "POST",
      body: JSON.stringify({
        recipient_id: recipientId,
        note,
        source,
        context_id: contextId,
      }),
    }),
  respond: (otherId: string, accept: boolean) =>
    request<SocialConnection>(`/api/social/connections/${encodeURIComponent(otherId)}/respond`, {
      method: "POST",
      body: JSON.stringify({ accept }),
    }),
  withdraw: (otherId: string) =>
    request<SocialConnection>(`/api/social/connections/${encodeURIComponent(otherId)}/withdraw`, {
      method: "POST",
    }),
  feed: () => request<FeedResponse>("/api/social/feed"),
  post: (
    body: string,
    presentation: "post" | "story" = "post",
    extras?: { image_media_id?: string; location?: string },
  ) =>
    request<FeedPost>("/api/social/feed", {
      method: "POST",
      body: JSON.stringify({
        body,
        presentation,
        image_media_id: extras?.image_media_id,
        location: extras?.location,
      }),
    }),
  /** Composer Photo / Clip upload — presentation only, never searchable. */
  uploadMedia: async (file: File, kind: "post" | "clip" = "post") => {
    const body = new FormData();
    body.append("file", file);
    body.append("kind", kind);
    const response = await fetch(`${API_BASE}/api/social/feed/media`, {
      method: "POST",
      headers: authHeaders(),
      body,
    });
    return handle<{ _id: string; media_type: string; kind: string; url: string }>(response);
  },
  /** Agent helps write the post. Still requires the member to hit Post. */
  draftPost: (notes: string) =>
    request<{ body: string; runtime_mode: string; model: string | null }>("/api/social/feed/draft", {
      method: "POST",
      body: JSON.stringify({ notes }),
    }),
  /** Image-first story — this is what the Create story button calls. */
  createStory: async (file: File, caption = "") => {
    const body = new FormData();
    body.append("file", file);
    if (caption.trim()) body.append("caption", caption.trim());
    const response = await fetch(`${API_BASE}/api/social/feed/story`, {
      method: "POST",
      headers: authHeaders(),
      body,
    });
    return handle<FeedPost>(response);
  },
  mediaSrc: (mediaId: string) =>
    `${API_BASE}/api/social/feed/media/${encodeURIComponent(mediaId)}/raw`,
  storySrc: (mediaId: string) =>
    `${API_BASE}/api/social/feed/media/${encodeURIComponent(mediaId)}/raw`,
  agentPost: () => request<FeedPost>("/api/social/feed/agent", { method: "POST" }),
  react: (postId: string, reaction: string | null) =>
    request<FeedPost>(`/api/social/feed/${encodeURIComponent(postId)}/react`, {
      method: "POST",
      body: JSON.stringify({ reaction }),
    }),
};

export const messagesApi = {
  conversations: () => request<MessageConversation[]>("/api/messages"),
  thread: (otherId: string) =>
    request<MessageThread>(`/api/messages/${encodeURIComponent(otherId)}`),
  send: (otherId: string, body: string) =>
    request<DirectMessage>(`/api/messages/${encodeURIComponent(otherId)}`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
  markRead: (otherId: string) =>
    request<void>(`/api/messages/${encodeURIComponent(otherId)}/read`, { method: "POST" }),
};

export const interviewApi = {
  presets: () => request<InterviewPresets>("/api/interviews/presets"),
  settings: () => request<InterviewSettings>("/api/interviews/settings"),
  updateSettings: (patch: Partial<InterviewSettings>) =>
    request<InterviewSettings>("/api/interviews/settings", {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  run: (subjectId: string, goal: string, questions: string[]) =>
    request<Interview>("/api/interviews", {
      method: "POST",
      body: JSON.stringify({ subject_id: subjectId, goal, questions }),
    }),
  list: () => request<Interview[]>("/api/interviews"),
  get: (id: string) => request<Interview>(`/api/interviews/${encodeURIComponent(id)}`),
};

export const researchApi = {
  status: () => request<ResearchStatus>("/api/research/status"),
  start: (subjectId: string, goal: string) =>
    request<ResearchBrief>("/api/research", {
      method: "POST",
      body: JSON.stringify({ subject_id: subjectId, goal }),
    }),
  list: () => request<ResearchBrief[]>("/api/research"),
  get: (id: string) => request<ResearchBrief>(`/api/research/${encodeURIComponent(id)}`),
};

export const outcomeApi = {
  record: (input: {
    subjectId: string;
    label: string;
    context: string;
    contextId: string;
    note?: string;
  }) =>
    request<OutcomeResult>("/api/outcomes", {
      method: "POST",
      body: JSON.stringify({
        subject_id: input.subjectId,
        label: input.label,
        context: input.context,
        context_id: input.contextId,
        note: input.note,
      }),
    }),
  mine: () => request<Outcome[]>("/api/outcomes"),
  calibration: () => request<Calibration>("/api/outcomes/calibration"),
  trust: (subjectId: string) =>
    request<TrustBreakdown>(`/api/outcomes/trust/${encodeURIComponent(subjectId)}`),
};

/** Unauthenticated: the explainer page shows the live stack to anyone, signed in or not. */
export const runtimeApi = {
  status: () => request<StackStatusPayload>("/api/runtime/status"),
};

/** What the agent learned and when, what looks wrong with it, and who it can reach. */
export const brainApi = {
  log: (limit = 50) => request<LearningEntry[]>(`/api/persona/log?limit=${limit}`),
  lint: () => request<{ findings: LintFinding[]; clean: boolean }>("/api/persona/lint"),
  paths: () => request<{ paths: NetworkPath[] }>("/api/interviews/network/paths"),
};
