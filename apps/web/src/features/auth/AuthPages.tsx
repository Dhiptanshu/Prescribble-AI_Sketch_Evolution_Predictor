import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../../lib/api";
import { useAuth, useAuthActions } from "../../lib/auth";

function useRedirect() {
  const { state } = useLocation() as { state: { from?: string } | null };
  return state?.from ?? "/studio";
}

function Gate({ children }: { children: React.ReactNode }) {
  const { user, backend, loading } = useAuth();
  const to = useRedirect();
  if (user) return <Navigate to={to} replace />;
  if (!loading && backend === "offline") {
    return <div className="auth-wrap card"><h1>Accounts unavailable</h1><p className="sub">This copy runs without a backend (offline mode). The Studio works fully; saving and accounts need the server.</p><Link className="btn primary" to="/studio">Open the Studio</Link></div>;
  }
  return <>{children}</>;
}

function Field({ id, label, error, ...rest }: { id: string; label: string; error?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} className="input" aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined} {...rest} />
      {error && <span id={`${id}-err`} className="field-error">{error}</span>}
    </div>
  );
}

function errorText(e: unknown): { message: string; fields: Record<string, string> } {
  if (e instanceof ApiError) return { message: e.code === "validation_error" ? "" : e.message, fields: e.fieldErrors() };
  return { message: "Could not reach the server. Check your connection and try again.", fields: {} };
}

export function LoginPage() {
  const { login } = useAuthActions();
  const navigate = useNavigate();
  const to = useRedirect();
  const [email, setEmail] = useState(""), [password, setPassword] = useState("");
  const err = login.error ? errorText(login.error) : null;
  const submit = (e: FormEvent) => { e.preventDefault(); login.mutate({ email, password }, { onSuccess: () => navigate(to, { replace: true }) }); };
  return (
    <Gate>
      <div className="auth-wrap card">
        <h1>Welcome back</h1><p className="sub">Sign in to see your drawings and stats.</p>
        <form className="form" onSubmit={submit}>
          <Field id="email" label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} error={err?.fields.email} />
          <Field id="password" label="Password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} error={err?.fields.password} />
          {err?.message && <div className="toast bad" role="alert">{err.message}</div>}
          <button className="btn primary lg" disabled={login.isPending}>{login.isPending ? "Signing in…" : "Sign in"}</button>
        </form>
        <p className="meta" style={{ marginTop: 14 }}>New here? <Link to="/register">Create an account</Link></p>
      </div>
    </Gate>
  );
}

export function RegisterPage() {
  const { register } = useAuthActions();
  const navigate = useNavigate();
  const to = useRedirect();
  const [name, setName] = useState(""), [email, setEmail] = useState(""), [password, setPassword] = useState("");
  const err = register.error ? errorText(register.error) : null;
  const submit = (e: FormEvent) => { e.preventDefault(); register.mutate({ display_name: name, email, password }, { onSuccess: () => navigate(to, { replace: true }) }); };
  return (
    <Gate>
      <div className="auth-wrap card">
        <h1>Create your account</h1><p className="sub">Free. Your drawings stay private; saving is always your choice.</p>
        <form className="form" onSubmit={submit}>
          <Field id="name" label="Display name" autoComplete="nickname" required maxLength={40} value={name} onChange={(e) => setName(e.target.value)} error={err?.fields.display_name} />
          <Field id="email" label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} error={err?.fields.email} />
          <Field id="password" label="Password (8+ characters)" type="password" autoComplete="new-password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} error={err?.fields.password} />
          {err?.message && <div className="toast bad" role="alert">{err.message}</div>}
          <button className="btn primary lg" disabled={register.isPending}>{register.isPending ? "Creating…" : "Create account"}</button>
        </form>
        <p className="meta" style={{ marginTop: 14 }}>Already have an account? <Link to="/login">Sign in</Link></p>
      </div>
    </Gate>
  );
}
