import { Activity, LockKeyhole, Search, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Button, TextField } from "../components/primitives";
import { ServiceMark } from "../components/ServiceMark";
import { SERVICE_NAME } from "../config/branding";

export function LoginPage() {
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!loginId.trim() || !password) {
      setError(new ApiError({ status: 400, code: "VALIDATION_ERROR", message: "Enter both login ID and password.", retryable: false, details: [], requestId: null }));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await auth.login({ loginId, password });
      const state = typeof location.state === "object" && location.state !== null ? location.state as { intended?: unknown } : null;
      navigate(typeof state?.intended === "string" ? state.intended : "/", { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-layout">
      <section className="login-context" aria-label={SERVICE_NAME}>
        <div className="login-brand">
          <div className="login-mark"><ServiceMark /></div>
          <span>{SERVICE_NAME}</span>
        </div>
        <h1><span>Move from signal</span>{" "}<span>to evidence.</span></h1>
        <ol aria-label="EDR evidence flow" className="login-signal-route">
          <li><Activity aria-hidden="true" size={17} /><span>01 SIGNAL</span><strong>Observe endpoint telemetry</strong></li>
          <li><Search aria-hidden="true" size={17} /><span>02 EVIDENCE</span><strong>Trace alerts to source records</strong></li>
          <li><ShieldCheck aria-hidden="true" size={17} /><span>03 DECISION</span><strong>Follow backend lifecycle state</strong></li>
        </ol>
        <div className="login-boundary"><strong>Read the state. Follow the source.</strong></div>
      </section>
      <section className="login-panel">
        <form onSubmit={(event) => void submit(event)}>
          <div className="login-heading"><LockKeyhole aria-hidden="true" size={20} /><h2>Sign in</h2></div>
          <TextField label="Login ID" autoCapitalize="none" autoComplete="username" autoFocus maxLength={64} minLength={3} onChange={(event) => setLoginId(event.target.value)} spellCheck={false} type="text" value={loginId} />
          <TextField label="Password" autoComplete="current-password" maxLength={1024} onChange={(event) => setPassword(event.target.value)} type="password" value={password} />
          {error ? <div className="login-error" role="alert"><strong>{error.code === "ACCOUNT_DISABLED" ? "Account disabled" : "Sign in failed"}</strong><span>{error.message}</span>{error.requestId ? <code>Request {error.requestId}</code> : null}</div> : null}
          <Button className="login-submit" loading={loading} type="submit" variant="primary">{loading ? "Signing in…" : "Sign in"}</Button>
        </form>
      </section>
    </main>
  );
}
