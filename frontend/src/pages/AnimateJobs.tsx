import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import {
  useAnimateJobs,
  useCreateAnimateJob,
  useUpdateAnimateJob,
  useDeleteAnimateJob,
  useGenerateAnimateJob,
} from "../lib/queries";
import { mediaUrl } from "../lib/api";
import ConfirmDialog from "../components/ConfirmDialog";
import ReferenceThumb from "../components/ReferenceThumb";
import StatusBadge from "../components/StatusBadge";
import type { AnimateJob } from "../schemas";

const RESOLUTIONS = ["832x480", "480x832", "1280x720", "720x1280"];

type Draft = {
  label: string;
  control_video_path: string;
  character_image_path: string;
  mask_path: string;
  prompt: string;
  mode: "replace" | "replace_see_through";
  relighting: boolean;
  seed: number;
  video_length: number;
  resolution: string;
};

const EMPTY_DRAFT: Draft = {
  label: "",
  control_video_path: "",
  character_image_path: "",
  mask_path: "",
  prompt: "",
  mode: "replace",
  relighting: false,
  seed: -1,
  video_length: 81,
  resolution: "832x480",
};

export default function AnimateJobs() {
  const { data: jobs, error } = useAnimateJobs();
  const createJob = useCreateAnimateJob();
  const deleteJob = useDeleteAnimateJob();
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  function addJob() {
    if (!draft.control_video_path.trim() || !draft.character_image_path.trim()) return;
    createJob.mutate(
      { ...draft, mask_path: draft.mask_path.trim() || null },
      { onSuccess: () => setDraft(EMPTY_DRAFT) },
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 pb-16 pt-6">
      <Link to="/" className="inline-flex items-center gap-1"><ArrowLeft size={14} /> Videos</Link>
      <h1 className="mb-1 mt-2 text-2xl font-bold">Animate Jobs</h1>
      <p className="mb-4 text-sm opacity-75">
        Wan2.2-Animate "Replacement mode" — replace the person in a control video with the person from a reference
        photo, keeping the control video's own motion/camera/background. Standalone from the Video/Clip chain above:
        each job is independent. Paths are read directly from disk, same as reference paths elsewhere in this app.
        No per-person mask is generated automatically — leave <em>Mask path</em> blank to accept a full-frame default,
        or paste the path to a pre-made mask video if you have one.
      </p>
      {error && <div className="mb-2 whitespace-pre-wrap rounded border border-danger bg-red-950/30 px-3 py-2 text-danger">{error.message}</div>}

      <div className="mb-4 rounded-lg border border-dashed border-border p-3.5">
        <h3 className="mb-2 font-semibold text-text-h">New job</h3>
        <AnimateJobFields draft={draft} setDraft={setDraft} />
        <button className="mt-2" disabled={createJob.isPending} onClick={addJob}>Create job</button>
      </div>

      <div className="flex flex-col gap-2.5">
        {jobs?.map((job) => (
          <AnimateJobRow key={job.id} job={job} onDelete={() => setPendingDeleteId(job.id)} />
        ))}
        {jobs?.length === 0 && <div className="py-6 opacity-60">No animate jobs yet — create one above.</div>}
      </div>

      <ConfirmDialog
        open={!!pendingDeleteId}
        onOpenChange={(open) => !open && setPendingDeleteId(null)}
        title="Delete this animate job?"
        description="Its generated output file (if any) is kept on disk."
        onConfirm={() => pendingDeleteId && deleteJob.mutate(pendingDeleteId)}
      />
    </div>
  );
}

function AnimateJobFields({ draft, setDraft }: { draft: Draft; setDraft: (fn: (d: Draft) => Draft) => void }) {
  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        Label
        <input
          placeholder="e.g. Scene 4 — Markos swap"
          value={draft.label}
          onChange={(e) => { const v = e.target.value; setDraft((d) => ({ ...d, label: v })); }}
        />
      </label>

      <div className="flex flex-wrap gap-3">
        <label className="flex min-w-[260px] flex-1 flex-col gap-1 text-sm">
          Control video path (driving motion + background)
          <input
            placeholder="C:\path\to\source_clip.mp4"
            value={draft.control_video_path}
            onChange={(e) => { const v = e.target.value; setDraft((d) => ({ ...d, control_video_path: v })); }}
            className="font-mono text-xs"
          />
        </label>
        <ReferenceThumb type="video" path={draft.control_video_path} />
      </div>

      <div className="flex flex-wrap gap-3">
        <label className="flex min-w-[260px] flex-1 flex-col gap-1 text-sm">
          Character image path (identity to insert)
          <input
            placeholder="C:\path\to\person.png"
            value={draft.character_image_path}
            onChange={(e) => { const v = e.target.value; setDraft((d) => ({ ...d, character_image_path: v })); }}
            className="font-mono text-xs"
          />
        </label>
        <ReferenceThumb type="image" path={draft.character_image_path} />
      </div>

      <label className="flex flex-col gap-1 text-sm">
        Mask path (optional — leave blank for full-frame default)
        <input
          placeholder="C:\path\to\mask.mp4"
          value={draft.mask_path}
          onChange={(e) => { const v = e.target.value; setDraft((d) => ({ ...d, mask_path: v })); }}
          className="font-mono text-xs"
        />
      </label>

      <label className="flex flex-col gap-1 text-sm">
        Prompt (plain text description of the desired scene/action)
        <textarea
          rows={3}
          value={draft.prompt}
          onChange={(e) => { const v = e.target.value; setDraft((d) => ({ ...d, prompt: v })); }}
        />
      </label>

      <div className="flex flex-wrap gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Mode
          <select
            value={draft.mode}
            onChange={(e) => { const v = e.target.value as Draft["mode"]; setDraft((d) => ({ ...d, mode: v })); }}
          >
            <option value="replace">Replace</option>
            <option value="replace_see_through">Replace — See Through Mask</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Resolution
          <select
            value={draft.resolution}
            onChange={(e) => { const v = e.target.value; setDraft((d) => ({ ...d, resolution: v })); }}
          >
            {RESOLUTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Video length (frames)
          <input
            type="number"
            value={draft.video_length}
            onChange={(e) => { const v = Number(e.target.value); setDraft((d) => ({ ...d, video_length: v })); }}
            className="w-24"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Seed
          <input
            type="number"
            value={draft.seed}
            onChange={(e) => { const v = Number(e.target.value); setDraft((d) => ({ ...d, seed: v })); }}
            className="w-28"
          />
        </label>
        <label className="flex items-start gap-2 self-end pb-1.5 text-sm">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={draft.relighting}
            onChange={(e) => { const v = e.target.checked; setDraft((d) => ({ ...d, relighting: v })); }}
          />
          Apply relighting
        </label>
      </div>
    </div>
  );
}

function AnimateJobRow({ job, onDelete }: { job: AnimateJob; onDelete: () => void }) {
  const updateJob = useUpdateAnimateJob();
  const deleteJob = useDeleteAnimateJob();
  const generateJob = useGenerateAnimateJob();
  const [draft, setDraft] = useState<Draft>({
    label: job.label,
    control_video_path: job.control_video_path,
    character_image_path: job.character_image_path,
    mask_path: job.mask_path ?? "",
    prompt: job.prompt,
    mode: job.mode,
    relighting: job.relighting,
    seed: job.seed,
    video_length: job.video_length ?? 81,
    resolution: job.resolution ?? "832x480",
  });

  function save() {
    updateJob.mutate({ id: job.id, body: { ...draft, mask_path: draft.mask_path.trim() || null } });
  }

  return (
    <div className="rounded-lg border border-border bg-bg-alt p-3.5">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <StatusBadge status={job.status} />
        <span className="font-semibold text-text-h">{job.label || "(untitled job)"}</span>
        <div className="ml-auto flex gap-2">
          <button onClick={save} disabled={updateJob.isPending}>Save</button>
          <button
            onClick={() => generateJob.mutate(job.id)}
            disabled={generateJob.isPending || job.status === "queued" || job.status === "running"}
          >
            {job.status === "done" ? "Regenerate" : "Generate"}
          </button>
          <button className="danger" onClick={onDelete}>Delete</button>
        </div>
      </div>

      {job.error && <div className="mb-2 whitespace-pre-wrap rounded border border-danger bg-red-950/30 px-3 py-2 text-sm text-danger">{job.error}</div>}

      <AnimateJobFields draft={draft} setDraft={setDraft} />

      {job.status === "done" && job.output_url && (
        <video className="mt-3 max-w-full rounded border border-border" src={mediaUrl(job.output_url) ?? undefined} controls />
      )}
    </div>
  );
}
