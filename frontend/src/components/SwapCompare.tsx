import { useEffect, useRef, useState } from "react";
import type { MediaPlayerInstance } from "@vidstack/react";
import VideoPlayer from "./VideoPlayer";
import { Pause, Play } from "lucide-react";
import { mediaUrl } from "../lib/api";
import type { SwapScene } from "../schemas";

// The scene of the original video next to the swapped result, started together, so both can be checked at once.
export type TrimInfo = { kept: number; raw: number; sceneFrames: number; onApply: (frames: number) => void };

export type ResultMeta = { width: number; height: number; quality: string; seed: number; testSize: boolean };

export default function SwapCompare({
  scene,
  sourceUrl,
  fps,
  resultUrl,
  resultLabel,
  aspect,
  idle,
  showTitle = true,
  meta,
  onFullRun,
  trim,
  originalUrl,
}: {
  originalUrl?: string | null; // another clip for the original side (the full render's source), instead of the scene's own
  trim?: TrimInfo; // frames kept of the full render (only for the result in use)
  showTitle?: boolean;
  meta?: ResultMeta;
  onFullRun?: () => void; // re-run this scene at the project's full size with the same seed
  idle: boolean; // no render running: safe to decode videos. While one runs they stay unloaded (they starve the GPU).
  scene: SwapScene;
  sourceUrl?: string | null;
  fps: number;
  resultUrl?: string | null;
  resultLabel: string;
  aspect: number;
}) {
  const original = useRef<MediaPlayerInstance>(null);
  const result = useRef<MediaPlayerInstance>(null);
  const lastRestart = useRef(0);
  const [playing, setPlaying] = useState(false);
  // The <video>s mount on the first "Play both": many decoding videos at once starve the GPU ComfyUI renders on.
  const [asked, setAsked] = useState(false);
  const loaded = asked || idle;
  const src = mediaUrl(originalUrl ?? scene.clip_url); // the scene's own clip of the original
  const out = mediaUrl(resultUrl);

  // Playing by default whenever nothing is rendering (the players themselves start once they scroll into view).
  useEffect(() => {
    setPlaying(idle);
  }, [idle, resultUrl]);

  if (!src) return null;

  function restart() {
    const a = original.current;
    const b = result.current;
    if (!a || !b) return;
    // both ended at about the same time: restart once, together
    if (Date.now() - lastRestart.current < 300) return;
    lastRestart.current = Date.now();
    a.currentTime = 0;
    b.currentTime = 0;
    void a.play();
    void b.play();
  }

  // Each side loops on its own (the scene is the same length on both, so they stay together).
  function replay(ref: React.RefObject<MediaPlayerInstance | null>, from: number) {
    const v = ref.current;
    if (!v) return;
    v.currentTime = from;
    void v.play();
  }

  function toggle() {
    if (!loaded) return firstPlay();
    const a = original.current;
    const b = result.current;
    if (!a || !b) return;
    if (playing) {
      a.pause();
      b.pause();
      setPlaying(false);
    } else {
      restart();
      setPlaying(true);
    }
  }

  function firstPlay() {
    setAsked(true);
    setPlaying(true);
    // restart() runs once the elements exist
    window.setTimeout(restart, 150);
  }

  return (
    <div>
      <div className="mb-1 flex items-center gap-2 text-xs text-text-muted">
        {showTitle && <span className="font-medium text-text-h">Scene {scene.index + 1}</span>}
        <span>{resultLabel}</span>
        <button className="ml-auto flex items-center gap-1 py-0.5 text-xs" onClick={toggle}>
          {playing ? <Pause size={12} /> : <Play size={12} />} {playing ? "Pause both" : "Play both"}
        </button>
      </div>
      {!loaded ? (
        <div className="flex max-w-3xl items-center justify-center rounded border border-border bg-bg p-6 text-xs text-text-muted">
          A render is running, so the videos stay unloaded to keep the GPU free. Press “Play both” to load them anyway.
        </div>
      ) : (
      <div className="flex flex-wrap items-start gap-4">
      <div className="grid w-full max-w-3xl grid-cols-2 gap-2 lg:w-[46rem]">
        <figure className="m-0">
          <VideoPlayer
            playerRef={original}
            src={src}
            muted
            controls={false}
            autoPlay={loaded}
            onEnded={() => replay(original, 0)}
            className="w-full rounded border border-border bg-black"
            style={{ aspectRatio: aspect }}
          />
          <figcaption className="mt-0.5 text-center text-[10px] uppercase tracking-wide text-text-muted">Original</figcaption>
        </figure>
        {out ? (
        <figure className="m-0">
          <VideoPlayer
            playerRef={result}
            src={out}
            muted
            controls={false}
            autoPlay={loaded}
            onEnded={() => replay(result, 0)}
            className="w-full rounded border border-border bg-black"
            style={{ aspectRatio: aspect }}
          />
          <figcaption className="mt-0.5 text-center text-[10px] uppercase tracking-wide text-text-muted">Swapped</figcaption>
        </figure>
        ) : (
          <figure className="m-0">
            <div
              className="flex w-full items-center justify-center rounded border border-dashed border-border p-4 text-center text-xs text-text-muted"
              style={{ aspectRatio: aspect }}
            >
              Not swapped: this scene keeps the original footage.
            </div>
            <figcaption className="mt-0.5 text-center text-[10px] uppercase tracking-wide text-text-muted">Final video</figcaption>
          </figure>
        )}
      </div>
      {meta && <ResultInfo meta={meta} onFullRun={onFullRun} trim={trim} />}
      </div>
      )}
    </div>
  );
}

// What the swapped video was rendered with, in the free space beside the pair (visible while scrolling).
function ResultInfo({ meta, onFullRun, trim }: { meta: ResultMeta; onFullRun?: () => void; trim?: TrimInfo }) {
  const tone = meta.testSize ? "border-amber-500/60 text-amber-300" : meta.quality === "final" ? "border-emerald-600/60 text-emerald-300" : "border-border text-text-muted";
  return (
    <div className={`w-52 shrink-0 space-y-1 rounded border px-3 py-2 text-xs ${tone}`}>
      <div className="text-sm font-semibold uppercase tracking-wide">{meta.quality}</div>
      <div>
        <span className="opacity-70">Resolution </span>
        {meta.width}×{meta.height}
      </div>
      <div>
        <span className="opacity-70">Seed </span>
        {meta.seed}
      </div>
      {trim && <TrimControl trim={trim} />}
      {meta.testSize && (
        <>
          <div className="font-semibold uppercase">Test size</div>
          {onFullRun && (
            <button className="mt-1 w-full py-0.5 text-xs" onClick={onFullRun} title="Same seed, the project's full size">
              Run at full size (seed {meta.seed})
            </button>
          )}
        </>
      )}
    </div>
  );
}

// The render is always at least 124 frames; the scene itself is shorter. The result is cut to the scene's length by default
// and can be cut anywhere (it is always re-cut from the full render, so it can also grow back).
function TrimControl({ trim }: { trim: TrimInfo }) {
  const [value, setValue] = useState(String(trim.kept));
  const n = Number(value);
  const valid = Number.isInteger(n) && n >= 1 && n <= trim.raw;
  return (
    <div className="space-y-1 border-t border-border/60 pt-1">
      <div className="opacity-70">
        Frames kept (24 fps) · render {trim.raw}, scene {trim.sceneFrames}
      </div>
      <div className="flex items-center gap-1">
        <input className="w-16 py-0.5 text-xs" inputMode="numeric" value={value} onChange={(e) => setValue(e.target.value.replace(/[^0-9]/g, ""))} />
        <span className="opacity-70">= {valid ? (n / 24).toFixed(2) : "?"}s</span>
        <button className="ml-auto py-0.5 text-xs" disabled={!valid || n === trim.kept} onClick={() => trim.onApply(n)}>
          Trim
        </button>
      </div>
      {trim.kept !== trim.sceneFrames && (
        <button className="w-full py-0.5 text-xs" onClick={() => trim.onApply(trim.sceneFrames)}>
          Back to the scene's {trim.sceneFrames} frames
        </button>
      )}
    </div>
  );
}
