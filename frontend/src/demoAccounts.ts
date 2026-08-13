/** Seeded prototype accounts — same people as `scripts.seed_users`. Password is always `agentcircle`. */
export const DEMO_PASSWORD = "agentcircle";

export const DEMO_ACCOUNTS = [
  {
    email: "maya@example.com",
    name: "Maya Chen",
    role: "Founder · Lumen AI",
    accent: "coral",
  },
  {
    email: "sofia@example.com",
    name: "Sofia Alvarez",
    role: "Research engineer",
    accent: "blue",
  },
  {
    email: "elena@example.com",
    name: "Elena Rossi",
    role: "Clinical ops · CareLoop",
    accent: "teal",
  },
  {
    email: "kenji@example.com",
    name: "Kenji Tanaka",
    role: "Infrastructure · GridPilot",
    accent: "gold",
  },
  {
    email: "priya@example.com",
    name: "Priya Raman",
    role: "Design lead",
    accent: "violet",
  },
] as const;

export function initials(name: string) {
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
