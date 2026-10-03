import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../../lib/api";
import { liveUrl, tokenHeader, type RoomState } from "../../lib/rooms";

export type LinkState = "connecting" | "live" | "reconnecting";
export type LiveState = RoomState & { receivedAt: number };

/**
 * The room's state, kept fresh by the server's WebSocket pushes. The socket reconnects with a short back-off; every few seconds the state is
 * also re-read over plain HTTP, so a flaky classroom wifi degrades to polling instead of a frozen screen.
 * `token` is a student's room token; teachers authenticate with their session cookie.
 */
export function useRoomLive(roomId: number, token: string | null) {
  const [state, setState] = useState<LiveState | null>(null);
  const [link, setLink] = useState<LinkState>("connecting");
  const [error, setError] = useState<ApiError | null>(null);

  const accept = useCallback((s: RoomState) => { setError(null); setState({ ...s, receivedAt: Date.now() }); }, []);

  useEffect(() => {
    let alive = true, tries = 0;
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const refetch = async () => {
      try { const s = await api<RoomState>(`/rooms/${roomId}/state`, { headers: tokenHeader(token) }); if (alive) accept(s); }
      catch (e) { if (alive && e instanceof ApiError) setError(e); }
    };
    const connect = () => {
      ws = new WebSocket(liveUrl(window.location, roomId));
      ws.onopen = () => { if (token) ws?.send(JSON.stringify({ token })); };
      ws.onmessage = (ev) => {
        tries = 0; setLink("live");
        try { accept(JSON.parse(String(ev.data)) as RoomState); } catch { /* a malformed push is replaced by the next one */ }
      };
      ws.onclose = (ev) => {
        if (!alive) return;
        if (ev.code === 4401 || ev.code === 4404) { void refetch(); return; }       // refused or deleted: the HTTP answer says why
        setLink("reconnecting");
        retry = setTimeout(connect, Math.min(5000, 400 * 2 ** tries++));
      };
    };

    void refetch();
    connect();
    const poll = setInterval(() => void refetch(), 5000);
    return () => { alive = false; ws?.close(); clearTimeout(retry); clearInterval(poll); };
  }, [roomId, token, accept]);

  return { state, link, error };
}
