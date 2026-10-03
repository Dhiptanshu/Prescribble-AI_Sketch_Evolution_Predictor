import { Link, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../lib/auth";

/** Gate for pages that need an account. Offline builds get an explanation instead of a broken page. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, backend, loading } = useAuth();
  const location = useLocation();
  if (loading || backend === "checking") return <p className="empty">Loading…</p>;
  if (backend === "offline") {
    return (
      <div className="auth-wrap card">
        <h1>Needs the server</h1>
        <p className="sub">This copy runs without a backend (offline mode), so saved drawings and stats are unavailable. The Studio works fully.</p>
        <Link className="btn primary" to="/studio">Open the Studio</Link>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}
