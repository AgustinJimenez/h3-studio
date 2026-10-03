import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { swapApi, type RunOverrides, type SwapPatch } from "./swapApi";
import type { SwapProject } from "../schemas";

const ACTIVE = new Set(["queued", "running"]);
const hasActive = (p: SwapProject | undefined) => !!p && p.passes.some((x) => ACTIVE.has(x.status));

export function useSwaps() {
  return useQuery({
    queryKey: ["swaps"],
    queryFn: swapApi.list,
    refetchInterval: (q) => (q.state.data?.some(hasActive) ? 4000 : false),
  });
}

export function useSwap(id: string) {
  return useQuery({
    queryKey: ["swap", id],
    queryFn: () => swapApi.get(id),
    refetchInterval: (q) => (hasActive(q.state.data) ? 4000 : false),
  });
}

export function useSwapCharacters() {
  return useQuery({ queryKey: ["swapCharacters"], queryFn: swapApi.characters });
}

function useSwapMutation<V>(id: string | null, fn: (v: V) => Promise<SwapProject | void>, ok?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      if (data && id) qc.setQueryData(["swap", id], data);
      qc.invalidateQueries({ queryKey: ["swaps"] });
      qc.invalidateQueries({ queryKey: ["activeJobs"] });
      if (ok) toast.success(ok);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export const useCreateSwap = () => useSwapMutation<{ title: string; file: File }>(null, (v) => swapApi.create(v.title, v.file));
export const useDeleteSwap = () => useSwapMutation<string>(null, (id) => swapApi.remove(id));
export const useDetectScenes = (id: string) => useSwapMutation<void>(id, () => swapApi.detect(id), "Scenes detected");
export const usePatchSwap = (id: string) => useSwapMutation<SwapPatch>(id, (b) => swapApi.patch(id, b));
export const useSetCuts = (id: string) => useSwapMutation<number[]>(id, (c) => swapApi.setCuts(id, c), "Scenes updated");
export const useConfirmScenes = (id: string) => useSwapMutation<boolean>(id, (c) => swapApi.confirmScenes(id, c));
export const useMakeStills = (id: string) =>
  useSwapMutation<{ passId: string; prompt: string; count: number; seed?: number }>(
    id,
    (v) => swapApi.makeStills(id, v.passId, { prompt: v.prompt, count: v.count, seed: v.seed }),
    "Making stills",
  );
export const useDeleteStill = (id: string) => useSwapMutation<{ passId: string; stillId: string }>(id, (v) => swapApi.deleteStill(id, v.passId, v.stillId));
export const useViggleRun = (id: string) =>
  useSwapMutation<{ passId: string; stillId: string; size: number; seed?: number }>(
    id,
    (v) => swapApi.viggle(id, v.passId, { still_id: v.stillId, size: v.size, seed: v.seed }),
    "Queued with Viggle",
  );
export const useMergeScenes = (id: string) => useSwapMutation<number>(id, (i) => swapApi.merge(id, i));
export const usePlanSwap = (id: string) => useSwapMutation<void>(id, () => swapApi.plan(id), "Plan built");
export const usePatchPass = (id: string) =>
  useSwapMutation<{ passId: string; prompt: string }>(id, (v) => swapApi.patchPass(id, v.passId, v.prompt), "Prompt saved");
export const useRunSwap = (id: string) =>
  useSwapMutation<{ quality: string; sceneIndex: number | null; overrides?: RunOverrides }>(
    id,
    (v) => swapApi.run(id, v.quality, v.sceneIndex, v.overrides),
    "Queued",
  );
export const useRerunPass = (id: string) =>
  useSwapMutation<{ passId: string; overrides?: RunOverrides }>(id, (v) => swapApi.rerun(id, v.passId, v.overrides), "Queued");
export const useCancelPass = (id: string) => useSwapMutation<string>(id, (p) => swapApi.cancel(id, p));
export const useAssembleSwap = (id: string) => useSwapMutation<void>(id, () => swapApi.assemble(id), "Video assembled");
export const useUseRun = (id: string) =>
  useSwapMutation<{ passId: string; runId: string }>(id, (v) => swapApi.useRun(id, v.passId, v.runId), "Now used in the final video");
export const useDeleteRun = (id: string) => useSwapMutation<{ passId: string; runId: string }>(id, (v) => swapApi.deleteRun(id, v.passId, v.runId), "Run deleted");
export const useTrimPass = (id: string) => useSwapMutation<{ passId: string; frames: number }>(id, (v) => swapApi.trim(id, v.passId, v.frames), "Trimmed");
