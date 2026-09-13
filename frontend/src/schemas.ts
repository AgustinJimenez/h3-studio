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

export const CharacterSchema = z.object({
  id: z.string(),
  order: z.number(),
  name: z.string().default(""),
  identity_description: z.string().default(""),
  wardrobe_notes: z.string().default(""),
  retention: z.string().default("fully_preserved"),
  references: z.array(ReferenceSchema).default([]),
  reference_videos: z.array(ReferenceVideoSchema).default([]),
  active_reference_video_id: z.string().nullable().optional(),
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
  active_character_ids: z.array(z.string()).nullable().optional(),
  status: StatusSchema.catch("draft"),
  job_id: z.string().nullable().optional(),
  output_path: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  output_url: z.string().nullable().optional(),
  own_segment_url: z.string().nullable().optional(),
  tail_frame_urls: z.array(z.string()).optional().default([]),
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

export const ModelTagSchema = z.object({
  tag: z.string(),
  description: z.string(),
});
export type ModelTag = z.infer<typeof ModelTagSchema>;

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
});
export type Options = z.infer<typeof OptionsSchema>;

export const ModelStatusSchema = z.object({
  model_type: z.string().nullable(),
});
export type ModelStatus = z.infer<typeof ModelStatusSchema>;
