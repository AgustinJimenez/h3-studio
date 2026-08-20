// MiniMax's own H3 prompt-writing guide targets ~350-500 words for
// detailed_description (relaxed for dialogue-dense scenes) — see AGENTS.md.
// This counts just the shot/action text the user is typing, not the full
// composed detailed_description (which also includes the style/environment/
// cinematic-realism preset text), so it's a rough guide, not exact.
export const WORD_TARGET_MIN = 350;
export const WORD_TARGET_MAX = 500;

export function wordCount(text: string | null | undefined): number {
  const trimmed = (text ?? "").trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

export function wordCountClass(count: number): string {
  if (count === 0) return "text-xs opacity-65";
  if (count < WORD_TARGET_MIN) return "text-xs opacity-65";
  if (count > WORD_TARGET_MAX) return "text-xs text-danger opacity-100";
  return "text-xs text-status-done opacity-100";
}
