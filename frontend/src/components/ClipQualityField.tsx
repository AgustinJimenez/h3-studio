import type { Clip } from "../schemas";

const RESOLUTIONS = ["", "320x576", "576x1024", "720x1280", "832x1472", "1088x1920"];

// Size and model for this clip only; empty / "template" keeps what the video's template says.
export default function ClipQualityField({
  clip,
  onChange,
}: {
  clip: Clip;
  onChange: (body: Partial<Clip>) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <label className="flex items-center gap-2">
        Size
        <select
          value={clip.resolution_override ?? ""}
          onChange={(e) => onChange({ resolution_override: e.target.value })}
        >
          {RESOLUTIONS.map((r) => (
            <option key={r} value={r}>
              {r || "Template size"}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-2">
        Model
        <select
          value={clip.model_preset ?? ""}
          onChange={(e) => onChange({ model_preset: e.target.value })}
        >
          <option value="">Template model</option>
          <option value="pdd8">PDD 8-step (fast)</option>
        </select>
      </label>
      <label
        className="flex items-center gap-2"
        title="H3's latent upscaler: a draft at half the Size, its latent upscaled 2x, then refined at the full Size. Not available with the PDD model."
      >
        <input
          type="checkbox"
          checked={!!clip.two_phase && !clip.model_preset}
          disabled={!!clip.model_preset}
          onChange={(e) => onChange({ two_phase: e.target.checked })}
        />
        Two-phase (latent upscale)
      </label>
      <label
        className="flex items-center gap-2"
        title="Off: this clip is generated without the characters' video references (for example a dance movement reference), keeping their pictures."
      >
        <input
          type="checkbox"
          checked={clip.video_references_enabled !== false}
          onChange={(e) => onChange({ video_references_enabled: e.target.checked })}
        />
        Use video references
      </label>
      <label
        className="flex items-center gap-2"
        title="Cuts this many frames off the start of the clip when the video is joined and in its own preview; the generated file is kept whole. 24 frames = 1 s."
      >
        Trim start
        <input
          type="number"
          min={0}
          className="w-20"
          defaultValue={clip.trim_start_frames ?? 0}
          key={clip.trim_start_frames ?? 0}
          onBlur={(e) => {
            const n = Math.max(0, Math.round(Number(e.target.value) || 0));
            if (n !== (clip.trim_start_frames ?? 0)) onChange({ trim_start_frames: n });
          }}
        />
        frames
      </label>
      <span className="text-xs opacity-70">
        For this clip only. The control video's size does not set the output size.
      </span>
    </div>
  );
}
