import { useState } from "react";
import { Plus, Trash2, ChevronUp, ChevronDown } from "lucide-react";
import {
  serializeShotPrompt,
  deriveSpeakerOptions,
  shotDisplayNumbers,
  type ParsedShot,
  type ShotSegment,
  type DialogueSegment,
  type SpeakerOption,
} from "../lib/shotPromptStructure";
import type { ModelTag, PromptTag } from "../schemas";

// Form-based alternative to the Simple (Lexical) tab for editing a
// shot_prompt: same underlying string, just built from shot/dialogue-line
// blocks instead of hand-typed [Shot N]/<d>[Speaker SN...]...</d> syntax.
// Owns its own ParsedShot[] state from a mount-once initial parse (mirrors
// PromptTagEditor's "uncontrolled after mount" contract) and reports every
// change back up as the serialized plain-text string, via ShotPromptEditor.
//
// Shot numbers are never stored/edited as text -- they're always derived
// from position (shotDisplayNumbers), so adding/reordering/deleting shots
// renumbers everything else automatically instead of leaving stale numbers.

function moveItem<T>(arr: T[], index: number, delta: number): T[] {
  const target = index + delta;
  if (target < 0 || target >= arr.length) return arr;
  const next = arr.slice();
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export default function StructuredShotEditor({
  initialShots,
  modelTags,
  promptTags,
  onChange,
}: {
  initialShots: ParsedShot[];
  modelTags: ModelTag[];
  promptTags: PromptTag[];
  onChange: (nextText: string) => void;
}) {
  const [shots, setShots] = useState<ParsedShot[]>(initialShots);
  const speakerOptions = deriveSpeakerOptions(modelTags);

  function commit(next: ParsedShot[]) {
    setShots(next);
    onChange(serializeShotPrompt(next));
  }

  function updateShot(shotIndex: number, fn: (shot: ParsedShot) => ParsedShot) {
    commit(shots.map((s, i) => (i === shotIndex ? fn(s) : s)));
  }

  function addShot() {
    commit([...shots, { hasMarker: true, startTime: null, segments: [] }]);
  }

  function removeShot(shotIndex: number) {
    commit(shots.filter((_, i) => i !== shotIndex));
  }

  function moveShot(shotIndex: number, delta: number) {
    commit(moveItem(shots, shotIndex, delta));
  }

  // Selecting a speaker also inserts a "Name (SN)" prose annotation right
  // before the dialogue line, matching how every real clip in this project
  // writes it by hand (e.g. "Santamaria (S1) <d>[Speaker S1, ...] ...</d>")
  // -- skipped if that exact annotation is already the preceding segment,
  // so toggling the same speaker twice doesn't duplicate it.
  function selectSpeaker(shotIndex: number, segIndex: number, opt: SpeakerOption | null) {
    updateShot(shotIndex, (s) => {
      const segments = s.segments.slice();
      const current = segments[segIndex] as DialogueSegment;
      segments[segIndex] = { ...current, speakerTag: opt?.speakerTag ?? null, audioTag: opt?.audioTag ?? null };
      if (opt) {
        const marker = `${opt.name} (${opt.speakerTag})`;
        const prev = segments[segIndex - 1];
        const alreadyAnnotated = prev && prev.type === "prose" && prev.text.trim().endsWith(marker);
        if (!alreadyAnnotated) segments.splice(segIndex, 0, { type: "prose", text: marker });
      }
      return { ...s, segments };
    });
  }

  const shotNumbers = shotDisplayNumbers(shots);

  return (
    <div className="flex flex-col gap-3">
      {shots.map((shot, shotIndex) => (
        <div key={shotIndex} className="rounded-lg border border-border bg-bg-alt p-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="font-semibold text-text-h">
              {shotNumbers[shotIndex] !== null ? `Shot ${shotNumbers[shotIndex]}` : "(no shot marker)"}
            </span>
            {shot.hasMarker && (
              <label className="flex items-center gap-1 text-xs opacity-75">
                Start time
                <input
                  className="w-24 font-mono text-xs"
                  placeholder="00:00.000"
                  value={shot.startTime ?? ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    updateShot(shotIndex, (s) => ({ ...s, startTime: v.trim() || null }));
                  }}
                />
              </label>
            )}
            <div className="ml-auto flex gap-1">
              <button
                title="Move shot up"
                className="border-0 bg-transparent px-1 py-0"
                disabled={shotIndex === 0}
                onClick={() => moveShot(shotIndex, -1)}
              >
                <ChevronUp size={14} />
              </button>
              <button
                title="Move shot down"
                className="border-0 bg-transparent px-1 py-0"
                disabled={shotIndex === shots.length - 1}
                onClick={() => moveShot(shotIndex, 1)}
              >
                <ChevronDown size={14} />
              </button>
              <button title="Delete shot" className="border-0 bg-transparent px-1 py-0 text-danger" onClick={() => removeShot(shotIndex)}>
                <Trash2 size={14} />
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            {shot.segments.map((seg, segIndex) => (
              <SegmentRow
                key={segIndex}
                segment={seg}
                isFirst={segIndex === 0}
                isLast={segIndex === shot.segments.length - 1}
                speakerOptions={speakerOptions}
                promptTags={promptTags}
                onUpdate={(next) =>
                  updateShot(shotIndex, (s) => ({ ...s, segments: s.segments.map((seg2, i) => (i === segIndex ? next : seg2)) }))
                }
                onSelectSpeaker={(opt) => selectSpeaker(shotIndex, segIndex, opt)}
                onRemove={() => updateShot(shotIndex, (s) => ({ ...s, segments: s.segments.filter((_, i) => i !== segIndex) }))}
                onMove={(delta) => updateShot(shotIndex, (s) => ({ ...s, segments: moveItem(s.segments, segIndex, delta) }))}
              />
            ))}
            {shot.segments.length === 0 && <div className="py-2 text-sm opacity-60">No content yet — add a line below.</div>}
          </div>

          <div className="mt-2 flex gap-2">
            <button
              className="inline-flex items-center gap-1 text-sm"
              onClick={() => updateShot(shotIndex, (s) => ({ ...s, segments: [...s.segments, { type: "prose", text: "" }] }))}
            >
              <Plus size={14} /> Prose
            </button>
            <button
              className="inline-flex items-center gap-1 text-sm"
              onClick={() =>
                updateShot(shotIndex, (s) => ({
                  ...s,
                  segments: [
                    ...s.segments,
                    { type: "dialogue", speakerTag: null, audioTag: null, primaryTagKey: null, extra: "", text: "" },
                  ],
                }))
              }
            >
              <Plus size={14} /> Dialogue line
            </button>
          </div>
        </div>
      ))}
      <button className="inline-flex items-center gap-1 self-start text-sm" onClick={addShot}>
        <Plus size={14} /> Add shot
      </button>
    </div>
  );
}

function SegmentRow({
  segment,
  isFirst,
  isLast,
  speakerOptions,
  promptTags,
  onUpdate,
  onSelectSpeaker,
  onRemove,
  onMove,
}: {
  segment: ShotSegment;
  isFirst: boolean;
  isLast: boolean;
  speakerOptions: ReturnType<typeof deriveSpeakerOptions>;
  promptTags: PromptTag[];
  onUpdate: (next: ShotSegment) => void;
  onSelectSpeaker: (opt: SpeakerOption | null) => void;
  onRemove: () => void;
  onMove: (delta: number) => void;
}) {
  const moveButtons = (
    <div className="flex shrink-0 flex-col gap-0.5 pt-1">
      <button title="Move up" className="border-0 bg-transparent px-1 py-0" disabled={isFirst} onClick={() => onMove(-1)}>
        <ChevronUp size={12} />
      </button>
      <button title="Move down" className="border-0 bg-transparent px-1 py-0" disabled={isLast} onClick={() => onMove(1)}>
        <ChevronDown size={12} />
      </button>
    </div>
  );

  if (segment.type === "prose") {
    return (
      <div className="flex items-start gap-1 rounded border border-border bg-bg p-2">
        {moveButtons}
        <div className="flex-1">
          <div className="mb-0.5 text-xs font-semibold uppercase opacity-60">Prose</div>
          <textarea
            rows={2}
            className="w-full"
            placeholder="Scene description / action / blocking..."
            value={segment.text}
            onChange={(e) => onUpdate({ ...segment, text: e.target.value })}
          />
        </div>
        <button title="Delete" className="shrink-0 border-0 bg-transparent px-1 py-0 pt-1 text-danger" onClick={onRemove}>
          <Trash2 size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-1 rounded border border-status-running bg-bg p-2">
      {moveButtons}
      <div className="flex flex-1 flex-col gap-1.5">
        <div className="text-xs font-semibold uppercase opacity-60">Dialogue line</div>
        <div className="flex flex-wrap gap-2">
          <label className="flex flex-col gap-0.5 text-xs">
            Speaker
            <select
              value={segment.speakerTag ?? ""}
              onChange={(e) => {
                const opt = speakerOptions.find((o) => o.speakerTag === e.target.value);
                onSelectSpeaker(opt ?? null);
              }}
            >
              <option value="">(none)</option>
              {speakerOptions.map((o) => (
                <option key={o.speakerTag} value={o.speakerTag}>
                  {o.name} ({o.speakerTag})
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-0.5 text-xs">
            Accent/delivery tag
            <select
              value={segment.primaryTagKey ?? ""}
              onChange={(e) => onUpdate({ ...segment, primaryTagKey: e.target.value || null })}
            >
              <option value="">(none)</option>
              {promptTags.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-w-[160px] flex-1 flex-col gap-0.5 text-xs">
            Mood / extra
            <input
              placeholder="calm, measured, quietly commanding"
              value={segment.extra}
              onChange={(e) => onUpdate({ ...segment, extra: e.target.value })}
            />
          </label>
        </div>
        <textarea
          rows={2}
          placeholder="Dialogue text..."
          value={segment.text}
          onChange={(e) => onUpdate({ ...segment, text: e.target.value })}
        />
      </div>
      <button title="Delete" className="shrink-0 border-0 bg-transparent px-1 py-0 pt-1 text-danger" onClick={onRemove}>
        <Trash2 size={14} />
      </button>
    </div>
  );
}

// Re-exported for ShotPromptEditor's convenience so it doesn't need a
// separate import of DialogueSegment just to type its own props.
export type { DialogueSegment };
