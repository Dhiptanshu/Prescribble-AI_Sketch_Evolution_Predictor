// Developer platform API: keys, usage, model info and admin metrics (react-query).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export interface ApiKeyInfo {
  id: number;
  name: string;
  prefix: string;
  daily_limit: number;
  used_today: number;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}
export interface CreatedKey extends ApiKeyInfo { key: string }
export interface UsageDay { day: string; requests: number; errors: number; avg_ms: number | null }
export interface Limits { requests_per_minute: number; requests_per_day: number; max_strokes: number; max_points: number; max_active_keys: number; top_k_max: number }
export interface ModelInfo { version: string; classes: string[]; limits: Limits }

export interface AdminMetrics {
  users: { total: number; last_7_days: number };
  drawings: { total: number; last_7_days: number };
  challenge_today: { players: number; attempts: number; flagged: number };
  api: {
    active_keys: number;
    requests_today: number;
    requests_7d: number;
    errors_7d: number;
    avg_ms_7d: number | null;
    daily: UsageDay[];
    top_keys: { prefix: string; name: string; owner: string; requests_7d: number }[];
  };
  model_version: string;
  model_loaded: boolean;
  training: { ready: number; classes_covered: number; classes_total: number | null; contributors: number; by_input_type: Record<string, number> };
}

export const useModelInfo = () => useQuery({ queryKey: ["model"], queryFn: () => api<ModelInfo>("/model"), staleTime: Infinity, retry: false });

export const useKeys = (enabled: boolean) => useQuery({ queryKey: ["keys"], queryFn: () => api<ApiKeyInfo[]>("/keys"), enabled });

export const useKeyUsage = (id: number | null) =>
  useQuery({ queryKey: ["keys", id, "usage"], queryFn: () => api<UsageDay[]>(`/keys/${id}/usage?days=14`), enabled: id !== null });

export function useKeyActions() {
  const qc = useQueryClient();
  const refresh = () => void qc.invalidateQueries({ queryKey: ["keys"] });
  return {
    create: useMutation({ mutationFn: (name: string) => api<CreatedKey>("/keys", { json: { name } }), onSuccess: refresh }),
    revoke: useMutation({ mutationFn: (id: number) => api(`/keys/${id}`, { method: "DELETE" }), onSuccess: refresh }),
  };
}

export const useAdminMetrics = () => useQuery({ queryKey: ["admin", "metrics"], queryFn: () => api<AdminMetrics>("/admin/metrics"), retry: false });
