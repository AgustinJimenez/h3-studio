import { useRef, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Trash2 } from "lucide-react";
import { useCreateSwap, useDeleteSwap, useSwaps } from "../lib/swapQueries";
import { mediaUrl } from "../lib/api";
import ConfirmDialog from "../components/ConfirmDialog";
import StatusBadge from "../components/StatusBadge";
import type { SwapProject } from "../schemas";

function progress(p: SwapProject) {
  const total = p.passes.length;
  const done = p.passes.filter((x) => x.status === "done").length;
  return { total, done };
}

function overallStatus(p: SwapProject): string {
  if (p.final.status === "done") return "done";
  if (p.passes.some((x) => x.status === "running")) return "running";
  if (p.passes.some((x) => x.status === "queued")) return "queued";
  if (p.passes.some((x) => x.status === "failed")) return "failed";
  return "draft";
}

export default function SwapsList() {
  const { data: swaps, error } = useSwaps();
  const create = useCreateSwap();
  const remove = useDeleteSwap();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [toDelete, setToDelete] = useState<SwapProject | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    const project = await create.mutateAsync({ title: title.trim() || file.name.replace(/\.[^.]+$/, ""), file });
    if (project) await navigate({ to: "/swaps/$id", params: { id: project.id } });
  }

  return (
    <div className="mx-auto max-w-5xl px-4 pb-52 pt-6">
      <div className="mb-6 flex items-center justify-between gap-4 border-b border-border pb-5">
        <div>
          <Link to="/" className="mb-1 inline-flex items-center gap-1 text-sm text-text-muted no-underline">
            <ArrowLeft size={14} /> Projects
          </Link>
          <h1 className="text-3xl font-bold tracking-tight text-text-h">Character swap</h1>
          <p className="mt-1 text-sm text-text-muted">Replace the people in an existing video with your characters, scene by scene.</p>
        </div>
      </div>

      {error && <div className="mb-4 rounded-lg border border-danger px-4 py-3 text-danger">{(error as Error).message}</div>}

      <form className="mb-6 flex flex-wrap items-center gap-2" onSubmit={submit}>
        <input placeholder="Title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} className="w-56" />
        <input ref={fileRef} type="file" accept="video/*" required />
        <button type="submit" disabled={create.isPending}>
          {create.isPending ? "Uploading…" : "Upload video"}
        </button>
      </form>

      <div className="grid gap-3 sm:grid-cols-2">
        {(swaps ?? []).map((p) => {
          const { total, done } = progress(p);
          const thumb = mediaUrl(p.scenes[0]?.thumb_url);
          return (
            <div key={p.id} className="flex gap-3 rounded-lg border border-border bg-bg-alt p-3">
              {thumb ? <img src={thumb} alt="" className="h-28 w-16 shrink-0 rounded object-cover" /> : <div className="h-28 w-16 shrink-0 rounded bg-bg" />}
              <div className="min-w-0 flex-1">
                <Link to="/swaps/$id" params={{ id: p.id }} className="block truncate text-lg font-semibold text-text-h no-underline">
                  {p.title}
                </Link>
                <div className="mt-1 flex items-center gap-2 text-xs text-text-muted">
                  <StatusBadge status={overallStatus(p)} />
                  <span>{p.scenes.length} scenes</span>
                  <span>{p.source.duration.toFixed(1)}s</span>
                </div>
                {total > 0 && (
                  <div className="mt-2">
                    <div className="h-1.5 w-full overflow-hidden rounded bg-bg">
                      <div className="h-full bg-accent" style={{ width: `${(done / total) * 100}%` }} />
                    </div>
                    <div className="mt-1 text-xs text-text-muted">
                      {done}/{total} passes
                    </div>
                  </div>
                )}
              </div>
              <button className="self-start" title="Delete" onClick={() => setToDelete(p)}>
                <Trash2 size={14} />
              </button>
            </div>
          );
        })}
        {swaps && swaps.length === 0 && <p className="text-text-muted">No swap projects yet. Upload a video to start.</p>}
      </div>

      <ConfirmDialog
        open={toDelete !== null}
        onOpenChange={(o) => !o && setToDelete(null)}
        title={`Delete “${toDelete?.title ?? ""}”?`}
        description="The uploaded video, every pass output and the assembled video are deleted."
        onConfirm={() => toDelete && remove.mutate(toDelete.id)}
      />
    </div>
  );
}
