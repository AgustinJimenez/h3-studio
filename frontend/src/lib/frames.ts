// H3 only renders frame counts on a 17k+5 grid, and WanGP rounds an off-grid request DOWN
// (backend/lint.py: 145 -> 141, 240 -> 226, verified on 133 past clips). Show what will really
// render, not what was typed.
export const FPS = 24;

export function renderedFrames(requested: number): number {
  const n = Math.max(5, Math.floor(requested));
  return Math.floor((n - 5) / 17) * 17 + 5;
}

/** One clip's length: the requested value, and what it actually renders when those differ. */
export function formatFrames(requested: number): string {
  const rendered = renderedFrames(requested);
  const seconds = (rendered / FPS).toFixed(1);
  return rendered === requested ? `${requested}f (~${seconds}s)` : `${requested}f → renders ${rendered}f (~${seconds}s)`;
}

/** A total across clips (already a sum of rendered frames), so no grid rounding. */
export function formatTotalFrames(frames: number): string {
  return `${frames}f (~${(frames / FPS).toFixed(1)}s)`;
}
