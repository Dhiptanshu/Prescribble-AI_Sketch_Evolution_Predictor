import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../../lib/api";
import { useAuth, useAuthActions } from "../../lib/auth";

function Toggle({ id, label, hint, checked, disabled, onChange }: { id: string; label: string; hint: string; checked: boolean; disabled?: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="setting">
      <label className="switch" htmlFor={id}>
        <input id={id} type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
        <i /> {label}
      </label>
      <p className="meta">{hint}</p>
    </div>
  );
}

/** Profile, privacy, data export and account deletion. */
export function SettingsPage() {
  const { user } = useAuth();
  const { updateProfile, deleteAccount, clearSession } = useAuthActions();
  const navigate = useNavigate();
  const [name, setName] = useState(user?.display_name ?? "");
  const [password, setPassword] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  if (!user) return null;

  const saveName = (e: FormEvent) => { e.preventDefault(); if (name.trim() && name.trim() !== user.display_name) updateProfile.mutate({ display_name: name }); };
  const nameError = updateProfile.error instanceof ApiError ? updateProfile.error.fieldErrors().display_name ?? updateProfile.error.message : null;

  async function exportData() {
    setExportError(null);
    try {
      const data = await api<unknown>("/me/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "prescribble-my-data.json" });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
    } catch {
      setExportError("Could not download your data. Try again in a moment.");
    }
  }

  return (
    <section aria-label="Settings" className="settings">
      <div className="page-head"><h1>Settings</h1><span className="meta">{user.email}</span></div>

      <section className="card">
        <div className="card-head"><h2>Profile</h2></div>
        <form className="form" onSubmit={saveName}>
          <div className="field">
            <label htmlFor="display-name">Display name</label>
            <input id="display-name" className="input" maxLength={40} value={name} onChange={(e) => setName(e.target.value)} aria-invalid={!!nameError} />
            {nameError && <span className="field-error">{nameError}</span>}
          </div>
          <div><button className="btn primary" disabled={updateProfile.isPending || !name.trim() || name.trim() === user.display_name}>Save name</button></div>
        </form>
      </section>

      <section className="card">
        <div className="card-head"><h2>Privacy</h2></div>
        <Toggle id="show-lb" label="Show my name on the leaderboard" checked={user.show_on_leaderboard} disabled={updateProfile.isPending}
          hint="When off, your scores still count and keep their rank, but other players see “Anonymous”." onChange={(v) => updateProfile.mutate({ show_on_leaderboard: v })} />
        <Toggle id="train" label="Allow my saved drawings to help improve the model" checked={user.consent_training} disabled={updateProfile.isPending}
          hint="Off by default. Nothing is used for training unless you turn this on, and you can turn it off any time." onChange={(v) => updateProfile.mutate({ consent_training: v })} />
      </section>

      <section className="card">
        <div className="card-head"><h2>Your data</h2></div>
        <p className="meta" style={{ marginBottom: 12 }}>Download everything we hold about you (account and saved drawings) as a JSON file.</p>
        <button className="btn" onClick={() => void exportData()}>Download my data</button>
        {exportError && <div className="toast bad" role="alert" style={{ marginTop: 10 }}>{exportError}</div>}
      </section>

      <section className="card">
        <div className="card-head"><h2>Delete account</h2></div>
        <p className="meta" style={{ marginBottom: 12 }}>Permanently deletes your account, saved drawings, share links and challenge scores. This cannot be undone.</p>
        {confirming ? (
          <form className="form" onSubmit={(e) => { e.preventDefault(); deleteAccount.mutate(password, { onSuccess: () => { navigate("/", { replace: true }); clearSession(); } }); }}>
            <div className="field">
              <label htmlFor="confirm-password">Type your password to confirm</label>
              <input id="confirm-password" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            {deleteAccount.error && <div className="toast bad" role="alert">{deleteAccount.error instanceof ApiError ? deleteAccount.error.message : "Could not reach the server."}</div>}
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn" style={{ borderColor: "var(--bad)" }} disabled={!password || deleteAccount.isPending}>Delete everything</button>
              <button type="button" className="btn ghost" onClick={() => { setConfirming(false); setPassword(""); deleteAccount.reset(); }}>Cancel</button>
            </div>
          </form>
        ) : (
          <button className="btn" onClick={() => setConfirming(true)}>Delete my account</button>
        )}
      </section>
    </section>
  );
}
