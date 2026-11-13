import React, { useEffect, useState } from "react";
import { api, setToken as setApiToken } from "../lib/api";

interface SessionRow {
  phone_masked: string;
  kind: string;
  state: string;
  provider: string;
  version: number;
  updated_at: string;
}

interface JobRow {
  id: string;
  kind: string;
  status: string;
  attempts: number;
  run_at: string;
}

interface DtmfEvent {
  session_id: string;
  state_before: string;
  digits: string;
  state_after: string;
  dropped_reason?: string | null;
  at: string;
}

interface HealthState {
  db: string;
  redis: string;
  provider: string;
  tts_clips: number;
  price_age_days: number;
}

function parseApiError(err: unknown): string {
  const body = (err as { body?: { error?: string; message?: string } } | undefined)?.body;
  if (body?.message) return body.message;
  if (body?.error) return body.error;
  if (err instanceof Error) return err.message;
  return "Request failed.";
}

export default function Ops(): React.ReactElement {
  const [adminEmail, setAdminEmail] = useState("admin@demo.test");
  const [adminPassword, setAdminPassword] = useState("");
  const [loggedIn, setLoggedIn] = useState(false);
  const [loading, setLoading] = useState(false);
  const [calls, setCalls] = useState<{ sessions: SessionRow[]; jobs: JobRow[]; breaker: { calls_today: number; budget: number } }>({
    sessions: [],
    jobs: [],
    breaker: { calls_today: 0, budget: 0 },
  });
  const [dtmf, setDtmf] = useState<{ events: DtmfEvent[] }>({ events: [] });
  const [health, setHealth] = useState<HealthState>({ db: "unknown", redis: "unknown", provider: "unknown", tts_clips: 0, price_age_days: 0 });
  const [pollingErrors, setPollingErrors] = useState<Record<string, string>>({});

  const recordPollingResult = (source: string, error?: unknown) => {
    setPollingErrors((current) => {
      if (error) return { ...current, [source]: parseApiError(error) };
      const next = { ...current };
      delete next[source];
      return next;
    });
  };

  const loginAsAdmin = async () => {
    setLoading(true);
    try {
      const response = await api.post("/api/auth/buyer/login", {
        email: adminEmail,
        password: adminPassword,
      });
      const token = response?.token as string | undefined;
      if (!token) {
        throw new Error("Admin login response missing token.");
      }
      setApiToken(token);
      localStorage.setItem("token", token);
      setLoggedIn(true);
    } catch (err) {
      window.alert(parseApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const flushRedis = async () => {
    if (!window.confirm("Flush Redis? Live calls should continue in demo mode.")) {
      return;
    }
    try {
      await api.post("/api/ops/chaos/flush-redis", {});
      window.alert("Redis flush requested.");
    } catch (err) {
      window.alert(parseApiError(err));
    }
  };

  useEffect(() => {
    if (!loggedIn) return;

    const pollCalls = async () => {
      try {
        const payload = await api.get("/api/ops/calls");
        setCalls(payload as { sessions: SessionRow[]; jobs: JobRow[]; breaker: { calls_today: number; budget: number } });
        recordPollingResult("Calls");
      } catch (err) {
        recordPollingResult("Calls", err);
      }
    };

    const pollDtmf = async () => {
      try {
        const payload = await api.get("/api/ops/dtmf?limit=50");
        setDtmf(payload as { events: DtmfEvent[] });
        recordPollingResult("DTMF", undefined);
      } catch (err) {
        recordPollingResult("DTMF", err);
      }
    };

    const pollHealth = async () => {
      try {
        const payload = await api.get("/health");
        setHealth(payload as HealthState);
        recordPollingResult("Health", undefined);
      } catch (err) {
        recordPollingResult("Health", err);
      }
    };

    pollCalls();
    pollDtmf();
    pollHealth();
    const callsTimer = window.setInterval(pollCalls, 1000);
    const dtmfTimer = window.setInterval(pollDtmf, 1000);
    const healthTimer = window.setInterval(pollHealth, 5000);

    return () => {
      window.clearInterval(callsTimer);
      window.clearInterval(dtmfTimer);
      window.clearInterval(healthTimer);
    };
  }, [loggedIn]);

  if (!loggedIn) {
    return (
      <div className="min-h-screen bg-slate-950 px-4 py-10 text-slate-100">
        <div className="mx-auto max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
          <p className="mb-2 text-xs uppercase tracking-[0.2em] text-emerald-400">Ops</p>
          <h1 className="mb-6 text-2xl font-bold text-white">Admin login</h1>

          <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-400">Email</label>
          <input
            type="email"
            value={adminEmail}
            onChange={(event) => setAdminEmail(event.target.value)}
            className="mb-4 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
          />

          <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-400">Password</label>
          <input
            type="password"
            value={adminPassword}
            onChange={(event) => setAdminPassword(event.target.value)}
            className="mb-4 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-emerald-500"
          />

          <button
            type="button"
            onClick={() => void loginAsAdmin()}
            disabled={loading}
            className="w-full rounded-xl bg-emerald-600 px-3 py-2.5 font-semibold text-white hover:bg-emerald-500 disabled:opacity-60"
          >
            {loading ? "Signing in..." : "Login as admin"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 px-4 py-6 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between rounded-2xl border border-slate-800 bg-slate-900 p-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-emerald-400">Ops console</p>
            <h1 className="text-2xl font-bold text-white">Live operations</h1>
          </div>
          <button
            type="button"
            onClick={() => void flushRedis()}
            className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm font-semibold text-amber-300 hover:bg-amber-500/20"
          >
            Flush Redis
          </button>
        </div>

        {Object.keys(pollingErrors).length > 0 && (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300" role="status">
            {Object.entries(pollingErrors).map(([source, message]) => (
              <p key={source}>{source}: {message}</p>
            ))}
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-slate-300">Health</h2>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {[
                ["db", health.db === "ok"],
                ["redis", health.redis === "ok"],
                ["pricing", health.price_age_days <= 7],
              ].map(([label, ok]) => (
                <div key={String(label)} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950 px-3 py-2">
                  <span className="text-slate-300">{String(label)}</span>
                  <span className={`inline-flex h-3 w-3 rounded-full ${ok ? "bg-emerald-400" : "bg-rose-500"}`} />
                </div>
              ))}
            </div>
            <div className="mt-4 text-sm text-slate-300">
              Provider: <span className="font-semibold text-white">{health.provider}</span>
            </div>
            <div className="mt-2 text-sm text-slate-300">
              TTS clips: <span className="font-semibold text-white">{health.tts_clips}</span>
            </div>
            <div className="mt-2 text-sm text-slate-300">
              Price age: <span className="font-semibold text-white">{health.price_age_days} days</span>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-slate-300">Call breaker</h2>
            <div className="space-y-2 text-sm text-slate-300">
              <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950 px-3 py-2">
                <span>Calls today</span>
                <span className="font-semibold text-white">{calls.breaker.calls_today}</span>
              </div>
              <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950 px-3 py-2">
                <span>Budget</span>
                <span className="font-semibold text-white">{calls.breaker.budget}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-slate-300">Live call sessions</h2>
            <div className="space-y-2">
              {calls.sessions.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-700 p-3 text-sm text-slate-400">No active sessions.</div>
              ) : (
                calls.sessions.map((session) => (
                  <div key={`${session.phone_masked}-${session.updated_at}`} className="rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-medium text-white">{session.phone_masked}</span>
                      <span className="rounded-full border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-300">
                        {session.state}
                      </span>
                    </div>
                    <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
                      <span>{session.kind}</span>
                      <span>{session.provider}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-slate-300">DTMF events</h2>
            <div className="space-y-2">
              {dtmf.events.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-700 p-3 text-sm text-slate-400">No digits captured yet.</div>
              ) : (
                dtmf.events.slice(0, 15).map((event, index) => (
                  <div key={`${event.session_id}-${event.at}-${index}`} className={`rounded-xl border px-3 py-2 text-xs ${event.dropped_reason === "BOUNCE" ? "border-rose-500/40 bg-rose-500/10 text-rose-200" : "border-slate-800 bg-slate-950 text-slate-300"}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-white">{event.session_id}</span>
                      <span>{event.digits || "-"}</span>
                    </div>
                    <div className="mt-2 flex justify-between text-[11px] text-slate-400">
                      <span>{event.state_before} → {event.state_after}</span>
                      {event.dropped_reason && <span>{event.dropped_reason}</span>}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-slate-300">Queued jobs</h2>
          <div className="space-y-2">
            {calls.jobs.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-700 p-3 text-sm text-slate-400">No queued jobs.</div>
            ) : (
              calls.jobs.map((job) => (
                <div key={job.id} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm">
                  <div>
                    <div className="font-medium text-white">{job.kind}</div>
                    <div className="text-xs text-slate-400">attempts: {job.attempts}</div>
                  </div>
                  <div className="text-right text-xs text-slate-400">
                    <div>{job.status}</div>
                    <div>{job.run_at}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
