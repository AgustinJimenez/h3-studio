import { referencePreviewUrl } from "../lib/api";
import type { Character, Clip } from "../schemas";

// Storyboard first frame for a clip (H3 image_start): pick one of the video's
// finished generated images -- typically a Qwen edit of the environment/set
// image, so every cut opens in the exact same room.
export default function StartFramePicker({
  clip,
  characters,
  onChange,
}: {
  clip: Clip;
  characters: Character[];
  onChange: (path: string) => void;
}) {
  const candidates = characters.flatMap((c) =>
    c.generated_images
      .filter((i) => i.status === "done" && i.output_path)
      .map((i) => ({ path: i.output_path as string, label: `${c.name || "?"} · seed ${i.seed}`, prompt: i.prompt }))
  );
  const selected = clip.start_frame_path ?? "";
  if (candidates.length === 0 && !selected) return null;

  return (
    <details className="text-sm" open={!!selected}>
      <summary className="cursor-pointer">
        First frame (storyboard){selected ? `: ${selected.split(/[\\/]/).pop()}` : " — none"}
      </summary>
      <p className="my-1 text-xs opacity-75">
        The clip opens exactly on this image (H3 start image). Make storyboard frames in a character's or the set's
        "Character images" section, as edits of the same set image, so every cut starts in the same room.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onChange("")}
          className={`flex h-[74px] w-[110px] items-center justify-center rounded border text-xs ${selected ? "border-border opacity-70" : "border-accent"}`}
        >
          None
        </button>
        {candidates.map((c) => (
          <button
            key={c.path}
            type="button"
            title={`${c.label}\n${c.prompt}`}
            onClick={() => onChange(c.path)}
            className={`flex flex-col items-center gap-0.5 rounded border p-0.5 text-[10px] ${selected === c.path ? "border-accent ring-2 ring-accent" : "border-border opacity-70"}`}
          >
            <img src={referencePreviewUrl(c.path) ?? undefined} alt="" className="h-[58px] w-[104px] rounded object-cover" />
            <span className="max-w-[104px] truncate">{c.label}</span>
          </button>
        ))}
      </div>
    </details>
  );
}
