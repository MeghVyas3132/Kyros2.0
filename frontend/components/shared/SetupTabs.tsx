"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

const TABS = [
  { href: "/setup/onboarding", label: "Onboarding" },
  { href: "/setup/seasons", label: "Seasons" },
  { href: "/setup/clusters", label: "Clusters" },
  { href: "/setup/stores", label: "Stores" },
  { href: "/setup/skus", label: "SKUs" },
];

export function SetupTabs() {
  const pathname = usePathname();

  return (
    <div className="flex flex-wrap gap-2 rounded-lg border border-slate-200 bg-white p-2 text-sm">
      {TABS.map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          className={clsx(
            "rounded-md px-3 py-1.5 font-medium",
            pathname === tab.href
              ? "bg-slate-900 text-white"
              : "text-slate-600 hover:bg-slate-100"
          )}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}
