"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { Logo } from "./brand";
import { Button, Card, Field, Input } from "./ui";

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const next = params.get("next") || "/app";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "login") await api.login(email, password);
      else await api.signup(email, password, name);
      router.replace(next.startsWith("/") ? next : "/app");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Logo />
        </div>
        <Card className="p-6">
          <h1 className="font-display text-xl font-semibold">{mode === "login" ? "Welcome back" : "Create your account"}</h1>
          <p className="mt-1 text-sm text-muted">
            {mode === "login" ? "Sign in to your projects and clips." : "Your projects stay private to this account."}
          </p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            {mode === "signup" && (
              <Field label="Name">
                <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" placeholder="Your name" />
              </Field>
            )}
            <Field label="Email">
              <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
            </Field>
            <Field label="Password" hint={mode === "signup" ? "At least 8 characters." : undefined}>
              <Input
                type="password"
                required
                minLength={mode === "signup" ? 8 : 1}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </Field>
            {error && (
              <div role="alert" className="rounded-xl bg-danger/10 px-3 py-2 text-sm text-danger">
                {error}
              </div>
            )}
            <Button type="submit" className="w-full" loading={busy}>
              {mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>
        </Card>
        <p className="mt-6 text-center text-sm text-muted">
          {mode === "login" ? "New to HypeSift? " : "Already have an account? "}
          <Link href={mode === "login" ? "/signup" : "/login"} className="font-medium text-primary hover:underline">
            {mode === "login" ? "Create an account" : "Sign in"}
          </Link>
        </p>
      </div>
    </div>
  );
}
