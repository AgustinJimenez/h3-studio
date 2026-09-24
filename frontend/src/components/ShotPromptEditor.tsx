import { useState } from "react";
import PromptTagEditor from "./PromptTagEditor";
import StructuredShotEditor from "./StructuredShotEditor";
import { parseShotPrompt } from "../lib/shotPromptStructure";
import { usePromptTags } from "../lib/queries";
import type { ModelTag } from "../schemas";

// Tab container in front of PromptTagEditor (Simple — the existing rich
// text editor) and StructuredShotEditor (Structured — a form built from
// [Shot N]/dialogue-line blocks). Same external prop contract as
// PromptTagEditor itself, so callers (ClipRow) don't need to change
// anything except which component they render.
//
// Both tabs are plain conditional renders at the same JSX slot, not both
// mounted at once — switching tabs naturally unmounts the inactive one and
// mounts the other fresh, which is exactly the "reseed with the latest
// text, but only once per switch" behavior both tabs need (Lexical's own
// InitialContentPlugin already only seeds once per mount; StructuredShotEditor
// mirrors that by copying its initialShots prop into local state once).
//
// onBlur is attached to the wrapping div, not threaded into each tab
// individually — React's onBlur bubbles (unlike native DOM blur), so this
// fires once when focus leaves the whole editor regardless of which tab is
// active or how many individual fields Structured mode has, without
// double-firing a save on every inter-field tab within Structured mode.
export default function ShotPromptEditor({
  initialValue,
  modelTags,
  onChange,
  onBlur,
}: {
  initialValue: string;
  modelTags: ModelTag[];
  onChange: (next: string) => void;
  onBlur?: () => void;
}) {
  const { data: promptTags } = usePromptTags();
  const [tab, setTab] = useState<"simple" | "structured">("structured");
  const [text, setText] = useState(initialValue);

  function handleChange(next: string) {
    setText(next);
    onChange(next);
  }

  const tabButtonClass = (active: boolean) =>
    `rounded-t border-0 border-b-2 bg-transparent px-2 py-1 text-sm ${
      active ? "border-accent font-semibold text-text-h" : "border-transparent opacity-60"
    }`;

  return (
    <div onBlur={onBlur}>
      <div className="mb-1 flex gap-1">
        <button type="button" className={tabButtonClass(tab === "simple")} onClick={() => setTab("simple")}>
          Simple
        </button>
        <button type="button" className={tabButtonClass(tab === "structured")} onClick={() => setTab("structured")}>
          Structured
        </button>
      </div>
      {tab === "simple" ? (
        <PromptTagEditor initialValue={text} modelTags={modelTags} onChange={handleChange} />
      ) : (
        <StructuredShotEditor
          initialShots={parseShotPrompt(text)}
          modelTags={modelTags}
          promptTags={promptTags ?? []}
          onChange={handleChange}
        />
      )}
    </div>
  );
}
