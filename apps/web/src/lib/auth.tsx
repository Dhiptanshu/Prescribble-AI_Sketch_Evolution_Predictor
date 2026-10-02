import { createContext, useContext, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, NetworkError, api } from "./api";

export interface User {
  id: number;
  email: string;
  display_name: string;
  is_admin: boolean;
  consent_training: boolean;
  created_at: string;
}

/** "online": API reachable. "offline": no backend (static/lab build): the Studio still works, accounts do not. */
export type Backend = "checking" | "online" | "offline";

interface AuthState {
  user: User | null;
  backend: Backend;
  loading: boolean;
}

const AuthContext = createContext<AuthState>({ user: null, backend: "checking", loading: true });

export function AuthProvider({ children }: { children: ReactNode }) {
  const me = useQuery<{ user: User | null; backend: Backend }>({
    queryKey: ["me"],
    retry: false,
    staleTime: 60_000,
    queryFn: async () => {
      try {
        return { user: await api<User>("/me"), backend: "online" };
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return { user: null, backend: "online" };
        if (e instanceof NetworkError) return { user: null, backend: "offline" };
        throw e;
      }
    },
  });
  const state: AuthState = { user: me.data?.user ?? null, backend: me.data?.backend ?? "checking", loading: me.isLoading };
  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);

export function useAuthActions() {
  const qc = useQueryClient();
  const setUser = (user: User | null) => qc.setQueryData(["me"], { user, backend: "online" });
  const login = useMutation({ mutationFn: (b: { email: string; password: string }) => api<User>("/auth/login", { json: b }), onSuccess: setUser });
  const register = useMutation({
    mutationFn: (b: { email: string; password: string; display_name: string }) => api<User>("/auth/register", { json: b }),
    onSuccess: setUser,
  });
  const logout = useMutation({ mutationFn: () => api("/auth/logout", { method: "POST" }), onSuccess: () => {
      setUser(null);
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });   // drop every cached per-user query, keep the live session query
    },
  });
  return { login, register, logout };
}
