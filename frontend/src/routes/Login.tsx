// Owner: Darshan. Minimal login used by every role during development.
import { useState } from "react";
import { api, setToken, ApiError } from "../lib/api";

export default function Login() {
  const [role, setRole] = useState<"buyer" | "agent">("buyer");
  const [id, setId] = useState("buyer1@demo.test");
  const [secret, setSecret] = useState("");
  const [msg, setMsg] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMsg("");
    try {
      const res =
        role === "buyer"
          ? await api.post("/api/auth/buyer/login", { email: id, password: secret })
          : await api.post("/api/auth/agent/login", { phone: id, pin: secret });
      setToken(res.token);
      setMsg(`Logged in as ${res.buyer?.org_name ?? res.agent?.name}`);
    } catch (err) {
      setMsg(err instanceof ApiError ? `Login failed: ${err.body?.error ?? err.status}` : "Network error");
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto mt-10 max-w-sm space-y-3 rounded-lg bg-white p-6 shadow">
      <h1 className="text-lg font-semibold">Log in</h1>
      <div className="flex gap-2">
        {(["buyer", "agent"] as const).map((r) => (
          <button
            type="button"
            key={r}
            onClick={() => {
              setRole(r);
              setId(r === "buyer" ? "buyer1@demo.test" : "+919800000101");
            }}
            className={`rounded px-3 py-1 text-sm ${role === r ? "bg-green-800 text-white" : "bg-stone-200"}`}
          >
            {r === "buyer" ? "Buyer / admin" : "FPO agent"}
          </button>
        ))}
      </div>
      <input
        className="w-full rounded border p-2"
        value={id}
        onChange={(e) => setId(e.target.value)}
        placeholder={role === "buyer" ? "email" : "phone (+91…)"}
      />
      <input
        className="w-full rounded border p-2"
        type="password"
        value={secret}
        onChange={(e) => setSecret(e.target.value)}
        placeholder={role === "buyer" ? "password" : "PIN"}
      />
      <button className="w-full rounded bg-green-800 p-2 text-white">Log in</button>
      {msg && <p className="text-sm">{msg}</p>}
      <p className="text-xs text-stone-500">
        The mock server accepts any non-empty password. Use admin@demo.test for the ops page.
      </p>
    </form>
  );
}
