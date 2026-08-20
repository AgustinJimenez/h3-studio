import { describe, expect, it } from "vitest";
import { wordCount, wordCountClass, WORD_TARGET_MIN, WORD_TARGET_MAX } from "./wordCount";

describe("wordCount", () => {
  it("counts words in plain text", () => {
    expect(wordCount("hello world")).toBe(2);
  });

  it("returns 0 for empty/whitespace-only input", () => {
    expect(wordCount("")).toBe(0);
    expect(wordCount("   ")).toBe(0);
    expect(wordCount(null)).toBe(0);
    expect(wordCount(undefined)).toBe(0);
  });

  it("collapses multiple whitespace runs", () => {
    expect(wordCount("one   two\nthree")).toBe(3);
  });
});

describe("wordCountClass", () => {
  it("flags under-target counts as neutral", () => {
    expect(wordCountClass(WORD_TARGET_MIN - 1)).not.toContain("text-danger");
  });

  it("flags in-range counts as ok", () => {
    expect(wordCountClass(WORD_TARGET_MIN)).toContain("text-status-done");
  });

  it("flags over-target counts as danger", () => {
    expect(wordCountClass(WORD_TARGET_MAX + 1)).toContain("text-danger");
  });
});
