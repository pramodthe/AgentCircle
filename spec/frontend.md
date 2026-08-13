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
| `/find` | | `Discover` (home) |
| `/feed` | | `Feed` (Circle → Updates) |
| `/community` | | `CommunityIndex` |
| `/community/:postId` | | `CommunityThreadPage` |
| `/messages` | | `Messages` (Circle → Messages) |
| `/messages/:userId` | | `Messages` |
| `/connections` | | `Connections` (Circle → Connections) |
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
- **AnonymousOnly:** authenticated → `/find`.

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

Left sticky nav (brand AgentCircle, me chip → `/me`, four primary destinations, footer
with `StackStatus` + Sign out). No floating topbar. No stock photography in chrome.
Avatars go through `Avatar` — never a second initials helper in the shell.

| `to` | Label |
|---|---|
| `/find` | Find |
| `/feed` | Circle (active also on `/messages` and `/connections`) |
| `/community` | Community |
| `/me` | You |

**Circle subnav** (`CircleNav`) on Feed, Messages, Connections: Updates · Messages · Connections.

**StackStatus:** `discoveryApi.status()` once. If `!embeddings.semantic` or Atlas off →
warn “Limited search”; else “Search is live”. Tooltip names path/model/rerank.
Do not add a second always-on “agent is online” card.

Export **`PageHeader`** with variants:

| variant | Use |
|---|---|
| `plain` (default) | Most pages, including Discover and Connections |
| `feature` | Messages |
| `hero` | Unused. If revived, solid ink — never Unsplash. |

Props: `icon?`, `title`, `blurb?`, `eyebrow?`, `action?`, `aside?`, `variant?`.

Every shell page uses `PageHeader` — do not invent a fifth header pattern.

---

## 5. Pages (behaviour contract)

### Landing `/`
Marketing: hero, product preview, walkthrough steps, under-the-hood, CTA.
Uses `useAuth().status` only (no API). Signed-in CTA → `/find`, else `/login`.

### HowItWorks `/how-it-works`
Reads `runtimeApi.status()`. Explains ingest → chunk → embed → store → retrieve → answer.
**Decline path shown with equal weight** as the answer path. Auto-advancing stages OK.

### SignIn `/login` `/register`
Prototype: `EnterAs` person picker (demo accounts). Uses `signIn(email, DEMO_PASSWORD)`.

### Onboarding `/onboarding`
Four steps: **Basics** (profile fields) → **Sources** (upload/link) → **Personality**
(extras) → **Build** (`personaApi.build`) → `navigate("/find")` + `refresh()`.

### Feed `/feed`
Circle → Updates. `socialApi.feed`, composer (text / photo / clip / location /
`draftPost` / `createStory`), `react`, agent post. **No Recents/Friends/Popular filters.**
Stories row only when a story exists. **No stock photos** as covers.
Client-only comments must say they are not saved. Empty feed: one CTA to `/find`.

### Discover `/find` (home)
Modes: People (`discoveryApi.search`, query ≥ 8) | Photos (`mediaApi.search`).
Match cards: quoted evidence first, then name, then one primary CTA → interview.
Do not show a ranked-match stat before a search. Show refusal reason for appearance queries.

### Community
**Index:** posts list, create post, consent sidebar (topics, pending publish, gap demand).
**Thread:** recruit (author), votes, citations, declines, `outcomeApi.record`, calibration.

### Messages
Inbox + thread. Auto-open first conversation if no `:userId`.
`messagesApi.conversations|thread|send`.

### Connections
Tabs: Accepted and Pending. Recommended / Rejected / Saved only if they have rows.
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
