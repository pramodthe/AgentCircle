/**
 * Routing ids are not display names. `/api/runtime/status` reports
 * `openai/gpt-5.6-luna`; the UI should say GPT-5.6 Luna.
 */
const MODEL_ALIASES: Record<string, string> = {
  "gpt-5.6-luna": "GPT-5.6 Luna",
  "gpt-5.6-terra": "GPT-5.6 Terra",
  "gpt-5.6-sol": "GPT-5.6 Sol",
  "gpt-4o-mini": "GPT-4o mini",
};

export function modelAlias(id: string | null | undefined): string {
  if (!id) return "—";
  const bare = id.split("/").pop() || id;
  return MODEL_ALIASES[bare] ?? bare;
}
