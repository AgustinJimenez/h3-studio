import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "./api";
import type { Character, Clip, AnimateJob } from "../schemas";

const ACTIVE_STATUSES = new Set(["queued", "running"]);

function videoHasActiveWork(video: { clips: Clip[]; characters: Character[] } | undefined): boolean {
  if (!video) return false;
  if (video.clips.some((c) => ACTIVE_STATUSES.has(c.status))) return true;
  for (const character of video.characters) {
    if (character.reference_videos.some((rv) => ACTIVE_STATUSES.has(rv.status) || ACTIVE_STATUSES.has(rv.upscale?.status ?? "none"))) return true;
    if (character.references.some((r) => ACTIVE_STATUSES.has(r.upscale?.status ?? "none"))) return true;
  }
  return false;
}

export function useVideos() {
  return useQuery({ queryKey: ["videos"], queryFn: api.listVideos });
}

export function useVideo(id: string) {
  return useQuery({
    queryKey: ["video", id],
    queryFn: () => api.getVideo(id),
    // Polls while anything in this video is queued/running, stops once idle —
    // replaces the manual setInterval+useEffect pattern every page hand-rolled before.
    refetchInterval: (query) => (videoHasActiveWork(query.state.data) ? 4000 : false),
  });
}

export function useCharacter(videoId: string, characterId: string) {
  return useQuery({
    queryKey: ["character", videoId, characterId],
    queryFn: () => api.getCharacter(videoId, characterId),
    refetchInterval: (query) => {
      const c = query.state.data;
      if (!c) return false;
      const active =
        c.reference_videos.some((rv) => ACTIVE_STATUSES.has(rv.status) || ACTIVE_STATUSES.has(rv.upscale?.status ?? "none")) ||
        c.references.some((r) => ACTIVE_STATUSES.has(r.upscale?.status ?? "none"));
      return active ? 4000 : false;
    },
  });
}

export function useOptions(modelType?: string | null) {
  return useQuery({ queryKey: ["options", modelType ?? null], queryFn: () => api.getOptions(modelType) });
}

export function usePromptTags() {
  return useQuery({ queryKey: ["promptTags"], queryFn: api.listPromptTags });
}

function useInvalidatePromptTags() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["promptTags"] });
}

export function useCreatePromptTag() {
  const invalidate = useInvalidatePromptTags();
  return useMutation({
    mutationFn: (body: { name: string; key: string; body: string }) => api.createPromptTag(body),
    onSuccess: invalidate,
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useUpdatePromptTag() {
  const invalidate = useInvalidatePromptTags();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<{ name: string; key: string; body: string }> }) => api.updatePromptTag(id, body),
    onSuccess: invalidate,
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useDeletePromptTag() {
  const invalidate = useInvalidatePromptTags();
  return useMutation({
    mutationFn: (id: string) => api.deletePromptTag(id),
    onSuccess: invalidate,
    onError: (err: Error) => toast.error(err.message),
  });
}

function useInvalidateVideo(videoId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["video", videoId] });
    qc.invalidateQueries({ queryKey: ["videos"] });
  };
}

export function useUpdateVideo(videoId: string) {
  const invalidate = useInvalidateVideo(videoId);
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.updateVideo(videoId, body),
    onSuccess: invalidate,
  });
}

export function useCreateClip(videoId: string) {
  const invalidate = useInvalidateVideo(videoId);
  return useMutation({
    mutationFn: (body: Partial<Clip>) => api.createClip(videoId, body),
    onSuccess: invalidate,
  });
}

export function useUpdateClip(videoId: string) {
  const invalidate = useInvalidateVideo(videoId);
  return useMutation({
    mutationFn: ({ clipId, body }: { clipId: string; body: Partial<Clip> }) => api.updateClip(videoId, clipId, body),
    onSuccess: invalidate,
  });
}

export function useDeleteClip(videoId: string) {
  const invalidate = useInvalidateVideo(videoId);
  return useMutation({
    mutationFn: (clipId: string) => api.deleteClip(videoId, clipId),
    onSuccess: invalidate,
  });
}

export function useReorderClips(videoId: string) {
  const invalidate = useInvalidateVideo(videoId);
  return useMutation({
    mutationFn: (clipIds: string[]) => api.reorderClips(videoId, clipIds),
    onSuccess: invalidate,
  });
}

export function useGenerateClip(videoId: string) {
  const invalidate = useInvalidateVideo(videoId);
  return useMutation({
    mutationFn: (clipId: string) => api.generateClip(clipId),
    onSuccess: () => {
      invalidate();
      toast.success("Clip generation queued");
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useAnalyzeClip(videoId: string) {
  const invalidate = useInvalidateVideo(videoId);
  return useMutation({
    mutationFn: (clipId: string) => api.analyzeClip(clipId),
    onSuccess: () => {
      invalidate();
      toast.success("Analysis complete");
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useUnloadModel() {
  return useMutation({
    mutationFn: () => api.unloadModel(),
    onSuccess: () => toast.success("Model unloaded"),
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useConcatVideo(videoId: string) {
  const invalidate = useInvalidateVideo(videoId);
  return useMutation({
    mutationFn: () => api.concatVideo(videoId),
    onSuccess: () => {
      invalidate();
      toast.success("Clips joined");
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

function useInvalidateCharacter(videoId: string, characterId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["character", videoId, characterId] });
    qc.invalidateQueries({ queryKey: ["video", videoId] });
  };
}

export function useUpdateCharacter(videoId: string, characterId: string) {
  const invalidate = useInvalidateCharacter(videoId, characterId);
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.updateCharacter(videoId, characterId, body),
    onSuccess: invalidate,
  });
}

export function useAddReference(videoId: string, characterId: string) {
  const invalidate = useInvalidateCharacter(videoId, characterId);
  return useMutation({
    mutationFn: (body: { type: string; path: string; note?: string }) => api.addReference(videoId, characterId, body),
    onSuccess: invalidate,
  });
}

export function useDeleteReference(videoId: string, characterId: string) {
  const invalidate = useInvalidateCharacter(videoId, characterId);
  return useMutation({
    mutationFn: (referenceId: string) => api.deleteReference(videoId, characterId, referenceId),
    onSuccess: invalidate,
  });
}

export function useUpscaleReference(videoId: string, characterId: string) {
  const invalidate = useInvalidateCharacter(videoId, characterId);
  return useMutation({
    mutationFn: (referenceId: string) => api.upscaleReference(videoId, characterId, referenceId),
    onSuccess: () => {
      invalidate();
      toast.success("Upscale queued");
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useCreateReferenceVideo(videoId: string, characterId: string) {
  const invalidate = useInvalidateCharacter(videoId, characterId);
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.createReferenceVideo(videoId, characterId, body),
    onSuccess: invalidate,
  });
}

export function useUpdateReferenceVideo(videoId: string, characterId: string) {
  const invalidate = useInvalidateCharacter(videoId, characterId);
  return useMutation({
    mutationFn: ({ referenceVideoId, body }: { referenceVideoId: string; body: Record<string, unknown> }) =>
      api.updateReferenceVideo(videoId, characterId, referenceVideoId, body),
    onSuccess: invalidate,
  });
}

export function useDeleteReferenceVideo(videoId: string, characterId: string) {
  const invalidate = useInvalidateCharacter(videoId, characterId);
  return useMutation({
    mutationFn: (referenceVideoId: string) => api.deleteReferenceVideo(videoId, characterId, referenceVideoId),
    onSuccess: invalidate,
  });
}

export function useGenerateReferenceVideo(videoId: string, characterId: string) {
  const invalidate = useInvalidateCharacter(videoId, characterId);
  return useMutation({
    mutationFn: (referenceVideoId: string) => api.generateReferenceVideo(characterId, referenceVideoId),
    onSuccess: () => {
      invalidate();
      toast.success("Reference video generation queued");
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useUpscaleReferenceVideo(videoId: string, characterId: string) {
  const invalidate = useInvalidateCharacter(videoId, characterId);
  return useMutation({
    mutationFn: (referenceVideoId: string) => api.upscaleReferenceVideo(characterId, referenceVideoId),
    onSuccess: () => {
      invalidate();
      toast.success("Upscale queued");
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

const ANIMATE_ACTIVE_STATUSES = new Set(["queued", "running"]);

export function useAnimateJobs() {
  return useQuery({
    queryKey: ["animateJobs"],
    queryFn: api.listAnimateJobs,
    refetchInterval: (query) => (query.state.data?.some((j) => ANIMATE_ACTIVE_STATUSES.has(j.status)) ? 4000 : false),
  });
}

function useInvalidateAnimateJobs() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["animateJobs"] });
}

export function useCreateAnimateJob() {
  const invalidate = useInvalidateAnimateJobs();
  return useMutation({
    mutationFn: (body: Partial<AnimateJob>) => api.createAnimateJob(body),
    onSuccess: invalidate,
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useUpdateAnimateJob() {
  const invalidate = useInvalidateAnimateJobs();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<AnimateJob> }) => api.updateAnimateJob(id, body),
    onSuccess: invalidate,
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useDeleteAnimateJob() {
  const invalidate = useInvalidateAnimateJobs();
  return useMutation({
    mutationFn: (id: string) => api.deleteAnimateJob(id),
    onSuccess: invalidate,
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useGenerateAnimateJob() {
  const invalidate = useInvalidateAnimateJobs();
  return useMutation({
    mutationFn: (id: string) => api.generateAnimateJob(id),
    onSuccess: () => {
      invalidate();
      toast.success("Animate job queued");
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useCaptureReferenceFrame(videoId: string, characterId: string) {
  const invalidate = useInvalidateCharacter(videoId, characterId);
  return useMutation({
    mutationFn: ({ referenceVideoId, body }: { referenceVideoId: string; body: { timestamp: number; source?: string; note?: string } }) =>
      api.captureReferenceFrame(characterId, referenceVideoId, body),
    onSuccess: () => {
      invalidate();
      toast.success("Frame captured");
    },
    onError: (err: Error) => toast.error(err.message),
  });
}
