import type { ModelTag } from "../schemas";

// Parses/serializes H3's informal shot/dialogue mini-syntax used inside a
// clip's shot_prompt: [Shot N] markers divide a clip into shots, and each
// spoken line is written as
//   <d>[Speaker SN, voice matches <Audio M> exactly, [[accent_tag]], mood] text</d>
// (see prompts_reference/h3_quality_presets.md sections 4-5, and
// promptTagNode.tsx's "structure" chip kind, which highlights these same
// tokens in the plain-text Simple editor). This module is the parser +
// serializer backing the Structured tab (StructuredShotEditor.tsx) — a
// second, form-based way to edit the exact same shot_prompt string.
//
// Parses into an ORDERED LIST OF SEGMENTS per shot, not "description then a
// list of dialogue lines" — real clips interleave prose and dialogue lines
// (a plain-text "Santamaria (S1)" annotation right before a <d> block,
// prose sentences after the last line, etc.), and a description+list model
// would silently reorder that content on first edit.

export type DialogueSegment = {
  type: "dialogue";
  speakerTag: string | null; // "S1", or null if unparseable
  audioTag: string | null; // "<Audio 1>", or null
  primaryTagKey: string | null; // first [[key]] found in the bracket, or null
  extra: string; // mood adjectives + any other bracket content verbatim -- never dropped
  text: string; // the spoken line
};
export type ProseSegment = { type: "prose"; text: string };
export type ShotSegment = ProseSegment | DialogueSegment;
// hasMarker: true -- a real [Shot N] block. The displayed/serialized N is
// always derived from this shot's position among hasMarker shots, never
// stored/edited as text -- so adding, reordering, or deleting a shot
// renumbers everything else for free instead of leaving stale numbers.
// false only ever occurs for at most one shot, the preamble before the
// first marker (or the whole text, if it has no markers at all).
// startTime: the "MM:SS.mmm" from an optional "[Shot N] At MM:SS.mmm, ..."
// cut timestamp (models/minimax_h3/prompt_enhancer.py) -- always null when
// hasMarker is false, since the timestamp only ever follows a real marker.
export type ParsedShot = { hasMarker: boolean; startTime: string | null; segments: ShotSegment[] };

export type SpeakerOption = { name: string; subjectTag: string; speakerTag: string; audioTag: string | null };

const SHOT_MARKER_RE = /\[Shot (\d+)\]/g;
// <d> ... </d>, non-greedy so back-to-back dialogue lines don't merge into one match.
const DIALOGUE_BLOCK_RE = /<d>([\s\S]*?)<\/d>/g;
const SPEAKER_RE = /Speaker (S\d+)\s*,?\s*/;
const AUDIO_RE = /voice matches (<Audio \d+>) exactly\s*,?\s*/;
const PRIMARY_TAG_RE = /\[\[([a-zA-Z0-9_-]+)\]\]\s*,?\s*/;
const START_TIME_RE = /^\s*At (\d{2}:\d{2}\.\d{3}),\s*/;

function parseDialogueBracket(bracketContent: string, text: string): DialogueSegment {
  let rest = bracketContent;

  let speakerTag: string | null = null;
  const speakerMatch = SPEAKER_RE.exec(rest);
  if (speakerMatch) {
    speakerTag = speakerMatch[1];
    rest = rest.slice(0, speakerMatch.index) + rest.slice(speakerMatch.index + speakerMatch[0].length);
  }

  let audioTag: string | null = null;
  const audioMatch = AUDIO_RE.exec(rest);
  if (audioMatch) {
    audioTag = audioMatch[1];
    rest = rest.slice(0, audioMatch.index) + rest.slice(audioMatch.index + audioMatch[0].length);
  }

  let primaryTagKey: string | null = null;
  const tagMatch = PRIMARY_TAG_RE.exec(rest);
  if (tagMatch) {
    primaryTagKey = tagMatch[1];
    rest = rest.slice(0, tagMatch.index) + rest.slice(tagMatch.index + tagMatch[0].length);
  }

  // Whatever's left (mood adjectives, any additional [[tag]] the regexes
  // above didn't specifically target, stray punctuation) is kept verbatim
  // so serialization never loses content the parser doesn't recognize.
  const extra = rest.replace(/^[,\s]+|[,\s]+$/g, "");

  return { type: "dialogue", speakerTag, audioTag, primaryTagKey, extra, text: text.trim() };
}

// Splits a leading "[...]" bracket off the front of a string, tracking
// bracket depth so a nested [[key]] (which has its own "]" characters)
// doesn't fool a naive first-"]" match into truncating the outer bracket.
// Returns null if the string doesn't start with "[" or the brackets never
// balance out (caller then treats the whole <d> block as opaque prose).
function splitOuterBracket(s: string): { bracket: string; rest: string } | null {
  if (!s.startsWith("[")) return null;
  let depth = 0;
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "[") depth++;
    else if (s[i] === "]") {
      depth--;
      if (depth === 0) return { bracket: s.slice(1, i), rest: s.slice(i + 1) };
    }
  }
  return null;
}

function parseShotChunk(chunk: string): ShotSegment[] {
  const segments: ShotSegment[] = [];
  let lastIndex = 0;
  for (const match of chunk.matchAll(DIALOGUE_BLOCK_RE)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      const prose = chunk.slice(lastIndex, index);
      if (prose.trim()) segments.push({ type: "prose", text: prose.trim() });
    }
    const inner = match[1];
    const split = splitOuterBracket(inner.trim());
    if (split) {
      segments.push(parseDialogueBracket(split.bracket, split.rest));
    } else {
      // Doesn't start with a [...] bracket right after <d> -- not the
      // recognized shape, keep the whole <d>...</d> block as opaque prose
      // rather than guessing, so nothing is ever silently mangled.
      segments.push({ type: "prose", text: match[0] });
    }
    lastIndex = index + match[0].length;
  }
  if (lastIndex < chunk.length) {
    const prose = chunk.slice(lastIndex);
    if (prose.trim()) segments.push({ type: "prose", text: prose.trim() });
  }
  return segments;
}

export function parseShotPrompt(text: string): ParsedShot[] {
  if (!text.trim()) return [{ hasMarker: false, startTime: null, segments: [] }];

  const markers = [...text.matchAll(SHOT_MARKER_RE)];
  if (markers.length === 0) {
    return [{ hasMarker: false, startTime: null, segments: parseShotChunk(text) }];
  }

  const shots: ParsedShot[] = [];
  const firstIndex = markers[0].index ?? 0;
  if (firstIndex > 0) {
    const preamble = text.slice(0, firstIndex);
    if (preamble.trim()) shots.push({ hasMarker: false, startTime: null, segments: parseShotChunk(preamble) });
  }
  for (let i = 0; i < markers.length; i++) {
    const marker = markers[i];
    const chunkStart = (marker.index ?? 0) + marker[0].length;
    const chunkEnd = i + 1 < markers.length ? markers[i + 1].index ?? text.length : text.length;
    let chunk = text.slice(chunkStart, chunkEnd);
    let startTime: string | null = null;
    const startMatch = START_TIME_RE.exec(chunk);
    if (startMatch) {
      startTime = startMatch[1];
      chunk = chunk.slice(startMatch[0].length);
    }
    shots.push({ hasMarker: true, startTime, segments: parseShotChunk(chunk) });
  }
  return shots;
}

function serializeDialogueSegment(seg: DialogueSegment): string {
  const bracketParts = [
    seg.speakerTag ? `Speaker ${seg.speakerTag}` : null,
    seg.audioTag ? `voice matches ${seg.audioTag} exactly` : null,
    seg.primaryTagKey ? `[[${seg.primaryTagKey}]]` : null,
    seg.extra.trim() || null,
  ].filter((p): p is string => !!p);
  return `<d>[${bracketParts.join(", ")}] ${seg.text}</d>`;
}

export function serializeShotPrompt(shots: ParsedShot[]): string {
  let shotNumber = 0;
  return shots
    .map((shot) => {
      const body = shot.segments
        .map((seg) => (seg.type === "prose" ? seg.text : serializeDialogueSegment(seg)))
        .join(" ")
        .trim();
      if (!shot.hasMarker) return body;
      shotNumber++;
      const timePrefix = shot.startTime ? `At ${shot.startTime}, ` : "";
      return `[Shot ${shotNumber}] ${timePrefix}${body}`.trim();
    })
    .filter((s) => s.length > 0)
    .join(" ");
}

// Display numbers for each shot, aligned index-for-index with the `shots`
// array passed in -- null for the (at most one) unlabeled preamble shot.
// Same counting rule as serializeShotPrompt, factored out so the UI never
// has to recompute or store shot numbers itself.
export function shotDisplayNumbers(shots: ParsedShot[]): (number | null)[] {
  let n = 0;
  return shots.map((shot) => (shot.hasMarker ? ++n : null));
}

// Groups video.model_tags (compose_model_tags's server-computed output)
// into per-character speaker options for the Structured tab's Speaker
// dropdown. Assumes Speaker SN == Subject N (confirmed against every real
// clip in this project at the time this was written; not an H3 rule --
// the Simple tab remains available if that assumption ever doesn't hold).
export function deriveSpeakerOptions(modelTags: ModelTag[]): SpeakerOption[] {
  const options: SpeakerOption[] = [];
  let current: SpeakerOption | null = null;
  for (const t of modelTags) {
    const subjectMatch = /^<Subject (\d+)>$/.exec(t.tag);
    if (subjectMatch) {
      const name = t.description.split(" — ")[0] || t.tag;
      current = { name, subjectTag: t.tag, speakerTag: `S${subjectMatch[1]}`, audioTag: null };
      options.push(current);
    } else if (current && /^<Audio \d+>$/.test(t.tag) && t.description.includes("audio reference") && !current.audioTag) {
      current.audioTag = t.tag;
    }
  }
  return options;
}
