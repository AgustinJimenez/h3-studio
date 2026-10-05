import { z } from "zod";

// Mirrors video_editor_app/backend/{prompt,main,store}.py's actual shapes.
// Zod schemas are the source of truth — types are inferred, not hand-duplicated,
// so a backend field rename shows up here as a type error instead of a silent
// runtime mismatch (the exact class of bug this app kept hitting pre-refactor).

export const StatusSchema = z.enum(["none", "draft", "queued", "running", "done", "failed"]);
export type Status = z.infer<typeof StatusSchema>;

export const UpscaleSchema = z.object({
  status: StatusSchema.catch("none"),
  job_id: z.string().nullable().optional(),
  output_path: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  output_url: z.string().nullable().optional(),
  last_generation_settings: z.record(z.string(), z.unknown()).nullable().optional(),
  generation_duration_seconds: z.number().nullable().optional(),
});
export type Upscale = z.infer<typeof UpscaleSchema>;

export const ReferenceSchema = z.object({
  id: z.string(),
  type: z.enum(["image", "video", "audio"]),
  path: z.string(),
  note: z.string().optional().default(""),
  upscale: UpscaleSchema.optional(),
});
export type Reference = z.infer<typeof ReferenceSchema>;

export const ReferenceVideoSchema = z.object({
  id: z.string(),
  name: z.string().default(""),
  style_prompt: z.string().optional().default(""),
  environment_prompt: z.string().optional().default(""),
  character_prompt: z.string().optional().default(""),
  action_prompt: z.string().optional().default(""),
  seed: z.number().default(-1),
  video_length: z.number().default(174),
  status: StatusSchema.catch("none"),
  job_id: z.string().nullable().optional(),
  output_path: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  output_url: z.string().nullable().optional(),
  upscale: UpscaleSchema.optional(),
  last_generation_settings: z.record(z.string(), z.unknown()).nullable().optional(),
  generation_duration_seconds: z.number().nullable().optional(),
});
export type ReferenceVideo = z.infer<typeof ReferenceVideoSchema>;

export const ModelTagSchema = z.object({
  tag: z.string(),
  description: z.string(),
});
export type ModelTag = z.infer<typeof ModelTagSchema>;

export const CharacterImageGenSchema = z.object({
  provider: z.enum(["comfyui", "wangp"]).catch("comfyui"),
  lora: z.string().default(""),
  lora_multiplier: z.number().default(1),
  trigger: z.string().default(""),
});
export type CharacterImageGen = z.infer<typeof CharacterImageGenSchema>;

export const GeneratedImageSchema = z.object({
  id: z.string(),
  prompt: z.string().default(""),
  source_paths: z.array(z.string()).default([]),
  seed: z.number().default(-1),
  aspect: z.string().default("square"),
  status: StatusSchema.catch("none"),
  job_id: z.string().nullable().optional(),
  output_path: z.string().nullable().optional(),
  output_url: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  last_generation_settings: z.record(z.string(), z.unknown()).nullable().optional(),
  generation_duration_seconds: z.number().nullable().optional(),
});
export type GeneratedImage = z.infer<typeof GeneratedImageSchema>;

export const CharacterSchema = z.object({
  id: z.string(),
  order: z.number(),
  kind: z.enum(["person", "environment"]).catch("person"),
  name: z.string().default(""),
  identity_description: z.string().default(""),
  wardrobe_notes: z.string().default(""),
  retention: z.string().default("fully_preserved"),
  references: z.array(ReferenceSchema).default([]),
  reference_videos: z.array(ReferenceVideoSchema).default([]),
  active_reference_video_id: z.string().nullable().optional(),
  model_tags: z.array(ModelTagSchema).optional().default([]),
  image_gen: CharacterImageGenSchema.default({ provider: "comfyui", lora: "", lora_multiplier: 1, trigger: "" }),
  generated_images: z.array(GeneratedImageSchema).default([]),
});
export type Character = z.infer<typeof CharacterSchema>;

export const QaVoiceResultSchema = z.object({
  reference_path: z.string(),
  score: z.number(),
  same_speaker: z.boolean(),
});
export type QaVoiceResult = z.infer<typeof QaVoiceResultSchema>;

export const QaReportSchema = z.object({
  visual_analysis: z.string(),
  voice_results: z.array(QaVoiceResultSchema).default([]),
  analyzed_at: z.number(),
});
export type QaReport = z.infer<typeof QaReportSchema>;

export const ClipSchema = z.object({
  id: z.string(),
  order: z.number(),
  shot_prompt: z.string().default(""),
  seed: z.number().default(-1),
  video_length: z.number().default(362),
  continue_from_previous: z.boolean().optional().default(false),
  continuation_keep_frames: z.number().nullable().optional(),
  bridge_to_next: z.boolean().optional().default(false),
  start_frame_path: z.string().nullable().optional(),
  control_video_path: z.string().nullable().optional(),
  control_video_url: z.string().nullable().optional(),
  control_video_enabled: z.boolean().nullable().optional(), // false: attached but left out of the generation
  resolution_override: z.string().nullable().optional(), // this clip only; empty = the template's
  model_preset: z.string().nullable().optional(), // "pdd8" = fast 8-step model for this clip
  two_phase: z.boolean().nullable().optional(), // draft at half size, H3 latent upscale, refine
  video_references_enabled: z.boolean().nullable().optional(), // false: this clip leaves out the characters' video references
  trim_start_frames: z.number().nullable().optional(), // frames cut off the start of this clip when the video is joined
  upscale: UpscaleSchema.nullable().optional(),
  control_video_info: z.object({ frames: z.number(), width: z.number(), height: z.number(), fps: z.number() }).nullable().optional(),
  active_character_ids: z.array(z.string()).nullable().optional(),
  status: StatusSchema.catch("draft"),
  job_id: z.string().nullable().optional(),
  output_path: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  output_url: z.string().nullable().optional(),
  own_segment_url: z.string().nullable().optional(),
  tail_frame_urls: z.array(z.string()).optional().default([]),
  history: z
    .array(
      z.object({
        id: z.string(),
        output_url: z.string().nullable().optional(),
        finished_at: z.number(),
        seconds: z.number().nullable().optional(),
        seed: z.number().nullable().optional(),
        resolution: z.string().nullable().optional(),
        steps: z.number().nullable().optional(),
        label: z.string().optional().default(""),
        current: z.boolean().optional().default(false),
      }),
    )
    .optional()
    .default([]),
  last_generation_settings: z.record(z.string(), z.unknown()).nullable().optional(),
  generation_duration_seconds: z.number().nullable().optional(),
  qa_report: QaReportSchema.nullable().optional(),
});
export type Clip = z.infer<typeof ClipSchema>;

export const BasePromptSchema = z.object({
  summary: z.string().optional().default(""),
  overall_soundscape: z.string().optional().default(""),
  non_diegetic_music: z.string().optional().default(""),
});
export type BasePrompt = z.infer<typeof BasePromptSchema>;

export const VideoSchema = z.object({
  id: z.string(),
  folder: z.string(),
  title: z.string(),
  description: z.string().optional().default(""),
  created_at: z.number().optional(),
  template_settings: z.record(z.string(), z.unknown()).default({}),
  base_prompt: BasePromptSchema.default({ summary: "", overall_soundscape: "", non_diegetic_music: "" }),
  characters: z.array(CharacterSchema).default([]),
  clips: z.array(ClipSchema).default([]),
  concat_output_path: z.string().nullable().optional(),
  concat_output_url: z.string().nullable().optional(),
  composed_subject_definitions: z.string().optional().default(""),
  composed_retention_analysis: z.string().optional().default(""),
  model_tags: z.array(ModelTagSchema).optional().default([]),
});
export type Video = z.infer<typeof VideoSchema>;

export const PromptTagSchema = z.object({
  id: z.string(),
  name: z.string(),
  key: z.string(),
  body: z.string(),
});
export type PromptTag = z.infer<typeof PromptTagSchema>;

export const AnimateJobSchema = z.object({
  id: z.string(),
  created_at: z.number().optional(),
  label: z.string().optional().default(""),
  control_video_path: z.string().optional().default(""),
  character_image_path: z.string().optional().default(""),
  mask_path: z.string().nullable().optional(),
  prompt: z.string().optional().default(""),
  mode: z.enum(["replace", "replace_see_through"]).default("replace"),
  relighting: z.boolean().optional().default(false),
  seed: z.number().default(-1),
  video_length: z.number().nullable().optional(),
  resolution: z.string().nullable().optional(),
  status: StatusSchema.catch("draft"),
  job_id: z.string().nullable().optional(),
  output_path: z.string().nullable().optional(),
  output_url: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  generation_duration_seconds: z.number().nullable().optional(),
});
export type AnimateJob = z.infer<typeof AnimateJobSchema>;

export const VideoSummarySchema = z.object({
  id: z.string(),
  title: z.string(),
  created_at: z.number().optional(),
  clip_count: z.number(),
  done_count: z.number(),
  thumbnail_url: z.string().nullable().optional(),
  concat_output_url: z.string().nullable().optional(),
  resolution: z.string().nullable().optional(),
  model_type: z.string().nullable().optional(),
  character_names: z.array(z.string()).optional().default([]),
  character_avatars: z.array(z.string().nullable()).optional().default([]),
  total_duration_seconds: z.number().nullable().optional(),
  has_running_job: z.boolean().optional().default(false),
});
export type VideoSummary = z.infer<typeof VideoSummarySchema>;

export const ModelTypeOptionSchema = z.object({
  model_type: z.string(),
  name: z.string(),
  model_filenames: z.array(z.string()),
});

export const ChoiceSchema = z.object({
  label: z.string(),
  value: z.union([z.string(), z.number()]),
});

export const OptionsSchema = z.object({
  model_types: z.array(ModelTypeOptionSchema),
  selected_model_type: z.string().nullable(),
  resolutions: z.array(ChoiceSchema),
  attention_modes: z.array(ChoiceSchema),
  memory_profiles: z.array(ChoiceSchema),
  loras: z.array(z.string()),
});
export type Options = z.infer<typeof OptionsSchema>;

export const ActiveJobSchema = z.object({
  job_id: z.string(),
  status: z.enum(["running", "queued"]),
  started_at: z.number().nullable().optional(),
  position: z.number(),
  kind: z.string(),
  label: z.string(),
  target_id: z.string().nullable().optional(),
  video_id: z.string().nullable().optional(),
  video_title: z.string().nullable().optional(),
  character_id: z.string().nullable().optional(),
  character_name: z.string().nullable().optional(),
  swap_id: z.string().nullable().optional(),
  progress: z
    .object({ stage: z.string(), value: z.number().nullable().optional(), max: z.number().nullable().optional(), fraction: z.number().nullable().optional() })
    .nullable()
    .optional(),
});
export type ActiveJob = z.infer<typeof ActiveJobSchema>;

export const ImageProviderSchema = z.object({
  id: z.enum(["comfyui", "wangp"]),
  name: z.string(),
  available: z.boolean(),
  loras: z.array(z.string()),
  note: z.string().optional().default(""),
});
export type ImageProvider = z.infer<typeof ImageProviderSchema>;

export const ModelStatusSchema = z.object({
  model_type: z.string().nullable(),
});
export type ModelStatus = z.infer<typeof ModelStatusSchema>;

// ---------------------------------------------------------------- swap --

export const SwapCastEntrySchema = z.object({
  id: z.string(),
  name: z.string().catch(""),
  image_path: z.string().catch(""),
  appearance: z.string().catch(""),
  outfit: z.string().catch(""),
  body: z.string().catch(""),
  source_character_id: z.string().nullable().optional(),
});
export type SwapCastEntry = z.infer<typeof SwapCastEntrySchema>;

export const SwapPersonSchema = z.object({
  id: z.string(),
  cast_id: z.string().nullable().catch(null),
  target_description: z.string().catch(""),
  order: z.number().catch(0),
});
export type SwapPerson = z.infer<typeof SwapPersonSchema>;

export const SwapChunkSchema = z.object({
  index: z.number(),
  start: z.number(),
  end: z.number(),
  frames_24: z.number(),
  padded_frames: z.number(),
});

export const SwapSceneSchema = z.object({
  index: z.number(),
  start_frame_src: z.number(),
  end_frame_src: z.number(),
  frames_24: z.number(),
  chunks: z.array(SwapChunkSchema).catch([]),
  background_text: z.string().catch(""),
  people: z.array(SwapPersonSchema).catch([]),
  thumb_url: z.string().nullable().optional(),
  clip_url: z.string().nullable().optional(), // this scene of the original, cut into its own clip
});
export type SwapScene = z.infer<typeof SwapSceneSchema>;

export const SwapRunSchema = z.object({
  id: z.string(),
  created_at: z.number().nullable().optional(),
  quality: z.string().nullable().optional(),
  width: z.number().nullable().optional(),
  height: z.number().nullable().optional(),
  seed: z.number().nullable().optional(),
  seconds: z.number().nullable().optional(),
  mean_luma: z.number().nullable().optional(),
  output_url: z.string().nullable().optional(),
  raw_url: z.string().nullable().optional(),
  source_clip_url: z.string().nullable().optional(),
  extra_loras: z.array(z.tuple([z.string(), z.number()])).catch([]),
  active: z.boolean().catch(false),
  method: z.string().nullable().optional(), // "viggle", "upscale"; empty for the normal swap
  edited_frame_url: z.string().nullable().optional(), // the still a Viggle run animated
});
export type SwapRun = z.infer<typeof SwapRunSchema>;

export const SwapStillSchema = z.object({
  id: z.string(),
  url: z.string().nullable().optional(),
  prompt: z.string().catch(""),
  seed: z.number().catch(0),
  created_at: z.number().nullable().optional(),
});
export type SwapStill = z.infer<typeof SwapStillSchema>;

export const SwapPassSchema = z.object({
  id: z.string(),
  scene_index: z.number(),
  chunk_index: z.number(),
  person_id: z.string(),
  order: z.number(),
  quality: z.string().catch("final"),
  prompt: z.string().catch(""),
  status: z.string().catch("draft"),
  job_id: z.string().nullable().optional(),
  output_path: z.string().nullable().optional(),
  raw_path: z.string().nullable().optional(),
  mean_luma: z.number().nullable().optional(),
  error: z.string().nullable().optional(),
  seconds: z.number().nullable().optional(),
  output_url: z.string().nullable().optional(),
  raw_url: z.string().nullable().optional(),
  started_at: z.number().nullable().optional(),
  history: z.array(SwapRunSchema).catch([]),
  stills: z.array(SwapStillSchema).catch([]), // candidate edited frames for the Viggle method
  activity: z.string().nullable().optional(), // "stills" while the candidate stills are being made
  still_error: z.string().nullable().optional(),
  params: z
    .object({
      character: z.string().catch(""),
      target: z.string().catch(""),
      steps: z.number().catch(0),
      sampler: z.string().catch(""),
      scheduler: z.string().catch(""),
      turbo: z.boolean().catch(false),
      quality: z.string().optional(),
      loras: z.array(z.string()).catch([]),
      model: z.string().catch(""),
      width: z.number().catch(0),
      height: z.number().catch(0),
      seed: z.number().catch(0),
      frames_24: z.number().nullable().optional(),
      padded_frames: z.number().nullable().optional(),
      raw_frames: z.number().nullable().optional(),
      lead_used: z.number().nullable().optional(),
      method: z.string().optional(),
      trim_frames: z.number().nullable().optional(),
      source: z.string().catch(""),
    })
    .optional(),
});
export type SwapPass = z.infer<typeof SwapPassSchema>;

export const SwapProjectSchema = z.object({
  id: z.string(),
  title: z.string().catch(""),
  created_at: z.number().catch(0),
  status: z.string().catch("draft"),
  source: z.object({
    path: z.string().catch(""),
    width: z.number().catch(0),
    height: z.number().catch(0),
    fps: z.number().catch(24),
    frames: z.number().catch(0),
    duration: z.number().catch(0),
    has_audio: z.boolean().catch(false),
  }),
  settings: z.object({
    quality: z.string().catch("final"),
    width: z.number().catch(704),
    height: z.number().catch(1248),
    seed: z.number().catch(904234),
  }),
  cast: z.array(SwapCastEntrySchema).catch([]),
  scenes: z.array(SwapSceneSchema).catch([]),
  scenes_confirmed: z.boolean().catch(false),
  passes: z.array(SwapPassSchema).catch([]),
  final: z
    .object({ path: z.string().nullable().optional(), status: z.string().catch("none"), error: z.string().nullable().optional() })
    .catch({ status: "none" }),
  plan_notes: z.array(z.string()).catch([]),
  source_url: z.string().nullable().optional(),
  final_url: z.string().nullable().optional(),
  size_bytes: z.number().catch(0),
});
export type SwapProject = z.infer<typeof SwapProjectSchema>;

export const SwapCharacterSchema = z.object({
  video_id: z.string(),
  video_title: z.string().catch(""),
  character_id: z.string(),
  name: z.string().catch(""),
  image_path: z.string(),
  appearance: z.string().catch(""),
  outfit: z.string().catch(""),
});
export type SwapCharacter = z.infer<typeof SwapCharacterSchema>;
