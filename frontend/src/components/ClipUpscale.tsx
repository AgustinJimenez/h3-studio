import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, mediaUrl } from "../lib/api";
import VideoPlayer from "./VideoPlayer";
import type { Clip } from "../schemas";

// FlashVSR spatial upscale of the clip's finished output (a separate file; the raw output is never replaced).
export default function ClipUpscale({ clip }: { clip: Clip }) {
  const qc = useQueryClient();
  const [scale, setScale] = useState("1.5");
  const [busy, setBusy] = useState(false);
  if (clip.status !== "done" || !clip.output_url) return null;
  const up = clip.upscale;
  const active = up?.status === "queued" || up?.status === "running";

  async function start() {
    setBusy(true);
    try {
      await api.upscaleClip(clip.id, Number(scale));
      await qc.invalidateQueries({ queryKey: ["video"] });
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="rounded-lg border border-border" open={active || up?.status === "done"}>
      <summary className="cursor-pointer select-none px-3 py-2 text-sm">
        <span className="font-medium text-text-h">Upscale (FlashVSR)</span>
        <span className="ml-2 text-xs text-text-muted">
          {active ? up?.status : up?.status === "done" ? "ready" : ""}
        </span>
      </summary>
      <div className="flex flex-col gap-3 border-t border-border p-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <select value={scale} onChange={(e) => setScale(e.target.value)}>
            <option value="1.5">x1.5</option>
            <option value="2">x2</option>
          </select>
          <button type="button" className="py-0.5 text-xs" disabled={busy || active} onClick={() => void start()}>
            {active ? "Upscaling..." : up?.status === "done" ? "Upscale again" : "Upscale this clip"}
          </button>
          <span className="text-xs opacity-70">
            Upscales the current output; the latest upscale is kept next to it.
          </span>
        </div>
        {up?.error && <div className="text-xs text-danger">{up.error}</div>}
        {up?.status === "done" && up.output_url && (
          <div className="w-64">
            <VideoPlayer src={mediaUrl(up.output_url) ?? ""} className="w-full rounded border border-border" loop muted />
            <a className="text-xs" href={mediaUrl(up.output_url) ?? undefined} target="_blank" rel="noreferrer">
              open file
            </a>
          </div>
        )}
      </div>
    </details>
  );
}
