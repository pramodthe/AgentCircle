# Frontend specification

Rebuild the React SPA so routes, data contracts, and honesty rules match the product.
CSS may evolve; structure and API usage may not.

Stack: React 19, React Router 7, Vite 7, TypeScript, lucide-react. Single `styles.css`.
No CSS framework. No Jest — `npm run build` (`tsc -b && vite build`) is the check.

---

## 1. Bootstrap (`main.tsx`)

```tsx
createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <ToastProvider>
      <AuthProvider>
        <Root />
      </AuthProvider>
    </ToastProvider>
  </BrowserRouter>
);
```

Import `./styles.css` once here.

---

## 2. Route table (`Root.tsx`)

| Path | Guard | Page |
|---|---|---|
| `/` | public | `Landing` |
| `/how-it-works` | public | `HowItWorks` |
| `/welcome` | — | redirect → `/` |
| `/login` | AnonymousOnly | `SignIn mode="login"` |
| `/register` | AnonymousOnly | `SignIn mode="register"` |
| `/onboarding` | Protected `allowIncomplete` | `Onboarding` |
| nested under Protected + `AppShell`: | | |
| `/feed` | | `Feed` |
| `/find` | | `Discover` |
| `/community` | | `CommunityIndex` |
| `/community/:postId` | | `CommunityThreadPage` |
| `/messages` | | `Messages` |
| `/messages/:userId` | | `Messages` |
| `/connections` | | `Connections` |
| `/me` | | `Me` |
| `/me/:tab` | | `Me` (map tab → hash) |
| `/interview/:subjectId` | | `InterviewPage` |
| `/research/:subjectId` | | `Research` |
| `/u/:handle` | | `PublicProfile` |
| `/agent` | | → `/me#documents` |
| `/profile` | | → `/me` |
| `/profile/edit` | | → `/me?edit=1` |
| `*` | | → `/` |

### Guards

- **Booting:** while `status === "loading"` show “Waking up your agent…”.
- **Protected:** anonymous → `/login` (keep `state.from`); if onboarding incomplete and
  not `allowIncomplete` → `/onboarding`.
- **AnonymousOnly:** authenticated → `/feed`.

---

## 3. Auth (`auth.tsx`)

Context:

```ts
status: "loading" | "authenticated" | "anonymous"
user?: AuthUser
profile?: UserProfile | null
persona?: Persona | null
onboarding?: OnboardingState
signIn(email, password): Promise<void>
signUp(email, password, displayName): Promise<void>
signOut(): void
refresh(): Promise<void>
```

- Token: `localStorage["agentcircle.token"]` via `api.setAuthToken`.
- Boot: if token → `auth.me()` else anonymous; failure clears token.
- Register 401 handler to clear session.
- After `personaApi.build`, server sets `onboarding_complete`; call `refresh()`.

---

## 4. AppShell

Left sticky nav (brand AgentCircle / “SF Builders”, me chip → `/me`, primary nav, footer
with “Your agent is online”, `StackStatus`, sign out).

| `to` | Label |
|---|---|
| `/feed` | News Feed |
| `/find` | Discover |
| `/community` | Community |
| `/messages` | Messages |
| `/connections` | Connections |
| `/me` | You |

**StackStatus:** `discoveryApi.status()` once. If `!embeddings.semantic` or Atlas off →
warn “Limited search mode”; else “Agent is grounded”. Tooltip names path/model/rerank.

Export **`PageHeader`** with variants:

| variant | Use |
|---|---|
| `plain` (default) | Most pages |
| `feature` | Messages-style |
| `hero` | Discover, Connections (photo banner) |

Props: `icon?`, `title`, `blurb?`, `eyebrow?`, `action?`, `aside?`, `variant?`.

Every shell page uses `PageHeader` — do not invent a fifth header pattern.

---

## 5. Pages (behaviour contract)

### Landing `/`
Marketing: hero, product preview, walkthrough steps, under-the-hood, CTA.
Uses `useAuth().status` only (no API). Signed-in CTA → `/feed`, else `/login`.

### HowItWorks `/how-it-works`
Reads `runtimeApi.status()`. Explains ingest → chunk → embed → store → retrieve → answer.
**Decline path shown with equal weight** as the answer path. Auto-advancing stages OK.

### SignIn `/login` `/register`
Prototype: `EnterAs` person picker (demo accounts). Uses `signIn(email, DEMO_PASSWORD)`.

### Onboarding `/onboarding`
Four steps: **Basics** (profile fields) → **Sources** (upload/link) → **Personality**
(extras) → **Build** (`personaApi.build`) → `navigate("/feed")` + `refresh()`.

### Feed `/feed`
`socialApi.feed`, composer (text / photo / clip / location / `draftPost` / `createStory`),
`react`, agent post. Connections-first feed. **No stock photos** as covers.
Client-only comment UI may exist but must not pretend server persistence if it does not.

### Discover `/find`
Modes: People (`discoveryApi.search`, query ≥ 8) | Photos (`mediaApi.search`).
Match cards: evidence, `match_percent`, retrieval badge, CTA → interview / research /
connect. Show refusal reason for appearance queries.

### Community
**Index:** posts list, create post, consent sidebar (topics, pending publish, gap demand).
**Thread:** recruit (author), votes, citations, declines, `outcomeApi.record`, calibration.

### Messages
Inbox + thread. Auto-open first conversation if no `:userId`.
`messagesApi.conversations|thread|send`.

### Connections
Tabs: Accepted / Pending / (optional empty Recommended/Rejected/Saved).
`socialApi.connections|respond|withdraw`. Show provenance counts.

### Me `/me`
Owner LinkedIn-style page via `ProfileView`. Sections: about, photos, documents,
permissions, memory. `?edit=1` opens `EditProfile`. Hash scroll for tabs.
APIs: `profileApi.public`, `personaApi.*`, `communityApi.gapDemand`, `mediaApi.forUser`,
`brainApi` via `AgentMemory`.

### PublicProfile `/u/:handle`
Same `ProfileView` without owner panels. Connect button via `socialApi`.

### EditProfile
Embedded modal from Me. Declared fields + theme + `ProfilePhotos`.
**Live preview must use the same backdrop→card nesting as public profile** (C4).
On save show “Saved, but not searchable yet” if `retrieval_synced === false`.

### Interview `/interview/:subjectId`
Goal + questions (presets). `interviewApi.run` → poll `get` every ~2s until not pending.
Render **table** (Question / Answer / Source / Confidence), unanswered highlighted.
Verdict `connect|maybe|pass`. Outcomes + connect CTA. Clear poll on unmount.

### Research `/research/:subjectId`
Goal chips + custom. Check `researchApi.status`. Start → poll. Show summary, findings,
open questions; unconfirmed sources **unattributed**; decline kinds named.

---

## 6. Components

| Component | Contract |
|---|---|
| `EnterAs` | Demo login from `demoAccounts.ts` |
| `Avatar` | `name`, `mediaId?`, `accent?`, `size?` — **own photo or initials only** |
| `Toast` / `ToastProvider` / `useToast` | Single channel; kinds ok/error/info; stack ≤3 |
| `Skeleton*` | Loading placeholders |
| `ProfileView` | Shared shell for Me + Public + edit preview; slots for documents/memory/permissions/photos |
| `AgentDocuments` | Sources, rebuild, gap demand resolve |
| `AgentMemory` | Self-fetches log, lint, network paths; states edge isolation plainly |
| `AgentPermissions` | Community + interview settings + calibration |
| `Photos` | Searchable evidence upload (caption required) |
| `ProfilePhotos` | Avatar/cover only (non-searchable) |

---

## 7. Types (`types.ts`) — must implement

Core (non-exhaustive; match `api.md` payloads):

- `AuthUser`, `UserProfile`, `ProfileTheme`, `Persona`, `PersonaItemRef`, `PersonaSource`,
  `PersonaCoverage`, `OnboardingState`, `AuthResponse`, `MeResponse`, `PublicProfile`
- `CommunitySettings`, `CommunityPost`, `CommunityComment`, `CommentCitation`,
  `CommunityThread`, `RecruitResult`, `GapDemand`, `ContextGap`
- `MemberPhoto`, `MediaStatus`, `PhotoSearchResponse`
- `OUTCOME_LABELS`, `Outcome`, `TrustBreakdown`, `Calibration`, `OutcomeResult`
- `DiscoveryResult`, `DiscoveryResponse`, `RetrievalStatus`, `RetrievalHealth`
- `Interview`, `InterviewRow`, `InterviewVerdict`, `InterviewSettings`, `InterviewPresets`
- `ResearchBrief`, `ResearchStatus`
- `SocialConnection`, `ConnectionsResponse`, `FeedPost`, `FeedResponse`
- `DirectMessage`, `MessageConversation`, `MessageThread`
- `LearningEntry`, `LintFinding`, `NetworkPath`
- `COMMENT_TOPICS`, `REACTIONS`

Drop legacy demo types (`Agent`, `IntroRequest`, …) unless needed.

---

## 8. Demo accounts (`demoAccounts.ts`)

```ts
export const DEMO_PASSWORD = "agentcircle";
export const DEMO_ACCOUNTS = [
  { email: "maya@example.com",  name: "Maya Chen",     role: "Founder · Lumen AI",         accent: "coral" },
  { email: "sofia@example.com", name: "Sofia Alvarez", role: "Research engineer",          accent: "blue" },
  { email: "elena@example.com", name: "Elena Rossi",   role: "Clinical ops · CareLoop",    accent: "teal" },
  { email: "kenji@example.com", name: "Kenji Tanaka",  role: "Infrastructure · GridPilot", accent: "gold" },
  { email: "priya@example.com", name: "Priya Raman",   role: "Design lead",                accent: "violet" },
];
```

---

## 9. Design tokens (minimum)

Fonts: **DM Sans** (UI), **Manrope** (display) — not Inter/Roboto/system-only.

CSS variables (define in `:root`):

```
--ink, --ink-2, --text, --text-muted, --text-subtle
--line, --line-soft, --surface, --surface-soft, --canvas
--accent, --accent-strong, --accent-soft
--ok, --danger, --warn-soft
--shadow-1..4, --r-sm/md/lg/xl, --ease, --fast/--base/--slow, --focus-ring
```

Accent tones for avatars: `violet`, `coral`, `blue`, `teal`, `gold`, `green`.

Key class families: `.shell*`, `.page-header|.page-heading|.page-hero`, `.feed-*`,
`.social-discover`, `.messages-*`, `.community-*`, `.profile-*`, `.toast-*`, `.skeleton*`,
`.avatar`, `.primary`, `.ghost`, `.chip`.

**Honesty classes:** `.stack-status.warn` when degraded; retrieval badges on discover;
`runtime_mode` visible on agent comments.

Avoid: purple-on-white AI cliché as the only look is fine if accent is already violet —
but do not add glow stacks, emoji clutter, or stock-photo member faces.

Responsive: collapse nav/rail ~900px / 600px.

---

## 10. Non-negotiable UI rules

1. Agents suggest; humans publish / connect / message / record outcomes.
2. Status line tells the truth about retrieval and model path.
3. Preview ≡ public profile structure (backdrop behind card).
4. Avatar = member photo or initials — never Unsplash labelled as Kenji.
5. Theme edits never described as improving discoverability; declared fields are.
6. `retrieval_synced: false` → “saved but not searchable yet”.
7. Interview = table, not chat transcript.
8. Research unconfirmed sources shown without attributing them to the member.
9. Edge memory panel states conversations are walled off.
10. One toast channel; shared skeletons; `PageHeader` everywhere in the shell.
