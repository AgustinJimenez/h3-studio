import {
  VideoSchema,
  VideoSummarySchema,
  CharacterSchema,
  ClipSchema,
  OptionsSchema,
  ModelStatusSchema,
  ActiveJobSchema,
  ImageProviderSchema,
  PromptTagSchema,
  AnimateJobSchema,
  type Video,
  type VideoSummary,
  type Character,
  type Clip,
  type Options,
  type ModelStatus,
  type ActiveJob,
  type ImageProvider,
  type PromptTag,
  type AnimateJob,
  type QaReport,
} from "../schemas";

// Derived from wherever this page was loaded from, so the same build works
// both on localhost and when opened from another device on the LAN (the
// backend always listens on the same port, just reached via a different host).
const API_BASE = `http://${window.location.hostname}:8787`;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ? JSON.stringify(body.detail) : detail;
    } catch {
      // ignore, keep statusText
    }
    throw new Error(`${res.status} ${detail}`);
  }
  if (res.status === 204) return null as T;
  return res.json();
}

export function mediaUrl(url?: string | null): string | null {
  if (!url) return null;
  return `${API_BASE}${url}`;
}

export function referencePreviewUrl(path?: string | null): string | null {
  if (!path) return null;
  return `${API_BASE}/reference-preview?path=${encodeURIComponent(path)}`;
}

export const api = {
  getOptions: async (modelType?: string | null): Promise<Options> =>
    OptionsSchema.parse(await request(`/options${modelType ? `?model_type=${encodeURIComponent(modelType)}` : ""}`)),

  listVideos: async (): Promise<VideoSummary[]> =>
    VideoSummarySchema.array().parse(await request("/videos")),
  createVideo: async (body: { title: string; template_settings?: Record<string, unknown>; base_prompt?: Record<string, unknown> }): Promise<Video> =>
    VideoSchema.parse(await request("/videos", { method: "POST", body: JSON.stringify(body) })),
  getVideo: async (id: string): Promise<Video> => VideoSchema.parse(await request(`/videos/${id}`)),
  updateVideo: async (id: string, body: Record<string, unknown>): Promise<Video> =>
    VideoSchema.parse(await request(`/videos/${id}`, { method: "PUT", body: JSON.stringify(body) })),
  deleteVideo: (id: string) => request(`/videos/${id}`, { method: "DELETE" }),

  createClip: async (videoId: string, body: Partial<Clip>): Promise<Clip> =>
    ClipSchema.parse(await request(`/videos/${videoId}/clips`, { method: "POST", body: JSON.stringify(body) })),
  updateClip: async (videoId: string, clipId: string, body: Partial<Clip>): Promise<Clip> =>
    ClipSchema.parse(await request(`/videos/${videoId}/clips/${clipId}`, { method: "PUT", body: JSON.stringify(body) })),
  deleteClip: (videoId: string, clipId: string) => request(`/videos/${videoId}/clips/${clipId}`, { method: "DELETE" }),
  reorderClips: (videoId: string, clipIds: string[]) =>
    request(`/videos/${videoId}/clips/reorder`, { method: "PATCH", body: JSON.stringify({ clip_ids: clipIds }) }),
  generateClip: (clipId: string) => request<{ job_id: string; status: string }>(`/clips/${clipId}/generate`, { method: "POST" }),
  analyzeClip: (clipId: string): Promise<QaReport> => request(`/clips/${clipId}/analyze`, { method: "POST" }),
  unloadModel: () => request<{ ok: boolean }>("/unload-model", { method: "POST" }),
  getCharacterImageProviders: async (): Promise<ImageProvider[]> =>
    ImageProviderSchema.array().parse(((await request("/character-images/options")) as { providers: unknown }).providers),
  listActiveJobs: async (): Promise<ActiveJob[]> => ActiveJobSchema.array().parse(await request("/jobs/active")),
  getModelStatus: async (): Promise<ModelStatus> => ModelStatusSchema.parse(await request("/model-status")),
  loadModel: (modelType: string) =>
    request<{ ok: boolean; model_type: string }>("/load-model", { method: "POST", body: JSON.stringify({ model_type: modelType }) }),
  concatVideo: async (videoId: string): Promise<Video> =>
    VideoSchema.parse(await request(`/videos/${videoId}/concat`, { method: "POST" })),

  createCharacter: async (videoId: string, body: Partial<Character>): Promise<Character> =>
    CharacterSchema.parse(await request(`/videos/${videoId}/characters`, { method: "POST", body: JSON.stringify(body) })),
  getCharacter: async (videoId: string, characterId: string): Promise<Character> =>
    CharacterSchema.parse(await request(`/videos/${videoId}/characters/${characterId}`)),
  updateCharacter: async (videoId: string, characterId: string, body: Record<string, unknown>): Promise<Character> =>
    CharacterSchema.parse(await request(`/videos/${videoId}/characters/${characterId}`, { method: "PUT", body: JSON.stringify(body) })),
  deleteCharacter: (videoId: string, characterId: string) => request(`/videos/${videoId}/characters/${characterId}`, { method: "DELETE" }),

  addReference: async (videoId: string, characterId: string, body: { type: string; path: string; note?: string }): Promise<Character> =>
    CharacterSchema.parse(await request(`/videos/${videoId}/characters/${characterId}/references`, { method: "POST", body: JSON.stringify(body) })),
  uploadReference: async (videoId: string, characterId: string, type: string, file: File, note?: string): Promise<Character> => {
    const form = new FormData();
    form.append("type", type);
    form.append("note", note ?? "");
    form.append("file", file);
    const res = await fetch(`${API_BASE}/videos/${videoId}/characters/${characterId}/references/upload`, { method: "POST", body: form });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const data = await res.json();
        detail = data.detail ? JSON.stringify(data.detail) : detail;
      } catch {
        // ignore, keep statusText
      }
      throw new Error(`${res.status} ${detail}`);
    }
    return CharacterSchema.parse(await res.json());
  },
  deleteReference: (videoId: string, characterId: string, referenceId: string) =>
    request(`/videos/${videoId}/characters/${characterId}/references/${referenceId}`, { method: "DELETE" }),
  upscaleReference: (videoId: string, characterId: string, referenceId: string) =>
    request<{ job_id: string; status: string }>(`/videos/${videoId}/characters/${characterId}/references/${referenceId}/upscale`, { method: "POST" }),

  createReferenceVideo: async (videoId: string, characterId: string, body: Record<string, unknown>): Promise<Character> =>
    CharacterSchema.parse(await request(`/videos/${videoId}/characters/${characterId}/reference-videos`, { method: "POST", body: JSON.stringify(body) })),
  updateReferenceVideo: async (videoId: string, characterId: string, referenceVideoId: string, body: Record<string, unknown>): Promise<Character> =>
    CharacterSchema.parse(await request(`/videos/${videoId}/characters/${characterId}/reference-videos/${referenceVideoId}`, { method: "PUT", body: JSON.stringify(body) })),
  deleteReferenceVideo: (videoId: string, characterId: string, referenceVideoId: string) =>
    request(`/videos/${videoId}/characters/${characterId}/reference-videos/${referenceVideoId}`, { method: "DELETE" }),
  generateReferenceVideo: (characterId: string, referenceVideoId: string) =>
    request<{ job_id: string; status: string }>(`/characters/${characterId}/reference-videos/${referenceVideoId}/generate`, { method: "POST" }),
  upscaleReferenceVideo: (characterId: string, referenceVideoId: string) =>
    request<{ job_id: string; status: string }>(`/characters/${characterId}/reference-videos/${referenceVideoId}/upscale`, { method: "POST" }),
  captureReferenceFrame: async (characterId: string, referenceVideoId: string, body: { timestamp: number; source?: string; note?: string }): Promise<Character> =>
    CharacterSchema.parse(await request(`/characters/${characterId}/reference-videos/${referenceVideoId}/capture-frame`, { method: "POST", body: JSON.stringify(body) })),

  generateCharacterImages: async (
    videoId: string,
    characterId: string,
    body: { prompt: string; source_paths: string[]; seed: number; count: number; aspect: string }
  ): Promise<Character> =>
    CharacterSchema.parse(await request(`/videos/${videoId}/characters/${characterId}/generated-images`, { method: "POST", body: JSON.stringify(body) })),
  deleteCharacterImage: (videoId: string, characterId: string, imageId: string) =>
    request(`/videos/${videoId}/characters/${characterId}/generated-images/${imageId}`, { method: "DELETE" }),
  useCharacterImageAsReference: async (videoId: string, characterId: string, imageId: string, note = ""): Promise<Character> =>
    CharacterSchema.parse(
      await request(`/videos/${videoId}/characters/${characterId}/generated-images/${imageId}/use-as-reference`, { method: "POST", body: JSON.stringify({ note }) })
    ),

  listPromptTags: async (): Promise<PromptTag[]> => PromptTagSchema.array().parse(await request("/prompt-tags")),
  createPromptTag: async (body: { name: string; key: string; body: string }): Promise<PromptTag> =>
    PromptTagSchema.parse(await request("/prompt-tags", { method: "POST", body: JSON.stringify(body) })),
  updatePromptTag: async (id: string, body: Partial<{ name: string; key: string; body: string }>): Promise<PromptTag> =>
    PromptTagSchema.parse(await request(`/prompt-tags/${id}`, { method: "PUT", body: JSON.stringify(body) })),
  deletePromptTag: (id: string) => request(`/prompt-tags/${id}`, { method: "DELETE" }),

  listAnimateJobs: async (): Promise<AnimateJob[]> => AnimateJobSchema.array().parse(await request("/animate-jobs")),
  createAnimateJob: async (body: Partial<AnimateJob>): Promise<AnimateJob> =>
    AnimateJobSchema.parse(await request("/animate-jobs", { method: "POST", body: JSON.stringify(body) })),
  updateAnimateJob: async (id: string, body: Partial<AnimateJob>): Promise<AnimateJob> =>
    AnimateJobSchema.parse(await request(`/animate-jobs/${id}`, { method: "PUT", body: JSON.stringify(body) })),
  deleteAnimateJob: (id: string) => request(`/animate-jobs/${id}`, { method: "DELETE" }),
  generateAnimateJob: (id: string) => request<{ job_id: string; status: string }>(`/animate-jobs/${id}/generate`, { method: "POST" }),
};
