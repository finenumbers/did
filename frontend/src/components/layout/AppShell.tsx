"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api/client";
import type { ProviderHealth } from "@/lib/types/api";

const links = [
  { href: "/free-numbers", label: "Свободные номера" },
  { href: "/purchased-numbers", label: "Купленные номера" },
  { href: "/settings", label: "Настройки" },
  { href: "/sync-logs", label: "Логи синхронизации" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [health, setHealth] = useState<ProviderHealth[]>([]);

  useEffect(() => {
    apiFetch<ProviderHealth[]>("/api/v1/providers/health")
      .then(setHealth)
      .catch(() => setHealth([]));
  }, [pathname]);

  const limited = health.flatMap((h) => h.limitations).length;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">DID Analytics</div>
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
