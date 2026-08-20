import { describe, expect, it } from "vitest";
import { CharacterSchema, ClipSchema, VideoSchema } from "./schemas";

// Fixtures are trimmed real shapes returned by the backend this session
// (video_editor_app/backend) — catches a field-rename/shape drift between
// frontend and backend at test time instead of at runtime in the browser.

describe("CharacterSchema", () => {
  it("parses a real character shape (image/audio refs, reference_videos, upscale)", () => {
    const raw = {
      id: "5e4b050f29244b428875a53eb239699e",
      order: 1,
      name: "Markos",
      identity_description: "his exact facial identity, stocky build, and voice",
      wardrobe_notes: "For this video he wears a navy blue Boca Juniors jersey.",
      retention: "fully_preserved",
      references: [
        { id: "ref1", type: "image", path: "C:/x/markos.png", note: "", upscale: {} },
        { id: "ref2", type: "audio", path: "C:/x/markos.mp3", note: "" },
      ],
      reference_videos: [
        {
          id: "rv1",
          name: "Reference video",
          style_prompt: "Photorealistic...",
          environment_prompt: "",
          character_prompt: "",
          action_prompt: "[Shot 1] ...",
          seed: -1,
          video_length: 362,
          status: "done",
          job_id: null,
          output_path: "E:/x/out.mp4",
          error: null,
          output_url: "/media/x/out.mp4",
          upscale: { status: "done", output_path: "E:/x/out_upscaled.mp4" },
          last_generation_settings: { model_type: "minimax_h3_ref2va" },
          generation_duration_seconds: 342.9,
        },
      ],
      active_reference_video_id: null,
    };
    const parsed = CharacterSchema.parse(raw);
    expect(parsed.name).toBe("Markos");
    expect(parsed.references).toHaveLength(2);
    expect(parsed.reference_videos[0]?.status).toBe("done");
  });
});

describe("ClipSchema", () => {
  it("parses a continuation clip with generation params", () => {
    const raw = {
      id: "clip1",
      order: 0,
      shot_prompt: "[Shot 1] ...",
      seed: -1,
      video_length: 362,
      continue_from_previous: true,
      continuation_keep_frames: null,
      status: "done",
      job_id: null,
      output_path: "E:/x/clip1.mp4",
      error: null,
      output_url: "/media/x/clip1.mp4",
      last_generation_settings: { image_prompt_type: "V", video_source: "E:/x/prev.mp4" },
      generation_duration_seconds: 334.7,
    };
    const parsed = ClipSchema.parse(raw);
    expect(parsed.continue_from_previous).toBe(true);
    expect(parsed.last_generation_settings?.image_prompt_type).toBe("V");
  });
});

describe("VideoSchema", () => {
  it("parses a video with characters and clips, defaulting missing base_prompt fields", () => {
    const raw = {
      id: "v1",
      folder: "test-v1",
      title: "Test Video",
      template_settings: { resolution: "576x320" },
      base_prompt: { summary: "A scene." },
      characters: [],
      clips: [],
      concat_output_path: null,
      composed_subject_definitions: "",
      composed_retention_analysis: "",
    };
    const parsed = VideoSchema.parse(raw);
    expect(parsed.base_prompt.overall_soundscape).toBe("");
    expect(parsed.base_prompt.summary).toBe("A scene.");
  });
});
