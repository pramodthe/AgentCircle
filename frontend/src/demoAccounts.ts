/** Featured EnterAs accounts. `scripts.seed_users` also creates 50+ crowd members around them. Password is always `agentcircle`. */
export const DEMO_PASSWORD = "agentcircle";

export const DEMO_ACCOUNTS = [
  {
    email: "maya@example.com",
    name: "Maya Chen",
    role: "Founder · Lumen AI",
    accent: "coral",
    photo: "/demo-avatars/maya.jpg",
  },
  {
    email: "sofia@example.com",
    name: "Sofia Alvarez",
    role: "Research engineer",
    accent: "blue",
    photo: "/demo-avatars/sofia.jpg",
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
    photo: "/demo-avatars/priya.jpg",
    photoAiGenerated: true,
  },
  {
    email: "anika@example.com",
    name: "Anika Shah",
    role: "Partner · Horizon",
    accent: "gold",
  },
  {
    email: "leo@example.com",
    name: "Leo Park",
    role: "Founder · Stackwell",
    accent: "green",
  },
  {
    email: "james@example.com",
    name: "James Okada",
    role: "RN · informatics",
    accent: "teal",
  },
  {
    email: "tess@example.com",
    name: "Tess McKenzie",
    role: "Staff engineer · payments",
    accent: "blue",
  },
  {
    email: "soren@example.com",
    name: "Soren Lindqvist",
    role: "Product designer",
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
