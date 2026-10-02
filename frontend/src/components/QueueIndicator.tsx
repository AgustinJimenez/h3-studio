import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ChevronDown, ChevronUp, Loader2, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import JobProgress from "./JobProgress";
import { useActiveJobs } from "../lib/queries";
import { requestFocus } from "../lib/jobFocus";
import type { ActiveJob } from "../schemas";

function elapsed(startedAt: number | null | undefined, now: number) {
  if (!startedAt) return "";
  const s = Math.max(0, Math.round(now / 1000 - startedAt));
  return s >= 60 ? `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s` : `${s}s`;
}

function where(job: ActiveJob) {
  return [job.video_title, job.character_name].filter(Boolean).join(" · ");
}

// Floating, app-wide view of the real WanGP queue (running job + pending
// ones) so a generation started further up/down a page — or on another
// page — never goes out of sight. Clicking a row opens that item's page and
// scrolls to it (see lib/jobFocus.ts).
export default function QueueIndicator() {
  const { data: jobs = [] } = useActiveJobs();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(Date.now());
  const qc = useQueryClient();
  const [cancelling, setCancelling] = useState<string | null>(null);

  async function cancel(job: ActiveJob) {
    setCancelling(job.job_id);
    try {
      await api.cancelJob(job.job_id);
      toast.success(job.status === "running" ? "Stopping…" : "Removed from the queue");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setCancelling(null);
      qc.invalidateQueries({ queryKey: ["activeJobs"] });
      qc.invalidateQueries({ queryKey: ["swaps"] });
      qc.invalidateQueries({ queryKey: ["swap"] });
    }
  }

  useEffect(() => {
    if (jobs.length === 0) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [jobs.length]);

  if (jobs.length === 0) return null;

  const running = jobs.filter((j) => j.status === "running").length;
  const queued = jobs.length - running;

  async function go(job: ActiveJob) {
    if (job.kind === "animate") {
      await navigate({ to: "/animate-jobs" });
    } else if (job.kind === "swap" && job.swap_id) {
      await navigate({ to: "/swaps/$id", params: { id: job.swap_id } });
    } else if (job.character_id && job.video_id) {
      await navigate({ to: "/videos/$id/characters/$characterId", params: { id: job.video_id, characterId: job.character_id } });
    } else if (job.video_id) {
      await navigate({ to: "/videos/$id", params: { id: job.video_id } });
    }
    if (job.target_id) requestFocus(job.target_id);
  }

  return (
    // One widget: a pill when collapsed that grows upward into the full list
    // (the toggle bar stays at the bottom, anchored to the corner).
    <div
      className={`fixed bottom-4 right-4 z-50 flex max-w-[calc(100vw-2rem)] flex-col overflow-hidden border border-border bg-bg-alt shadow-lg ${
        open ? "w-80 rounded-lg" : "rounded-full"
      }`}
    >
      {open && (
        <ul className="max-h-80 overflow-y-auto border-b border-border py-1">
          {jobs.map((job) => (
            <li key={job.job_id} className="flex items-stretch">
              <button
                onClick={() => go(job)}
                className="flex min-w-0 flex-1 items-start gap-2 rounded-none border-0 bg-transparent px-3 py-2 text-left hover:bg-bg"
                title="Go to this item"
              >
                {job.status === "running" ? (
                  <Loader2 size={14} className="mt-0.5 shrink-0 animate-spin text-accent" />
                ) : (
                  <span className="mt-0.5 w-3.5 shrink-0 text-center text-xs opacity-60">{job.position}</span>
                )}
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm">{job.label}</span>
                  {where(job) && <span className="truncate text-xs opacity-65">{where(job)}</span>}
                  {job.status === "running" && <JobProgress progress={job.progress} />}
                </span>
                <span className="ml-auto shrink-0 text-xs opacity-75">
                  {job.status === "running" ? elapsed(job.started_at, now) : "queued"}
                </span>
              </button>
              <button
                className="shrink-0 rounded-none border-0 bg-transparent px-2.5 text-text-muted hover:bg-bg hover:text-danger"
                title={job.status === "running" ? "Stop this generation" : "Remove from the queue"}
                aria-label={job.status === "running" ? "Stop this generation" : "Remove from the queue"}
                disabled={cancelling === job.job_id}
                onClick={() => cancel(job)}
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 rounded-none border-0 bg-transparent px-3.5 py-2 text-sm"
        title={open ? "Hide queue" : "Show queue"}
      >
        <Loader2 size={15} className={running ? "animate-spin text-accent" : "opacity-60"} />
        <span>
          {open && <span className="mr-1.5 text-xs font-semibold uppercase opacity-75">Queue</span>}
          {running > 0 && `${running} running`}
          {running > 0 && queued > 0 && " · "}
          {queued > 0 && `${queued} queued`}
        </span>
        <span className="ml-auto">{open ? <ChevronDown size={14} /> : <ChevronUp size={14} />}</span>
      </button>
    </div>
  );
}
