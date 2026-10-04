import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, mediaUrl } from "../lib/api";
import VideoPlayer from "./VideoPlayer";
import type { Clip } from "../schemas";

// Every finished generation of the clip, newest first, so an earlier take can be watched and brought back.
export default function ClipHistory({ clip }: { clip: Clip }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState("");
  const takes = [...clip.history].reverse();
  if (takes.length === 0) return null;

  async function use(id: string) {
    setBusy(id);
    try {
      await api.useClipTake(clip.id, id);
      await qc.invalidateQueries({ queryKey: ["video"] });
      toast.success("That take is the clip's output again");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  return (
    <details className="rounded-lg border border-border">
      <summary className="cursor-pointer select-none px-3 py-2 text-sm">
        <span className="font-medium text-text-h">History</span>
        <span className="ml-2 text-xs text-text-muted">
          {takes.length} take{takes.length === 1 ? "" : "s"}
        </span>
      </summary>
      <div className="flex flex-wrap gap-3 border-t border-border p-3">
        {takes.map((t, i) => (
          <div key={t.id} className="flex w-44 flex-col gap-1 text-xs">
            <VideoPlayer
              src={mediaUrl(t.output_url) ?? ""}
              className="w-full rounded border border-border"
              loop
              muted
            />
            <div>
              <span className="font-medium text-text-h">
                {t.label || `Take ${takes.length - i}`}
              </span>
              {t.current && <span className="ml-1 text-accent">· current</span>}
            </div>
            <div className="opacity-70">
              {[
                t.resolution,
                t.steps ? `${t.steps} steps` : null,
                t.seed != null ? `seed ${t.seed}` : null,
                t.seconds ? `${Math.round(t.seconds / 60)} min` : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </div>
            <div className="opacity-50">
              {new Date(t.finished_at * 1000).toLocaleString()}
            </div>
            {!t.current && (
              <button
                type="button"
                className="py-0.5 text-xs"
                disabled={busy !== ""}
                onClick={() => void use(t.id)}
              >
                {busy === t.id ? "Working…" : "Use this take"}
              </button>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}
