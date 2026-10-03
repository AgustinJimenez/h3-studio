import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { mediaUrl } from "../lib/api";
import {
  wordCount,
  wordCountClass,
  WORD_TARGET_MIN,
  WORD_TARGET_MAX,
} from "../lib/wordCount";
import StatusBadge from "./StatusBadge";
import GenerationParams from "./GenerationParams";
import ShotPromptEditor from "./ShotPromptEditor";
import VideoPlayer from "./VideoPlayer";
import type { Clip, ModelTag, Character } from "../schemas";
import { jobTargetDomId, useFocusTarget } from "../lib/jobFocus";
import StartFramePicker from "./StartFramePicker";
import ControlVideoField from "./ControlVideoField";
import { formatFrames } from "../lib/frames";

// Solid fill + white text, same treatment as StatusBadge elsewhere in the
// app -- a dark outline-only ring read as murky/low-contrast on the dark
// background (bg-alt is near-black), a solid fill doesn't have that problem.
const STATUS_FILL: Record<string, string> = {
  draft: "bg-status-draft",
  queued: "bg-status-queued",
  running: "bg-status-running",
  done: "bg-status-done",
  failed: "bg-status-failed",
};

type ClipFieldsHandlers = {
  onUpdate: (clipId: string, body: Partial<Clip>) => void;
  onGenerate: (clipId: string) => void;
  onAnalyze: (clipId: string) => void;
  onDelete: (clipId: string) => void;
};

// The clip's own video, with the same own-segment/full-chain toggle the List
// view's ClipRow has. Self-contained (owns its own previewFull state) so it
// can be reused unmodified for both the current clip and every peeking
// neighbor in the row.
function ClipVideoBlock({
  clip,
  selected = true,
}: {
  clip: Clip;
  selected?: boolean;
}) {
  const [previewFull, setPreviewFull] = useState(false);
  const hasOwnSegment =
    !!clip.own_segment_url && clip.own_segment_url !== clip.output_url;
  const previewUrl =
    previewFull || !hasOwnSegment ? clip.output_url : clip.own_segment_url;
  // The player takes the clip's own shape (from its render size) so a portrait clip is not letterboxed inside a 16:9 box.
  const size = /^(\d+)x(\d+)$/.exec(String(clip.last_generation_settings?.resolution ?? ""));
  const ratio = size ? Number(size[1]) / Number(size[2]) : 16 / 9;
  const box = { aspectRatio: ratio, height: `min(74vh, ${28 / ratio}rem)`, width: "auto", maxWidth: "100%" } as const;

  if (!previewUrl) {
    return (
      <div style={box} className="mx-auto flex items-center justify-center rounded border border-dashed border-border text-sm opacity-60">
        {clip.status === "running" || clip.status === "queued"
          ? "Generating…"
          : "Not generated yet"}
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center gap-1">
      <VideoPlayer
        key={previewUrl}
        className="mx-auto rounded"
        style={box}
        src={mediaUrl(previewUrl)}
        controls={selected}
      />
      {hasOwnSegment && (
        <button onClick={() => setPreviewFull(!previewFull)}>
          {previewFull
            ? "Show this clip's own segment only"
            : "Show full chain up to this clip"}
        </button>
      )}
    </div>
  );
}

// Seed, frames and the actions of one clip, under its prompt.
function ClipActions({
  clip,
  anyActive,
  analyzing,
  onUpdate,
  onGenerate,
  onAnalyze,
  onDelete,
}: {
  clip: Clip;
  anyActive: boolean;
  analyzing: boolean;
} & ClipFieldsHandlers) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1 text-xs text-text-muted">
        Seed
        <input
          className="w-28"
          type="number"
          value={clip.seed}
          onChange={(e) => onUpdate(clip.id, { seed: Number(e.target.value) })}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-text-muted">
        Frames
        <input
          className="w-24"
          type="number"
          value={clip.video_length}
          onChange={(e) =>
            onUpdate(clip.id, { video_length: Number(e.target.value) })
          }
        />
      </label>
      <span className="pb-2 text-xs text-text-muted">
        {formatFrames(clip.video_length)}
      </span>
      <span className="ml-auto flex items-center gap-2 pb-0.5">
        <button disabled={anyActive} onClick={() => onGenerate(clip.id)}>
          {clip.status === "done" ? "Regenerate" : "Generate"}
        </button>
        {clip.status === "done" && (
          <button
            disabled={anyActive || analyzing}
            onClick={() => onAnalyze(clip.id)}
            title="Check for duplicated/cloned people, ghosting artifacts, and voice consistency"
          >
            {analyzing
              ? "Analyzing…"
              : clip.qa_report
                ? "Re-analyze"
                : "Analyze"}
          </button>
        )}
        <button
          className="border-0 bg-transparent p-0 text-xs text-danger"
          onClick={() => onDelete(clip.id)}
        >
          Delete
        </button>
      </span>
    </div>
  );
}

// The settings that are set once per shot and rarely touched again, behind one collapsed section with a one-line summary.
function ClipSetup({
  clip,
  characters,
  isFirst,
  canBridge,
  onUpdate,
}: {
  clip: Clip;
  characters: Character[];
  isFirst: boolean;
  canBridge: boolean;
  onUpdate: (clipId: string, body: Partial<Clip>) => void;
}) {
  const activeIds = clip.active_character_ids ?? characters.map((c) => c.id);
  const activeNames = characters
    .filter((c) => activeIds.includes(c.id))
    .map((c) => c.name || "(unnamed)");
  const info = clip.control_video_info;
  const bits = [
    clip.continue_from_previous && "continues from the previous clip",
    clip.bridge_to_next && "bridges to the next clip",
    clip.start_frame_path && "first frame set",
    clip.control_video_path &&
      `control video${info ? ` · ${info.frames} frames` : ""}`,
    characters.length > 0 && `characters: ${activeNames.join(", ") || "none"}`,
  ].filter(Boolean) as string[];

  return (
    <details className="rounded-lg border border-border">
      <summary className="cursor-pointer select-none px-3 py-2 text-sm">
        <span className="font-medium text-text-h">Shot setup</span>
        <span className="ml-2 text-xs text-text-muted">
          {bits.join(" · ") || "nothing set"}
        </span>
      </summary>
      <div className="flex flex-col gap-4 border-t border-border p-3">
        <div className="flex flex-col gap-1.5 text-sm">
          <label
            className="flex items-center gap-2"
            title="Real video continuation, not just a shared description: the preceding clip must already be done"
          >
            <input
              type="checkbox"
              checked={!!clip.continue_from_previous}
              disabled={isFirst}
              onChange={(e) =>
                onUpdate(clip.id, {
                  continue_from_previous: e.target.checked,
                  // H3 needs 17n+5 frames of context: without a valid count the generation fails ("got 1").
                  ...(e.target.checked && !clip.continuation_keep_frames
                    ? { continuation_keep_frames: 5 }
                    : {}),
                })
              }
            />
            Continue from the previous clip
          </label>
          {clip.continue_from_previous && (
            <label
              className="ml-6 flex items-center gap-2 whitespace-nowrap text-xs text-text-muted"
              title="How many of the previous clip's last frames H3 takes as context (it needs 17n+5)"
            >
              Context frames
              <select
                className="w-32"
                value={clip.continuation_keep_frames ?? 5}
                onChange={(e) =>
                  onUpdate(clip.id, {
                    continuation_keep_frames: Number(e.target.value),
                  })
                }
              >
                {[5, 22, 39, 56].map((n) => (
                  <option key={n} value={n}>
                    {n} ({(n / 24).toFixed(1)} s)
                  </option>
                ))}
              </select>
            </label>
          )}
          <label
            className="flex items-center gap-2"
            title={
              canBridge
                ? "Steer this regeneration to land back on the next clip's existing first frame, so the rest of the chain does not need to be redone"
                : "The next clip must exist and already be done to bridge into it"
            }
          >
            <input
              type="checkbox"
              checked={!!clip.bridge_to_next}
              disabled={!canBridge}
              onChange={(e) =>
                onUpdate(clip.id, { bridge_to_next: e.target.checked })
              }
            />
            Bridge to the next clip
          </label>
        </div>

        {characters.length > 1 && (
          <fieldset className="flex flex-col gap-1.5 text-sm">
            <legend className="mb-1 text-xs text-text-muted">
              Characters in this shot (unchecked ones are left out of the prompt
              entirely)
            </legend>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {characters.map((character) => {
                const checked = activeIds.includes(character.id);
                return (
                  <label
                    key={character.id}
                    className="flex items-center gap-1.5"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        const next = e.target.checked
                          ? [...activeIds, character.id]
                          : activeIds.filter((id) => id !== character.id);
                        const isFullRoster = characters.every((c) =>
                          next.includes(c.id),
                        );
                        onUpdate(clip.id, {
                          active_character_ids: isFullRoster ? null : next,
                        });
                      }}
                    />
                    {character.name || "(unnamed)"}
                  </label>
                );
              })}
            </div>
          </fieldset>
        )}

        <StartFramePicker
          clip={clip}
          characters={characters}
          onChange={(path) => onUpdate(clip.id, { start_frame_path: path })}
        />
        <ControlVideoField
          clip={clip}
          onChange={(path) => onUpdate(clip.id, { control_video_path: path })}
        />
      </div>
    </details>
  );
}

// What came out of the last generation: the error if it failed, the tail frames, the QA report and the parameters.
function ClipResults({ clip }: { clip: Clip }) {
  const hasDetails = clip.tail_frame_urls.length > 0 || !!clip.qa_report;
  return (
    <>
      {clip.error && (
        <div className="whitespace-pre-wrap rounded border border-danger bg-red-950/30 px-3 py-2 text-sm text-danger">
          {clip.error}
        </div>
      )}
      {hasDetails && (
        <details className="rounded-lg border border-border">
          <summary className="cursor-pointer select-none px-3 py-2 text-sm">
            <span className="font-medium text-text-h">Results</span>
            <span className="ml-2 text-xs text-text-muted">
              {[
                clip.tail_frame_urls.length > 0 && "tail check",
                clip.qa_report && "QA report",
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </summary>
          <div className="flex flex-col gap-3 border-t border-border p-3">
            {clip.tail_frame_urls.length > 0 && (
              <div className="flex flex-col gap-1">
                <span
                  className="text-xs text-text-muted"
                  title="The literal last ~2s of this clip's output: check here for identity clones or blends before trusting it as a continuation source"
                >
                  Tail check (last ~2 s), click a frame to inspect it closely
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {clip.tail_frame_urls.map((url) => (
                    <a
                      key={url}
                      href={mediaUrl(url) ?? undefined}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <img
                        src={mediaUrl(url) ?? undefined}
                        alt="Tail frame"
                        className="h-16 w-auto rounded border border-border object-cover hover:border-accent"
                      />
                    </a>
                  ))}
                </div>
              </div>
            )}
            {clip.qa_report && (
              <div className="flex flex-col gap-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-text-h">QA report</span>
                  <span className="text-xs opacity-60">
                    {new Date(
                      clip.qa_report.analyzed_at * 1000,
                    ).toLocaleString()}
                  </span>
                </div>
                <div>
                  <div className="mb-1 text-xs font-semibold uppercase opacity-60">
                    Visual (duplicates / ghosting)
                  </div>
                  <p className="whitespace-pre-wrap">
                    {clip.qa_report.visual_analysis}
                  </p>
                </div>
                {clip.qa_report.voice_results.length > 0 && (
                  <div>
                    <div className="mb-1 text-xs font-semibold uppercase opacity-60">
                      Voice consistency
                    </div>
                    <div className="flex flex-col gap-1">
                      {clip.qa_report.voice_results.map((r) => (
                        <div
                          key={r.reference_path}
                          className="flex items-center gap-2"
                        >
                          <span
                            className={`rounded-full px-2 py-0.5 text-xs text-white ${r.same_speaker ? "bg-status-done" : "bg-status-failed"}`}
                          >
                            {r.same_speaker ? "matches" : "not detected"}
                          </span>
                          <span className="font-mono text-xs opacity-75">
                            {r.reference_path.split(/[\\/]/).pop()}
                          </span>
                          <span className="text-xs opacity-60">
                            score {r.score.toFixed(2)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </details>
      )}
      <GenerationParams
        settings={clip.last_generation_settings}
        durationSeconds={clip.generation_duration_seconds}
      />
    </>
  );
}

// One small tile per clip: the last frame it made (or a plain tile), its number and its status. Replaces the shrunken neighbour cards.
function Filmstrip({
  clips,
  index,
  onSelect,
}: {
  clips: Clip[];
  index: number;
  onSelect: (i: number) => void;
}) {
  return (
    <div className="flex items-start justify-center gap-2 overflow-x-auto px-1 py-1">
      {clips.map((c, i) => {
        const poster = mediaUrl(
          c.tail_frame_urls[c.tail_frame_urls.length - 1] ?? null,
        );
        const on = i === index;
        return (
          <button
            key={c.id}
            onClick={() => onSelect(i)}
            title={`Clip #${c.order} · ${c.status}`}
            className={`relative aspect-[3/4] w-24 shrink-0 overflow-hidden rounded-lg border-2 bg-bg-alt p-0 ${on ? "border-accent" : "border-border opacity-75 hover:opacity-100"}`}
          >
            {poster && (
              <img src={poster} alt="" className="h-full w-full object-cover" />
            )}
            <span className="absolute left-1 top-1 rounded bg-black/65 px-1.5 text-[11px] font-semibold leading-5 text-white">
              {c.order}
            </span>
            <span
              className={`absolute right-1.5 top-1.5 h-2.5 w-2.5 rounded-full ring-1 ring-black/40 ${STATUS_FILL[c.status] ?? "bg-status-draft"}`}
            />
          </button>
        );
      })}
    </div>
  );
}

/** One clip at a time (the point: a big preview and a calm editor, not 20 clips competing for space). A filmstrip of small
 * tiles moves between clips; everything that is set once per shot or only read after a generation sits in two collapsed
 * sections below the prompt. */
export default function ClipCarousel({
  clips,
  characters,
  modelTags,
  anyActive,
  analyzing,
  onUpdate,
  onGenerate,
  onAnalyze,
  onDelete,
}: {
  clips: Clip[];
  characters: Character[];
  modelTags: ModelTag[];
  anyActive: boolean;
  analyzing: boolean;
} & ClipFieldsHandlers) {
  const firstNotDone = clips.findIndex((c) => c.status !== "done");
  const [index, setIndex] = useState(firstNotDone >= 0 ? firstNotDone : 0);
  const [shotPromptDraft, setShotPromptDraft] = useState("");

  // Clip list can shrink (delete) or the whole thing can be empty briefly -- keep the index in bounds.
  useEffect(() => {
    if (index >= clips.length) setIndex(Math.max(0, clips.length - 1));
  }, [clips.length, index]);

  useFocusTarget(
    clips.map((c) => c.id),
    (id) => {
      const i = clips.findIndex((c) => c.id === id);
      if (i >= 0) setIndex(i);
    },
  );

  const clip = clips[index];
  useEffect(
    () => setShotPromptDraft(clip?.shot_prompt ?? ""),
    [clip?.id, clip?.shot_prompt],
  );
  if (!clip)
    return <div className="py-6 text-sm opacity-60">No clips yet.</div>;

  const isFirst = index === 0;
  const isLast = index === clips.length - 1;
  const canBridge = !isLast && clips[index + 1]?.status === "done";
  const handlers: ClipFieldsHandlers = {
    onUpdate,
    onGenerate,
    onAnalyze,
    onDelete,
  };

  return (
    <div id={jobTargetDomId(clip.id)} className="relative left-1/2 flex w-[min(94vw,80rem)] -translate-x-1/2 flex-col gap-3">
      <div className="flex items-center justify-center gap-2">
        <button
          className="border-0 bg-transparent p-1 disabled:opacity-30"
          disabled={isFirst}
          onClick={() => setIndex(index - 1)}
          title="Previous clip"
        >
          <ChevronLeft size={20} />
        </button>
        <Filmstrip clips={clips} index={index} onSelect={setIndex} />
        <button
          className="border-0 bg-transparent p-1 disabled:opacity-30"
          disabled={isLast}
          onClick={() => setIndex(index + 1)}
          title="Next clip"
        >
          <ChevronRight size={20} />
        </button>
      </div>

      <div className="rounded-xl border border-border bg-bg p-4">
        <div className="mb-3 flex items-center gap-2">
          <span className="font-semibold text-text-h">
            Clip {index + 1} of {clips.length}
          </span>
          <StatusBadge status={clip.status} />
        </div>
        <div className="grid gap-6 md:grid-cols-[minmax(20rem,28rem)_minmax(0,1fr)]">
          <ClipVideoBlock clip={clip} />
          <div className="flex min-w-0 flex-col gap-3">
            <ShotPromptEditor
              key={clip.id}
              initialValue={clip.shot_prompt}
              modelTags={modelTags}
              onChange={setShotPromptDraft}
              onBlur={() => onUpdate(clip.id, { shot_prompt: shotPromptDraft })}
            />
            <span
              className={`text-xs ${wordCountClass(wordCount(shotPromptDraft))}`}
            >
              {wordCount(shotPromptDraft)} / {WORD_TARGET_MIN}-{WORD_TARGET_MAX}{" "}
              words
            </span>
            <ClipActions
              clip={clip}
              anyActive={anyActive}
              analyzing={analyzing}
              {...handlers}
            />
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-2">
          <ClipSetup
            clip={clip}
            characters={characters}
            isFirst={isFirst}
            canBridge={canBridge}
            onUpdate={onUpdate}
          />
          <ClipResults clip={clip} />
        </div>
      </div>
    </div>
  );
}
