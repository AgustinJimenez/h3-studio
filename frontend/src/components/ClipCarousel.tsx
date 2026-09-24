import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { mediaUrl } from "../lib/api";
import { wordCount, wordCountClass, WORD_TARGET_MIN, WORD_TARGET_MAX } from "../lib/wordCount";
import StatusBadge from "./StatusBadge";
import GenerationParams from "./GenerationParams";
import ShotPromptEditor from "./ShotPromptEditor";
import VideoPlayer from "./VideoPlayer";
import type { Clip, ModelTag, Character } from "../schemas";
import { jobTargetDomId, useFocusTarget } from "../lib/jobFocus";

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

function formatFrames(frames: number): string {
  const seconds = frames / 24;
  return `${frames}f (~${seconds.toFixed(1)}s)`;
}

// How many neighboring clips peek in on each side of the current one.
const PEEK = 2;

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
function ClipVideoBlock({ clip, selected = true }: { clip: Clip; selected?: boolean }) {
  const [previewFull, setPreviewFull] = useState(false);
  const hasOwnSegment = !!clip.own_segment_url && clip.own_segment_url !== clip.output_url;
  const previewUrl = previewFull || !hasOwnSegment ? clip.output_url : clip.own_segment_url;

  if (!previewUrl) {
    return (
      <div className="flex aspect-video w-full items-center justify-center rounded border border-dashed border-border text-sm opacity-60">
        {clip.status === "running" || clip.status === "queued" ? "Generating…" : "Not generated yet"}
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center gap-1">
      <VideoPlayer key={previewUrl} className="w-full max-w-full rounded" src={mediaUrl(previewUrl)} controls={selected} />
      {hasOwnSegment && (
        <button onClick={() => setPreviewFull(!previewFull)}>
          {previewFull ? "Show this clip's own segment only" : "Show full chain up to this clip"}
        </button>
      )}
    </div>
  );
}

// Everything below the video for one clip: prompt editor, seed/frames/status/
// actions, continue/bridge checkboxes, per-clip character checkboxes, error,
// tail frames, QA report, generation params. Self-contained (owns its own
// shot-prompt draft state) so the exact same fields can be reused at full
// size for the current clip and shrunk down for peeking neighbors.
function ClipFields({
  clip,
  characters,
  modelTags,
  isFirst,
  canBridge,
  anyActive,
  analyzing,
  onUpdate,
  onGenerate,
  onAnalyze,
  onDelete,
}: {
  clip: Clip;
  characters: Character[];
  modelTags: ModelTag[];
  isFirst: boolean;
  canBridge: boolean;
  anyActive: boolean;
  analyzing: boolean;
} & ClipFieldsHandlers) {
  const [shotPromptDraft, setShotPromptDraft] = useState(clip.shot_prompt);
  useEffect(() => setShotPromptDraft(clip.shot_prompt), [clip.id, clip.shot_prompt]);

  return (
    <div className="flex flex-col gap-3">
      <ShotPromptEditor
        key={clip.id}
        initialValue={clip.shot_prompt}
        modelTags={modelTags}
        onChange={setShotPromptDraft}
        onBlur={() => onUpdate(clip.id, { shot_prompt: shotPromptDraft })}
      />
      <span className={wordCountClass(wordCount(shotPromptDraft))}>
        {wordCount(shotPromptDraft)} / {WORD_TARGET_MIN}-{WORD_TARGET_MAX} words
      </span>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Seed
          <input type="number" value={clip.seed} onChange={(e) => onUpdate(clip.id, { seed: Number(e.target.value) })} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Frames
          <input
            type="number"
            value={clip.video_length}
            onChange={(e) => onUpdate(clip.id, { video_length: Number(e.target.value) })}
          />
        </label>
        <span className="text-sm opacity-75">{formatFrames(clip.video_length)}</span>
        <StatusBadge status={clip.status} />
        <button disabled={anyActive} onClick={() => onGenerate(clip.id)}>
          {clip.status === "done" ? "Regenerate" : "Generate"}
        </button>
        {clip.status === "done" && (
          <button
            disabled={anyActive || analyzing}
            onClick={() => onAnalyze(clip.id)}
            title="Check for duplicated/cloned people, ghosting artifacts, and voice consistency"
          >
            {analyzing ? "Analyzing…" : clip.qa_report ? "Re-analyze" : "Analyze"}
          </button>
        )}
        <button className="border-0 bg-transparent p-0 text-danger" onClick={() => onDelete(clip.id)}>
          Delete
        </button>
      </div>

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={!!clip.continue_from_previous}
          disabled={isFirst}
          className="mt-0.5"
          onChange={(e) => onUpdate(clip.id, { continue_from_previous: e.target.checked })}
        />
        Continue from previous clip (real video continuation, not just a shared description — the preceding clip
        must already be done)
      </label>
      <label
        className="flex items-start gap-2 text-sm"
        title={!canBridge ? "The next clip must exist and already be done to bridge into it" : undefined}
      >
        <input
          type="checkbox"
          checked={!!clip.bridge_to_next}
          disabled={!canBridge}
          className="mt-0.5"
          onChange={(e) => onUpdate(clip.id, { bridge_to_next: e.target.checked })}
        />
        Bridge to next clip (steer this regeneration to land back on the next clip's existing first frame, so the
        rest of the chain doesn't need to be redone)
      </label>

      {characters.length > 1 && (
        <fieldset className="flex flex-col gap-1 text-sm">
          <legend className="opacity-75">
            Characters in this shot (unchecked ones are left out of the prompt entirely — no "appears throughout"
            claim for someone who isn't in this scene)
          </legend>
          <div className="flex flex-wrap gap-3">
            {characters.map((character) => {
              const activeIds = clip.active_character_ids ?? characters.map((c) => c.id);
              const checked = activeIds.includes(character.id);
              return (
                <label key={character.id} className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => {
                      const next = e.target.checked
                        ? [...activeIds, character.id]
                        : activeIds.filter((id) => id !== character.id);
                      const isFullRoster = characters.every((c) => next.includes(c.id));
                      onUpdate(clip.id, { active_character_ids: isFullRoster ? null : next });
                    }}
                  />
                  {character.name || "(unnamed)"}
                </label>
              );
            })}
          </div>
        </fieldset>
      )}

      {clip.error && (
        <div className="whitespace-pre-wrap rounded border border-danger bg-red-950/30 px-3 py-2 text-danger">{clip.error}</div>
      )}

      {clip.tail_frame_urls.length > 0 && (
        <div className="flex flex-col gap-1">
          <span
            className="text-sm opacity-75"
            title="The literal last ~2s of this clip's output — check here for identity clones or blends before trusting it as a continuation source"
          >
            Tail check (last ~2s) — click a frame to inspect closely
          </span>
          <div className="flex flex-wrap gap-1.5">
            {clip.tail_frame_urls.map((url) => (
              <a key={url} href={mediaUrl(url) ?? undefined} target="_blank" rel="noreferrer">
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
        <div className="flex flex-col gap-2 rounded-lg border border-border bg-bg p-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-text-h">QA report</span>
            <span className="text-xs opacity-60">{new Date(clip.qa_report.analyzed_at * 1000).toLocaleString()}</span>
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold uppercase opacity-60">Visual (duplicates / ghosting)</div>
            <p className="whitespace-pre-wrap">{clip.qa_report.visual_analysis}</p>
          </div>
          {clip.qa_report.voice_results.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-semibold uppercase opacity-60">Voice consistency</div>
              <div className="flex flex-col gap-1">
                {clip.qa_report.voice_results.map((r) => (
                  <div key={r.reference_path} className="flex items-center gap-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs text-white ${r.same_speaker ? "bg-status-done" : "bg-status-failed"}`}
                    >
                      {r.same_speaker ? "matches" : "not detected"}
                    </span>
                    <span className="font-mono text-xs opacity-75">{r.reference_path.split(/[\\/]/).pop()}</span>
                    <span className="text-xs opacity-60">score {r.score.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <GenerationParams settings={clip.last_generation_settings} durationSeconds={clip.generation_duration_seconds} />
    </div>
  );
}

// A neighboring (non-current) clip in the peek row -- the exact same video +
// fields as the current clip gets, just laid out at double width and then
// visually shrunk with CSS zoom so it fits a peek-sized column without
// re-deriving a separate "compact" layout. isFirst/canBridge are computed
// from this clip's OWN position in the chain, not the currently-selected one.
function MiniClipCard({
  clip,
  isFirst,
  canBridge,
  characters,
  modelTags,
  anyActive,
  analyzing,
  onJump,
  ...handlers
}: {
  clip: Clip;
  isFirst: boolean;
  canBridge: boolean;
  characters: Character[];
  modelTags: ModelTag[];
  anyActive: boolean;
  analyzing: boolean;
  onJump: () => void;
} & ClipFieldsHandlers) {
  return (
    <div className="relative z-0 w-80 shrink-0 overflow-hidden rounded-lg border border-border bg-bg p-2 opacity-80 transition-opacity hover:opacity-100">
      {/* A neighbor card is a preview, not a second editing surface -- none of
          its video controls, inputs, checkboxes, or buttons should be
          individually clickable. One invisible full-card button captures
          every click and jumps to this clip; the real content underneath is
          pointer-events-none so nothing inside it can intercept the click. */}
      <button
        onClick={onJump}
        title={`Jump to clip #${clip.order}`}
        aria-label={`Jump to clip #${clip.order}`}
        className="absolute inset-0 z-10 cursor-pointer border-0 bg-transparent p-0"
      />
      <div className="pointer-events-none">
        <div className="mb-2 flex w-full items-center justify-between gap-1">
          <span className="text-xs font-semibold opacity-75">#{clip.order}</span>
          <StatusBadge status={clip.status} />
        </div>
        <div style={{ width: 640, zoom: 0.5 }}>
          <ClipVideoBlock clip={clip} selected={false} />
          <div className="mt-3">
            <ClipFields
              clip={clip}
              characters={characters}
              modelTags={modelTags}
              isFirst={isFirst}
              canBridge={canBridge}
              anyActive={anyActive}
              analyzing={analyzing}
              {...handlers}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/** Experimental alternative to the List view: one clip at a time, video preview
 * up top (the whole point -- big preview, details below it, not competing for
 * space with 20 other clips), a status-colored index strip plus prev/next to
 * move between clips. Deliberately a separate component from ClipRow rather
 * than a shared refactor, so the working List view stays untouched while this
 * is still experimental. */
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
  const [index, setIndexRaw] = useState(firstNotDone >= 0 ? firstNotDone : 0);
  // Which way the row should slide in from -- set right before the index
  // change so the CSS animation (keyed on index below) picks the matching
  // direction. A ref, not state: it only needs to be read during the same
  // render that setIndex triggers, never causes its own render.
  const direction = useRef<"left" | "right">("right");
  function setIndex(next: number) {
    direction.current = next < index ? "left" : "right";
    setIndexRaw(next);
  }

  // Clip list can shrink (delete) or the whole thing can be empty briefly --
  // keep the index in bounds rather than pointing past the end.
  useEffect(() => {
    if (index >= clips.length) setIndexRaw(Math.max(0, clips.length - 1));
  }, [clips.length, index]);

  useFocusTarget(clips.map((c) => c.id), (id) => {
    const i = clips.findIndex((c) => c.id === id);
    if (i >= 0) setIndexRaw(i);
  });

  const clip = clips[index];
  if (!clip) return <div className="py-6 text-sm opacity-60">No clips yet.</div>;

  const isFirst = index === 0;
  const isLast = index === clips.length - 1;
  const canBridge = !isLast && clips[index + 1]?.status === "done";
  const handlers: ClipFieldsHandlers = { onUpdate, onGenerate, onAnalyze, onDelete };

  return (
    // Breaks out to full viewport width as ONE panel (not just the peek row
    // below) -- the index strip/nav used to sit in the page's normal
    // contained width while the row below spanned edge to edge, which read
    // as two mismatched pieces rather than one carousel. The index strip and
    // nav stay visually centered via their own inner max-width wrapper; only
    // the peek row itself uses the full panel width.
    <div id={jobTargetDomId(clip.id)} className="relative left-1/2 right-1/2 -mx-[50vw] flex w-screen flex-col gap-3 border-y border-border bg-bg-alt py-3.5">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-3 px-4">
      <div className="flex flex-wrap items-center justify-center gap-1.5">
        {clips.map((c, i) => (
          <button
            key={c.id}
            title={`Clip #${c.order} — ${c.status}`}
            onClick={() => setIndex(i)}
            className={`flex h-7 w-7 items-center justify-center rounded-full border-0 text-xs font-semibold text-white ${STATUS_FILL[c.status] ?? "bg-status-draft"} ${i === index ? "ring-2 ring-accent ring-offset-2 ring-offset-bg-alt" : "opacity-70 hover:opacity-100"}`}
          >
            {c.order}
          </button>
        ))}
      </div>

      <div className="flex items-center justify-center gap-4">
        <button
          className="border-0 bg-transparent p-1 disabled:opacity-30"
          disabled={isFirst}
          onClick={() => setIndex(index - 1)}
          title="Previous clip"
        >
          <ChevronLeft size={20} />
        </button>
        <span className="font-semibold text-text-h">
          Clip {index + 1} of {clips.length}
        </span>
        <button
          className="border-0 bg-transparent p-1 disabled:opacity-30"
          disabled={isLast}
          onClick={() => setIndex(index + 1)}
          title="Next clip"
        >
          <ChevronRight size={20} />
        </button>
      </div>
      </div>

      {/* Peek row spans the panel's full breakout width (the panel itself
          already broke out above, so no second breakout needed here) so
          neighboring clips can peek in on both sides of the current one. */}
      <div
        key={index}
        className={`hidden items-start justify-center gap-3 overflow-x-auto px-4 md:flex ${
          direction.current === "left" ? "carousel-slide-from-left" : "carousel-slide-from-right"
        }`}
      >
          {/* Near the start/end of the chain there are fewer than PEEK real
              neighbors on that side. Padding with same-width invisible spacers
              (instead of just rendering fewer cards) keeps the row's total
              width constant, so the center card stays fixed in the middle of
              the screen instead of drifting left/right as you navigate --
              without this, justify-center centers the whole (variable-width)
              row rather than keeping the current clip's position stable. */}
          {Array.from({ length: PEEK - Math.min(PEEK, index) }).map((_, i) => (
            <div key={`pad-left-${i}`} className="w-80 shrink-0" aria-hidden />
          ))}
          {clips.slice(Math.max(0, index - PEEK), index).map((c, offset) => {
            const i = Math.max(0, index - PEEK) + offset;
            return (
              <MiniClipCard
                key={c.id}
                clip={c}
                isFirst={i === 0}
                canBridge={i < clips.length - 1 && clips[i + 1]?.status === "done"}
                characters={characters}
                modelTags={modelTags}
                anyActive={anyActive}
                analyzing={analyzing}
                onJump={() => setIndex(i)}
                {...handlers}
              />
            );
          })}
          <div className="relative z-10 w-full max-w-2xl shrink-0 rounded-lg border border-border bg-bg p-2">
            <ClipVideoBlock clip={clip} />
            <div className="mt-3">
              <ClipFields
                clip={clip}
                characters={characters}
                modelTags={modelTags}
                isFirst={isFirst}
                canBridge={canBridge}
                anyActive={anyActive}
                analyzing={analyzing}
                {...handlers}
              />
            </div>
          </div>
          {clips.slice(index + 1, index + 1 + PEEK).map((c, offset) => {
            const i = index + 1 + offset;
            return (
              <MiniClipCard
                key={c.id}
                clip={c}
                isFirst={i === 0}
                canBridge={i < clips.length - 1 && clips[i + 1]?.status === "done"}
                characters={characters}
                modelTags={modelTags}
                anyActive={anyActive}
                analyzing={analyzing}
                onJump={() => setIndex(i)}
                {...handlers}
              />
            );
          })}
          {Array.from({ length: PEEK - Math.min(PEEK, clips.length - 1 - index) }).map((_, i) => (
            <div key={`pad-right-${i}`} className="w-80 shrink-0" aria-hidden />
          ))}
        </div>
        {/* Narrow viewports: no room to peek, just the current clip's video and fields, still full-width. */}
        <div className="flex flex-col gap-3 px-4 md:hidden">
          <ClipVideoBlock clip={clip} />
          <ClipFields
            clip={clip}
            characters={characters}
            modelTags={modelTags}
            isFirst={isFirst}
            canBridge={canBridge}
            anyActive={anyActive}
            analyzing={analyzing}
            {...handlers}
          />
        </div>
    </div>
  );
}
