import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useVideos, useUnloadModel } from "../lib/queries";
import ConfirmDialog from "../components/ConfirmDialog";

export default function VideosList() {
  const { data: videos, error } = useVideos();
  const qc = useQueryClient();
  const unloadModel = useUnloadModel();
  const [title, setTitle] = useState("");
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const createVideo = useMutation({
    mutationFn: (t: string) => api.createVideo({ title: t }),
    onSuccess: () => {
      setTitle("");
      qc.invalidateQueries({ queryKey: ["videos"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteVideo = useMutation({
    mutationFn: (id: string) => api.deleteVideo(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["videos"] }),
    onError: (e: Error) => toast.error(e.message),
  });

  function removeVideo(id: string) {
    setPendingDeleteId(id);
  }

  const sortedVideos = videos
    ? [...videos].sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0))
    : [];

  return (
    <div className="mx-auto max-w-3xl px-4 pb-52 pt-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Videos</h1>
        <div className="flex gap-2">
          <button
            disabled={unloadModel.isPending}
            title="Free the currently-loaded model's GPU memory; the next generation reloads it automatically"
            onClick={() => unloadModel.mutate()}
          >
            Unload model
          </button>
          <Link to="/animate-jobs"><button>Animate jobs</button></Link>
          <Link to="/prompt-tags"><button>Prompt tags</button></Link>
        </div>
      </div>
      {error && <div className="mb-2 whitespace-pre-wrap rounded border border-danger bg-red-950/30 px-3 py-2 text-danger">{error.message}</div>}

      <form
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (title.trim()) createVideo.mutate(title.trim());
        }}
      >
        <input
          className="max-w-xs"
          placeholder="New video title..."
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <button disabled={createVideo.isPending} type="submit">Create video</button>
      </form>

      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
        {sortedVideos.map((v) => (
          <Link
            key={v.id}
            to="/videos/$id"
            params={{ id: v.id }}
            className="block rounded-lg border border-border bg-bg-alt p-3.5 no-underline hover:border-accent"
          >
            <div className="mb-1 font-semibold text-text-h">{v.title}</div>
            <div className="text-sm opacity-75">{v.done_count}/{v.clip_count} clips done</div>
            {v.created_at && (
              <div className="mt-1 text-xs opacity-50">
                {new Date(v.created_at * 1000).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </div>
            )}
            <button
              className="mt-2 border-0 bg-transparent p-0 text-danger"
              onClick={(e) => {
                e.preventDefault();
                removeVideo(v.id);
              }}
            >
              Delete
            </button>
          </Link>
        ))}
        {sortedVideos.length === 0 && <div className="py-6 opacity-60">No videos yet — create one above.</div>}
      </div>

      <ConfirmDialog
        open={!!pendingDeleteId}
        onOpenChange={(open) => !open && setPendingDeleteId(null)}
        title="Delete this video?"
        description="All its clips and characters will be removed. Generated files are kept on disk."
        onConfirm={() => pendingDeleteId && deleteVideo.mutate(pendingDeleteId)}
      />
    </div>
  );
}
