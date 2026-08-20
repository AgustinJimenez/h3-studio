import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { LexicalComposer } from "@lexical/react/LexicalComposer";
import { PlainTextPlugin } from "@lexical/react/LexicalPlainTextPlugin";
import { ContentEditable } from "@lexical/react/LexicalContentEditable";
import { HistoryPlugin } from "@lexical/react/LexicalHistoryPlugin";
import { OnChangePlugin } from "@lexical/react/LexicalOnChangePlugin";
import { LexicalErrorBoundary } from "@lexical/react/LexicalErrorBoundary";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { LexicalTypeaheadMenuPlugin, MenuOption, type MenuTextMatch } from "@lexical/react/LexicalTypeaheadMenuPlugin";
import {
  $getRoot,
  $createParagraphNode,
  $createTextNode,
  $insertNodes,
  BLUR_COMMAND,
  COMMAND_PRIORITY_LOW,
} from "lexical";
import { ChevronDown } from "lucide-react";
import { usePromptTags } from "../lib/queries";
import { $createPromptTagNode, PromptTagNode, splitPlainTextWithTags, structureTagHint } from "../lib/promptTagNode";
import type { ModelTag, PromptTag } from "../schemas";

// A tag-aware replacement for a plain <textarea> — see promptTagNode.tsx for
// how [[key]] (custom) and <Subject N>-style (model) tokens round-trip
// through $getRoot().getTextContent() unchanged while rendering as colored
// pills in the editor. Uncontrolled after mount (Lexical owns its own
// EditorState); the initial value is parsed into nodes once, and every edit
// is reported via onChange as a plain tag-containing string, same shape as
// the old plain textarea's value — callers don't need to know this isn't a
// <textarea> underneath.

class PromptTagOption extends MenuOption {
  tagKey: string;
  label: string;
  body: string;
  constructor(tagKey: string, label: string, body: string) {
    super(tagKey);
    this.tagKey = tagKey;
    this.label = label;
    this.body = body;
  }
}

function tagTriggerMatch(text: string): MenuTextMatch | null {
  const match = /\[\[([a-zA-Z0-9_-]{0,40})$/.exec(text);
  if (!match) return null;
  return { leadOffset: match.index ?? 0, matchingString: match[1], replaceableString: match[0] };
}

// The "available tags" reference panel — every model tag (<Subject N> etc.,
// computed server-side from this video's actual character roster, since
// the numbering is global across characters and not something a human
// should be expected to recompute by hand) plus every custom [[key]] tag.
// Clicking one always appends it at the very end of the prompt, regardless
// of where the cursor currently is — the user repositions it manually from
// there (unlike the [[ typeahead below, which inserts at the cursor as you
// type, this is a browse-and-grab reference, not an in-place edit).
function AvailableTagsButton({ modelTags, customTags }: { modelTags: ModelTag[]; customTags: PromptTag[] }) {
  const [editor] = useLexicalComposerContext();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  function insertAtEnd(kind: "model" | "custom", tagKey: string, label: string, body: string) {
    editor.update(() => {
      const node = $createPromptTagNode(kind, tagKey, label, body);
      $getRoot().selectEnd().insertNodes([node]);
    });
    setOpen(false);
  }

  return (
    <div ref={containerRef} className="relative inline-block">
      <button type="button" className="inline-flex items-center gap-1 text-sm" onClick={() => setOpen(!open)}>
        Available tags <ChevronDown size={14} />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 max-h-80 w-72 overflow-auto rounded border border-border bg-bg-alt p-1 shadow-lg">
          <details open>
            <summary className="cursor-pointer px-2 py-1 text-xs font-semibold uppercase opacity-60">MiniMax H3 tags (this video)</summary>
            {modelTags.map((t) => (
              <button
                key={t.tag}
                type="button"
                className="block w-full border-0 bg-transparent px-2 py-1.5 text-left"
                onClick={() => insertAtEnd("model", t.tag, t.tag, t.description)}
                title={t.description}
              >
                <span className="font-mono font-semibold text-text-h">{t.tag}</span>
                <div className="text-xs opacity-60">{t.description}</div>
              </button>
            ))}
            {modelTags.length === 0 && <div className="px-2 py-1.5 text-sm opacity-60">No characters/references yet</div>}
          </details>
          <details open className="mt-1 border-t border-dashed border-border pt-1">
            <summary className="cursor-pointer px-2 py-1 text-xs font-semibold uppercase opacity-60">Custom tags</summary>
            {customTags.map((tag) => (
              <button
                key={tag.id}
                type="button"
                className="block w-full border-0 bg-transparent px-2 py-1.5 text-left"
                onClick={() => insertAtEnd("custom", tag.key, tag.name, tag.body)}
                title={tag.body}
              >
                <span className="font-semibold text-text-h">{tag.name}</span>{" "}
                <span className="font-mono text-xs opacity-60">[[{tag.key}]]</span>
                <div className="truncate text-xs opacity-60">{tag.body}</div>
              </button>
            ))}
            {customTags.length === 0 && <div className="px-2 py-1.5 text-sm opacity-60">No prompt tags yet</div>}
          </details>
        </div>
      )}
    </div>
  );
}

function TagTypeaheadPlugin({ tags }: { tags: PromptTag[] }) {
  const [editor] = useLexicalComposerContext();
  const [queryString, setQueryString] = useState<string | null>(null);

  const options = useMemo(() => {
    const q = (queryString ?? "").toLowerCase();
    return tags
      .filter((t) => !q || t.key.toLowerCase().includes(q) || t.name.toLowerCase().includes(q))
      .slice(0, 10)
      .map((t) => new PromptTagOption(t.key, t.name, t.body));
  }, [tags, queryString]);

  return (
    <LexicalTypeaheadMenuPlugin<PromptTagOption>
      onQueryChange={setQueryString}
      onSelectOption={(option, textNodeContainingQuery, closeMenu) => {
        editor.update(() => {
          const node = $createPromptTagNode("custom", option.tagKey, option.label, option.body);
          if (textNodeContainingQuery) {
            textNodeContainingQuery.replace(node);
          } else {
            $insertNodes([node]);
          }
        });
        closeMenu();
      }}
      triggerFn={tagTriggerMatch}
      options={options}
      menuRenderFn={(anchorElementRef, { selectedIndex, selectOptionAndCleanUp, setHighlightedIndex }) =>
        anchorElementRef.current && options.length > 0
          ? createPortal(
              <div className="z-30 max-h-60 w-64 overflow-auto rounded border border-border bg-bg-alt p-1 shadow-lg">
                {options.map((option, i) => (
                  <div
                    key={option.key}
                    className={`cursor-pointer rounded px-2 py-1.5 text-sm ${i === selectedIndex ? "bg-accent text-accent-text" : ""}`}
                    title={option.body}
                    onMouseEnter={() => setHighlightedIndex(i)}
                    onClick={() => selectOptionAndCleanUp(option)}
                  >
                    <span className="font-semibold">{option.label}</span>{" "}
                    <span className="font-mono text-xs opacity-60">[[{option.tagKey}]]</span>
                  </div>
                ))}
              </div>,
              anchorElementRef.current,
            )
          : null
      }
    />
  );
}

function InitialContentPlugin({
  initialValue,
  customByKey,
  modelByTag,
}: {
  initialValue: string;
  customByKey: Map<string, PromptTag>;
  modelByTag: Map<string, string>;
}) {
  const [editor] = useLexicalComposerContext();
  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current) return;
    seeded.current = true;
    editor.update(() => {
      const root = $getRoot();
      const paragraph = $createParagraphNode();
      for (const part of splitPlainTextWithTags(initialValue)) {
        if (typeof part === "string") {
          if (part) paragraph.append($createTextNode(part));
        } else if (part.kind === "custom") {
          const tag = customByKey.get(part.tagKey);
          paragraph.append($createPromptTagNode("custom", part.tagKey, tag?.name ?? part.tagKey, tag?.body ?? "(this prompt tag no longer exists)"));
        } else if (part.kind === "model") {
          const description = modelByTag.get(part.tagKey);
          paragraph.append($createPromptTagNode("model", part.tagKey, part.tagKey, description ?? "(this reference no longer exists)"));
        } else {
          paragraph.append($createPromptTagNode("structure", part.tagKey, part.tagKey, structureTagHint(part.tagKey)));
        }
      }
      root.clear();
      root.append(paragraph);
    });
    // Intentionally only ever seeded once per mount — see the module docstring.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editor]);
  return null;
}

function BlurPlugin({ onBlur }: { onBlur?: () => void }) {
  const [editor] = useLexicalComposerContext();
  useEffect(() => {
    if (!onBlur) return;
    return editor.registerCommand(
      BLUR_COMMAND,
      () => {
        onBlur();
        return false;
      },
      COMMAND_PRIORITY_LOW,
    );
  }, [editor, onBlur]);
  return null;
}

export default function PromptTagEditor({
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
  const { data: tags } = usePromptTags();

  if (!tags) {
    return <textarea rows={12} defaultValue={initialValue} disabled placeholder="Loading..." />;
  }

  const customByKey = new Map(tags.map((t) => [t.key, t]));
  const modelByTag = new Map(modelTags.map((t) => [t.tag, t.description]));
  const initialConfig = {
    namespace: "prompt-editor",
    nodes: [PromptTagNode],
    onError: (error: Error) => console.error(error),
    theme: {},
  };

  return (
    <LexicalComposer initialConfig={initialConfig}>
      <div className="relative">
        <PlainTextPlugin
          contentEditable={
            <ContentEditable className="min-h-[240px] w-full whitespace-pre-wrap rounded-md border border-border bg-bg px-2 py-1.5 text-text-h outline-none focus:border-accent" />
          }
          placeholder={null}
          ErrorBoundary={LexicalErrorBoundary}
        />
        <HistoryPlugin />
        <InitialContentPlugin initialValue={initialValue} customByKey={customByKey} modelByTag={modelByTag} />
        <BlurPlugin onBlur={onBlur} />
        <TagTypeaheadPlugin tags={tags} />
        <OnChangePlugin onChange={(editorState) => editorState.read(() => onChange($getRoot().getTextContent()))} />
      </div>
      <div className="mt-1">
        <AvailableTagsButton modelTags={modelTags} customTags={tags} />
      </div>
    </LexicalComposer>
  );
}
