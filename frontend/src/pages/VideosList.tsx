import { useState, useMemo } from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, mediaUrl } from "../lib/api";
import { useVideos, useUnloadModel } from "../lib/queries";
import ConfirmDialog from "../components/ConfirmDialog";
import type { VideoSummary } from "../schemas";

type FilterStatus = "all" | "completed" | "in_progress" | "draft";
type SortOption = "newest" | "oldest" | "clips" | "az";

export default function VideosList() {
  const { data: videos, error } = useVideos();
  const qc = useQueryClient();
  const unloadModel = useUnloadModel();
  const [title, setTitle] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<FilterStatus>("all");
  const [sortBy, setSortBy] = useState<SortOption>("newest");
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const createVideo = useMutation({
    mutationFn: (t: string) => api.createVideo({ title: t }),
    onSuccess: () => {
      setTitle("");
      qc.invalidateQueries({ queryKey: ["videos"] });
      toast.success("Project created");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteVideo = useMutation({
    mutationFn: (id: string) => api.deleteVideo(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["videos"] });
      toast.success("Project deleted");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  function removeVideo(id: string, e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setPendingDeleteId(id);
  }

  // Filter & Search
  const filteredVideos = useMemo(() => {
    if (!videos) return [];
    return videos.filter((v: VideoSummary) => {
      // Search text
      if (search.trim()) {
        const q = search.toLowerCase();
        const matchesTitle = v.title.toLowerCase().includes(q);
        const matchesChar = v.character_names?.some((c) => c.toLowerCase().includes(q));
        const matchesRes = v.resolution?.toLowerCase().includes(q);
        if (!matchesTitle && !matchesChar && !matchesRes) return false;
      }
      // Status filter
      if (statusFilter === "completed") {
        return v.clip_count > 0 && v.done_count === v.clip_count;
      }
      if (statusFilter === "in_progress") {
        return v.has_running_job || (v.done_count > 0 && v.done_count < v.clip_count);
      }
      if (statusFilter === "draft") {
        return v.done_count === 0;
      }
      return true;
    });
  }, [videos, search, statusFilter]);

  // Sorting
  const sortedVideos = useMemo(() => {
    return [...filteredVideos].sort((a, b) => {
      if (sortBy === "newest") return (b.created_at ?? 0) - (a.created_at ?? 0);
      if (sortBy === "oldest") return (a.created_at ?? 0) - (b.created_at ?? 0);
      if (sortBy === "clips") return b.clip_count - a.clip_count;
      if (sortBy === "az") return a.title.localeCompare(b.title);
      return 0;
    });
  }, [filteredVideos, sortBy]);

  // Overall Stats
  const totalProjects = videos?.length ?? 0;
  const completedProjects = videos?.filter((v) => v.clip_count > 0 && v.done_count === v.clip_count).length ?? 0;
  const inProgressProjects = videos?.filter((v) => v.has_running_job || (v.done_count > 0 && v.done_count < v.clip_count)).length ?? 0;
  const draftProjects = videos?.filter((v) => v.done_count === 0).length ?? 0;

  return (
    <div className="mx-auto max-w-7xl px-4 pb-52 pt-6">
      {/* Top Studio Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-text-h">Studio Projects</h1>
          <p className="mt-1 text-sm text-text-muted">
            {totalProjects} total projects &bull; {completedProjects} completed &bull; MiniMax H3 Video Suite
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            disabled={unloadModel.isPending}
            title="Free GPU VRAM (next generation transparently reloads model)"
            onClick={() => unloadModel.mutate()}
            className="flex items-center gap-1.5"
          >
            <span className="inline-block h-2 w-2 rounded-full bg-accent animate-pulse" />
            Unload model
          </button>
          <Link to="/animate-jobs">
            <button>Animate jobs</button>
          </Link>
          <Link to="/prompt-tags">
            <button>Prompt tags</button>
          </Link>
        </div>
      </div>

      {error && (
        <div className="mb-4 whitespace-pre-wrap rounded-lg border border-danger bg-red-950/30 px-4 py-3 text-danger">
          {error.message}
        </div>
      )}

      {/* Action Bar: Create Project + Search & Filters */}
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        {/* Create Video Inline Form */}
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (title.trim()) createVideo.mutate(title.trim());
          }}
        >
          <input
            className="w-72"
            placeholder="New project title..."
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <button disabled={createVideo.isPending || !title.trim()} type="submit" className="whitespace-nowrap">
            + Create project
          </button>
        </form>

        {/* Search, Filter Pills & Sort */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Search Input */}
          <input
            className="w-48 text-sm"
            placeholder="Search projects..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          {/* Filter Pills */}
          <div className="flex rounded-lg border border-border bg-bg-alt p-0.5 text-xs font-medium">
            <button
              type="button"
              className={`rounded-md px-2.5 py-1 border-0 ${statusFilter === "all" ? "bg-accent text-white" : "bg-transparent opacity-70 hover:opacity-100"}`}
              onClick={() => setStatusFilter("all")}
            >
              All ({totalProjects})
            </button>
            <button
              type="button"
              className={`rounded-md px-2.5 py-1 border-0 ${statusFilter === "completed" ? "bg-accent text-white" : "bg-transparent opacity-70 hover:opacity-100"}`}
              onClick={() => setStatusFilter("completed")}
            >
              Done ({completedProjects})
            </button>
            <button
              type="button"
              className={`rounded-md px-2.5 py-1 border-0 ${statusFilter === "in_progress" ? "bg-accent text-white" : "bg-transparent opacity-70 hover:opacity-100"}`}
              onClick={() => setStatusFilter("in_progress")}
            >
              Active ({inProgressProjects})
            </button>
            <button
              type="button"
              className={`rounded-md px-2.5 py-1 border-0 ${statusFilter === "draft" ? "bg-accent text-white" : "bg-transparent opacity-70 hover:opacity-100"}`}
              onClick={() => setStatusFilter("draft")}
            >
              Drafts ({draftProjects})
            </button>
          </div>

          {/* Sort Selector */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortOption)}
            className="rounded-lg border border-border bg-bg-alt px-2.5 py-1.5 text-xs text-text-h"
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="clips">Most clips</option>
            <option value="az">Alphabetical</option>
          </select>
        </div>
      </div>

      {/* Responsive Visual Grid */}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(290px,1fr))] gap-5">
        {sortedVideos.map((v) => {
          const isComplete = v.clip_count > 0 && v.done_count === v.clip_count;
          const progressPerc = v.clip_count > 0 ? Math.round((v.done_count / v.clip_count) * 100) : 0;
          const isVideoPoster = v.thumbnail_url?.endsWith(".mp4");

          return (
            <Link
              key={v.id}
              to="/videos/$id"
              params={{ id: v.id }}
              className="group relative flex flex-col overflow-hidden rounded-xl border border-border bg-bg-alt no-underline transition-all duration-200 hover:-translate-y-1 hover:border-accent hover:shadow-lg hover:shadow-accent/5"
            >
              {/* Poster / Thumbnail Header (16:9 Aspect Ratio) */}
              <div className="relative aspect-video w-full overflow-hidden bg-zinc-900">
                {v.thumbnail_url ? (
                  isVideoPoster ? (
                    <video
                      src={mediaUrl(v.thumbnail_url) ?? undefined}
                      className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                      muted
                      playsInline
                      preload="metadata"
                    />
                  ) : (
                    <img
                      src={mediaUrl(v.thumbnail_url) ?? undefined}
                      alt={v.title}
                      className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                    />
                  )
                ) : (
                  <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-br from-zinc-800 to-zinc-950 text-zinc-600">
                    <svg className="h-10 w-10 stroke-current opacity-40" fill="none" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z" />
                    </svg>
                    <span className="mt-1 text-xs opacity-50">No footage yet</span>
                  </div>
                )}

                {/* Top Badges: Status & Resolution */}
                <div className="absolute inset-x-2 top-2 flex items-center justify-between gap-1 pointer-events-none">
                  {/* Status Badge */}
                  {isComplete ? (
                    <span className="rounded-md bg-emerald-950/80 px-2 py-0.5 text-[11px] font-medium text-emerald-300 backdrop-blur-sm border border-emerald-500/30">
                      Done
                    </span>
                  ) : v.has_running_job ? (
                    <span className="flex items-center gap-1 rounded-md bg-sky-950/80 px-2 py-0.5 text-[11px] font-medium text-sky-300 backdrop-blur-sm border border-sky-500/30">
                      <span className="inline-block h-1.5 w-1.5 rounded-full bg-sky-400 animate-ping" />
                      Rendering
                    </span>
                  ) : v.done_count > 0 ? (
                    <span className="rounded-md bg-amber-950/80 px-2 py-0.5 text-[11px] font-medium text-amber-300 backdrop-blur-sm border border-amber-500/30">
                      {v.done_count}/{v.clip_count} clips
                    </span>
                  ) : (
                    <span className="rounded-md bg-zinc-900/80 px-2 py-0.5 text-[11px] font-medium text-zinc-400 backdrop-blur-sm border border-zinc-700/50">
                      Draft
                    </span>
                  )}

                  {/* Resolution Badge */}
                  {v.resolution && (
                    <span className="rounded-md bg-black/70 px-2 py-0.5 text-[11px] font-semibold text-zinc-200 backdrop-blur-sm border border-white/10">
                      {v.resolution.includes("1080") || v.resolution.includes("1088") || v.resolution.includes("1920") ? "1080p" : v.resolution.includes("720") || v.resolution.includes("704") || v.resolution.includes("1280") ? "720p" : v.resolution}
                    </span>
                  )}
                </div>

                {/* Bottom Right: Duration Badge */}
                {v.total_duration_seconds && v.total_duration_seconds > 0 ? (
                  <div className="absolute bottom-2 right-2 rounded bg-black/80 px-1.5 py-0.5 text-[11px] font-mono font-medium text-zinc-200 backdrop-blur-sm border border-white/10">
                    {v.total_duration_seconds.toFixed(1)}s
                  </div>
                ) : null}

                {/* Hover Play / Open Overlay */}
                <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-accent text-white shadow-md">
                    <svg className="h-5 w-5 fill-current ml-0.5" viewBox="0 0 24 24">
                      <path d="M8 5v14l11-7z" />
                    </svg>
                  </div>
                </div>
              </div>

              {/* Card Body */}
              <div className="flex flex-1 flex-col p-4">
                {/* Title */}
                <div className="line-clamp-2 font-semibold text-text-h text-base leading-snug group-hover:text-accent">
                  {v.title}
                </div>

                {/* Characters Tag Row */}
                {v.character_names && v.character_names.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                    {v.character_names.map((name, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center rounded-md bg-zinc-800/80 px-2 py-0.5 text-[11px] font-medium text-zinc-300 border border-zinc-700/50"
                      >
                        {name}
                      </span>
                    ))}
                  </div>
                )}

                {/* Progress Bar */}
                {v.clip_count > 0 && (
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-xs text-text-muted mb-1">
                      <span>{v.done_count} of {v.clip_count} clips ready</span>
                      <span className="font-mono">{progressPerc}%</span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
                      <div
                        className={`h-full transition-all duration-300 ${isComplete ? "bg-emerald-500" : "bg-accent"}`}
                        style={{ width: `${progressPerc}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* Card Footer: Date + Delete Action */}
                <div className="mt-4 flex items-center justify-between border-t border-border/50 pt-3 text-xs text-text-muted">
                  <span>
                    {v.created_at
                      ? new Date(v.created_at * 1000).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "Recently created"}
                  </span>
                  <button
                    type="button"
                    title="Delete project"
                    className="border-0 bg-transparent p-1 text-text-muted hover:text-danger"
                    onClick={(e) => removeVideo(v.id, e)}
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                    </svg>
                  </button>
                </div>
              </div>
            </Link>
          );
        })}

        {sortedVideos.length === 0 && (
          <div className="col-span-full py-16 text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-zinc-800 text-zinc-500">
              <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
              </svg>
            </div>
            <p className="text-base font-medium text-text-h">No matching projects found</p>
            <p className="mt-1 text-sm text-text-muted">Try clearing your search or filter criteria.</p>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={!!pendingDeleteId}
        onOpenChange={(open) => !open && setPendingDeleteId(null)}
        title="Delete this video project?"
        description="All its clips, characters, and settings will be permanently removed. Generated video files will remain on disk."
        onConfirm={() => pendingDeleteId && deleteVideo.mutate(pendingDeleteId)}
      />
    </div>
  );
}
