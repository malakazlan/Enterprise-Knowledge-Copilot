"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { ApiError, login, register } from "@/lib/api";
import { applyStoredTheme } from "@/components/shell";
import { Button, Field } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    applyStoredTheme();
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "register") {
        await register(email, password, fullName);
      }
      await login(email, password);
      router.replace("/ask");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="w-[360px] max-w-full">
        <div className="mb-5 grid h-11 w-11 place-items-center rounded-xl bg-accent text-[19px] font-bold text-white">
          K
        </div>
        <h1 className="text-[22px] font-bold tracking-[-0.02em]">
          {mode === "login" ? "Welcome back" : "Create your account"}
        </h1>
        <p className="mt-1.5 mb-6 text-[13.5px] text-ink-2">
          {mode === "login"
            ? "Sign in to Knowledge Copilot"
            : "The first account becomes the administrator"}
        </p>

        <form onSubmit={submit} className="flex flex-col gap-3.5">
          {mode === "register" && (
            <Field
              label="Full name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Jane Counsel"
              required
            />
          )}
          <Field
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="counsel@firm.com"
            required
          />
          <Field
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••••••"
            minLength={8}
            required
          />
          {error && <p className="text-[12.5px] text-danger">{error}</p>}
          <Button variant="primary" type="submit" disabled={busy} className="justify-center py-2">
            {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
          </Button>
        </form>

        <p className="mt-4.5 text-center text-xs leading-relaxed text-ink-3">
          {mode === "login" ? (
            <>
              New here?{" "}
              <button className="text-accent hover:underline" onClick={() => setMode("register")}>
                Create an account
              </button>
            </>
          ) : (
            <>
              Already registered?{" "}
              <button className="text-accent hover:underline" onClick={() => setMode("login")}>
                Sign in
              </button>
            </>
          )}
          <br />
          Self-hosted · your data never leaves this server.
        </p>
      </div>
    </div>
  );
}
