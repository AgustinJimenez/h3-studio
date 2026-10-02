import { useState } from "react";
import { Trash2 } from "lucide-react";
import SwapCompare, { type ResultMeta } from "./SwapCompare";
import type { SwapPass, SwapRun, SwapScene } from "../schemas";

function when(ts: number | null | undefined) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function metaOf(run: SwapRun, projectSize: { width: number; height: number; seed: number }): ResultMeta {
  const w = run.width ?? projectSize.width;
  const h = run.height ?? projectSize.height;
  return {
    width: w,
    height: h,
    quality: run.quality ?? "final",
    seed: run.seed ?? projectSize.seed, // a result made before runs were recorded used the project's seed
    testSize: Math.min(w, h) < Math.min(projectSize.width, projectSize.height),
  };
}

// One scene's result: the original next to the chosen run, and the list of every run made for it. The run in use
// (the one the final video takes) is marked; any other run can be compared, put in use, or deleted.
export default function SwapSceneResults({
  scene,
  pass,
  sourceUrl,
  fps,
  aspect,
  idle,
  projectSize,
  onUse,
  onDelete,
  onFullRun,
  onTrim,
}: {
  scene: SwapScene;
  pass: SwapPass; // the last pass of the scene's chain: its result is what the final video uses
  sourceUrl?: string | null;
  fps: number;
  aspect: number;
  idle: boolean;
  projectSize: { width: number; height: number; seed: number };
  onUse: (runId: string) => void;
  onDelete: (runId: string) => void;
  onFullRun: (seed: number) => void;
  onTrim: (frames: number) => void;
}) {
  const runs = [...pass.history].sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0));
  const active = runs.find((r) => r.active) ?? runs[0];
  const [picked, setPicked] = useState<string | null>(null);
  const [full, setFull] = useState(false); // the whole render (at least 124 frames), not just the scene's own frames
  const shown = runs.find((r) => r.id === picked) ?? active;
  if (!shown) return null;
  const meta = metaOf(shown, projectSize);

  return (
    <div className="space-y-2">
      <SwapCompare
        key={`${shown.id}-${full}`}
        scene={scene}
        sourceUrl={sourceUrl}
        fps={fps}
        resultUrl={full && shown.raw_url ? shown.raw_url : shown.output_url}
        originalUrl={full && shown.raw_url ? shown.source_clip_url : null}
        resultLabel={shown.active ? "original and the result in the final video" : "original and a previous run"}
        idle={idle}
        showTitle={false}
        meta={meta}
        onFullRun={() => onFullRun(meta.seed)}
        trim={
          shown.active && pass.params?.raw_frames && pass.params.raw_frames > 0
            ? { kept: pass.params.trim_frames ?? scene.frames_24, raw: pass.params.raw_frames, sceneFrames: scene.frames_24, onApply: onTrim }
            : undefined
        }
        aspect={aspect}
      />
      {shown.raw_url && (
        <label className="flex items-center gap-2 text-xs text-text-muted">
          <input type="checkbox" checked={full} onChange={(e) => setFull(e.target.checked)} />
          Show the full render
          {pass.params?.raw_frames ? ` (${pass.params.raw_frames + (pass.params.lead_used ?? 0)} frames, ${((pass.params.raw_frames + (pass.params.lead_used ?? 0)) / 24).toFixed(1)}s)` : ""}
          <span className="opacity-70">, beyond the scene it also covers the footage that follows</span>
        </label>
      )}
      {runs.length > 1 && (
        <details className="rounded border border-border bg-bg text-xs" open={runs.length <= 6}>
          <summary className="cursor-pointer px-2 py-1 text-text-muted">History · {runs.length} runs</summary>
          <ul className="divide-y divide-border">
            {runs.map((r) => {
              const m = metaOf(r, projectSize);
              const isShown = r.id === shown.id;
              return (
                <li key={r.id} className={`flex flex-wrap items-center gap-2 px-2 py-1.5 ${isShown ? "bg-bg-alt" : ""}`}>
                  <span className="w-28 text-text-muted">{when(r.created_at)}</span>
                  <span className="font-semibold uppercase">{m.quality}</span>
                  <span>
                    {m.width}×{m.height}
                  </span>
                  <span>seed {m.seed}</span>
                  {r.extra_loras.map(([name, w]) => (
                    <span key={name} className="rounded bg-bg-alt px-1.5 text-[10px]" title={name}>
                      + {name.replace(/\.safetensors$/, "").slice(0, 28)} {w}
                    </span>
                  ))}
                  {r.seconds != null && <span className="text-text-muted">{Math.max(1, Math.round(r.seconds))}s</span>}
                  {m.testSize && <span className="rounded bg-amber-600/80 px-1.5 text-[10px] font-semibold uppercase text-white">test size</span>}
                  {r.active && <span className="rounded bg-emerald-700 px-1.5 text-[10px] font-semibold uppercase text-white">in final video</span>}
                  <span className="ml-auto flex gap-1.5">
                    <button className="py-0.5 text-xs" disabled={isShown} onClick={() => setPicked(r.id)}>
                      {isShown ? "Showing" : "Compare"}
                    </button>
                    {!r.active && (
                      <>
                        <button className="py-0.5 text-xs" onClick={() => onUse(r.id)} title="The final video will use this run">
                          Use in final video
                        </button>
                        <button className="py-0.5 text-xs" title="Delete this run and its files" aria-label="Delete this run" onClick={() => onDelete(r.id)}>
                          <Trash2 size={12} />
                        </button>
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </details>
      )}
    </div>
  );
}
