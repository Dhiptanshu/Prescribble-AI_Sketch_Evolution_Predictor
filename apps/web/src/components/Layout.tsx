import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth, useAuthActions } from "../lib/auth";
import { useEngine } from "../lib/engine";
import { useTheme } from "../lib/theme";

export const APP_NAME = "Prescribble";

function Logo() {
  return (
    <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
      <defs><linearGradient id="lg" x1="0" x2="1"><stop stopColor="#7c5cff" /><stop offset="1" stopColor="#22d3ee" /></linearGradient></defs>
      <path d="M5 24c4-14 9-16 12-8s7 6 10-12" fill="none" stroke="url(#lg)" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

function EngineChip() {
  const e = useEngine();
  if (e.status === "loading") return <span className="chip loading"><i className="dot" />loading model…</span>;
  if (e.status === "error") return <span className="chip err" title={e.message}><i className="dot" />model failed to load</span>;
  return <span className="chip ok"><i className="dot" />model ready · runs in your browser</span>;
}

export function Layout() {
  const { user, backend } = useAuth();
  const { logout } = useAuthActions();
  const { theme, toggle } = useTheme();
  return (
    <div className="shell">
      <header className="nav">
        <Link to="/" className="brand"><Logo />{APP_NAME}</Link>
        <nav className="nav-links" aria-label="Main">
          <NavLink to="/studio">Studio</NavLink>
          {backend === "online" && <NavLink to="/challenge">Challenge</NavLink>}
          {user && <NavLink to="/gallery">Gallery</NavLink>}
          {user && <NavLink to="/stats">Stats</NavLink>}
        </nav>
        <div className="nav-right">
          <EngineChip />
          {backend === "offline" && <span className="chip" title="No backend reachable: accounts are unavailable, the Studio works normally."><i className="dot" />offline mode</span>}
          {backend === "online" && (user ? (
            <>
              <NavLink className="who" to="/settings" aria-label="Account settings">{user.display_name}</NavLink>
              <button className="btn" onClick={() => logout.mutate()} disabled={logout.isPending}>Sign out</button>
            </>
          ) : (
            <>
              <Link className="btn ghost" to="/login">Sign in</Link>
              <Link className="btn primary" to="/register">Create account</Link>
            </>
          ))}
          <button className="icon-btn" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} title="Toggle theme">◐</button>
        </div>
      </header>
      <main className="main"><Outlet /></main>
      <footer className="footer">{APP_NAME}: your drawings are analysed in your browser and never leave your device unless you save them.</footer>
    </div>
  );
}
