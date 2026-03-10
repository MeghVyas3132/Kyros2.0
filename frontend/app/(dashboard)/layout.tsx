"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAlertCount } from "@/lib/hooks/useAlerts";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/grn", label: "GRN" },
  { href: "/performance/styles", label: "Performance Styles" },
  { href: "/performance/stores", label: "Performance Stores" },
  { href: "/ingestion", label: "Upload Hub" },
  { href: "/setup/onboarding", label: "Onboarding" },
  { href: "/setup/stores", label: "Setup" },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: alertCount } = useAlertCount();

  useEffect(() => {
    const token = localStorage.getItem("kyros_access_token");
    if (!token) router.replace("/login");
  }, [router]);

  return (
    <div className="min-h-screen bg-transparent">
      <header className="border-b border-slate-800 bg-slate-950 text-slate-100">
        <div className="mx-auto flex max-w-[1680px] items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="h-2 w-2 rounded-full bg-emerald-400" />
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-300">Kyros</p>
          </div>
          <nav className="flex items-center gap-1 text-sm">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={
                  pathname === item.href
                    ? "rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 font-medium text-slate-100"
                    : "rounded-md px-3 py-1.5 text-slate-400 hover:bg-slate-900/70 hover:text-slate-100"
                }
              >
                {item.label}
              </Link>
            ))}
            <span className="ml-2 rounded-full border border-red-500/30 bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-300">
              Alerts {alertCount?.unread ?? 0}
            </span>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-[1680px] p-6">{children}</main>
    </div>
  );
}
