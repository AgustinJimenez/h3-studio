import { useEffect, useRef, useState } from "react";
import type { MediaPlayerInstance } from "@vidstack/react";
import VideoPlayer from "./VideoPlayer";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { mediaUrl } from "../lib/api";
import type { SwapScene } from "../schemas";

export type PlaylistItem = { scene: SwapScene; resultUrl: string | null; label: string }; // null: not swapped, original footage

// Plays every finished scene as original | swapped, one after another, and starts over at the end. Only one pair of
// <video>s is ever mounted (and only once started): many decoding videos at once starve the GPU ComfyUI renders on.
export default function SwapPlaylist({
  items,
  sourceUrl,
  fps,
  aspect,
}: {
  items: PlaylistItem[];
  sourceUrl?: string | null;
  fps: number;
  aspect: number;
}) {
  const [started, setStarted] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [index, setIndex] = useState(0);
  const original = useRef<MediaPlayerInstance>(null);
  const result = useRef<MediaPlayerInstance>(null);
  const item = items[index % Math.max(1, items.length)];
  const src = mediaUrl(item?.scene.clip_url); // this scene's own clip of the original

  useEffect(() => {
    if (!started || !item) return;
    const a = original.current;
    const b = result.current;
    if (!a || !b) return;
    a.currentTime = 0;
    b.currentTime = 0;
    if (playing) {
      void a.play();
      void b.play();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, started, item?.resultUrl]);

  if (items.length === 0 || !src) return null;
  const next = () => setIndex((i) => (i + 1) % items.length);
  const prev = () => setIndex((i) => (i - 1 + items.length) % items.length);

  function toggle() {
    if (!started) {
      setStarted(true);
      setPlaying(true);
      return;
    }
    const a = original.current;
    const b = result.current;
    if (playing) {
      a?.pause();
      b?.pause();
      setPlaying(false);
    } else {
      void a?.play();
      void b?.play();
      setPlaying(true);
    }
  }

  return (
    <div className="mb-6 rounded-lg border border-border bg-bg-alt p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <button className="flex items-center gap-1 py-0.5" onClick={toggle}>
          {playing ? <Pause size={14} /> : <Play size={14} />} {playing ? "Pause" : "Play all in a loop"}
        </button>
        <button className="py-0.5" onClick={prev} title="Previous scene" aria-label="Previous scene">
          <SkipBack size={14} />
        </button>
        <button className="py-0.5" onClick={next} title="Next scene" aria-label="Next scene">
          <SkipForward size={14} />
        </button>
        <span className="text-text-h">
          Scene {item.scene.index + 1} <span className="text-xs text-text-muted">({index + 1}/{items.length}) · {item.label}</span>
        </span>
      </div>
      {started && (
        <div className="grid max-w-3xl grid-cols-2 gap-2">
          <figure className="m-0">
            <VideoPlayer
              playerRef={original}
              key={`o-${index}`}
              src={src}
              muted
              controls={false}
              autoPlay={playing}
              {...(item.resultUrl ? {} : { onEnded: next })}
              className="w-full rounded border border-border bg-black"
              style={{ aspectRatio: aspect }}
            />
            <figcaption className="mt-0.5 text-center text-[10px] uppercase tracking-wide text-text-muted">Original</figcaption>
          </figure>
          {item.resultUrl ? (
          <figure className="m-0">
            <VideoPlayer
              playerRef={result}
              key={`r-${index}`}
              src={mediaUrl(item.resultUrl)}
              muted
              controls={false}
              autoPlay={playing}
              onEnded={next}
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
      )}
    </div>
  );
}
