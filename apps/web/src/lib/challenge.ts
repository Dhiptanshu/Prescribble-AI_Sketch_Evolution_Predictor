// Daily challenge API (react-query). Scores always come from the server; the browser only displays them.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Stroke } from "@prescribble/engine/pipeline";
import { api } from "./api";

export interface AttemptSummary { attempt_no: number; score: number; recognised_at: number | null; counted: boolean; created_at: string }
export interface Today {
  day: string;
  target: string;
  model_version: string;
  attempts_max: number;
  seconds_left: number;
  me: { attempts_used: number; best_score: number | null; attempts: AttemptSummary[] } | null;
}
export interface TimelineStep { fraction: number; top1: string; top1_p: number; p_target: number }
export interface AttemptResult {
  attempt_no: number;
  attempts_left: number;
  score: number;
  recognised_at: number | null;
  confidence_at_hit: number | null;
  final_guess: string;
  final_confidence: number;
  counted: boolean;
  best_score: number | null;
  rank: number | null;
  participants: number;
  timeline: TimelineStep[];
}
export interface LeaderboardEntry { rank: number; name: string; score: number; recognised_at: number | null; is_me: boolean }
export interface Leaderboard { day: string; target: string; participants: number; entries: LeaderboardEntry[]; me: LeaderboardEntry | null }
export interface ChallengeStats {
  played: number;
  best_score: number | null;
  average_best: number | null;
  streak: { current: number; longest: number };
  history: { day: string; target: string; best_score: number }[];
}

export const useToday = () => useQuery({ queryKey: ["challenge", "today"], queryFn: () => api<Today>("/challenge/today"), staleTime: 30_000 });

export const useLeaderboard = (day?: string) =>
  useQuery({
    queryKey: ["challenge", "leaderboard", day ?? "today"],
    queryFn: () => api<Leaderboard>(`/challenge/leaderboard${day ? `?day=${day}` : ""}`),
    retry: false,
  });

export const useChallengeStats = (enabled: boolean) =>
  useQuery({ queryKey: ["challenge", "me"], queryFn: () => api<ChallengeStats>("/challenge/me"), enabled });

export function useSubmitAttempt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { strokes: Stroke[]; duration_ms: number | null }) => api<AttemptResult>("/challenge/attempts", { json: b }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["challenge"] }),
  });
}

/** The calendar day before an ISO date (UTC), for the "Yesterday" leaderboard tab. */
export function previousDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

export function formatCountdown(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
}
