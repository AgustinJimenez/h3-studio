import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { mediaUrl } from "../lib/api";
import { swapApi } from "../lib/swapApi";
import {
  useDeleteStill,
  useMakeStills,
  useViggleRun,
} from "../lib/swapQueries";
import type { SwapPass, SwapScene } from "../schemas";

// The second way to swap a scene. The usual swap pastes the reference photo when the person does not face the camera (seen from
// behind) or the face is tiny. Here the scene's own first frame is edited into the character first (Qwen), then Viggle animates that
// still with the scene's motion. The panel: write the edit instruction, make candidate stills, pick one, animate it.
export default function SwapStillsPanel({
  swapId,
  pass,
  scene,
  aspect,
  sceneBusy,
}: {
  swapId: string;
  pass: SwapPass; // the first pass of the scene
  scene: SwapScene;
  aspect: number;
  sceneBusy: boolean;
}) {
  const makeStills = useMakeStills(swapId);
  const deleteStill = useDeleteStill(swapId);
  const viggle = useViggleRun(swapId);
  const [view, setView] = useState<"front" | "behind">("front");
  const [prompt, setPrompt] = useState("");
  const [count, setCount] = useState("4");
  const [stillSeed, setStillSeed] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const [size, setSize] = useState("480");
  const [runSeed, setRunSeed] = useState("");
  const [promptError, setPromptError] = useState<string | null>(null);
  const stills = pass.stills;
  const chosen = stills.find((s) => s.id === picked) ?? null;
  const making = pass.activity === "stills";
  const thumb = mediaUrl(scene.thumb_url);

  // The default instruction depends on the view, the character and who is replaced; fetch it again when those change.
  useEffect(() => {
    let alive = true;
    setPromptError(null);
    swapApi
      .stillPrompt(swapId, pass.id, view)
      .then((r) => alive && setPrompt(r.prompt))
      .catch((e: Error) => alive && setPromptError(e.message));
    return () => {
      alive = false;
    };
  }, [swapId, pass.id, view, pass.params?.target, pass.params?.character]);

  const num = (v: string) =>
    v.trim() !== "" && Number.isFinite(Number(v)) ? Number(v) : undefined;

  return (
    <details
      className="rounded border border-border bg-bg text-sm"
      open={stills.length > 0 || making}
    >
      <summary className="cursor-pointer px-2 py-1.5 text-text-muted">
        Redo from an edited still (Viggle)
        {stills.length > 0
          ? ` · ${stills.length} still${stills.length === 1 ? "" : "s"}`
          : ""}
      </summary>
      <div className="space-y-3 border-t border-border p-3">
        <p className="max-w-3xl text-xs text-text-muted">
          Use this when the normal swap pastes the reference photo, for example
          when the person is seen from behind or the face is tiny. The scene’s
          first frame is edited into the character, then Viggle animates that
          still with the scene’s movement.
        </p>
        <div className="flex flex-wrap gap-3">
          <div className="w-32 shrink-0">
            {thumb ? (
              <img
                src={thumb}
                alt=""
                className="w-full rounded bg-black object-contain"
                style={{ aspectRatio: aspect }}
              />
            ) : (
              <div
                className="w-full rounded bg-bg-alt"
                style={{ aspectRatio: aspect }}
              />
            )}
            <div className="mt-0.5 text-center text-[10px] uppercase tracking-wide text-text-muted">
              first frame
            </div>
          </div>
          <div className="min-w-64 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-xs text-text-muted">The person is</label>
              <select
                value={view}
                onChange={(e) => setView(e.target.value as "front" | "behind")}
                disabled={sceneBusy}
              >
                <option value="front">seen from the front or side</option>
                <option value="behind">seen from behind</option>
              </select>
            </div>
            <textarea
              className="h-28 w-full text-xs"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              readOnly={sceneBusy}
              aria-label="Instruction for editing the first frame"
            />
            {promptError && (
              <div className="text-xs text-danger">{promptError}</div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-xs text-text-muted">Stills</label>
              <input
                className="w-14 py-0.5 text-xs"
                type="number"
                min={1}
                max={8}
                value={count}
                onChange={(e) => setCount(e.target.value)}
              />
              <input
                className="w-28 py-0.5 text-xs"
                placeholder="Seed"
                value={stillSeed}
                onChange={(e) =>
                  setStillSeed(e.target.value.replace(/[^0-9]/g, ""))
                }
                title="First seed; each further still adds 101. Empty = the pass seed"
              />
              <button
                className="py-0.5 text-xs"
                disabled={sceneBusy || !prompt.trim() || makeStills.isPending}
                onClick={() =>
                  makeStills.mutate({
                    passId: pass.id,
                    prompt,
                    count: Math.min(8, Math.max(1, num(count) ?? 4)),
                    seed: num(stillSeed),
                  })
                }
              >
                {making ? "Making stills…" : "Make stills"}
              </button>
              {making && (
                <span className="text-xs text-text-muted">
                  {stills.length} made so far; each takes about a minute.
                </span>
              )}
            </div>
          </div>
        </div>
        {pass.still_error && (
          <div className="text-xs text-danger">{pass.still_error}</div>
        )}

        {stills.length > 0 && (
          <>
            <div className="flex flex-wrap gap-2">
              {stills.map((s) => (
                <div key={s.id} className="relative">
                  <button
                    className={`block w-28 overflow-hidden rounded border-2 p-0 ${picked === s.id ? "border-accent" : "border-border"}`}
                    onClick={() => setPicked(s.id)}
                    title={`seed ${s.seed}`}
                  >
                    <img
                      src={mediaUrl(s.url) ?? ""}
                      alt={`still, seed ${s.seed}`}
                      className="w-full object-contain"
                      style={{ aspectRatio: aspect }}
                    />
                  </button>
                  <button
                    className="absolute right-1 top-1 rounded bg-black/60 p-1 text-white"
                    title="Delete this still"
                    aria-label="Delete this still"
                    disabled={sceneBusy}
                    onClick={() => {
                      if (picked === s.id) setPicked(null);
                      deleteStill.mutate({ passId: pass.id, stillId: s.id });
                    }}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-text-muted">
                {chosen
                  ? `Selected: seed ${chosen.seed}`
                  : "Click a still to select it"}
              </span>
              <select
                value={size}
                onChange={(e) => setSize(e.target.value)}
                title="Render size (shorter side)"
              >
                <option value="320">320p (fast test)</option>
                <option value="480">480p</option>
                <option value="640">640p</option>
              </select>
              <input
                className="w-28 py-0.5 text-xs"
                placeholder="Seed"
                value={runSeed}
                onChange={(e) =>
                  setRunSeed(e.target.value.replace(/[^0-9]/g, ""))
                }
                title="Seed for the animation; empty = the pass seed"
              />
              <button
                disabled={!chosen || sceneBusy || viggle.isPending}
                onClick={() =>
                  chosen &&
                  viggle.mutate({
                    passId: pass.id,
                    stillId: chosen.id,
                    size: Number(size),
                    seed: num(runSeed),
                  })
                }
              >
                Animate with Viggle
              </button>
            </div>
          </>
        )}
      </div>
    </details>
  );
}
