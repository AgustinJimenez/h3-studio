import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, mediaUrl } from "../lib/api";
import { useSwaps } from "../lib/swapQueries";
import VideoPlayer from "./VideoPlayer";
import type { Clip } from "../schemas";

// Per-clip depth control video (H3 "Transfer Depth Map From Control Video"): the clip's camera movement and the placement and
// motion of its people follow this video; the look still comes from the prompt and the references. It does not set the
// output size (that is the clip's Size, or the template's).
// It can be a path, an uploaded file, or consecutive scenes of a swap project's source video.
export default function ControlVideoField({
  clip,
  onChange,
  onEnabledChange,
}: {
  clip: Clip;
  onChange: (path: string) => void;
  onEnabledChange?: (enabled: boolean) => void;
}) {
  const enabled = clip.control_video_enabled !== false;
  const [draft, setDraft] = useState(clip.control_video_path ?? "");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [swapId, setSwapId] = useState("");
  const [first, setFirst] = useState("1");
  const [last, setLast] = useState("1");
  const [size, setSize] = useState("320");
  const [length, setLength] = useState(""); // "" = keep the scenes' own length (at least 124)
  const fileInput = useRef<HTMLInputElement>(null);
  const { data: swaps } = useSwaps();
  useEffect(
    () => setDraft(clip.control_video_path ?? ""),
    [clip.control_video_path],
  );

  const swap = swaps?.find((s) => s.id === swapId);
  const info = clip.control_video_info;
  const url = mediaUrl(clip.control_video_url);

  async function run(work: () => Promise<{ path: string }>) {
    setBusy(true);
    try {
      const r = await work();
      onChange(r.path);
      setOpen(false);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div>
        Control video (depth guide)
        <span className="ml-2 text-xs opacity-70">
          Sets this shot's camera movement and where its people are and how they
          move; the look comes from the prompt and references. The output size
          is the clip's Size above, not this video's.
        </span>
      </div>
      {clip.control_video_path && onEnabledChange && (
        <label
          className="flex items-center gap-2"
          title="Off: the clip keeps this control video attached but is generated without it"
        >
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => onEnabledChange(e.target.checked)}
          />
          Use it for this clip
          {!enabled && (
            <span className="text-xs text-amber-400">
              off: generated without it, so the camera and layout come from the
              prompt and the output size from the template resolution
            </span>
          )}
        </label>
      )}
      {url ? (
        <div
          className={`flex flex-wrap items-start gap-3 ${enabled ? "" : "opacity-50"}`}
        >
          <div className="w-44 shrink-0">
            <VideoPlayer
              src={url}
              className="w-full rounded border border-border"
              loop
              muted
            />
          </div>
          <div className="text-xs opacity-80">
            {info ? (
              <>
                {info.width}×{info.height} · {info.frames} frames ·{" "}
                {(info.frames / (info.fps || 24)).toFixed(1)} s
              </>
            ) : (
              "video not found on disk"
            )}
            <div className="mt-1 break-all font-mono opacity-70">
              {clip.control_video_path}
            </div>
          </div>
        </div>
      ) : (
        <div className="text-xs opacity-70">
          No control video: the camera and the layout come from the prompt
          alone.
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="py-0.5 text-xs"
          disabled={busy}
          onClick={() => fileInput.current?.click()}
        >
          Upload a video…
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="video/*"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) void run(() => api.uploadControlVideo(clip.id, file));
          }}
        />
        <button
          type="button"
          className="py-0.5 text-xs"
          disabled={busy}
          onClick={() => setOpen((o) => !o)}
        >
          From scenes of a swap project…
        </button>
        {clip.control_video_path && (
          <button
            type="button"
            className="border-0 bg-transparent p-0 text-xs text-danger"
            onClick={() => onChange("")}
          >
            Clear
          </button>
        )}
        {busy && <span className="text-xs opacity-70">Working…</span>}
      </div>
      {open && (
        <div className="flex flex-wrap items-center gap-2 rounded border border-border p-2 text-xs">
          <select
            value={swapId}
            onChange={(e) => {
              setSwapId(e.target.value);
              setFirst("1");
              setLast("1");
            }}
          >
            <option value="">Swap project…</option>
            {(swaps ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
          {swap && (
            <>
              <label>
                from scene{" "}
                <select
                  value={first}
                  onChange={(e) => setFirst(e.target.value)}
                >
                  {swap.scenes.map((s) => (
                    <option key={s.index} value={s.index + 1}>
                      {s.index + 1} · frames {s.start_frame_src}–
                      {s.end_frame_src}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                to scene{" "}
                <select value={last} onChange={(e) => setLast(e.target.value)}>
                  {swap.scenes.map((s) => (
                    <option key={s.index} value={s.index + 1}>
                      {s.index + 1} · frames {s.start_frame_src}–
                      {s.end_frame_src}
                    </option>
                  ))}
                </select>
              </label>
              <select
                value={size}
                onChange={(e) => setSize(e.target.value)}
                title="Shorter side of the control video; match it to the clip's Size"
              >
                <option value="320">320p (fast test)</option>
                <option value="480">480p</option>
                <option value="640">640p</option>
                <option value="1088">1080p (1088 short side)</option>
              </select>
              <select
                value={length}
                onChange={(e) => setLength(e.target.value)}
                title="Fit the control video to exactly this many frames (H3 lengths are 17k+5); a clip of another length is slowed down or sped up"
              >
                <option value="">Length: as the scenes, min 124</option>
                {[124, 141, 158, 175, 192, 243, 294, 345].map((n) => (
                  <option key={n} value={n}>
                    Fit to {n} frames ({(n / 24).toFixed(1)} s)
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="py-0.5"
                disabled={busy || Number(last) < Number(first)}
                onClick={() =>
                  void run(() =>
                    api.controlVideoFromSwap(clip.id, {
                      swap_id: swapId,
                      first_scene: Number(first),
                      last_scene: Number(last),
                      size: Number(size),
                      frames: length ? Number(length) : undefined,
                    }),
                  )
                }
              >
                Create control video
              </button>
              <span className="opacity-70">
                A shorter stretch is slowed down to the 124-frame minimum.
              </span>
            </>
          )}
        </div>
      )}
      <label className="flex flex-col gap-1 text-xs opacity-80">
        Path
        <input
          className="font-mono text-xs"
          placeholder="E:\\repo\\previs\\...\\07_remote_640.mp4"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() =>
            draft !== (clip.control_video_path ?? "") && onChange(draft.trim())
          }
        />
      </label>
    </div>
  );
}
