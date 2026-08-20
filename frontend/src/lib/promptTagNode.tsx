import { DecoratorNode, type LexicalNode, type NodeKey, type SerializedLexicalNode, type Spread } from "lexical";
import type { JSX } from "react";

// An atomic, non-splittable inline node representing one prompt-tag
// reference, of two kinds:
//   - "custom": a [[key]] reference to this app's own Prompt Tags library —
//     see prompt.py::expand_prompt_tags on the backend, which substitutes
//     the exact same [[key]] syntax into its stored body text right before
//     generation. getTextContent() returns "[[key]]" (not the display
//     label), which is what makes $getRoot().getTextContent() produce the
//     correct plain-text value to persist/send.
//   - "model": a literal H3 model tag like "<Subject 1>" — these are
//     already in their final form (no substitution happens), so
//     getTextContent() returns tagKey verbatim. Exists purely so these are
//     visually distinct + hoverable in the editor, same as custom tags.
//   - "structure": H3's own dialogue/shot markup that a human types by hand
//     (not inserted via a picker, since Shot/Speaker numbers are scene-
//     specific) — <d>/</d> dialogue-line wrappers, [Shot N] shot markers,
//     and the [Speaker SN prefix of a per-line delivery bracket (see
//     prompts_reference/h3_quality_presets.md section 4/5). Same
//     already-final-text treatment as "model": getTextContent() returns
//     tagKey verbatim. Deliberately NOT the whole [Speaker SN, ...] bracket
//     — that bracket's body (voice/accent/mood text, plus nested <Audio N>
//     and [[key]] tags) must stay normal editable text.
export type PromptTagKind = "custom" | "model" | "structure";

export type SerializedPromptTagNode = Spread<
  { kind: PromptTagKind; tagKey: string; label: string; body: string },
  SerializedLexicalNode
>;

export class PromptTagNode extends DecoratorNode<JSX.Element> {
  __kind: PromptTagKind;
  __tagKey: string;
  __label: string;
  __body: string;

  static getType(): string {
    return "prompt-tag";
  }

  static clone(node: PromptTagNode): PromptTagNode {
    return new PromptTagNode(node.__kind, node.__tagKey, node.__label, node.__body, node.__key);
  }

  constructor(kind: PromptTagKind, tagKey: string, label: string, body: string, key?: NodeKey) {
    super(key);
    this.__kind = kind;
    this.__tagKey = tagKey;
    this.__label = label;
    this.__body = body;
  }

  static importJSON(serializedNode: SerializedPromptTagNode): PromptTagNode {
    return $createPromptTagNode(serializedNode.kind, serializedNode.tagKey, serializedNode.label, serializedNode.body);
  }

  exportJSON(): SerializedPromptTagNode {
    return { type: "prompt-tag", version: 1, kind: this.__kind, tagKey: this.__tagKey, label: this.__label, body: this.__body };
  }

  createDOM(): HTMLElement {
    return document.createElement("span");
  }

  updateDOM(): boolean {
    return false;
  }

  isInline(): boolean {
    return true;
  }

  getTextContent(): string {
    return this.__kind === "custom" ? `[[${this.__tagKey}]]` : this.__tagKey;
  }

  decorate(): JSX.Element {
    const modelStyle = "bg-status-draft text-white";
    const customStyle = "bg-accent text-accent-text";
    const structureStyle = "bg-status-running text-white";
    const style = this.__kind === "model" ? modelStyle : this.__kind === "structure" ? structureStyle : customStyle;
    return (
      <span
        className={`mx-0.5 inline-block select-none rounded-full px-2 py-0.5 align-baseline text-xs font-semibold ${style}`}
        title={this.__body}
        contentEditable={false}
      >
        {this.__label}
      </span>
    );
  }
}

export function $createPromptTagNode(kind: PromptTagKind, tagKey: string, label: string, body: string): PromptTagNode {
  return new PromptTagNode(kind, tagKey, label, body);
}

export function $isPromptTagNode(node: LexicalNode | null | undefined): node is PromptTagNode {
  return node instanceof PromptTagNode;
}

const TAG_TOKEN_RE =
  /\[\[([a-zA-Z0-9_-]+)\]\]|(<(?:Subject|Picture|Video|Audio) \d+>)|(<\/?d>)|(\[Shot \d+\])|(\[Speaker S\d+)|(\(S\d+\))|(At \d{2}:\d{2}\.\d{3},)|(<scenetrans>)|(<cutoff>)/g;

export type TagPart = { kind: PromptTagKind; tagKey: string };

// Splits raw text containing [[key]], <Subject N>/<Picture N>/<Video N>/
// <Audio N>, and H3's own hand-typed dialogue/shot markup (<d>, </d>,
// [Shot N], the [Speaker SN prefix of a delivery bracket, the (SN) inline
// speaker-ID marker, the "At MM:SS.mmm," cut timestamp, <scenetrans>,
// <cutoff> -- see models/minimax_h3/prompt_enhancer.py for the format
// spec these last five come from) into an alternating list of plain
// strings and tag markers, for building the initial node tree from a
// clip's stored shot_prompt (or any other plain-text field) when the
// editor first mounts.
export function splitPlainTextWithTags(text: string): Array<string | TagPart> {
  const parts: Array<string | TagPart> = [];
  let lastIndex = 0;
  for (const match of text.matchAll(TAG_TOKEN_RE)) {
    const index = match.index ?? 0;
    if (index > lastIndex) parts.push(text.slice(lastIndex, index));
    if (match[1] !== undefined) {
      parts.push({ kind: "custom", tagKey: match[1] });
    } else if (match[2] !== undefined) {
      parts.push({ kind: "model", tagKey: match[2] });
    } else {
      const structureKey = match[3] ?? match[4] ?? match[5] ?? match[6] ?? match[7] ?? match[8] ?? match[9];
      parts.push({ kind: "structure", tagKey: structureKey as string });
    }
    lastIndex = index + match[0].length;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return parts;
}

// Hover-tooltip text for a "structure" tag chip — see PromptTagKind's
// docstring above for what each of these actually means in H3's prompt
// syntax (prompts_reference/h3_quality_presets.md sections 4/5,
// models/minimax_h3/prompt_enhancer.py for the timestamp/scenetrans/cutoff
// tokens).
export function structureTagHint(tagKey: string): string {
  if (tagKey === "<d>") return "Dialogue line start";
  if (tagKey === "</d>") return "Dialogue line end";
  if (/^\[Shot \d+\]$/.test(tagKey)) return "Shot marker — starts a new camera shot/cut";
  if (/^\[Speaker S\d+$/.test(tagKey)) return "Speaker delivery bracket — voice/accent/delivery instructions go here, before the spoken line";
  if (/^\(S\d+\)$/.test(tagKey)) return "Inline speaker-ID marker — a readable cue for who's about to speak";
  if (/^At \d{2}:\d{2}\.\d{3},$/.test(tagKey)) return "Cut timestamp — when this shot starts";
  if (tagKey === "<scenetrans>") return "Marks dialogue that continues across a shot cut";
  if (tagKey === "<cutoff>") return "Marks speech truncated by the video ending mid-line";
  return "";
}
