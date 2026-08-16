"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api/client";
import { clearSession, getAccessToken, getUsername } from "@/lib/auth";
import type { ProviderHealth } from "@/lib/types/api";

const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || "dev";

const links = [
  { href: "/free-numbers", label: "Свободные номера" },
  { href: "/purchased-numbers", label: "Купленные номера" },
  { href: "/booking", label: "Бронирование" },
  { href: "/regions", label: "Регионы" },
  { href: "/settings", label: "Настройки" },
  { href: "/sync-logs", label: "Синхронизация" },
];

const externalLinks: { href: string; label: string; dividerBefore?: boolean }[] = [
  { href: "https://reg.finenumbers.com/", label: "OSS Platform" },
  { href: "https://pstn.finenumbers.com/", label: "PSTN Platform" },
  { href: "https://sms-adm.finenumbers.com/", label: "SMS Platform" },
  { href: "https://check.finenumbers.com/", label: "Check Platform" },
  { href: "https://admin.finenumbers.cloud/", label: "iTooLabs Platform", dividerBefore: true },
  { href: "https://5.227.161.180:8445/", label: "RTU Softswitch" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isLogin = pathname.startsWith("/login");
  const [health, setHealth] = useState<ProviderHealth[]>([]);
  const [hasSession, setHasSession] = useState(false);
  const [ready, setReady] = useState(isLogin);
  const [gateError, setGateError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);

  const checkAuthGate = useCallback(() => {
    if (isLogin) {
      setReady(true);
      setGateError(null);
      return;
    }
    const token = getAccessToken();
    setHasSession(Boolean(token || getUsername()));
    setReady(false);
    setGateError(null);
    void apiFetch<{ auth_required: boolean }>("/api/v1/auth/status")
      .then((st) => {
        if (st.auth_required && !token) {
          router.replace(`/login?next=${encodeURIComponent(pathname)}`);
          return;
        }
        setReady(true);
      })
      .catch(() => {
        setReady(false);
        setGateError(
          token
            ? "Не удалось проверить авторизацию (backend недоступен). Повторите попытку."
            : "Не удалось проверить авторизацию. Повторите попытку или войдите снова.",
        );
      });
  }, [pathname, isLogin, router]);

  useEffect(() => {
    checkAuthGate();
  }, [checkAuthGate, retryTick]);

  useEffect(() => {
    if (isLogin || !ready) return;
    apiFetch<ProviderHealth[]>("/api/v1/providers/health")
      .then(setHealth)
      .catch(() => setHealth([]));
  }, [pathname, isLogin, ready]);

  if (isLogin) {
    return <>{children}</>;
  }

  if (gateError) {
    return (
      <div className="state error" style={{ padding: "2rem", maxWidth: 480, margin: "4rem auto" }}>
        <p>{gateError}</p>
        <button type="button" onClick={() => setRetryTick((n) => n + 1)} style={{ marginTop: "1rem" }}>
          Повторить
        </button>
        {!getAccessToken() ? (
          <button
            type="button"
            className="secondary"
            style={{ marginTop: "0.5rem", marginLeft: "0.5rem" }}
            onClick={() => router.replace(`/login?next=${encodeURIComponent(pathname)}`)}
          >
            Войти
          </button>
        ) : null}
      </div>
    );
  }

  if (!ready) {
    return <div className="state">Загрузка…</div>;
  }

  const limited = health.flatMap((h) => h.limitations).length;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <img src="/logo-full.png" alt="fine numbers" className="brand-logo" />
        </div>
        <nav className="nav">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={pathname.startsWith(l.href) ? "active" : undefined}
            >
              {l.label}
            </Link>
          ))}
          <div className="nav-divider" role="separator" />
          {externalLinks.map((l) => (
            <Fragment key={l.href}>
              {l.dividerBefore ? <div className="nav-divider" role="separator" /> : null}
              <a
                href={l.href}
                target="_blank"
                rel="noopener noreferrer"
                className="nav-external"
              >
                {l.label}
              </a>
            </Fragment>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-version">{APP_VERSION}</div>
          {hasSession ? (
            <button
              type="button"
              className="nav-logout"
              onClick={() => {
                clearSession();
                router.replace("/login");
              }}
            >
              Выйти
            </button>
          ) : null}
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div>Внутренняя панель нумерации</div>
          <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
            Провайдеров: {health.length}
            {limited > 0 ? ` · ограничений docs: ${limited}` : ""}
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
