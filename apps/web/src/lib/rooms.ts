// Classroom API: rooms, rounds, the live state and the student's room token. Scores always come from the server.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export type Phase = "lobby" | "drawing" | "collecting" | "results" | "closed";
export interface RoomSummary { id: number; name: string; code: string; closed: boolean; members: number; rounds: number; created_at: string }
export interface Member { nickname: string; online: boolean; submitted: boolean; is_me: boolean }
export interface ResultEntry { rank: number | null; submission_id: number; nickname: string; score: number; recognised_at: number | null; final_guess: string; counted: boolean; is_me: boolean }
export interface RoundResults { round_no: number; target: string; entries: ResultEntry[]; ai: { drawings: number; named: number; median_recognised_at: number | null } }
export interface TotalEntry { rank: number; nickname: string; points: number; rounds_played: number; is_me: boolean }
export interface RoomState {
  role: "teacher" | "student";
  room: { id: number; name: string; code: string; closed: boolean };
  phase: Phase;
  round: { no: number; target: string; duration_s: number; seconds_left: number } | null;
  me: Member | null;
  members: Member[];
  results: RoundResults | null;
  totals: TotalEntry[];
  rounds_finished: number;
}
export interface RoundDrawing { submission_id: number; nickname: string; strokes: [number, number][][] }
export interface Joined { room_id: number; room_name: string; nickname: string; token: string }

// ------------------------------------------------------------------ the student's token (kept in this browser only)

const KEY = (roomId: number) => `prescribble.room.${roomId}`;

export function saveRoomToken(roomId: number, token: string, nickname: string): void {
  try { localStorage.setItem(KEY(roomId), JSON.stringify({ token, nickname })); } catch { /* private mode: the student must rejoin after a reload */ }
}
export function loadRoomToken(roomId: number): { token: string; nickname: string } | null {
  try {
    const v = JSON.parse(localStorage.getItem(KEY(roomId)) ?? "null") as { token?: unknown; nickname?: unknown } | null;
    return v && typeof v.token === "string" && typeof v.nickname === "string" ? { token: v.token, nickname: v.nickname } : null;
  } catch { return null; }
}
export function forgetRoomToken(roomId: number): void {
  try { localStorage.removeItem(KEY(roomId)); } catch { /* nothing stored */ }
}

export const tokenHeader = (token: string | null): Record<string, string> | undefined => (token ? { "X-Room-Token": token } : undefined);

// ------------------------------------------------------------------ teacher

export const useMyRooms = () => useQuery({ queryKey: ["rooms"], queryFn: () => api<RoomSummary[]>("/rooms") });

export function useRoomActions() {
  const qc = useQueryClient();
  const done = () => void qc.invalidateQueries({ queryKey: ["rooms"] });
  return {
    create: useMutation({ mutationFn: (name: string) => api<RoomSummary>("/rooms", { json: { name } }), onSuccess: done }),
    close: useMutation({ mutationFn: (id: number) => api<RoomSummary>(`/rooms/${id}/close`, { method: "POST" }), onSuccess: done }),
    remove: useMutation({ mutationFn: (id: number) => api(`/rooms/${id}`, { method: "DELETE" }), onSuccess: done }),
    start: useMutation({
      mutationFn: (v: { id: number; target: string | null; duration_s: number }) =>
        api<RoomState>(`/rooms/${v.id}/rounds`, { json: { target: v.target, duration_s: v.duration_s } }),
    }),
    end: useMutation({ mutationFn: (id: number) => api<RoomState>(`/rooms/${id}/rounds/current/end`, { method: "POST" }) }),
  };
}

// ------------------------------------------------------------------ student

export const joinRoom = (code: string, nickname: string) => api<Joined>("/rooms/join", { json: { code, nickname } });

export const submitDrawing = (roomId: number, token: string, body: { strokes: [number, number][][]; duration_ms: number | null }) =>
  api<{ submitted: boolean; round_no: number }>(`/rooms/${roomId}/submit`, { json: body, headers: { "X-Room-Token": token } });

export const useRoundDrawings = (roomId: number, no: number | null, token: string | null) =>
  useQuery({
    queryKey: ["rooms", roomId, "drawings", no],
    queryFn: () => api<RoundDrawing[]>(`/rooms/${roomId}/rounds/${no}/drawings`, { headers: tokenHeader(token) }),
    enabled: no != null,
    staleTime: Infinity,
  });

// ------------------------------------------------------------------ live

/** ws:// or wss:// for this page's own origin (the app and the API share one origin in production and via the dev proxy). */
export function liveUrl(loc: Pick<Location, "protocol" | "host">, roomId: number): string {
  return `${loc.protocol === "https:" ? "wss:" : "ws:"}//${loc.host}/api/v1/rooms/${roomId}/live`;
}

/** Seconds still on the round clock, given the value the server sent and when it arrived. */
export function remaining(secondsAtReceipt: number, receivedAtMs: number, nowMs: number): number {
  return Math.max(0, secondsAtReceipt - (nowMs - receivedAtMs) / 1000);
}

export function formatClock(seconds: number): string {
  const s = Math.ceil(Math.max(0, seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
