// Typed access to the saved-drawings API (react-query). Every cache entry is per-user and dropped on sign-out (see lib/auth.tsx).
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Stroke } from "@prescribble/engine/pipeline";
import { api } from "./api";

export interface Drawing {
  id: number;
  created_at: string;
  label: string | null;
  ai_guess: string;
  ai_confidence: number;
  recognised_at: number | null;
  mode: "free" | "challenge" | "teach";
  label_confirmed: boolean;
  input_type: "mouse" | "touch" | "pen" | null;
  model_version: string;
  strokes: Stroke[];
  n_strokes: number;
  ink: number;
  duration_ms: number | null;
  share_token: string | null;
}

export interface DrawingInput {
  strokes: Stroke[];
  label: string | null;
  ai_guess: string;
  ai_confidence: number;
  recognised_at: number | null;
  mode: "free" | "challenge" | "teach";
  duration_ms: number | null;
  model_version: string;
  label_confirmed?: boolean;
  input_type?: "mouse" | "touch" | "pen" | null;
}

interface Page { items: Drawing[]; next_before: number | null }

export interface PublicDrawing {
  strokes: Stroke[];
  label: string | null;
  ai_guess: string;
  ai_confidence: number;
  recognised_at: number | null;
  created_at: string;
  model_version: string;
  author: string;
}

export interface Stats {
  total: number;
  labelled: number;
  ai_final_correct: number;
  ai_ever_recognised: number;
  avg_recognised_at: number | null;
  early_rate: number | null;
  by_class: { label: string; count: number; avg_recognised_at: number | null }[];
  streak: { current: number; longest: number };
  activity: { date: string; count: number }[];
  first_drawing_at: string | null;
  last_drawing_at: string | null;
}

export const useDrawings = () =>
  useInfiniteQuery({
    queryKey: ["drawings"],
    initialPageParam: undefined as number | undefined,
    queryFn: ({ pageParam }) => api<Page>(`/drawings?limit=24${pageParam ? `&before=${pageParam}` : ""}`),
    getNextPageParam: (last) => last.next_before ?? undefined,
  });

export const useDrawing = (id: number) => useQuery({ queryKey: ["drawing", id], queryFn: () => api<Drawing>(`/drawings/${id}`), retry: false });

export const useStats = () => useQuery({ queryKey: ["stats"], queryFn: () => api<Stats>("/me/stats") });

export const usePublicDrawing = (token: string) =>
  useQuery({ queryKey: ["public", token], queryFn: () => api<PublicDrawing>(`/public/drawings/${token}`), retry: false });

export function useDrawingActions() {
  const qc = useQueryClient();
  const refresh = (id?: number) => {
    void qc.invalidateQueries({ queryKey: ["drawings"] });
    void qc.invalidateQueries({ queryKey: ["stats"] });
    if (id !== undefined) void qc.invalidateQueries({ queryKey: ["drawing", id] });
  };
  return {
    save: useMutation({ mutationFn: (d: DrawingInput) => api<Drawing>("/drawings", { json: d }), onSuccess: (d) => refresh(d.id) }),
    relabel: useMutation({
      mutationFn: ({ id, label }: { id: number; label: string | null }) => api<Drawing>(`/drawings/${id}`, { method: "PATCH", json: { label } }),
      onSuccess: (d) => refresh(d.id),
    }),
    remove: useMutation({ mutationFn: (id: number) => api(`/drawings/${id}`, { method: "DELETE" }), onSuccess: (_, id) => { refresh(); qc.removeQueries({ queryKey: ["drawing", id] }); } }),
    share: useMutation({ mutationFn: (id: number) => api<{ token: string }>(`/drawings/${id}/share`, { method: "POST" }), onSuccess: (_, id) => refresh(id) }),
    unshare: useMutation({ mutationFn: (id: number) => api(`/drawings/${id}/share`, { method: "DELETE" }), onSuccess: (_, id) => refresh(id) }),
  };
}

/** Public URL for a share token on the current origin. */
export const shareUrl = (token: string) => `${location.origin}/d/${token}`;
