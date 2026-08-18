"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Fragment, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api/client";
import { clearSession, getAccessToken, getUsername } from "@/lib/auth";

const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || "dev";

const links = [
  { href: "/free-numbers", label: "Свободные номера" },
  { href: "/purchased-numbers", label: "Купленные номера" },
  { href: "/booking", label: "Бронирование" },
  { href: "/masks", label: "Маски и типы" },
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
  const pathnameRef = useRef(pathname);
  pathnameRef.current = pathname;

  const [hasSession, setHasSession] = useState(false);
  const [ready, setReady] = useState(isLogin);
  const [authRequired, setAuthRequired] = useState<boolean | null>(null);
  const [gateError, setGateError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);
  const readyRef = useRef(ready);
  readyRef.current = ready;
  const prevRetryTick = useRef(retryTick);

  // HTTP auth gate once per shell session (cold load / leave login / Retry) — not on pathname.
  useEffect(() => {
    if (isLogin) {
      setReady(true);
      setGateError(null);
      return;
    }

    let cancelled = false;
    const token = getAccessToken();
    const isRetry = prevRetryTick.current !== retryTick;
    prevRetryTick.current = retryTick;
    setHasSession(Boolean(token || getUsername()));
    setGateError(null);
    // Never unmount an already-shown shell on route/login re-entry.
    // Full-screen loading only on cold bootstrap or explicit Retry.
    if (isRetry || !readyRef.current) {
      setReady(false);
    }

    void apiFetch<{ auth_required: boolean }>("/api/v1/auth/status")
      .then((st) => {
        if (cancelled) return;
        setAuthRequired(st.auth_required);
        if (st.auth_required && !token) {
          router.replace(`/login?next=${encodeURIComponent(pathnameRef.current)}`);
          return;
        }
        setReady(true);
      })
      .catch(() => {
        if (cancelled) return;
        setReady(false);
        setGateError(
          token
            ? "Не удалось проверить авторизацию (backend недоступен). Повторите попытку."
            : "Не удалось проверить авторизацию. Повторите попытку или войдите снова.",
        );
      });

    return () => {
      cancelled = true;
    };
  }, [isLogin, retryTick, router]);

  // Sync-only guard on navigation: no HTTP, no shell unmount.
  useEffect(() => {
    if (isLogin || !ready) return;
    if (authRequired && !getAccessToken()) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [pathname, isLogin, ready, authRequired, router]);

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
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
