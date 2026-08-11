"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, apiFetch } from "@/lib/api/client";
import { getAccessToken, setSession } from "@/lib/auth";
import { safeNextPath } from "@/lib/auth-redirect";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNextPath(params.get("next"));
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (getAccessToken()) {
      router.replace(next);
    }
  }, [router, next]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<{ access_token: string; username: string }>(
        "/api/v1/auth/login",
        {
          method: "POST",
          body: JSON.stringify({ username, password }),
        },
      );
      setSession(res.access_token, res.username);
      router.replace(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ошибка входа");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card panel" onSubmit={onSubmit}>
        <img src="/logo-login.png" alt="fine numbers" className="login-logo" />
        <h1>Вход администратора</h1>
        <p className="login-hint">Внутренняя панель аналитики нумерации</p>
        <label>
          Логин
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label>
          Пароль
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && <div className="state error">{error}</div>}
        <button type="submit" disabled={loading}>
          {loading ? "Вход…" : "Войти"}
        </button>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="state">Загрузка…</div>}>
      <LoginForm />
    </Suspense>
  );
}
