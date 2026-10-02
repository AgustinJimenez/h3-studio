import { describe, expect, it } from "vitest";
import { formatFrames, formatTotalFrames, renderedFrames } from "./frames";

describe("renderedFrames", () => {
  // Expected values are what WanGP really delivered for past clips of this app (see backend/lint.py).
  it("rounds an off-grid request DOWN onto H3's 17k+5 grid", () => {
    const delivered: Record<number, number> = { 125: 124, 145: 141, 240: 226, 174: 158, 289: 277, 337: 328, 193: 192 };
    for (const [requested, expected] of Object.entries(delivered)) {
      expect(renderedFrames(Number(requested))).toBe(expected);
    }
  });

  it("leaves on-grid lengths alone", () => {
    for (const n of [124, 141, 158, 175, 192, 243, 345, 362]) expect(renderedFrames(n)).toBe(n);
  });

  it("never goes below the 5-frame floor", () => {
    expect(renderedFrames(1)).toBe(5);
    expect(renderedFrames(0)).toBe(5);
  });
});

describe("formatFrames", () => {
  it("shows just the length when it is on the grid", () => {
    expect(formatFrames(192)).toBe("192f (~8.0s)");
  });

  it("shows what an off-grid request will really render", () => {
    expect(formatFrames(145)).toBe("145f → renders 141f (~5.9s)");
  });
});

describe("formatTotalFrames", () => {
  it("formats a sum without grid rounding", () => {
    expect(formatTotalFrames(300)).toBe("300f (~12.5s)");
  });
});
