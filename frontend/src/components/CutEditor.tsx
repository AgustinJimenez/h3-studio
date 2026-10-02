import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Scissors, X } from "lucide-react";
import { API_BASE } from "../lib/api";

// Manual scene splitting with frame precision: step through the source frame by frame, mark the first frame of each new scene.
export default function CutEditor({
  sourceId,
  frames,
  fps,
  aspect,
  cuts,
  hasWork,
  hasScenes,
  busy,
  onApply,
  onDirtyChange,
}: {
  sourceId: string;
  frames: number;
  fps: number;
  aspect: number;
  cuts: number[];
  hasWork: boolean;
  hasScenes: boolean;
  busy: boolean;
  onApply: (cuts: number[]) => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [frame, setFrame] = useState(0);
  const [draft, setDraft] = useState<number[]>(cuts);
  const saved = useMemo(() => cuts.join(","), [cuts]);
  useEffect(() => setDraft(cuts), [saved]); // eslint-disable-line react-hooks/exhaustive-deps
  const clamp = (n: number) => Math.max(0, Math.min(frames - 1, n));
  const go = (n: number) => setFrame(clamp(Math.round(n)));
  const [dragging, setDragging] = useState<number | null>(null); // the cut being dragged along the slider (its current frame)
  const track = useRef<HTMLDivElement>(null);
  const isCut = draft.includes(frame);
  const dirty = draft.join(",") !== saved;
  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLInputElement;
      if (t.tagName === "INPUT" && t.type !== "range") return;
      if (e.key === "ArrowLeft") go(frame - (e.shiftKey ? 10 : 1));
      else if (e.key === "ArrowRight") go(frame + (e.shiftKey ? 10 : 1));
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [frame]); // eslint-disable-line react-hooks/exhaustive-deps

  // Preload the neighbours so stepping is instant.
  useEffect(() => {
    for (const n of [frame - 1, frame + 1]) if (n >= 0 && n < frames) new Image().src = `${API_BASE}/swaps/${sourceId}/frame/${n}`;
  }, [frame, frames, sourceId]);

  // Drag a cut marker: it follows the pointer frame by frame, staying between its neighbours; the preview shows the frame it is on.
  function dragTo(clientX: number) {
    if (dragging === null || !track.current) return;
    const rect = track.current.getBoundingClientRect();
    const raw = Math.round(((clientX - rect.left - 8) / Math.max(1, rect.width - 16)) * (frames - 1));
    const i = draft.indexOf(dragging);
    const next = Math.max((draft[i - 1] ?? 0) + 1, Math.min((draft[i + 1] ?? frames) - 1, raw));
    if (next === dragging) return;
    setDraft(draft.map((c) => (c === dragging ? next : c)));
    setDragging(next);
    setFrame(next);
  }

  function toggleCut() {
    if (frame === 0) return;
    setDraft(isCut ? draft.filter((c) => c !== frame) : [...draft, frame].sort((a, b) => a - b));
  }

  const scenes = [0, ...draft].map((start, i, all) => ({ start, end: (all[i + 1] ?? frames) - 1 }));
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-sm">
        <span className="text-xs text-text-muted">
          Arrow keys step one frame (Shift: 10). A cut makes the shown frame the first frame of a new scene.
        </span>
      </div>
      <div className="flex flex-wrap gap-4">
        <img
          alt={`frame ${frame}`}
          src={`${API_BASE}/swaps/${sourceId}/frame/${frame}`}
          className="max-h-96 rounded border border-border"
          style={{ aspectRatio: aspect }}
        />
        <div className="min-w-64 flex-1 space-y-3">
          <div className="text-sm text-text-h">
            Frame <strong>{frame}</strong> / {frames - 1} · {(frame / fps).toFixed(2)}s
            {isCut && <span className="ml-2 rounded bg-accent px-1.5 py-0.5 text-xs text-white">scene starts here</span>}
          </div>
          <div className="relative py-1" ref={track}>
            <input type="range" className="relative z-0 w-full" min={0} max={frames - 1} value={frame} onChange={(e) => go(Number(e.target.value))} />
            {draft.map((c, i) => (
              <span
                key={i} // by position, not frame: the marker keeps its pointer capture while its frame changes during a drag
                role="slider"
                aria-label={`Cut at frame ${c}`}
                aria-valuenow={c}
                title={`Cut at frame ${c}: drag to move`}
                className={`absolute top-0 z-10 flex h-full w-3 -translate-x-1/2 cursor-ew-resize touch-none items-center justify-center`}
                style={{ left: `calc(8px + (100% - 16px) * ${c / Math.max(1, frames - 1)})` }}
                onPointerDown={(e) => {
                  try {
                    e.currentTarget.setPointerCapture(e.pointerId);
                  } catch {
                    // no active pointer to capture (synthetic events): moves still reach the marker while the pointer is over it
                  }
                  setDragging(c);
                  setFrame(c);
                }}
                onPointerMove={(e) => dragTo(e.clientX)}
                onPointerUp={() => setDragging(null)}
                onPointerCancel={() => setDragging(null)}
              >
                <span className={`h-full rounded-sm bg-accent ${c === dragging ? "w-1.5 ring-2 ring-white" : "w-1"}`} />
              </span>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-1">
            <button title="-10 frames" onClick={() => go(frame - 10)}>
              <ChevronsLeft size={14} />
            </button>
            <button title="previous frame" onClick={() => go(frame - 1)}>
              <ChevronLeft size={14} />
            </button>
            <button title="next frame" onClick={() => go(frame + 1)}>
              <ChevronRight size={14} />
            </button>
            <button title="+10 frames" onClick={() => go(frame + 10)}>
              <ChevronsRight size={14} />
            </button>
            <input
              className="w-20"
              type="number"
              min={0}
              max={frames - 1}
              value={frame}
              onChange={(e) => e.target.value !== "" && go(Number(e.target.value))}
            />
            <button disabled={frame === 0} onClick={toggleCut}>
              <Scissors size={14} className="mr-1 inline" />
              {isCut ? "Remove cut here" : "Cut here"}
            </button>
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold text-text-h">Scenes</div>
            <div className="flex flex-wrap gap-1.5 text-xs">
              {scenes.map((s, i) => {
                const here = frame >= s.start && frame <= s.end;
                return (
                  <span
                    key={s.start}
                    title={`Scene ${i + 1}: ${s.end - s.start + 1} frames (${((s.end - s.start + 1) / fps).toFixed(2)}s). Click to jump to its first frame.`}
                    className={`inline-flex items-stretch overflow-hidden rounded-full border ${here ? "border-accent" : "border-border"}`}
                  >
                    <button
                      className={`rounded-none border-0 px-2 py-0.5 text-xs ${here ? "bg-accent text-white" : "bg-border text-text-h"}`}
                      onClick={() => go(s.start)}
                    >
                      {i + 1}
                    </button>
                    <button className="rounded-none border-0 bg-transparent px-2 py-0.5 text-xs text-text-muted" onClick={() => go(s.start)}>
                      {s.start}f to {s.end}f
                    </button>
                    {i > 0 && (
                      <button
                        title="Remove the cut before this scene (joins it with the previous one)"
                        className="rounded-none border-0 border-l border-border bg-transparent px-1.5 py-0.5 text-text-muted"
                        onClick={() => setDraft(draft.filter((c) => c !== s.start))}
                      >
                        <X size={11} />
                      </button>
                    )}
                  </span>
                );
              })}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              disabled={busy || (!dirty && hasScenes)}
              onClick={() => {
                if (!hasWork || window.confirm("Applying new cuts rebuilds the scenes and discards the planned and rendered passes. Continue?")) onApply(draft);
              }}
            >
              Apply {draft.length + 1} scenes
            </button>
            {draft.length > 0 && (
              <button onClick={() => setDraft([])} className="text-xs">
                Clear all cuts
              </button>
            )}
            {dirty && (
              <button onClick={() => setDraft(cuts)} className="text-xs">
                Reset
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
