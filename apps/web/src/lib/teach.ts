// Teach the AI: ask for the word the model has the fewest examples of, and save the person's drawing of it (consented, confirmed).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export interface TeachSummary { mine: number; ready_total: number; classes_covered: number; classes_total: number | null; consent: boolean; model_version: string }
export interface TeachNext { target: string; summary: TeachSummary }

export const useTeachSummary = () => useQuery({ queryKey: ["teach", "summary"], queryFn: () => api<TeachSummary>("/teach/summary") });

export function useTeachActions() {
  const qc = useQueryClient();
  const refresh = () => void qc.invalidateQueries({ queryKey: ["teach"] });
  return {
    next: useMutation({ mutationFn: (avoid: string | null) => api<TeachNext>(`/teach/next${avoid ? `?avoid=${encodeURIComponent(avoid)}` : ""}`) }),
    withdraw: useMutation({ mutationFn: () => api<{ deleted: number }>("/teach/contributions", { method: "DELETE" }), onSuccess: refresh }),
    refresh,
  };
}
