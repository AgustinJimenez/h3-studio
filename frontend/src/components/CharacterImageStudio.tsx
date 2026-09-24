import { useEffect, useState } from "react";
import { mediaUrl, referencePreviewUrl } from "../lib/api";
import {
  useCharacterImageProviders,
  useUpdateCharacter,
  useGenerateCharacterImages,
  useDeleteCharacterImage,
  useCharacterImageAsReference,
} from "../lib/queries";
import StatusBadge from "./StatusBadge";
import { jobTargetDomId } from "../lib/jobFocus";
import type { Character, CharacterImageGen } from "../schemas";

// Must match backend prompt.CHARACTER_IMAGE_ASPECTS.
const ASPECTS = [
  { value: "square", label: "Square (1024x1024)" },
  { value: "portrait", label: "Portrait (896x1152)" },
  { value: "landscape", label: "Landscape (1152x896)" },
];
const ACTIVE_STATUSES = new Set(["queued", "running"]);
// Reference note for outfit-only use -- prompt.compose_subject_definitions turns
// it into "...whose wardrobe and outfit comes from <Picture N>", keeping the
// generated face out of the identity clause.
const OUTFIT_NOTE = "wardrobe and outfit";

type Mode = "text" | "edit";

function fileName(path: string) {
  return path.split(/[\\/]/).pop() || path;
}

export default function CharacterImageStudio({ videoId, character }: { videoId: string; character: Character }) {
  const { data: providers = [] } = useCharacterImageProviders();
  const updateCharacter = useUpdateCharacter(videoId, character.id);
  const generate = useGenerateCharacterImages(videoId, character.id);
  const deleteImage = useDeleteCharacterImage(videoId, character.id);
  const promoteToReference = useCharacterImageAsReference(videoId, character.id);

  const [gen, setGen] = useState<CharacterImageGen>(character.image_gen);
  useEffect(() => setGen(character.image_gen), [character.image_gen]);

  const [mode, setMode] = useState<Mode>("text");
  const [promptText, setPromptText] = useState("");
  const [sources, setSources] = useState<string[]>([]);
  const [seed, setSeed] = useState(-1);
  const [count, setCount] = useState(2);
  const [aspect, setAspect] = useState("square");

  function saveGen(next: CharacterImageGen) {
    setGen(next);
    updateCharacter.mutate({ image_gen: next });
  }

  // Candidate edit sources: the character's image references plus every finished generated image.
  const referencePaths = new Set(character.references.map((r) => r.path));
  const referenceNoteByPath = new Map(character.references.map((r) => [r.path, r.note ?? ""]));
  const sourceCandidates = [
    ...character.references.filter((r) => r.type === "image").map((r) => ({ path: r.path, label: `ref: ${fileName(r.path)}` })),
    ...character.generated_images
      .filter((i) => i.status === "done" && i.output_path && !referencePaths.has(i.output_path))
      .map((i) => ({ path: i.output_path as string, label: `generated: seed ${i.seed}` })),
  ];

  function toggleSource(path: string) {
    setSources((prev) => (prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path].slice(0, 10)));
  }

  function editFrom(path: string) {
    setMode("edit");
    setSources([path]);
  }

  function submit() {
    generate.mutate({
      prompt: promptText,
      source_paths: mode === "edit" ? sources : [],
      seed: Number(seed),
      count: Number(count),
      aspect,
    });
  }

  const canSubmit = promptText.trim().length > 0 && (mode === "text" || sources.length > 0) && !generate.isPending;
  const provider = providers.find((p) => p.id === gen.provider);
  const loras = provider?.loras ?? [];
  const loraMissing = !!gen.lora && providers.length > 0 && !loras.includes(gen.lora);

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Provider
          <select value={gen.provider} onChange={(e) => saveGen({ ...gen, provider: e.target.value as CharacterImageGen["provider"] })}>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>{p.name}{p.available ? "" : " (offline)"}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Character LoRA (Qwen-Image 2.1)
          <select value={gen.lora} onChange={(e) => saveGen({ ...gen, lora: e.target.value })}>
            <option value="">None</option>
            {loras.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          LoRA strength
          <input
            type="number"
            step={0.1}
            min={0}
            max={2}
            value={gen.lora_multiplier}
            onChange={(e) => setGen({ ...gen, lora_multiplier: Number(e.target.value) })}
            onBlur={() => saveGen(gen)}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Trigger word (prepended to every prompt)
          <input
            placeholder="e.g. maria_silvero"
            value={gen.trigger}
            onChange={(e) => setGen({ ...gen, trigger: e.target.value })}
            onBlur={() => saveGen(gen)}
          />
        </label>
      </div>

      {provider && (provider.note || !provider.available || loraMissing) && (
        <div className={`text-xs ${provider.available && !loraMissing ? "opacity-75" : "text-danger"}`}>
          {!provider.available && `${provider.name} is offline. `}
          {loraMissing && `LoRA "${gen.lora}" isn't in this provider's LoRA folder. `}
          {provider.note}
        </div>
      )}

      <div className="rounded-lg border border-dashed border-border p-3.5">
        <div className="mb-2 flex gap-4 text-sm">
          <label className="flex items-center gap-1.5">
            <input type="radio" className="w-auto" checked={mode === "text"} onChange={() => setMode("text")} /> From text
          </label>
          <label className="flex items-center gap-1.5">
            <input type="radio" className="w-auto" checked={mode === "edit"} onChange={() => setMode("edit")} /> Edit existing image(s)
          </label>
        </div>

        {mode === "edit" && (
          <div className="mb-2">
            <div className="mb-1 text-sm opacity-75">
              Source images, in order (refer to them as &lt;image1&gt;, &lt;image2&gt;… in the prompt). The output keeps the first image's
              size, so Aspect only applies to text mode. Upload new photos in References above.
            </div>
            {sourceCandidates.length === 0 && <div className="text-sm text-danger">No image references or generated images yet.</div>}
            <div className="flex flex-wrap gap-2">
              {sourceCandidates.map((c) => {
                const idx = sources.indexOf(c.path);
                return (
                  <button
                    key={c.path}
                    type="button"
                    title={c.path}
                    onClick={() => toggleSource(c.path)}
                    className={`relative flex flex-col items-center gap-1 rounded border p-1 text-xs ${idx >= 0 ? "border-accent" : "border-border opacity-70"}`}
                  >
                    <img src={referencePreviewUrl(c.path) ?? undefined} alt="" className="h-20 w-20 rounded object-cover" />
                    <span className="max-w-[88px] truncate">{c.label}</span>
                    {idx >= 0 && <span className="absolute left-1 top-1 rounded bg-accent px-1 text-white">{idx + 1}</span>}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <label className="flex flex-col gap-1 text-sm">
          Prompt{gen.trigger ? ` (will start with "${gen.trigger}, ")` : ""}
          <textarea
            rows={3}
            placeholder={
              mode === "text"
                ? "full body, a stocky heavyset man with a round full face, brown skin, a goatee and black-framed glasses, wearing a black leather trench coat, plain grey studio background, soft light, photorealistic"
                : "Same man from <image1>, now wearing a white suit and red tie. Keep his face, glasses and build unchanged."
            }
            value={promptText}
            onChange={(e) => setPromptText(e.target.value)}
          />
        </label>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Aspect
            <select value={aspect} onChange={(e) => setAspect(e.target.value)}>
              {ASPECTS.map((a) => (
                <option key={a.value} value={a.value}>{a.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Images
            <select value={count} onChange={(e) => setCount(Number(e.target.value))}>
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Seed (-1 = random)
            <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
          </label>
          <button disabled={!canSubmit} onClick={submit}>Generate</button>
        </div>
      </div>

      {character.generated_images.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
          {[...character.generated_images].reverse().map((img) => {
            const isRef = !!img.output_path && referencePaths.has(img.output_path);
            const role = isRef ? ((referenceNoteByPath.get(img.output_path as string) ?? "") ? "outfit" : "identity") : null;
            return (
              <div key={img.id} id={jobTargetDomId(img.id)} className="flex flex-col gap-2 rounded-lg border border-border bg-bg-alt p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <StatusBadge status={img.status === "none" ? "draft" : img.status} label={img.status} />
                  <span className="text-xs opacity-75">seed {img.seed}{img.source_paths.length ? " · edit" : ""}</span>
                </div>
                {img.output_url ? (
                  <a href={mediaUrl(img.output_url) ?? undefined} target="_blank" rel="noreferrer">
                    <img src={mediaUrl(img.output_url) ?? undefined} alt="" className="w-full rounded" />
                  </a>
                ) : (
                  <div className="flex aspect-square w-full items-center justify-center rounded bg-bg text-xs opacity-60">
                    {ACTIVE_STATUSES.has(img.status) ? "generating…" : "no image"}
                  </div>
                )}
                <div className="line-clamp-2 text-xs opacity-85" title={img.prompt}>{img.prompt}</div>
                {img.error && <div className="whitespace-pre-wrap rounded border border-danger bg-red-950/30 px-2 py-1 text-xs text-danger">{img.error}</div>}
                <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
                  {img.status === "done" && (
                    <>
                      <button
                        disabled={role === "outfit"}
                        title="Adds it as an outfit/wardrobe reference: H3 takes the clothes from it but not the face."
                        onClick={() => promoteToReference.mutate({ imageId: img.id, note: OUTFIT_NOTE })}
                      >
                        {role === "outfit" ? "Outfit reference ✓" : "Use as outfit ref"}
                      </button>
                      <button
                        disabled={role === "identity"}
                        title="Adds it as an identity reference: H3 will also take the FACE from it. A generated face can pull the likeness away from real photos -- prefer real photos for identity."
                        onClick={() => promoteToReference.mutate({ imageId: img.id, note: "" })}
                      >
                        {role === "identity" ? "Identity reference ✓" : "Use as identity ref"}
                      </button>
                      <button onClick={() => img.output_path && editFrom(img.output_path)}>Edit from this</button>
                    </>
                  )}
                  <button className="border-0 bg-transparent p-0 text-danger" disabled={ACTIVE_STATUSES.has(img.status)} onClick={() => deleteImage.mutate(img.id)}>
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
