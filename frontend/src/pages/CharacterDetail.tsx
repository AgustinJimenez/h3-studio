import { useEffect, useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { Controller, useForm } from "react-hook-form";
import { ArrowLeft } from "lucide-react";
import { mediaUrl } from "../lib/api";
import {
  useCharacter,
  useUpdateCharacter,
  useAddReference,
  useDeleteReference,
  useUpscaleReference,
  useCreateReferenceVideo,
  useUpdateReferenceVideo,
  useDeleteReferenceVideo,
  useGenerateReferenceVideo,
  useUpscaleReferenceVideo,
  useCaptureReferenceFrame,
} from "../lib/queries";
import { wordCount, wordCountClass, WORD_TARGET_MIN, WORD_TARGET_MAX } from "../lib/wordCount";
import ReferenceThumb from "../components/ReferenceThumb";
import StatusBadge from "../components/StatusBadge";
import GenerationParams from "../components/GenerationParams";
import RetentionSelect from "../components/RetentionSelect";
import type { ReferenceVideo } from "../schemas";

const REFERENCE_TYPES = ["image", "video", "audio"] as const;
const ACTIVE_STATUSES = new Set(["queued", "running"]);

type CharacterFieldsForm = {
  name: string;
  retention: string;
  identity_description: string;
  wardrobe_notes: string;
};

export default function CharacterDetail() {
  const { id, characterId } = useParams({ from: "/videos/$id/characters/$characterId" });
  const { data: character, error } = useCharacter(id, characterId);

  const updateCharacter = useUpdateCharacter(id, characterId);
  const addReference = useAddReference(id, characterId);
  const deleteReference = useDeleteReference(id, characterId);
  const upscaleReference = useUpscaleReference(id, characterId);
  const createReferenceVideo = useCreateReferenceVideo(id, characterId);
  const deleteReferenceVideo = useDeleteReferenceVideo(id, characterId);

  const [newRefDraft, setNewRefDraft] = useState({ type: "image" as string, path: "", note: "" });
  const [newRvName, setNewRvName] = useState("");

  const { register, control, reset, handleSubmit } = useForm<CharacterFieldsForm>({
    values: character
      ? {
          name: character.name,
          retention: character.retention || "fully_preserved",
          identity_description: character.identity_description,
          wardrobe_notes: character.wardrobe_notes,
        }
      : undefined,
  });

  if (error) return <div className="mx-auto max-w-4xl px-4 py-6 text-danger">{error.message}</div>;
  if (!character) return <div className="mx-auto max-w-4xl px-4 py-6">Loading...</div>;

  function saveFields(fields: Partial<CharacterFieldsForm>) {
    updateCharacter.mutate(fields);
  }

  function addRef() {
    if (!newRefDraft.path.trim()) return;
    addReference.mutate(newRefDraft, { onSuccess: () => setNewRefDraft({ type: "image", path: "", note: "" }) });
  }

  function addRv() {
    createReferenceVideo.mutate({ name: newRvName || "Reference video" }, { onSuccess: () => setNewRvName("") });
  }

  return (
    <div className="mx-auto max-w-4xl px-4 pb-52 pt-6">
      <Link to="/videos/$id/characters" params={{ id }} className="inline-flex items-center gap-1"><ArrowLeft size={14} /> Characters</Link>
      <h1 className="mb-4 mt-2 text-2xl font-bold">Subject {character.order + 1}: {character.name || "(unnamed)"}</h1>

      <form onBlur={handleSubmit(saveFields)} onSubmit={(e) => e.preventDefault()}>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Name
            <input {...register("name")} onBlur={() => reset(undefined, { keepValues: true })} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Retention
            <Controller
              name="retention"
              control={control}
              render={({ field }) => (
                <RetentionSelect
                  value={field.value}
                  onChange={(value) => {
                    field.onChange(value);
                    saveFields({ retention: value });
                  }}
                />
              )}
            />
          </label>
        </div>
        <label className="mt-3 flex flex-col gap-1 text-sm">
          Identity description (physical traits to preserve)
          <textarea rows={2} placeholder="his exact facial identity, beard, hair, and build" {...register("identity_description")} />
        </label>
        <label className="mt-3 flex flex-col gap-1 text-sm">
          Wardrobe / props for this video
          <textarea
            rows={2}
            placeholder="For this video he wears a tie-dye windbreaker and cargo pants, and holds a flashlight."
            {...register("wardrobe_notes")}
          />
        </label>
      </form>

      <h2 className="mb-1 mt-5 text-xl font-bold">References</h2>
      <p className="mb-2 text-sm opacity-75">
        This is the resource list the main pipeline actually draws from when composing a generation (identity
        photos, wardrobe/style images, voice/motion clips, and any frames captured below).
      </p>
      <div className="mt-1 flex flex-col gap-1.5 border-t border-dashed border-border pt-2">
        {character.references.map((ref) => (
          <div key={ref.id} className="flex items-center gap-2.5">
            <ReferenceThumb type={ref.type} path={ref.upscale?.status === "done" ? ref.upscale.output_path : ref.path} />
            <span className="rounded-full bg-status-draft px-2 py-0.5 text-xs uppercase text-white">{ref.type}</span>
            <span className="flex-1 overflow-hidden text-ellipsis font-mono text-xs opacity-85">
              {ref.path}
              {ref.note && <div className="text-accent opacity-100">note: {ref.note}</div>}
              {ref.upscale?.status && ref.upscale.status !== "none" && (
                <div className="text-accent opacity-100">
                  upscale: {ref.upscale.status}{ref.upscale.error ? ` — ${ref.upscale.error}` : ""}
                </div>
              )}
            </span>
            {ref.type === "image" && (
              <button disabled={ACTIVE_STATUSES.has(ref.upscale?.status ?? "")} onClick={() => upscaleReference.mutate(ref.id)}>
                {ref.upscale?.status === "done" ? "Re-upscale" : "Upscale"}
              </button>
            )}
            <button className="border-0 bg-transparent p-0 text-danger" onClick={() => deleteReference.mutate(ref.id)}>Remove</button>
          </div>
        ))}
        <div className="flex flex-wrap items-end gap-3">
          <select value={newRefDraft.type} onChange={(e) => setNewRefDraft({ ...newRefDraft, type: e.target.value })} className="w-auto">
            {REFERENCE_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <input
            placeholder="Full file path..."
            value={newRefDraft.path}
            onChange={(e) => setNewRefDraft({ ...newRefDraft, path: e.target.value })}
            className="max-w-xs"
          />
          <input
            placeholder="Optional note, e.g. 'wardrobe and costume style reference' — leave blank if this is a normal identity reference"
            value={newRefDraft.note}
            onChange={(e) => setNewRefDraft({ ...newRefDraft, note: e.target.value })}
            className="max-w-sm"
          />
          <button onClick={addRef}>Add reference</button>
        </div>
      </div>

      <h2 className="mb-1 mt-5 text-xl font-bold">Reference video studio</h2>
      <p className="mb-2 text-sm opacity-75">
        Generate any number of small videos from this character's raw references above — a neutral turnaround,
        a specific pose, an emotion, an outfit test. Scrub each one and capture clean frames as new image
        references above (unlike video/audio refs, image refs aren't duration-capped). One entry can also be
        marked "active" to substitute for the raw references directly in real generations, if you'd rather
        reuse a whole video than picked stills.
      </p>

      <div className="flex flex-col gap-3">
        {character.reference_videos.map((rv) => (
          <ReferenceVideoCard
            key={rv.id}
            videoId={id}
            characterId={characterId}
            rv={rv}
            isActive={character.active_reference_video_id === rv.id}
            onActivate={() => updateCharacter.mutate({ active_reference_video_id: rv.id })}
            onDeactivate={() => updateCharacter.mutate({ active_reference_video_id: "" })}
            onDelete={() => deleteReferenceVideo.mutate(rv.id)}
          />
        ))}
      </div>

      <div className="my-4 flex items-end gap-3 rounded-lg border border-dashed border-border p-3.5">
        <input
          placeholder="Name, e.g. 'Angry close-up' or 'Neutral turnaround'"
          value={newRvName}
          onChange={(e) => setNewRvName(e.target.value)}
          className="max-w-xs"
        />
        <button onClick={addRv}>Add reference video</button>
      </div>
    </div>
  );
}

function ReferenceVideoCard({
  videoId,
  characterId,
  rv,
  isActive,
  onActivate,
  onDeactivate,
  onDelete,
}: {
  videoId: string;
  characterId: string;
  rv: ReferenceVideo;
  isActive: boolean;
  onActivate: () => void;
  onDeactivate: () => void;
  onDelete: () => void;
}) {
  const updateReferenceVideo = useUpdateReferenceVideo(videoId, characterId);
  const generateReferenceVideo = useGenerateReferenceVideo(videoId, characterId);
  const upscaleReferenceVideo = useUpscaleReferenceVideo(videoId, characterId);
  const captureReferenceFrame = useCaptureReferenceFrame(videoId, characterId);

  const [draft, setDraft] = useState(rv);
  const [captureTime, setCaptureTime] = useState(0);
  useEffect(() => setDraft(rv), [rv]);

  const rvActive = ACTIVE_STATUSES.has(rv.status);
  const rvuActive = ACTIVE_STATUSES.has(rv.upscale?.status ?? "");
  const captureSourceUrl = rv.upscale?.status === "done" ? rv.upscale.output_url : rv.output_url;

  function saveDraft() {
    updateReferenceVideo.mutate({
      referenceVideoId: rv.id,
      body: {
        name: draft.name,
        style_prompt: draft.style_prompt,
        environment_prompt: draft.environment_prompt,
        character_prompt: draft.character_prompt,
        action_prompt: draft.action_prompt,
        seed: Number(draft.seed),
        video_length: Number(draft.video_length),
      },
    });
  }

  function generate() {
    saveDraft();
    generateReferenceVideo.mutate(rv.id);
  }

  return (
    <details open className="rounded-lg border border-border bg-bg-alt p-3.5">
      <summary className="cursor-pointer font-semibold text-text-h">
        {rv.name || "Reference video"} — <StatusBadge status={rv.status === "none" ? "draft" : rv.status} label={rv.status} />
        {isActive && <span className="ml-1.5 inline-block"><StatusBadge status="done" label="active" /></span>}
      </summary>
      <label className="mt-2 flex flex-col gap-1 text-sm">
        Name
        <input value={draft.name || ""} onChange={(e) => setDraft({ ...draft, name: e.target.value })} onBlur={saveDraft} />
      </label>
      <label className="mt-2 flex flex-col gap-1 text-sm">
        Style (rendering style — realistic vs. cartoon, color grading, grain; reusable across everything)
        <textarea
          rows={2}
          placeholder="Photorealistic, cinematic color grading, natural film grain, realistic skin texture and lighting, no over-smoothing or plastic look, no cartoon or illustrated rendering anywhere in the shot."
          value={draft.style_prompt || ""}
          onChange={(e) => setDraft({ ...draft, style_prompt: e.target.value })}
          onBlur={saveDraft}
        />
      </label>
      <label className="mt-2 flex flex-col gap-1 text-sm">
        Environment / ambient (background, lighting — usually reusable across shots/characters)
        <textarea
          rows={2}
          placeholder="Plain seamless white studio background, evenly lit with soft, shadowless studio lighting, no props, no other objects in frame."
          value={draft.environment_prompt || ""}
          onChange={(e) => setDraft({ ...draft, environment_prompt: e.target.value })}
          onBlur={saveDraft}
        />
      </label>
      <label className="mt-2 flex flex-col gap-1 text-sm">
        Character aspect (expression, stance, demeanor — no timing, reusable across different actions)
        <textarea
          rows={2}
          placeholder="Calm, neutral expression, standing straight, arms relaxed at the sides."
          value={draft.character_prompt || ""}
          onChange={(e) => setDraft({ ...draft, character_prompt: e.target.value })}
          onBlur={saveDraft}
        />
      </label>
      <label className="mt-2 flex flex-col gap-1 text-sm">
        Action (shot structure — framing, camera cuts/timing, dialogue; the part that usually changes every time)
        <textarea
          rows={3}
          placeholder="[Shot 1] Close-up on the face, speaking to camera... [Shot 2] At 00:0X.000, camera cuts to a wider shot showing the full body..."
          value={draft.action_prompt || ""}
          onChange={(e) => setDraft({ ...draft, action_prompt: e.target.value })}
          onBlur={saveDraft}
        />
        <span className={wordCountClass(wordCount(draft.action_prompt))}>
          {wordCount(draft.action_prompt)} / {WORD_TARGET_MIN}-{WORD_TARGET_MAX} words
        </span>
      </label>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Seed
          <input type="number" value={draft.seed ?? -1} onChange={(e) => setDraft({ ...draft, seed: Number(e.target.value) })} onBlur={saveDraft} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Frames
          <input
            type="number"
            value={draft.video_length ?? 174}
            onChange={(e) => setDraft({ ...draft, video_length: Number(e.target.value) })}
            onBlur={saveDraft}
          />
        </label>
        <button disabled={rvActive} onClick={generate}>{rv.status === "done" ? "Regenerate" : "Generate"}</button>
        {rv.status === "done" && !isActive && <button onClick={onActivate}>Use as active reference</button>}
        {isActive && <button onClick={onDeactivate}>Stop using as active reference</button>}
        <button className="border-0 bg-transparent p-0 text-danger" onClick={onDelete}>Delete</button>
      </div>
      {rv.error && <div className="mt-2 whitespace-pre-wrap rounded border border-danger bg-red-950/30 px-3 py-2 text-danger">{rv.error}</div>}
      {rv.output_url && <video controls width={320} className="mt-1.5 max-w-full rounded" src={mediaUrl(rv.output_url) ?? undefined} />}
      <GenerationParams settings={rv.last_generation_settings} durationSeconds={rv.generation_duration_seconds} />

      {rv.status === "done" && (
        <div className="mt-3 border-t border-dashed border-border pt-2.5">
          <div className="flex items-end gap-3">
            <StatusBadge
              status={rv.upscale?.status === "none" || !rv.upscale?.status ? "draft" : rv.upscale.status}
              label={`upscale: ${rv.upscale?.status || "none"}`}
            />
            <button disabled={rvuActive} onClick={() => upscaleReferenceVideo.mutate(rv.id)}>
              {rv.upscale?.status === "done" ? "Re-upscale (1.5x, FlashVSR)" : "Upscale (1.5x, FlashVSR)"}
            </button>
          </div>
          {rv.upscale?.error && <div className="mt-2 whitespace-pre-wrap rounded border border-danger bg-red-950/30 px-3 py-2 text-danger">{rv.upscale.error}</div>}

          {captureSourceUrl && (
            <>
              <video
                controls
                width={320}
                className="mt-1.5 max-w-full rounded"
                src={mediaUrl(captureSourceUrl) ?? undefined}
                onTimeUpdate={(e) => setCaptureTime(e.currentTarget.currentTime)}
              />
              <div className="mt-2 flex items-center gap-3">
                <span>Scrub to a frame, then:</span>
                <span>{captureTime.toFixed(2)}s</span>
                <button onClick={() => captureReferenceFrame.mutate({ referenceVideoId: rv.id, body: { timestamp: captureTime, source: "auto" } })}>
                  Capture frame as new reference
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </details>
  );
}
