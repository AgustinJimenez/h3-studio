import { Dices } from "lucide-react";
import { useEffect, useState } from "react";
import StatusBadge from "./StatusBadge";
import { jobTargetDomId } from "../lib/jobFocus";
import JobProgress from "./JobProgress";
import { useActiveJobs } from "../lib/queries";
import type { SwapPass } from "../schemas";

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-wide text-text-muted">{label}</div>
      <div className="break-words text-xs text-text-h">{children}</div>
    </div>
  );
}

function elapsed(startedAt: number | null | undefined, now: number) {
  if (!startedAt) return null;
  const s = Math.max(0, Math.round(now / 1000 - startedAt));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default function SwapPassRow({
  pass,
  label,
  onSavePrompt,
  onRun,
  onRerun,
  onCancel,
}: {
  pass: SwapPass;
  label: string;
  onSavePrompt: (prompt: string) => void;
  onRun: (seed?: number) => void; // a seed typed on this pass overrides the one at the top, for this scene only
  onRerun: (seed?: number) => void;
  onCancel: () => void;
}) {
  const active = pass.status === "queued" || pass.status === "running";
  const [prompt, setPrompt] = useState(pass.prompt);
  // Details are open while the pass is queued/running (that is when you want to know what it is doing).
  const [open, setOpen] = useState(active);
  const [now, setNow] = useState(Date.now());
  const [seed, setSeed] = useState("");
  const ownSeed = seed.trim() !== "" ? Number(seed) : undefined;
  const dirty = prompt !== pass.prompt;
  const params = pass.params;
  // The same live progress the floating queue shows (it comes from the active-jobs list, keyed by this pass).
  const { data: activeJobs } = useActiveJobs();
  const job = activeJobs?.find((j) => j.target_id === pass.id);

  useEffect(() => {
    if (active) setOpen(true);
  }, [active]);
  useEffect(() => {
    if (pass.status !== "running") return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [pass.status]);

  return (
    <div id={jobTargetDomId(pass.id)} className="rounded border border-border bg-bg p-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={pass.status} />
        <span className="font-medium text-text-h">{label}</span>
        <span className="text-xs text-text-muted">
          chunk {pass.chunk_index + 1} · {pass.quality}
          {pass.status === "running" && elapsed(pass.started_at, now) ? ` · running ${elapsed(pass.started_at, now)}` : ""}
          {pass.seconds ? ` · took ${Math.round(pass.seconds / 60)} min` : ""}
          {pass.mean_luma != null ? ` · luma ${pass.mean_luma}` : ""}
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          {!active && pass.status !== "blocked" && (
            <div className="relative w-36">
              <input
                className="w-full py-0.5 pr-7 text-xs"
                placeholder={params?.seed != null ? `Seed (${params.seed})` : "Seed"}
                value={seed}
                onChange={(e) => setSeed(e.target.value.replace(/[^0-9]/g, ""))}
                title="Seed for this scene's next run; empty = the seed chosen above (or the project seed)"
              />
              <button
                type="button"
                className="absolute right-1 top-1/2 -translate-y-1/2 border-0 bg-transparent p-0.5 text-text-muted hover:text-text-h"
                title="Random seed for this scene"
                aria-label="Random seed for this scene"
                onClick={() => setSeed(String(Math.floor(Math.random() * 1_000_000)))}
              >
                <Dices size={14} />
              </button>
            </div>
          )}
          <button className="py-0.5 text-xs" onClick={() => setOpen((o) => !o)}>
            {open ? "Hide details" : "Details"}
          </button>
          {active ? (
            <button className="py-0.5 text-xs" onClick={onCancel}>
              Cancel
            </button>
          ) : (
            pass.status !== "blocked" &&
            (pass.status === "draft" && !pass.output_path ? (
              // Not run yet: starts the scene with the quality, size and seed chosen above (the same as "Run all", for this scene).
              <button className="py-0.5 text-xs" title="Runs this scene with the quality and size chosen above, and this scene's seed if you typed one" onClick={() => onRun(ownSeed)}>
                Run
              </button>
            ) : (
              <button className="py-0.5 text-xs" onClick={() => onRerun(ownSeed)}>
                Re-run
              </button>
            ))
          )}
        </span>
      </div>
      {pass.status === "running" && (
        <div className="mt-1 max-w-md text-xs">
          <JobProgress progress={job?.progress} />
        </div>
      )}
      {pass.status === "queued" && job && <div className="mt-1 text-xs text-text-muted">Waiting in the queue · position {job.position}</div>}
      {pass.error && <div className="mt-1 whitespace-pre-wrap text-xs text-danger">{pass.error}</div>}
      {open && (
        <div className="mt-2 space-y-2">
          {params && (
            <div className="grid gap-x-4 gap-y-2 rounded border border-border p-2 sm:grid-cols-2 lg:grid-cols-4">
              <Fact label="Replaces">{params.target || "—"}</Fact>
              <Fact label="With">{params.character || "—"}</Fact>
              <Fact label="Source">{params.source}</Fact>
              <Fact label="Frames">
                {params.frames_24} real · {params.padded_frames} rendered (24 fps)
              </Fact>
              <Fact label="Sampling">
                {params.steps} steps · {params.sampler} / {params.scheduler}
              </Fact>
              <Fact label="Resolution">
                {params.width}×{params.height}
              </Fact>
              <Fact label="Seed">{params.seed}</Fact>
              <Fact label="Model">{params.model.replace(".safetensors", "")}</Fact>
              <div className="sm:col-span-2 lg:col-span-4">
                <Fact label="LoRAs">{params.loras.map((l) => l.replace(".safetensors", "")).join(" + ")}</Fact>
              </div>
            </div>
          )}
          <div>
            <div className="text-[10px] uppercase tracking-wide text-text-muted">Prompt{active ? " (locked while queued/running)" : ""}</div>
            <textarea className="h-40 w-full text-xs" value={prompt} onChange={(e) => setPrompt(e.target.value)} readOnly={active} />
            {!active && (
              <button className="mt-1 py-0.5 text-xs" disabled={!dirty} onClick={() => onSavePrompt(prompt)}>
                Save prompt
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
