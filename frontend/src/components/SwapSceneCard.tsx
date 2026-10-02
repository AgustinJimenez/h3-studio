import { useState } from "react";
import VideoPlayer from "./VideoPlayer";
import { Play } from "lucide-react";
import { mediaUrl } from "../lib/api";
import type { SwapCastEntry, SwapScene } from "../schemas";
import type { SwapScenePatch } from "../lib/swapApi";

// Naming a feature the scene lacks makes the model invent it ("keep the stripes" grew light rays).
const RISKY = ["stripe", "ray", "beam", "door", "window", "cabinet"];

type PersonDraft = {
  id?: string;
  cast_id: string | null;
  target_description: string;
  order: number;
};

export default function SwapSceneCard({
  scene,
  cast,
  isLast,
  busy,
  sourceUrl,
  fps,
  aspect,
  onSave,
  onMerge,
  hideMedia = false,
  sceneBusy = false,
  hasResults = false,
  children,
}: {
  sourceUrl?: string | null;
  fps: number;
  aspect: number;
  scene: SwapScene;
  cast: SwapCastEntry[];
  isLast: boolean;
  busy: boolean;
  onSave: (patch: SwapScenePatch) => void;
  onMerge: () => void;
  hideMedia?: boolean; // the result below shows the original beside it, so the still is not repeated
  sceneBusy?: boolean; // this scene has a queued or running pass: it cannot be edited
  hasResults?: boolean; // saving re-plans the scene; earlier results stay in its history
  children?: React.ReactNode; // this scene's runs and results
}) {
  const [background, setBackground] = useState(scene.background_text);
  const [people, setPeople] = useState<PersonDraft[]>(
    scene.people.map((p) => ({ ...p })),
  );
  const warnings = RISKY.filter((w) => background.toLowerCase().includes(w));
  const thumb = mediaUrl(scene.thumb_url);
  const [playing, setPlaying] = useState(false);
  const [replay, setReplay] = useState(0); // remounting the clip player is the simple way to loop a scene's stretch
  const src = mediaUrl(scene.clip_url); // this scene's own clip of the original

  return (
    <div className="space-y-3 rounded-lg border border-border bg-bg-alt p-3">
      <div className="flex gap-3">
        {!hideMedia && (
          <div className="w-72 shrink-0 max-sm:w-40">
            {playing && src ? (
              <VideoPlayer
                key={replay}
                src={src}
                className="w-full rounded bg-black"
                style={{ aspectRatio: aspect }}
                autoPlay
                onEnded={() => setReplay((n) => n + 1)}
              />
            ) : (
              <button
                className="relative block w-full p-0"
                title="Play this scene"
                onClick={() => setPlaying(true)}
                disabled={!src}
              >
                {thumb ? (
                  <img
                    src={thumb}
                    alt=""
                    className="w-full rounded bg-black object-contain"
                    style={{ aspectRatio: aspect }}
                  />
                ) : (
                  <div
                    className="w-full rounded bg-bg"
                    style={{ aspectRatio: aspect }}
                  />
                )}
                <span className="absolute inset-0 flex items-center justify-center">
                  <Play
                    size={36}
                    className="rounded-full bg-black/60 p-1.5 text-white"
                  />
                </span>
              </button>
            )}
            {playing && (
              <button
                className="mt-1 w-full py-0.5 text-xs"
                onClick={() => setPlaying(false)}
              >
                Show still
              </button>
            )}
          </div>
        )}
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-text-h">
              Scene {scene.index + 1}
            </span>
            <span className="text-xs text-text-muted">
              {scene.frames_24} frames · {scene.chunks.length} chunk
              {scene.chunks.length === 1 ? "" : "s"}
            </span>
            {!isLast && (
              <button
                className="ml-auto py-0.5 text-xs"
                disabled={busy || sceneBusy}
                onClick={onMerge}
              >
                Merge with next
              </button>
            )}
          </div>

          <div>
            <label className="text-xs text-text-muted">
              What is in the background (only things that really are there)
            </label>
            <textarea
              className="h-14 w-full text-sm"
              placeholder="Empty = keep the background exactly as in the video"
              value={background}
              onChange={(e) => setBackground(e.target.value)}
            />
            {warnings.length > 0 && (
              <div className="text-xs text-amber-400">
                Risky word{warnings.length > 1 ? "s" : ""}:{" "}
                {warnings.join(", ")} — naming something the scene lacks can
                make the model draw it.
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            {people.map((p, i) => (
              <div
                key={p.id ?? i}
                className="flex flex-wrap items-center gap-2"
              >
                <input
                  className="min-w-[14rem] flex-1 text-sm"
                  placeholder='Who to replace, e.g. "the man on the left in the grey hoodie"'
                  value={p.target_description}
                  onChange={(e) =>
                    setPeople(
                      people.map((x, j) =>
                        j === i
                          ? { ...x, target_description: e.target.value }
                          : x,
                      ),
                    )
                  }
                />
                <select
                  value={p.cast_id ?? ""}
                  onChange={(e) =>
                    setPeople(
                      people.map((x, j) =>
                        j === i ? { ...x, cast_id: e.target.value || null } : x,
                      ),
                    )
                  }
                >
                  <option value="">— character —</option>
                  {cast.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name || "(unnamed)"}
                    </option>
                  ))}
                </select>
                <button
                  className="py-0.5 text-xs"
                  onClick={() =>
                    setPeople(
                      people
                        .filter((_, j) => j !== i)
                        .map((x, j) => ({ ...x, order: j })),
                    )
                  }
                >
                  Remove
                </button>
              </div>
            ))}
            {people.length === 0 && (
              <div className="text-xs text-text-muted">
                Nobody assigned: this scene keeps the original footage.
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <button
                className="py-0.5 text-xs"
                disabled={sceneBusy}
                onClick={() =>
                  setPeople([
                    ...people,
                    {
                      cast_id: null,
                      target_description: "",
                      order: people.length,
                    },
                  ])
                }
              >
                Add person
              </button>
              <button
                className="py-0.5 text-xs"
                disabled={busy || sceneBusy}
                onClick={() =>
                  onSave({
                    index: scene.index,
                    background_text: background,
                    people: people.map((p, i) => ({ ...p, order: i })),
                  })
                }
              >
                Save scene
              </button>
              {sceneBusy ? (
                <span className="text-xs text-text-muted">
                  Queued or running: wait or cancel it to edit this scene.
                </span>
              ) : (
                hasResults && (
                  <span className="text-xs text-text-muted">
                    Saving changes re-plans this scene; its earlier results stay
                    in the history.
                  </span>
                )
              )}
            </div>
          </div>
        </div>
      </div>
      {children}
    </div>
  );
}
