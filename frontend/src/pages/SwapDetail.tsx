import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { ArrowLeft, ChevronDown, ChevronRight, Dices } from "lucide-react";
import {
  useAssembleSwap,
  useCancelPass,
  useDetectScenes,
  useMergeScenes,
  usePatchPass,
  usePatchSwap,
  useRerunPass,
  useRunSwap,
  useSetCuts,
  useConfirmScenes,
  useSwap,
  useSwapCharacters,
  useUseRun,
  useDeleteRun,
  useTrimPass,
} from "../lib/swapQueries";
import { mediaUrl } from "../lib/api";
import CutEditor from "../components/CutEditor";
import ReferenceThumb from "../components/ReferenceThumb";
import SwapPassRow from "../components/SwapPassRow";
import SwapSceneCard from "../components/SwapSceneCard";
import SwapSceneResults from "../components/SwapSceneResults";
import SwapCompare, { type ResultMeta } from "../components/SwapCompare";
import SwapPlaylist, { type PlaylistItem } from "../components/SwapPlaylist";
import VideoPlayer from "../components/VideoPlayer";
import type { SwapCastEntry, SwapPass } from "../schemas";

const newId = () =>
  crypto.randomUUID
    ? crypto.randomUUID().replace(/-/g, "")
    : String(Date.now()) + Math.random().toString(16).slice(2);

function Section({
  title,
  children,
  defaultOpen = true,
  summary,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  summary?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="mb-8">
      <button
        className="mb-3 flex w-full items-center gap-2 border-0 border-b border-border bg-transparent px-0 pb-1 text-left"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {open ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        <h2 className="text-xl font-semibold text-text-h">{title}</h2>
        {!open && summary && (
          <span className="ml-2 text-xs font-normal text-text-muted">
            {summary}
          </span>
        )}
      </button>
      {open && children}
    </section>
  );
}

// What the result was rendered with; "test size" when it is smaller than the project's size (a quick 320p try, say).
function metaOf(
  params: SwapPass["params"],
  settings: { width: number; height: number },
): ResultMeta | undefined {
  if (!params) return undefined;
  return {
    width: params.width,
    height: params.height,
    quality: params.quality ?? (params.turbo ? "preview" : "final"),
    seed: params.seed,
    testSize:
      Math.min(params.width, params.height) <
      Math.min(settings.width, settings.height),
  };
}

export default function SwapDetail() {
  const { id } = useParams({ from: "/swaps/$id" });
  const { data: project, error } = useSwap(id);
  const { data: library } = useSwapCharacters();
  const sortedLibrary = useMemo(
    () =>
      [...(library ?? [])].sort(
        (a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }) || a.video_title.localeCompare(b.video_title, undefined, { sensitivity: "base" }),
      ),
    [library],
  );
  const detect = useDetectScenes(id);
  const patch = usePatchSwap(id);
  const merge = useMergeScenes(id);
  const setCuts = useSetCuts(id);
  const confirmScenes = useConfirmScenes(id);
  const [cutsDirty, setCutsDirty] = useState(false);
  const run = useRunSwap(id);
  const rerun = useRerunPass(id);
  const cancel = useCancelPass(id);
  const savePrompt = usePatchPass(id);
  const assemble = useAssembleSwap(id);
  const useRun = useUseRun(id);
  const deleteRun = useDeleteRun(id);
  const trimPass = useTrimPass(id);

  const [cast, setCast] = useState<SwapCastEntry[]>([]);
  const [castLoaded, setCastLoaded] = useState(false);
  const [quality, setQuality] = useState("final");
  const [size, setSize] = useState(""); // "" = project default; otherwise the shorter side in px for the next runs
  const [splitTab, setSplitTab] = useState<"auto" | "manual">("auto");
  const [playMode, setPlayMode] = useState<"individual" | "loop">("individual");
  const [seed, setSeed] = useState(""); // "" = project seed
  const overrides = {
    ...(size ? { size: Number(size) } : {}),
    ...(seed.trim() !== "" && Number.isFinite(Number(seed))
      ? { seed: Number(seed) }
      : {}),
  };
  // A seed typed on one scene's pass wins over the one at the top, for that scene's run only.
  const withSeed = (own?: number) => (own !== undefined && Number.isFinite(own) ? { ...overrides, seed: own } : overrides);

  useEffect(() => {
    if (project && !castLoaded) {
      setCast(project.cast);
      setQuality(project.settings.quality);
      setCastLoaded(true);
    }
  }, [project, castLoaded]);

  if (error)
    return <div className="p-6 text-danger">{(error as Error).message}</div>;
  if (!project) return <div className="p-6 text-text-muted">Loading…</div>;

  const hasScenes = project.scenes.length > 0;
  const castSaved = hasScenes && project.scenes_confirmed && project.cast.length > 0; // scenes and run open once a cast is saved
  const confirmed = hasScenes && project.scenes_confirmed; // the cuts are final: the next steps open
  const busy =
    patch.isPending ||
    merge.isPending ||
    setCuts.isPending ||
    confirmScenes.isPending ||
    run.isPending ||
    detect.isPending;
  const castName = (castId: string | null) =>
    project.cast.find((c) => c.id === castId)?.name || "person";
  const personLabel = (sceneIndex: number, personId: string) => {
    const person = project.scenes
      .find((s) => s.index === sceneIndex)
      ?.people.find((p) => p.id === personId);
    return `Scene ${sceneIndex + 1} · ${castName(person?.cast_id ?? null)}`;
  };
  const previewOnlyScenes = Array.from(
    new Set(
      project.passes
        .filter((p) => p.status === "done" && p.quality === "preview")
        .map((p) => p.scene_index + 1),
    ),
  );
  // Every scene in order, so the loop plays the whole video: swapped scenes with their result, the rest as original footage.
  const playlist: PlaylistItem[] = project.scenes.map((s) => {
    const last = project.passes
      .filter((p) => p.scene_index === s.index && p.status === "done")
      .sort((a, b) => b.order - a.order)[0];
    const hasPasses = project.passes.some((p) => p.scene_index === s.index);
    if (!last?.output_url)
      return {
        scene: s,
        resultUrl: null,
        label: hasPasses ? "not rendered yet" : "original footage",
      };
    const m = metaOf(last.params, project.settings);
    const label = m
      ? `${m.quality} · ${m.width}×${m.height} · seed ${m.seed}${m.testSize ? " · test size" : ""}`
      : `result (${last.quality})`;
    return { scene: s, resultUrl: last.output_url, label };
  });
  const activeCount = project.passes.filter(
    (p) => p.status === "queued" || p.status === "running",
  ).length;
  const doneCount = project.passes.filter((p) => p.status === "done").length;

  function updateCast(i: number, fields: Partial<SwapCastEntry>) {
    setCast(cast.map((c, j) => (j === i ? { ...c, ...fields } : c)));
  }

  return (
    <div className="mx-auto max-w-5xl px-4 pb-52 pt-6">
      <Link
        to="/swaps"
        className="mb-1 inline-flex items-center gap-1 text-sm text-text-muted no-underline"
      >
        <ArrowLeft size={14} /> Character swap
      </Link>
      <h1 className="mb-6 text-3xl font-bold tracking-tight text-text-h">
        {project.title}
      </h1>

      <Section title="1 · Source">
        <div className="flex flex-wrap gap-4">
          <VideoPlayer
            className="max-h-80 rounded border border-border"
            src={mediaUrl(project.source_url)}
          />
          <div className="space-y-1 text-sm text-text-muted">
            <div>
              {project.source.width}×{project.source.height} ·{" "}
              {project.source.fps.toFixed(1)} fps · {project.source.frames}{" "}
              frames · {project.source.duration.toFixed(1)}s ·{" "}
              {project.source.has_audio ? "with audio" : "no audio"}
            </div>
            <div>
              Rendered at {project.settings.width}×{project.settings.height}, 24
              fps.
            </div>
            <p className="max-w-md text-xs">
              The MiniMax H3 licence excludes some territories (see the H3
              licence); check it before sharing results.
            </p>
          </div>
        </div>
        {confirmed ? (
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-bg-alt px-3 py-2 text-sm">
            <span className="text-text-h">
              <strong>{project.scenes.length}</strong> scenes confirmed
            </span>
            <span className="text-xs text-text-muted">
              {project.scenes
                .map((s) => `${s.start_frame_src}–${s.end_frame_src}`)
                .join(" · ")}
            </span>
            <button
              className="ml-auto py-0.5 text-xs"
              disabled={busy || activeCount > 0}
              onClick={() => confirmScenes.mutate(false)}
            >
              Edit cuts
            </button>
          </div>
        ) : (
          <>
            <h3 className="mb-1.5 mt-5 text-sm font-semibold text-text-h">
              Split into scenes
            </h3>
            <div className="mt-4 overflow-hidden rounded-lg border border-border bg-bg-alt">
              <div
                className="flex items-center gap-1 border-b border-border px-2 pt-1"
                role="tablist"
                aria-label="Split the video into scenes"
              >
                {(
                  [
                    ["auto", "Automatic detection"],
                    ["manual", "Manual split"],
                  ] as const
                ).map(([t, label]) => (
                  <button
                    key={t}
                    role="tab"
                    aria-selected={splitTab === t}
                    className={`-mb-px rounded-none rounded-t-md border-0 border-b-2 bg-transparent px-3 py-1.5 text-sm ${
                      splitTab === t
                        ? "border-accent font-semibold text-text-h"
                        : "border-transparent text-text-muted"
                    }`}
                    onClick={() => setSplitTab(t)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="p-3" role="tabpanel">
                {splitTab === "auto" ? (
                  <div className="space-y-2 text-sm text-text-muted">
                    <p className="max-w-xl text-xs">
                      Finds hard cuts by comparing neighbouring frames.
                      Dissolves and fades are usually missed; correct those in
                      Manual split.
                    </p>
                    <button
                      disabled={busy || activeCount > 0}
                      onClick={() => detect.mutate()}
                    >
                      {hasScenes ? "Detect scenes again" : "Detect scenes"}
                    </button>
                  </div>
                ) : (
                  <CutEditor
                    sourceId={id}
                    frames={project.source.frames}
                    fps={project.source.fps}
                    aspect={
                      project.source.width / Math.max(1, project.source.height)
                    }
                    cuts={project.scenes
                      .map((s) => s.start_frame_src)
                      .filter((f) => f > 0)}
                    hasWork={project.passes.length > 0}
                    hasScenes={hasScenes}
                    busy={busy || activeCount > 0}
                    onApply={(cuts) => setCuts.mutate(cuts)}
                    onDirtyChange={setCutsDirty}
                  />
                )}
              </div>
            </div>
            {hasScenes && (
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <button
                  disabled={busy || cutsDirty}
                  onClick={() => confirmScenes.mutate(true)}
                >
                  Confirm {project.scenes.length} scenes and continue
                </button>
                <span className="text-xs text-text-muted">
                  {cutsDirty
                    ? "Apply or reset your cut changes first."
                    : "The cast, scenes and run steps open once the cuts are final."}
                </span>
              </div>
            )}
          </>
        )}
      </Section>

      {confirmed && (
        <Section
          title="2 · Cast"
          defaultOpen={project.passes.length === 0}
          summary={
            project.cast.map((c) => c.name || "(unnamed)").join(", ") ||
            "no characters"
          }
        >
          <div className="space-y-3">
            {cast.map((c, i) => (
              <div
                key={c.id}
                className="flex gap-3 rounded-lg border border-border bg-bg-alt p-3"
              >
                <ReferenceThumb type="image" path={c.image_path} size="lg" />
                <div className="grid flex-1 gap-2">
                  <input
                    placeholder="Name"
                    value={c.name}
                    onChange={(e) => updateCast(i, { name: e.target.value })}
                  />
                  <input
                    placeholder="Appearance, e.g. a slim woman with long dark hair"
                    value={c.appearance}
                    onChange={(e) =>
                      updateCast(i, { appearance: e.target.value })
                    }
                  />
                  <input
                    placeholder="Outfit, fixed for every scene, e.g. a green satin dress"
                    value={c.outfit}
                    onChange={(e) => updateCast(i, { outfit: e.target.value })}
                  />
                  <input
                    placeholder="Body (optional), e.g. slim"
                    value={c.body}
                    onChange={(e) => updateCast(i, { body: e.target.value })}
                  />
                </div>
                <button
                  className="self-start py-0.5 text-xs"
                  onClick={() => setCast(cast.filter((_, j) => j !== i))}
                >
                  Remove
                </button>
              </div>
            ))}
            <div className="flex flex-wrap items-center gap-2">
              <select
                value=""
                onChange={(e) => {
                  const ch = library?.find(
                    (l) => `${l.video_id}/${l.character_id}` === e.target.value,
                  );
                  if (ch)
                    setCast([
                      ...cast,
                      {
                        id: newId(),
                        name: ch.name,
                        image_path: ch.image_path,
                        appearance: ch.appearance,
                        outfit: ch.outfit,
                        body: "",
                        source_character_id: ch.character_id,
                      },
                    ]);
                }}
              >
                <option value="">Add from a character…</option>
                {sortedLibrary.map((l) => (
                  <option
                    key={`${l.video_id}/${l.character_id}`}
                    value={`${l.video_id}/${l.character_id}`}
                  >
                    {l.name} ({l.video_title})
                  </option>
                ))}
              </select>
              <button
                disabled={busy}
                onClick={() =>
                  patch.mutate({ cast }, { onSuccess: () => undefined })
                }
              >
                Save cast
              </button>
              {!castSaved && (
                <span className="text-xs text-text-muted">
                  Add at least one character and save the cast to continue.
                </span>
              )}
            </div>
          </div>
        </Section>
      )}

      {castSaved && (
        <Section
          title="3 · Scenes"
          summary={`${project.scenes.length} scenes · ${new Set(project.passes.map((p) => p.scene_index)).size} with swaps · ${doneCount}/${project.passes.length} passes done`}
        >
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <select value={quality} onChange={(e) => setQuality(e.target.value)}>
              <option value="preview">Preview (turbo, 4 steps, fast)</option>
              <option value="accel8">Accel 8 steps (experimental LoRA)</option>
              <option value="final">Final (20 steps, slow)</option>
            </select>
            <select value={size} onChange={(e) => setSize(e.target.value)} title="Render size for the next runs (shorter side)">
              <option value="">
                Size: project ({project.settings.width}×{project.settings.height})
              </option>
              <option value="320">320p (fast test)</option>
              <option value="480">480p</option>
              <option value="640">640p</option>
              <option value="832">832p</option>
            </select>
            <div className="relative w-44">
              <input
                className="w-full pr-8"
                placeholder={`Seed (${project.settings.seed})`}
                value={seed}
                onChange={(e) => setSeed(e.target.value.replace(/[^0-9]/g, ""))}
                title="Seed for the next runs; empty = project seed"
              />
              <button
                type="button"
                className="absolute right-1 top-1/2 -translate-y-1/2 border-0 bg-transparent p-1 text-text-muted hover:text-text-h"
                title="Random seed"
                aria-label="Random seed"
                onClick={() => setSeed(String(Math.floor(Math.random() * 1_000_000)))}
              >
                <Dices size={16} />
              </button>
            </div>
          </div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <button disabled={busy || project.passes.length === 0} onClick={() => run.mutate({ quality, sceneIndex: null, overrides })}>
              Run all
            </button>
            <span className="text-xs text-text-muted">
              {doneCount}/{project.passes.length} passes done
              {activeCount > 0 ? ` · ${activeCount} queued/running` : ""}
            </span>
          </div>
          <p className="mb-2 text-xs text-text-muted">
            Say who is replaced in each scene and save it: that plans the scene and builds its prompt. Scenes without anyone assigned keep the original
            footage.
          </p>
          {previewOnlyScenes.length > 0 && (
            <div className="mb-2 rounded border border-amber-500/50 px-3 py-2 text-xs text-amber-400">
              Scenes {previewOnlyScenes.join(", ")} only have preview renders (turbo: softer, can show colour drift). Pick Final and press “Re-run” on a scene
              (only that scene is re-planned and re-rendered) or “Run all” for the deliverable.
            </div>
          )}

          {project.passes.some((p) => p.status === "done") && (
            <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
              <span className="text-text-muted">Playback</span>
              <div className="inline-flex overflow-hidden rounded-lg border border-border">
                {(
                  [
                    ["individual", "Each scene on its own"],
                    ["loop", "Loop all scenes"],
                  ] as const
                ).map(([mode, label]) => (
                  <button
                    key={mode}
                    className={`rounded-none border-0 px-3 py-1 text-xs ${playMode === mode ? "bg-accent text-white" : "bg-transparent"}`}
                    aria-pressed={playMode === mode}
                    onClick={() => setPlayMode(mode)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}
          {playMode === "loop" && (
            <SwapPlaylist items={playlist} sourceUrl={project.source_url} fps={project.source.fps} aspect={project.source.width / Math.max(1, project.source.height)} />
          )}

          <div className="space-y-4">
            {project.scenes.map((s, i) => {
              const passes = project.passes.filter((p) => p.scene_index === s.index);
              const last = passes.filter((p) => p.status === "done").sort((a, b) => b.order - a.order)[0];
              const aspect = project.source.width / Math.max(1, project.source.height);
              return (
                <SwapSceneCard
                  key={`${s.start_frame_src}-${s.end_frame_src}-${project.cast.length}`}
                  scene={s}
                  sourceUrl={project.source_url}
                  fps={project.source.fps}
                  aspect={aspect}
                  cast={project.cast}
                  isLast={i === project.scenes.length - 1}
                  busy={busy}
                  sceneBusy={passes.some((p) => p.status === "queued" || p.status === "running")}
                  hasResults={passes.some((p) => p.status === "done")}
                  hideMedia={playMode === "individual" && !!last}
                  onSave={(p) => patch.mutate({ scenes: [p] })}
                  onMerge={() => merge.mutate(s.index)}
                >
                  {passes.length > 0 && (
                    <div className="space-y-2">
                      {passes.map((p) => (
                        <SwapPassRow
                          key={p.id}
                          pass={p}
                          label={personLabel(p.scene_index, p.person_id)}
                          onSavePrompt={(prompt) => savePrompt.mutate({ passId: p.id, prompt })}
                          onRun={(ownSeed) => run.mutate({ quality, sceneIndex: p.scene_index, overrides: withSeed(ownSeed) })}
                          onRerun={(ownSeed) =>
                            // Another quality than the pass was planned with: the scene is re-planned at the chosen one, then run.
                            p.quality !== quality
                              ? run.mutate({ quality, sceneIndex: p.scene_index, overrides: withSeed(ownSeed) })
                              : rerun.mutate({ passId: p.id, overrides: withSeed(ownSeed) })
                          }
                          onCancel={() => cancel.mutate(p.id)}
                        />
                      ))}
                      {playMode === "individual" && last && (
                        <SwapSceneResults
                          scene={s}
                          pass={last}
                          sourceUrl={project.source_url}
                          fps={project.source.fps}
                          aspect={aspect}
                          idle={activeCount === 0}
                          projectSize={project.settings}
                          onUse={(runId) => useRun.mutate({ passId: last.id, runId })}
                          onDelete={(runId) => deleteRun.mutate({ passId: last.id, runId })}
                          onTrim={(frames) => trimPass.mutate({ passId: last.id, frames })}
                          onFullRun={(runSeed) =>
                            rerun.mutate({
                              passId: passes.filter((p) => p.chunk_index === last.chunk_index).sort((a, b) => a.order - b.order)[0].id,
                              overrides: { size: Math.min(project.settings.width, project.settings.height), seed: runSeed },
                            })
                          }
                        />
                      )}
                    </div>
                  )}
                </SwapSceneCard>
              );
            })}
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-border pt-4">
            <button disabled={busy || assemble.isPending || activeCount > 0} onClick={() => assemble.mutate()}>
              {assemble.isPending ? "Assembling…" : "Assemble final video"}
            </button>
            <span className="text-xs text-text-muted">Uses the original audio; scenes without swaps use the original footage.</span>
            <span className="text-xs text-text-muted">{(project.size_bytes / 1e6).toFixed(0)} MB on disk</span>
          </div>
          {project.final.error && <div className="mt-2 text-xs text-danger">{project.final.error}</div>}
          {project.final_url && (
            <div className="mt-3">
              <VideoPlayer className="max-h-96 rounded border border-border" src={mediaUrl(project.final_url)} />
              <a className="mt-1 inline-block text-sm" href={mediaUrl(project.final_url) ?? "#"} download>
                Download
              </a>
            </div>
          )}
        </Section>
      )}
    </div>
  );
}
