import { z } from "zod";
import { API_BASE } from "./api";
import { SwapCharacterSchema, SwapProjectSchema, type SwapCastEntry, type SwapProject } from "../schemas";

async function call<T>(path: string, schema: z.ZodType<T>, options?: RequestInit): Promise<T> {
  const isForm = options?.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    headers: isForm || !options?.body ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : detail;
    } catch {
      // keep statusText
    }
    throw new Error(detail);
  }
  return schema.parse(await res.json());
}

const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) });

// Applied to the passes a run submits only (not the project): shorter side in pixels, and the seed.
export type RunOverrides = { size?: number; seed?: number };

export type SwapScenePatch = {
  index: number;
  background_text?: string;
  people?: { id?: string; cast_id: string | null; target_description: string; order: number }[];
};

export type SwapPatch = {
  title?: string;
  settings?: Partial<{ quality: string; width: number; height: number; seed: number }>;
  cast?: Partial<SwapCastEntry>[];
  scenes?: SwapScenePatch[];
};

export const swapApi = {
  list: () => call("/swaps", z.array(SwapProjectSchema)),
  get: (id: string) => call(`/swaps/${id}`, SwapProjectSchema),
  create: (title: string, file: File): Promise<SwapProject> => {
    const form = new FormData();
    form.append("title", title);
    form.append("file", file);
    return call("/swaps", SwapProjectSchema, { method: "POST", body: form });
  },
  remove: async (id: string) => {
    const res = await fetch(`${API_BASE}/swaps/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(res.statusText);
  },
  detect: (id: string) => call(`/swaps/${id}/detect-scenes`, SwapProjectSchema, json("POST")),
  patch: (id: string, body: SwapPatch) => call(`/swaps/${id}`, SwapProjectSchema, json("PATCH", body)),
  setCuts: (id: string, cuts: number[]) => call(`/swaps/${id}/cuts`, SwapProjectSchema, json("PUT", { cuts })),
  confirmScenes: (id: string, confirmed: boolean) => call(`/swaps/${id}/scenes/confirm`, SwapProjectSchema, json("POST", { confirmed })),
  stillPrompt: (id: string, passId: string, view: "front" | "behind") =>
    call(`/swaps/${id}/passes/${passId}/still-prompt?view=${view}`, z.object({ prompt: z.string() })),
  makeStills: (id: string, passId: string, body: { prompt: string; count: number; seed?: number }) =>
    call(`/swaps/${id}/passes/${passId}/stills`, SwapProjectSchema, json("POST", body)),
  deleteStill: (id: string, passId: string, stillId: string) => call(`/swaps/${id}/passes/${passId}/stills/${stillId}`, SwapProjectSchema, json("DELETE")),
  viggle: (id: string, passId: string, body: { still_id: string; size: number; seed?: number }) =>
    call(`/swaps/${id}/passes/${passId}/viggle`, SwapProjectSchema, json("POST", body)),
  merge: (id: string, index: number) => call(`/swaps/${id}/scenes/merge`, SwapProjectSchema, json("POST", { index })),
  plan: (id: string) => call(`/swaps/${id}/plan`, SwapProjectSchema, json("POST")),
  patchPass: (id: string, passId: string, prompt: string) => call(`/swaps/${id}/passes/${passId}`, SwapProjectSchema, json("PATCH", { prompt })),
  run: (id: string, quality: string, sceneIndex: number | null, o: RunOverrides = {}) =>
    call(`/swaps/${id}/run`, SwapProjectSchema, json("POST", { quality, scene_index: sceneIndex, ...o })),
  rerun: (id: string, passId: string, o: RunOverrides = {}) => call(`/swaps/${id}/passes/${passId}/rerun`, SwapProjectSchema, json("POST", o)),
  cancel: (id: string, passId: string) => call(`/swaps/${id}/passes/${passId}/cancel`, SwapProjectSchema, json("POST")),
  useRun: (id: string, passId: string, runId: string) =>
    call(`/swaps/${id}/passes/${passId}/use-run`, SwapProjectSchema, json("POST", { run_id: runId })),
  deleteRun: (id: string, passId: string, runId: string) => call(`/swaps/${id}/passes/${passId}/runs/${runId}`, SwapProjectSchema, json("DELETE")),
  trim: (id: string, passId: string, frames: number) => call(`/swaps/${id}/passes/${passId}/trim`, SwapProjectSchema, json("POST", { frames })),
  assemble: (id: string) => call(`/swaps/${id}/assemble`, SwapProjectSchema, json("POST")),
  characters: () => call("/swap-characters", z.array(SwapCharacterSchema)),
};
