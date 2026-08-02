"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api/client";
import { clearSession, getAccessToken, getUsername } from "@/lib/auth";
import type { ProviderHealth } from "@/lib/types/api";

const links = [
  { href: "/free-numbers", label: "Свободные номера" },
  { href: "/purchased-numbers", label: "Купленные номера" },
  { href: "/settings", label: "Настройки" },
  { href: "/sync-logs", label: "Синхронизация" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isLogin = pathname.startsWith("/login");
  const [health, setHealth] = useState<ProviderHealth[]>([]);
  const [user, setUser] = useState<string | null>(null);
  const [ready, setReady] = useState(isLogin);

  useEffect(() => {
    if (isLogin) {
      setReady(true);
      return;
    }
    const token = getAccessToken();
    setUser(getUsername());
    void apiFetch<{ auth_required: boolean }>("/api/v1/auth/status")
      .then((st) => {
        if (st.auth_required && !token) {
          router.replace(`/login?next=${encodeURIComponent(pathname)}`);
          return;
        }
        setReady(true);
      })
      .catch(() => setReady(true));
  }, [pathname, isLogin, router]);

  useEffect(() => {
    if (isLogin || !ready) return;
    apiFetch<ProviderHealth[]>("/api/v1/providers/health")
      .then(setHealth)
      .catch(() => setHealth([]));
  }, [pathname, isLogin, ready]);

  if (isLogin) {
    return <>{children}</>;
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
        </nav>
        <div style={{ marginTop: "auto", fontSize: "0.8rem", color: "#9aabba" }}>
          {user ? (
            <>
              <div style={{ marginBottom: "0.5rem" }}>{user}</div>
              <button
                type="button"
                className="secondary"
                style={{ width: "100%" }}
                onClick={() => {
                  clearSession();
                  router.replace("/login");
                }}
              >
                Выйти
              </button>
            </>
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
