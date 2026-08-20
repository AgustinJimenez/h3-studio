import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { DndContext, closestCenter, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ChevronDown, ChevronRight, ArrowLeft } from "lucide-react";
import { mediaUrl } from "../lib/api";
import {
  useVideo,
  useOptions,
  useUpdateVideo,
  useCreateClip,
  useUpdateClip,
  useDeleteClip,
  useReorderClips,
  useGenerateClip,
  useAnalyzeClip,
  useConcatVideo,
} from "../lib/queries";
import { wordCount, wordCountClass, WORD_TARGET_MIN, WORD_TARGET_MAX } from "../lib/wordCount";
import StatusBadge from "../components/StatusBadge";
import GenerationParams from "../components/GenerationParams";
import ReferenceThumb from "../components/ReferenceThumb";
import ConfirmDialog from "../components/ConfirmDialog";
import ShotPromptEditor from "../components/ShotPromptEditor";
import type { Clip, BasePrompt, ModelTag, QaReport } from "../schemas";

const ACTIVE_STATUSES = new Set(["queued", "running"]);
const FPS = 24; // H3's frame rate — see prompt.py's DEFAULT_VIDEO_LENGTH comment.

function formatFrames(frames: number): string {
  const seconds = frames / FPS;
  return `${frames}f (~${seconds.toFixed(1)}s)`;
}

const BASE_PROMPT_FIELDS: [keyof BasePrompt, string][] = [
  ["summary", "Summary"],
  ["overall_soundscape", "Overall soundscape"],
  ["non_diegetic_music", "Non-diegetic music"],
];

export default function VideoDetail() {
  const { id } = useParams({ from: "/videos/$id" });
  const { data: video, error } = useVideo(id);
  const { data: options } = useOptions(video?.template_settings?.model_type as string | undefined);

  const updateVideo = useUpdateVideo(id);
  const createClip = useCreateClip(id);
  const updateClip = useUpdateClip(id);
  const deleteClip = useDeleteClip(id);
  const reorderClips = useReorderClips(id);
  const generateClip = useGenerateClip(id);
  const analyzeClip = useAnalyzeClip(id);
  const concatVideo = useConcatVideo(id);

  const [basePromptDraft, setBasePromptDraft] = useState<BasePrompt | null>(null);
  const [templateDraft, setTemplateDraft] = useState<Record<string, unknown> | null>(null);
  const [newClip, setNewClip] = useState<{ shot_prompt: string; seed: number; video_length: number }>({
    shot_prompt: "",
    seed: -1,
    video_length: 362,
  });
  const [collapseSignal, setCollapseSignal] = useState<{ action: "collapse" | "expand"; token: number } | null>(null);
  const [pendingDeleteClipId, setPendingDeleteClipId] = useState<string | null>(null);

  if (error) return <div className="mx-auto max-w-4xl px-4 py-6 text-danger">{error.message}</div>;
  if (!video) return <div className="mx-auto max-w-4xl px-4 py-6">Loading...</div>;

  const basePrompt = basePromptDraft ?? video.base_prompt;
  const templateSettings = templateDraft ?? video.template_settings;

  const anyActive = video.clips.some((c) => ACTIVE_STATUSES.has(c.status));
  const anyDone = video.clips.some((c) => c.status === "done");
  const sortedClips = [...video.clips].sort((a, b) => a.order - b.order);
  const sortedCharacters = [...video.characters].sort((a, b) => a.order - b.order);
  // Each clip's video_length is its OWN new frame count, not a running total (continuation clips'
  // *output files* grow cumulatively, but the setting itself stays per-clip) — so the timeline total
  // is the sum across done clips, not the last clip's value alone.
  const doneFramesSoFar = sortedClips.filter((c) => c.status === "done").reduce((sum, c) => sum + c.video_length, 0);

  function saveBasePrompt() {
    updateVideo.mutate({ base_prompt: basePrompt });
  }

  function saveTemplateSettings() {
    updateVideo.mutate({ template_settings: templateSettings });
  }

  async function onModelTypeChange(modelType: string) {
    const modelDef = options?.model_types.find((m) => m.model_type === modelType);
    const next = { ...templateSettings, model_type: modelType, model_filename: modelDef?.model_filenames?.[0] || "" };
    setTemplateDraft(next);
    updateVideo.mutate({ template_settings: next });
  }

  function addClip() {
    if (!newClip.shot_prompt.trim()) return;
    createClip.mutate(newClip, { onSuccess: () => setNewClip({ shot_prompt: "", seed: -1, video_length: 362 }) });
  }

  function removeClip(clipId: string) {
    setPendingDeleteClipId(clipId);
  }

  function confirmRemoveClip() {
    if (!pendingDeleteClipId) return;
    deleteClip.mutate(pendingDeleteClipId);
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const ids = sortedClips.map((c) => c.id);
    const fromIdx = ids.indexOf(String(active.id));
    const toIdx = ids.indexOf(String(over.id));
    ids.splice(fromIdx, 1);
    ids.splice(toIdx, 0, String(active.id));
    reorderClips.mutate(ids);
  }

  return (
    <div className="mx-auto max-w-4xl px-4 pb-16 pt-6">
      <Link to="/" className="inline-flex items-center gap-1"><ArrowLeft size={14} /> Videos</Link>
      <h1 className="mb-4 mt-2 text-2xl font-bold">{video.title}</h1>

      <details className="mb-3 rounded-lg border border-border bg-bg-alt p-3.5">
        <summary className="cursor-pointer font-semibold text-text-h">Base prompt (shared across all clips)</summary>
        <div className="mt-3 grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3">
          {BASE_PROMPT_FIELDS.map(([key, label]) => (
            <label key={key} className="flex flex-col gap-1 text-sm">
              {label}
              <textarea
                rows={3}
                value={basePrompt[key] || ""}
                onChange={(e) => setBasePromptDraft({ ...basePrompt, [key]: e.target.value })}
              />
            </label>
          ))}
        </div>
        <button className="mt-2" onClick={saveBasePrompt}>Save base prompt</button>
      </details>

      <details className="mb-3 rounded-lg border border-border bg-bg-alt p-3.5">
        <summary className="cursor-pointer font-semibold text-text-h">Template settings (model, resolution, references)</summary>
        <p className="mt-2 text-sm opacity-75">
          Choices below come straight from the loaded WanGP runtime (real installed/supported options for this
          machine and model) instead of free-typed strings — see <code>GET /options</code>.
        </p>
        {!options ? (
          <div className="py-6 opacity-60">Loading options...</div>
        ) : (
          <div className="mt-3 grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3">
            <label className="flex flex-col gap-1 text-sm">
              Model type
              <select value={(templateSettings.model_type as string) ?? ""} onChange={(e) => onModelTypeChange(e.target.value)}>
                {options.model_types.map((m) => (
                  <option key={m.model_type} value={m.model_type}>{m.name}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Model checkpoint
              <select
                value={(templateSettings.model_filename as string) ?? ""}
                onChange={(e) => setTemplateDraft({ ...templateSettings, model_filename: e.target.value })}
              >
                {(options.model_types.find((m) => m.model_type === templateSettings.model_type)?.model_filenames || []).map((url) => (
                  <option key={url} value={url}>{url.split("/").pop()}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Resolution
              <select
                value={(templateSettings.resolution as string) ?? ""}
                onChange={(e) => setTemplateDraft({ ...templateSettings, resolution: e.target.value })}
              >
                {options.resolutions.map((r) => (
                  <option key={String(r.value)} value={r.value}>{r.label}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Inference steps
              <input
                type="number"
                value={(templateSettings.num_inference_steps as number) ?? ""}
                onChange={(e) => setTemplateDraft({ ...templateSettings, num_inference_steps: Number(e.target.value) })}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Override memory profile
              <select
                value={(templateSettings.override_profile as number) ?? -1}
                onChange={(e) => setTemplateDraft({ ...templateSettings, override_profile: Number(e.target.value) })}
              >
                {options.memory_profiles.map((p) => (
                  <option key={String(p.value)} value={p.value}>{p.label}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Override attention mode
              <select
                value={(templateSettings.override_attention as string) ?? ""}
                onChange={(e) => setTemplateDraft({ ...templateSettings, override_attention: e.target.value })}
              >
                {options.attention_modes.map((a) => (
                  <option key={String(a.value)} value={a.value}>{a.label}</option>
                ))}
              </select>
            </label>
          </div>
        )}
        <button className="mt-3" onClick={saveTemplateSettings}>Save template settings</button>
      </details>

      <details open className="mb-3 rounded-lg border border-border bg-bg-alt p-3.5">
        <summary className="cursor-pointer font-semibold text-text-h">Characters ({sortedCharacters.length})</summary>
        <div className="mt-3 flex flex-col gap-1.5">
          {sortedCharacters.map((character) => (
            <Link
              key={character.id}
              to="/videos/$id/characters/$characterId"
              params={{ id, characterId: character.id }}
              className="flex items-center gap-2.5 rounded-md border border-border px-2.5 py-1.5 no-underline hover:border-accent"
            >
              {character.references[0] && <ReferenceThumb type={character.references[0].type} path={character.references[0].path} />}
              <span>Subject {character.order + 1}: {character.name || "(unnamed)"}</span>
              <span className="text-sm opacity-75">{character.references.length} ref{character.references.length === 1 ? "" : "s"}</span>
            </Link>
          ))}
        </div>
        <Link to="/videos/$id/characters" params={{ id }}><button className="mt-2">Manage characters</button></Link>

        {sortedCharacters.length > 0 && (
          <details className="mt-3 rounded border border-border bg-bg p-2.5">
            <summary className="cursor-pointer text-sm font-semibold text-text-h">Composed prompt preview (auto-generated, sent as-is)</summary>
            <div className="mt-2 grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3">
              <label className="flex flex-col gap-1 text-sm">
                subject_definitions
                <textarea rows={4} readOnly value={video.composed_subject_definitions} />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                retention_analysis
                <textarea rows={4} readOnly value={video.composed_retention_analysis} />
              </label>
            </div>
          </details>
        )}
      </details>

      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-bold">
          Clips ({sortedClips.length}
          {doneFramesSoFar > 0 && `, ${formatFrames(doneFramesSoFar)} generated so far`})
        </h2>
        <div className="flex gap-2">
          <button onClick={() => setCollapseSignal({ action: "collapse", token: Date.now() })}>Collapse done clips</button>
          <button onClick={() => setCollapseSignal({ action: "expand", token: Date.now() })}>Expand all</button>
        </div>
      </div>
      <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={sortedClips.map((c) => c.id)} strategy={verticalListSortingStrategy}>
          <div className="flex flex-col gap-2.5">
            {sortedClips.map((clip, i) => (
              <ClipRow
                key={clip.id}
                clip={clip}
                modelTags={video.model_tags}
                isFirst={i === 0}
                isLast={i === sortedClips.length - 1}
                nextClipDone={sortedClips[i + 1]?.status === "done"}
                anyActive={anyActive}
                collapseSignal={collapseSignal}
                onUpdate={(body) => updateClip.mutate({ clipId: clip.id, body })}
                onGenerate={() => generateClip.mutate(clip.id)}
                onAnalyze={() => analyzeClip.mutate(clip.id)}
                analyzing={analyzeClip.isPending}
                onDelete={() => removeClip(clip.id)}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      <div className="my-4 rounded-lg border border-dashed border-border p-3.5">
        <h3 className="mb-2 font-semibold text-text-h">Add clip</h3>
        <textarea
          rows={2}
          placeholder="Shot-specific prompt (becomes detailed_description)..."
          value={newClip.shot_prompt}
          onChange={(e) => setNewClip({ ...newClip, shot_prompt: e.target.value })}
        />
        <span className={wordCountClass(wordCount(newClip.shot_prompt))}>
          {wordCount(newClip.shot_prompt)} / {WORD_TARGET_MIN}-{WORD_TARGET_MAX} words
        </span>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Seed
            <input type="number" value={newClip.seed} onChange={(e) => setNewClip({ ...newClip, seed: Number(e.target.value) })} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Frames
            <input type="number" value={newClip.video_length} onChange={(e) => setNewClip({ ...newClip, video_length: Number(e.target.value) })} />
          </label>
          <button onClick={addClip}>Add clip</button>
        </div>
      </div>

      <div className="my-4 rounded-lg border border-dashed border-border p-3.5">
        <button disabled={!anyDone} onClick={() => concatVideo.mutate()}>Join clips</button>
        {video.concat_output_url && <video controls width={480} className="mt-1.5 max-w-full rounded" src={mediaUrl(video.concat_output_url) ?? undefined} />}
      </div>

      <ConfirmDialog
        open={!!pendingDeleteClipId}
        onOpenChange={(open) => !open && setPendingDeleteClipId(null)}
        title="Delete this clip?"
        onConfirm={confirmRemoveClip}
      />
    </div>
  );
}

function ClipRow({
  clip,
  modelTags,
  isFirst,
  isLast,
  nextClipDone,
  anyActive,
  collapseSignal,
  onUpdate,
  onGenerate,
  onAnalyze,
  analyzing,
  onDelete,
}: {
  clip: Clip;
  modelTags: ModelTag[];
  isFirst: boolean;
  isLast: boolean;
  nextClipDone: boolean;
  anyActive: boolean;
  collapseSignal: { action: "collapse" | "expand"; token: number } | null;
  onUpdate: (body: Partial<Clip>) => void;
  onGenerate: () => void;
  onAnalyze: () => void;
  analyzing: boolean;
  onDelete: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: clip.id });
  const style = { transform: CSS.Transform.toString(transform), transition };
  const [shotPromptDraft, setShotPromptDraft] = useState(clip.shot_prompt);
  const [expanded, setExpanded] = useState(clip.status !== "done");
  const [previewFull, setPreviewFull] = useState(false);
  const statusRef = useRef(clip.status);
  statusRef.current = clip.status;

  useEffect(() => {
    if (!collapseSignal) return;
    setExpanded(collapseSignal.action === "expand" || statusRef.current !== "done");
  }, [collapseSignal]);

  const hasOwnSegment = !!clip.own_segment_url && clip.own_segment_url !== clip.output_url;
  const previewUrl = previewFull || !hasOwnSegment ? clip.output_url : clip.own_segment_url;
  const canBridge = !isLast && nextClipDone;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex gap-3 rounded-lg border border-border border-l-4 p-2.5 ${isDragging ? "opacity-50" : ""}`}
      data-status={clip.status}
    >
      <div
        {...attributes}
        {...listeners}
        className="flex min-w-8 cursor-grab flex-col items-center gap-1 font-semibold"
        title="Drag to reorder"
      >
        #{clip.order}
      </div>

      {!expanded ? (
        <button
          className="flex min-w-0 flex-1 items-center gap-2.5 border-0 bg-transparent p-0 text-left"
          onClick={() => setExpanded(true)}
        >
          {clip.output_url && (
            <video className="h-10 w-16 shrink-0 rounded border border-border object-cover" src={mediaUrl(clip.output_url) ?? undefined} muted />
          )}
          <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap opacity-85">{clip.shot_prompt || "(no prompt)"}</span>
          <span className="shrink-0 text-sm opacity-75">{formatFrames(clip.video_length)}</span>
          <StatusBadge status={clip.status} />
          <ChevronRight size={16} className="shrink-0 opacity-60" />
        </button>
      ) : (
        <div className="flex flex-1 flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm opacity-75">{formatFrames(clip.video_length)}</span>
            {clip.status === "done" && (
              <button
                title="Collapse"
                className="border-0 bg-transparent px-1 py-0 opacity-60 hover:opacity-100"
                onClick={() => setExpanded(false)}
              >
                <ChevronDown size={16} />
              </button>
            )}
          </div>
          <ShotPromptEditor
            initialValue={clip.shot_prompt}
            modelTags={modelTags}
            onChange={setShotPromptDraft}
            onBlur={() => onUpdate({ shot_prompt: shotPromptDraft })}
          />
          <span className={wordCountClass(wordCount(shotPromptDraft))}>
            {wordCount(shotPromptDraft)} / {WORD_TARGET_MIN}-{WORD_TARGET_MAX} words
          </span>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm">
              Seed
              <input type="number" value={clip.seed} onChange={(e) => onUpdate({ seed: Number(e.target.value) })} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Frames
              <input type="number" value={clip.video_length} onChange={(e) => onUpdate({ video_length: Number(e.target.value) })} />
            </label>
            <StatusBadge status={clip.status} />
            <button disabled={anyActive} onClick={onGenerate}>{clip.status === "done" ? "Regenerate" : "Generate"}</button>
            {clip.status === "done" && (
              <button disabled={anyActive || analyzing} onClick={onAnalyze} title="Check for duplicated/cloned people, ghosting artifacts, and voice consistency">
                {analyzing ? "Analyzing…" : clip.qa_report ? "Re-analyze" : "Analyze"}
              </button>
            )}
            <button className="border-0 bg-transparent p-0 text-danger" onClick={onDelete}>Delete</button>
          </div>
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!clip.continue_from_previous}
              disabled={isFirst}
              className="mt-0.5"
              onChange={(e) => onUpdate({ continue_from_previous: e.target.checked })}
            />
            Continue from previous clip (real video continuation, not just a shared description — the preceding
            clip must already be done)
          </label>
          <label className="flex items-start gap-2 text-sm" title={!canBridge ? "The next clip must exist and already be done to bridge into it" : undefined}>
            <input
              type="checkbox"
              checked={!!clip.bridge_to_next}
              disabled={!canBridge}
              className="mt-0.5"
              onChange={(e) => onUpdate({ bridge_to_next: e.target.checked })}
            />
            Bridge to next clip (steer this regeneration to land back on the next clip's existing first frame, so
            the rest of the chain doesn't need to be redone)
          </label>
          {clip.error && <div className="whitespace-pre-wrap rounded border border-danger bg-red-950/30 px-3 py-2 text-danger">{clip.error}</div>}
          {previewUrl && (
            <div className="flex flex-col items-start gap-1">
              <video controls width={320} className="max-w-full rounded" src={mediaUrl(previewUrl) ?? undefined} />
              {hasOwnSegment && (
                <button onClick={() => setPreviewFull(!previewFull)}>
                  {previewFull ? "Show this clip's own segment only" : "Show full chain up to this clip"}
                </button>
              )}
            </div>
          )}
          {clip.tail_frame_urls.length > 0 && (
            <div className="flex flex-col gap-1">
              <span className="text-sm opacity-75" title="The literal last ~2s of this clip's output — check here for identity clones or blends before trusting it as a continuation source">
                Tail check (last ~2s) — click a frame to inspect closely
              </span>
              <div className="flex flex-wrap gap-1.5">
                {clip.tail_frame_urls.map((url) => (
                  <a key={url} href={mediaUrl(url) ?? undefined} target="_blank" rel="noreferrer">
                    <img src={mediaUrl(url) ?? undefined} alt="Tail frame" className="h-16 w-auto rounded border border-border object-cover hover:border-accent" />
                  </a>
                ))}
              </div>
            </div>
          )}
          {clip.qa_report && <QaReportPanel report={clip.qa_report} />}
          <GenerationParams settings={clip.last_generation_settings} durationSeconds={clip.generation_duration_seconds} />
        </div>
      )}
    </div>
  );
}

function basename(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

function QaReportPanel({ report }: { report: QaReport }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-bg-alt p-3 text-sm">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-text-h">QA report</span>
        <span className="text-xs opacity-60">{new Date(report.analyzed_at * 1000).toLocaleString()}</span>
      </div>
      <div>
        <div className="mb-1 text-xs font-semibold uppercase opacity-60">Visual (duplicates / ghosting)</div>
        <p className="whitespace-pre-wrap">{report.visual_analysis}</p>
      </div>
      {report.voice_results.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold uppercase opacity-60">Voice consistency</div>
          <div className="flex flex-col gap-1">
            {report.voice_results.map((r) => (
              <div key={r.reference_path} className="flex items-center gap-2">
                <span className={`rounded-full px-2 py-0.5 text-xs text-white ${r.same_speaker ? "bg-status-done" : "bg-status-failed"}`}>
                  {r.same_speaker ? "matches" : "not detected"}
                </span>
                <span className="font-mono text-xs opacity-75">{basename(r.reference_path)}</span>
                <span className="text-xs opacity-60">score {r.score.toFixed(2)}</span>
              </div>
            ))}
          </div>
          <p className="mt-1 text-xs opacity-60">
            Compares each reference voice against the clip's whole audio track, not per-speaker segments — a coarse
            check, not precise per-line attribution.
          </p>
        </div>
      )}
    </div>
  );
}
