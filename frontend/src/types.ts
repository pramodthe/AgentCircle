export interface AuthUser {
  _id: string;
  email: string;
  display_name: string;
  handle: string;
  onboarding_complete: boolean;
  created_at: string;
}

export interface ProfileTheme {
  accent?: string;
  background?: string;
  font?: string;
  layout?: string;
  song_url?: string;
}

export interface UserProfile {
  _id: string;
  user_id: string;
  display_name: string;
  headline: string;
  bio: string;
  location?: string;
  pronouns?: string;
  organization?: string;
  role?: string;
  website?: string;
  availability?: string;
  skills: string[];
  interests: string[];
  looking_for: string[];
  likes: string[];
  dislikes: string[];
  hobbies: string[];
  theme: ProfileTheme;
  /**
   * Presentation only. Uploading an image never changes who finds you — the same rule
   * `theme` follows. Absent slots are explicit nulls so a card cannot render a stale
   * avatar left over from the previous row.
   */
  avatar_media_id?: string | null;
  avatar_ai_generated?: boolean;
  cover_media_id?: string | null;
  cover_ai_generated?: boolean;
  /** Only on the PATCH response: false when the save landed but embedding did not. */
  retrieval_synced?: boolean;
}

/** A persona claim plus the ingested chunk that supports it. */
export interface PersonaItemRef {
  value: string;
  chunk_id?: string;
  source_id?: string;
  source_title?: string;
}

export interface PersonaCoverage {
  missing: string[];
  score: number;
}

export interface Persona {
  headline: string;
  summary: string;
  skills: PersonaItemRef[];
  interests: PersonaItemRef[];
  looking_for: PersonaItemRef[];
  notable: PersonaItemRef[];
  extraction_mode: "model" | "heuristic" | "empty";
  extraction_model: string | null;
  extraction_error?: string;
  source_count: number;
  chunk_count: number;
  coverage: PersonaCoverage;
}

export interface PersonaSource {
  _id: string;
  title: string;
  kind: "upload" | "link" | "declared";
  detail: string;
  characters: number;
  chunk_count: number;
  preview: string;
  created_at: string;
}

export interface PersonaChunkHit {
  _id: string;
  text: string;
  source_id: string;
  source_title: string;
  ordinal: number;
  score: number;
}

export interface OnboardingState {
  complete: boolean;
  steps: Record<string, boolean>;
  source_count: number;
  coverage: PersonaCoverage;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
  onboarding: OnboardingState;
}

export interface MeResponse {
  user: AuthUser;
  profile: UserProfile | null;
  persona: Persona | null;
  onboarding: OnboardingState;
}

export interface PersonaBuildResult {
  persona: Persona;
  onboarding: OnboardingState;
}

export interface PublicProfile {
  user: AuthUser;
  profile: UserProfile | null;
  persona: {
    headline: string;
    summary: string;
    skills: string[];
    interests: string[];
    looking_for: string[];
  };
}

export const COMMENT_TOPICS = [
  "product",
  "engineering",
  "design",
  "hiring",
  "fundraising",
  "go_to_market",
  "research",
  "operations",
] as const;

export interface CommunitySettings {
  comment_enabled: boolean;
  comment_topics: string[];
  review_before_publish: boolean;
  /** Opt-out: on by default, but a member can stop appearing in search. */
  discoverable: boolean;
  /** Opt-IN, unlike `discoverable` — photos are a separate decision (spec §9). */
  photo_search_enabled: boolean;
  /** Opt-IN. Being findable is not the same as being profiled. */
  research_enabled: boolean;
}

export interface MemberPhoto {
  _id: string;
  user_id: string;
  /** Required. What the photo is matched on, and the evidence shown to a searcher. */
  caption: string;
  media_type: string;
  size_bytes: number;
  /** False when the photo is stored but was never embedded, so it cannot be found. */
  indexed: boolean;
  space: string | null;
  created_at: string;
  score?: number;
  member?: { _id: string; display_name: string; handle: string } | null;
}

export interface MediaStatus {
  available: boolean;
  model: string | null;
  dimensions: number;
  space: string;
}

export interface PhotoSearchResponse {
  /** True when the query asked about appearance and was declined on purpose. */
  refused?: boolean;
  reason?: string;
  available?: boolean;
  results: MemberPhoto[];
}

export interface CommunityPost {
  _id: string;
  author_id: string;
  author?: { display_name: string; handle: string } | null;
  title: string;
  body: string;
  topics: string[];
  comment_count: number;
  declined_count: number;
  recruited_at: string | null;
  created_at: string;
}

export interface CommentCitation {
  chunk_id: string;
  source_id: string;
  source_title: string;
  excerpt: string;
}

export interface CommunityComment {
  _id: string;
  post_id: string;
  responder_id: string;
  responder?: {
    user_id: string;
    display_name: string;
    handle: string | null;
    headline: string;
  } | null;
  body: string;
  citations: CommentCitation[];
  declined: boolean;
  decline_reason: string | null;
  runtime_mode: string;
  model: string | null;
  recruit_score: number;
  published: boolean;
  score: number;
  up_votes: number;
  down_votes: number;
  created_at: string;
}

export const OUTCOME_LABELS = [
  { id: "great", label: "Great", hint: "Met and it was clearly worth it" },
  { id: "useful", label: "Useful", hint: "Met and it was worth it" },
  { id: "neutral", label: "Fine", hint: "Met, nothing special" },
  { id: "waste", label: "Waste", hint: "Met and it wasn't worth it" },
  { id: "passed", label: "Passed", hint: "Didn't pursue it" },
] as const;

export interface Outcome {
  _id: string;
  reporter_id: string;
  subject_id: string;
  subject?: { display_name: string; handle: string } | null;
  label: string;
  score: number;
  context: string;
  context_id: string;
  predicted_score: number | null;
  note: string;
  created_at: string;
}

/** Why the agent rates someone the way it does — direct vs propagated. */
export interface TrustBreakdown {
  value: number;
  direct: number | null;
  propagated: number | null;
  contributors: number;
  reasons: string[];
}

export interface Calibration {
  samples: number;
  bias: number;
  mean_error: number;
  confidence_multiplier: number;
  summary: string;
}

export interface OutcomeResult {
  outcome: Outcome;
  trust: TrustBreakdown;
  calibration: Calibration;
}

export interface CommunityThread {
  post: CommunityPost;
  comments: CommunityComment[];
  my_votes: Record<string, number>;
  my_outcomes: Record<string, Outcome>;
  trust: Record<string, TrustBreakdown>;
}

export interface RecruitResult {
  post: CommunityPost;
  recruited: number;
  commented: number;
  declined: number;
  reason?: string;
}

/** A question people keep asking that this member's persona cannot answer. */
export interface GapDemandRow {
  key: string;
  question: string;
  count: number;
  sources: string[];
  ids: string[];
  last_asked: string;
}

export interface GapDemand {
  demand: GapDemandRow[];
  total_unanswered: number;
}

export interface ContextGap {
  _id: string;
  question: string;
  source: string;
  post_id: string | null;
  created_at: string;
}

export interface DiscoveryEvidence {
  text: string;
  source_title: string | null;
  source_id: string | null;
  score: number;
}

export interface DiscoveryResult {
  user_id: string;
  member:
    | {
        user_id: string;
        display_name: string;
        handle: string;
        avatar_media_id?: string | null;
        cover_media_id?: string | null;
        avatar_ai_generated?: boolean;
        cover_ai_generated?: boolean;
      }
    | null;
  headline: string;
  location: string;
  skills: string[];
  interests: string[];
  looking_for: string[];
  persona_summary: string;
  /**
   * An absolute similarity in [0, 100] — comparable across queries, which is what
   * makes a fixed threshold meaningful. See `similarity_basis` for what measured it.
   */
  match_percent: number;
  /** `rerank` (cross-encoder relevance), `vector` (cosine), or `keyword_only` (0). */
  similarity_basis: "rerank" | "vector" | "keyword_only";
  score: number;
  fusion_score: number;
  vector_rank: number | null;
  keyword_rank: number | null;
  rerank_score?: number;
  trust: number;
  trust_detail: TrustBreakdown;
  evidence: DiscoveryEvidence[];
  matched_terms: string[];
  why_it_clicks: string[];
}

/** Which retrieval path actually served the query. Surfaced so the UI never overclaims. */
export interface RetrievalStatus {
  vector: "atlas" | "local";
  keyword: "atlas" | "local";
  fusion: string;
  /** Rerank model name, or "off" when reranking did not run. */
  rerank: string;
  embedding_space: string;
  semantic: boolean;
  /** What produced match_percent for this result set. */
  similarity?: "rerank" | "vector" | "keyword_only" | "none";
}

export interface DiscoveryThreshold {
  min_match_percent: number;
  /** Never a silent cut — "no matches" and "none above your bar" read differently. */
  hidden_below_threshold: number;
}

/** Which retrieval and model paths are actually live, for the shell status line. */
export interface RetrievalHealth {
  atlas_vector: boolean;
  atlas_text: boolean;
  atlas_enabled: boolean;
  embeddings: {
    provider: string;
    model: string;
    dimensions: number;
    space: string;
    degraded: boolean;
    semantic: boolean;
  };
  rerank?: { enabled: boolean; model: string | null; degraded?: boolean };
}

export interface DiscoveryResponse {
  query: string;
  matches: DiscoveryResult[];
  retrieval: RetrievalStatus;
  threshold: DiscoveryThreshold;
  filters: AppliedDiscoveryFilters;
}

/** What the caller asked to narrow by, and how many members survived it. */
export interface AppliedDiscoveryFilters {
  location: string | null;
  goal: string | null;
  evidence_only: boolean;
  /** Members left after filtering, before the query ranked them. */
  candidates: number;
}

export interface DiscoveryFilters {
  location?: string;
  goal?: string;
  evidenceOnly?: boolean;
}

export interface FacetValue {
  value: string;
  count: number;
}

/** Filter values that exist on real profiles, so no option can return nobody. */
export interface DiscoveryFacets {
  locations: FacetValue[];
  goals: FacetValue[];
}

export interface InterviewCitation {
  chunk_id: string;
  source_id: string | null;
  source_title: string | null;
  excerpt: string;
}

export type DeclineKind = "not_in_profile" | "permission" | "no_model" | "error" | null;

export interface InterviewRow {
  question: string;
  kind: "professional" | "personal" | "contact";
  answered: boolean;
  answer: string;
  citations: InterviewCitation[];
  confidence: number;
  decline_kind: DeclineKind;
  decline_reason: string | null;
}

export interface InterviewVerdict {
  recommendation: "connect" | "maybe" | "pass";
  rationale: string;
  met: string[];
  missing: string[];
  confidence: number;
  coverage: number;
}

export interface Interview {
  _id: string;
  status: "pending" | "complete" | "failed";
  error?: string;
  questions?: string[];
  asker_id: string;
  subject_id: string;
  subject?: { user_id: string; display_name: string; handle: string } | null;
  goal: string;
  rows: InterviewRow[];
  verdict: InterviewVerdict;
  offer: string;
  runtime_mode: string;
  model: string | null;
  answered_count: number;
  question_count: number;
  blocked_count: number;
  created_at: string;
}

export interface InterviewSettings {
  interview_enabled: boolean;
  interview_topics: string[];
  disclose_personal: boolean;
}

export interface InterviewPresets {
  presets: Record<string, string[]>;
  max_questions: number;
}

export const REACTIONS = ["like", "insightful", "same"] as const;

export interface SocialPerson {
  user_id: string;
  display_name: string;
  handle: string;
  headline: string;
  organization?: string;
  role?: string;
  accent: string;
  /**
   * Presentation only. Uploading an image never changes who finds you — the same rule
   * `theme` follows. Absent slots are explicit nulls so a card cannot render a stale
   * avatar left over from the previous row.
   */
  avatar_media_id?: string | null;
  avatar_ai_generated?: boolean;
  cover_media_id?: string | null;
  cover_ai_generated?: boolean;
}

/** Distinct from the legacy demo `Connection` below, which the old shell still uses. */
export interface SocialConnection {
  _id: string;
  members: string[];
  requester_id: string;
  recipient_id: string;
  status: "pending" | "accepted" | "ignored" | "withdrawn";
  note: string;
  source: string;
  context_id: string | null;
  member?: SocialPerson | null;
  updated_at: string;
}

export interface ConnectionsResponse {
  accepted: SocialConnection[];
  incoming: SocialConnection[];
  outgoing: SocialConnection[];
  /** Which part of the product actually produced each connection. */
  provenance: Record<string, number>;
}

export interface DirectMessage {
  _id: string;
  conversation_id: string;
  participants: string[];
  sender_id: string;
  recipient_id: string;
  body: string;
  created_at: string;
  read_at: string | null;
}

export interface MessageConversation {
  conversation_id: string;
  member_id: string;
  member: SocialPerson;
  last_message: DirectMessage;
  unread_count: number;
  updated_at: string;
}

export interface MessageThread {
  conversation_id: string;
  member: SocialPerson;
  messages: DirectMessage[];
}

export interface FeedPostEvidence {
  kind: "gap" | "interview";
  id: string;
  detail: string;
}

export interface FeedPost {
  _id: string;
  author_id: string;
  author?: SocialPerson | null;
  body: string;
  kind: "human" | "agent";
  /**
   * A story is the same grounded pipeline filed as a dated episode: it is ingested as
   * `kind: "episodic"` so the agent can recall *when* something happened. Only the
   * story card is ephemeral — see `story_active`.
   */
  presentation?: "post" | "story";
  /**
   * Whether this story still belongs in the story strip. The server owns the 24h rule
   * so two clients cannot disagree about what is on screen. Never true for a post.
   */
  story_active?: boolean;
  /** Presentation-only story/post photo or clip. Never searchable. */
  image_media_id?: string | null;
  image_media_type?: string | null;
  location?: string | null;
  evidence: FeedPostEvidence[];
  /** True when the post was folded into the author's persona and is now retrievable. */
  ingested: boolean;
  ingested_chunks?: number;
  reaction_counts: Record<string, number>;
  from_connection?: boolean;
  created_at: string;
}

export interface FeedResponse {
  posts: FeedPost[];
  my_reactions: Record<string, string>;
  connection_count: number;
}

export interface Capability { name: string; level: number }

export interface Agent {
  _id: string;
  name: string;
  display_name?: string;
  handle: string;
  initials: string;
  accent: string;
  role: string;
  organization?: string;
  location?: string;
  bio: string;
  mission?: string;
  capabilities: Capability[];
  status: string;
  reliability: number;
}

export interface Post {
  _id: string;
  author_agent_id: string;
  author: Agent;
  title?: string;
  content: string;
  tag: string;
  media_kind: string;
  reaction_counts: Record<string, number>;
  comment_count: number;
  created_at: string;
}

export interface RuntimeStatus {
  mode: "live" | "deterministic_fallback";
  configured: boolean;
  provider: string;
  model: string;
  fallback_enabled: boolean;
  tools: string[];
}

export interface AgentMemory {
  _id: string;
  content: string;
  source: string;
  created_at: string;
}

export interface AgentCircleProfile extends Agent {
  memories: AgentMemory[];
  permissions: Record<string, boolean>;
  recent_activity: Array<{ title: string; detail: string }>;
}

export interface DiscoveryMatch {
  agent: Agent;
  match_percent: number;
  why_it_clicks: string[];
  memory_ids: string[];
  tags: string[];
  first_conversation: string;
  status: string;
}

export interface NegotiationTurn { speaker: string; message: string }

export interface IntroRequest {
  _id: string;
  primary_agent_id: string;
  candidate_agent_id: string;
  candidate?: Agent;
  goal: string;
  status: "waiting_approval" | "sent" | "accepted" | "withdrawn" | "rejected";
  match_strength: string;
  mutual_value: string;
  best_connection: string;
  conversation_starter: string;
  suggested_activity: string;
  why_recommended: string;
  suggested_message: string;
  transcript: NegotiationTurn[];
  human_approval_required: boolean;
  runtime_mode: string;
  memory_ids: string[];
  updated_at: string;
}

export interface Connection {
  agent: Agent;
  status: string;
  agent_note: string;
}

/** A sourced brief on one member. Private to whoever requested it. */
export interface ResearchBrief {
  _id: string;
  asker_id: string;
  subject_id: string;
  goal: string;
  status: "pending" | "complete" | "failed";
  summary: string;
  findings: { claim: string; source_url: string }[];
  open_questions: string[];
  /** Confirmed to be about this member — the only ones findings may come from. */
  sources: { url: string; title: string; author?: string; published?: string | null;
    matched_on?: string[] }[];
  /** Pages carrying the name that nothing tied to this member. Never a finding. */
  unconfirmed_sources?: { url: string; title: string }[];
  declined: boolean;
  decline_reason?: string;
  decline_kind?: string;
  /** Claims the model made that cited a URL never returned — dropped, not shown. */
  dropped_claims?: number;
  runtime_mode?: string | null;
  model?: string | null;
  cost_usd: number;
  queries: string[];
  error?: string;
  created_at: string;
}

export interface ResearchStatus {
  available: boolean;
  provider: string | null;
  search_type: string;
}

/** One uploaded presentation image. Never embedded, never searchable. */
export interface ProfileImage {
  _id: string;
  user_id: string;
  kind: "avatar" | "cover";
  media_type: string;
  size_bytes: number;
  ai_generated: boolean;
  created_at: string;
}

/** Public runtime state — what is actually wired up right now, no session required. */
export interface StackStatusPayload {
  model: { configured: boolean; provider: string | null; model: string | null; mode: string; warnings: string[] };
  embeddings: {
    provider: string; model: string; dimensions: number;
    space: string; degraded: boolean; semantic: boolean;
  };
  rerank: { enabled: boolean; model: string | null; degraded: boolean };
  research: { available: boolean; provider: string | null; search_type: string | null };
}

/** Edge-scoped agent memory — one relationship's worth, never another's. */
export interface LearningEntry {
  _id: string;
  kind: string;
  summary: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface LintFinding {
  kind: string;
  field?: string;
  value?: string;
  values?: string[];
  sources?: string[];
  source_id?: string;
  message: string;
}

export interface NetworkPath {
  user_id: string;
  hops: number;
  via: string[];
  member: { display_name: string; handle: string } | null;
  through: Array<{ display_name: string; handle: string }>;
}
