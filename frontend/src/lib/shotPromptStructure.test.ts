import { describe, expect, it } from "vitest";
import { parseShotPrompt, serializeShotPrompt, deriveSpeakerOptions, shotDisplayNumbers } from "./shotPromptStructure";

// Real shot_prompt from this project's breaking-bad-style-lab-standoff-e3d5a28f
// clip #0 -- interleaved prose + 2 dialogue lines + a trailing sentence, the
// exact shape the "ordered segments" parsing model exists to handle without
// reordering/dropping anything.
const REAL_CLIP_SHOT_PROMPT =
  "[Shot 1] Interior of a run-down industrial warehouse repurposed as a makeshift clandestine chemistry lab. Harsh yellow-tinted fluorescent light flickers overhead, casting long shadows. Blue plastic tarps line the walls, a metal table holds glass flasks, coiled tubing, and beakers of amber liquid. Both men wear their own everyday clothing, exactly as shown in their reference photos, no costume changes, no uniforms, no protective gear. <Subject 1> Santamaria stands alone at the metal table, calmly adjusting a glass flask with his bare hands, unhurried and focused - he is the only person at the table. <Subject 2> Markos paces slowly near a doorway in the background, glancing over his shoulder repeatedly, visibly on edge - he is the only person near the doorway. Camera starts on a wide establishing shot of the whole room, then slowly pushes in over the course of the shot to a medium two-shot framing both men, and only these two men. Santamaria (S1) <d>[Speaker S1, voice matches <Audio 1> exactly, [[neutral_spanish]], calm, measured, quietly commanding] Tranquilo, Markos. Todo esta bajo control, solo necesito que termines de sellar esos bidones antes de que lleguen.</d> Markos (S2) <d>[Speaker S2, voice matches <Audio 2> exactly, [[neutral_spanish]], tense, anxious, slightly breathless] Es que... escuche ruidos afuera hace un rato, Santamaria, no se, tengo un mal presentimiento con todo esto.</d> Each spoken line is sized to fit naturally within the shot's full duration, ending right around the shot's final second, no trailing silence or dead air with the mouth closed before the cut. Natural, casual conversational register, not a polished voice-over.";

describe("parseShotPrompt / serializeShotPrompt round-trip", () => {
  it("reproduces the real clip text exactly", () => {
    const shots = parseShotPrompt(REAL_CLIP_SHOT_PROMPT);
    expect(serializeShotPrompt(shots)).toBe(REAL_CLIP_SHOT_PROMPT);
  });

  it("parses exactly one shot with the two dialogue lines as separate segments", () => {
    const shots = parseShotPrompt(REAL_CLIP_SHOT_PROMPT);
    expect(shots).toHaveLength(1);
    expect(shots[0].hasMarker).toBe(true);
    expect(shotDisplayNumbers(shots)).toEqual([1]);
    const dialogueSegments = shots[0].segments.filter((s) => s.type === "dialogue");
    expect(dialogueSegments).toHaveLength(2);
    expect(dialogueSegments[0]).toMatchObject({
      speakerTag: "S1",
      audioTag: "<Audio 1>",
      primaryTagKey: "neutral_spanish",
      extra: "calm, measured, quietly commanding",
    });
    expect(dialogueSegments[0].text).toContain("Tranquilo, Markos.");
    expect(dialogueSegments[1]).toMatchObject({
      speakerTag: "S2",
      audioTag: "<Audio 2>",
      primaryTagKey: "neutral_spanish",
      extra: "tense, anxious, slightly breathless",
    });
    // prose segments preserved, including the "Santamaria (S1)"/"Markos (S2)"
    // annotations right before each <d> and the trailing sentence after the
    // last one -- nothing collapsed into a single "description" blob.
    const prose = shots[0].segments.filter((s) => s.type === "prose").map((s) => s.text);
    expect(prose.some((p) => p.endsWith("Santamaria (S1)"))).toBe(true);
    expect(prose.some((p) => p.startsWith("Markos (S2)"))).toBe(true);
    expect(prose.some((p) => p.includes("Natural, casual conversational register"))).toBe(true);
  });

  it("handles empty text as a single empty implicit shot", () => {
    expect(parseShotPrompt("")).toEqual([{ hasMarker: false, startTime: null, segments: [] }]);
  });

  it("handles text with no [Shot N] marker as one implicit unlabeled shot", () => {
    const shots = parseShotPrompt("Just some plain prose, no shot markers at all.");
    expect(shots).toHaveLength(1);
    expect(shots[0].hasMarker).toBe(false);
    expect(shotDisplayNumbers(shots)).toEqual([null]);
    expect(shots[0].segments).toEqual([{ type: "prose", text: "Just some plain prose, no shot markers at all." }]);
  });

  it("keeps a malformed <d> block (no leading bracket) as opaque prose instead of guessing", () => {
    const text = "[Shot 1] Some setup. <d>no bracket here, just text</d> more prose.";
    const shots = parseShotPrompt(text);
    expect(shots[0].segments.every((s) => s.type === "prose")).toBe(true);
    expect(serializeShotPrompt(shots)).toBe(text);
  });

  it("round-trips a second [Shot N] block independently", () => {
    const text = "[Shot 1] First shot text. [Shot 2] Second shot text with <d>[Speaker S1] Hola</d> line.";
    const shots = parseShotPrompt(text);
    expect(shots).toHaveLength(2);
    expect(shotDisplayNumbers(shots)).toEqual([1, 2]);
    expect(serializeShotPrompt(shots)).toBe(text);
  });

  it("renumbers sequentially even if the original text had non-sequential/gapped shot numbers", () => {
    const shots = parseShotPrompt("[Shot 1] First. [Shot 5] Second (originally numbered 5, not 2).");
    expect(shotDisplayNumbers(shots)).toEqual([1, 2]);
    expect(serializeShotPrompt(shots)).toBe("[Shot 1] First. [Shot 2] Second (originally numbered 5, not 2).");
  });

  it("renumbers after reordering shots", () => {
    const shots = parseShotPrompt("[Shot 1] First. [Shot 2] Second.");
    const reordered = [shots[1], shots[0]];
    expect(shotDisplayNumbers(reordered)).toEqual([1, 2]);
    expect(serializeShotPrompt(reordered)).toBe("[Shot 1] Second. [Shot 2] First.");
  });

  it("parses and round-trips a [Shot N] At MM:SS.mmm, cut timestamp", () => {
    const text = "[Shot 1] First shot. [Shot 2] At 00:03.500, camera cuts to a wider shot.";
    const shots = parseShotPrompt(text);
    expect(shots[1].startTime).toBe("00:03.500");
    expect(shots[1].segments).toEqual([{ type: "prose", text: "camera cuts to a wider shot." }]);
    expect(serializeShotPrompt(shots)).toBe(text);
  });

  it("leaves startTime null when a shot has no timestamp", () => {
    const shots = parseShotPrompt("[Shot 1] No timestamp here.");
    expect(shots[0].startTime).toBeNull();
  });
});

describe("deriveSpeakerOptions", () => {
  it("groups Subject/Audio tags per character in order", () => {
    const modelTags = [
      { tag: "<Subject 1>", description: "Santamaria — character reference" },
      { tag: "<Picture 1>", description: "Santamaria — image reference" },
      { tag: "<Audio 1>", description: "Santamaria — audio reference: santamaria.wav" },
      { tag: "<Subject 2>", description: "Markos — character reference" },
      { tag: "<Picture 2>", description: "Markos — image reference" },
      { tag: "<Audio 2>", description: "Markos — audio reference: markos.wav" },
    ];
    expect(deriveSpeakerOptions(modelTags)).toEqual([
      { name: "Santamaria", subjectTag: "<Subject 1>", speakerTag: "S1", audioTag: "<Audio 1>" },
      { name: "Markos", subjectTag: "<Subject 2>", speakerTag: "S2", audioTag: "<Audio 2>" },
    ]);
  });

  it("leaves audioTag null for a character with no audio reference", () => {
    const modelTags = [
      { tag: "<Subject 1>", description: "Horacio — character reference" },
      { tag: "<Picture 1>", description: "Horacio — image reference" },
    ];
    expect(deriveSpeakerOptions(modelTags)).toEqual([
      { name: "Horacio", subjectTag: "<Subject 1>", speakerTag: "S1", audioTag: null },
    ]);
  });
});
