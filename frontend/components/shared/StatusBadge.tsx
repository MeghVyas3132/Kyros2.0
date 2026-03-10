import clsx from "clsx";

interface Props {
  label: string;
}

export function StatusBadge({ label }: Props) {
  const normalized = label.toUpperCase();
  const known = [
    "HEALTHY",
    "WATCH",
    "PROBLEM",
    "CRITICAL",
    "HIGH",
    "MEDIUM",
    "LOW",
    "DRAFT",
    "UNDER_REVIEW",
    "APPROVED",
    "ALLOCATED",
    "DISPATCHED",
    "RECEIVED",
  ];
  return (
    <span
      className={clsx(
        "rounded-full px-2 py-0.5 text-xs font-medium",
        normalized === "HEALTHY" && "bg-emerald-100 text-emerald-700",
        normalized === "WATCH" && "bg-amber-100 text-amber-700",
        normalized === "PROBLEM" && "bg-orange-100 text-orange-700",
        normalized === "CRITICAL" && "bg-red-100 text-red-700",
        normalized === "HIGH" && "bg-emerald-100 text-emerald-700",
        normalized === "MEDIUM" && "bg-amber-100 text-amber-700",
        normalized === "LOW" && "bg-red-100 text-red-700",
        normalized === "DRAFT" && "bg-slate-200 text-slate-700",
        normalized === "UNDER_REVIEW" && "bg-slate-300 text-slate-800",
        normalized === "APPROVED" && "bg-emerald-100 text-emerald-700",
        normalized === "ALLOCATED" && "bg-emerald-100 text-emerald-700",
        normalized === "DISPATCHED" && "bg-slate-800 text-slate-100",
        normalized === "RECEIVED" && "bg-amber-100 text-amber-700",
        known.includes(normalized) ? "" : "bg-slate-100 text-slate-700"
      )}
    >
      {label}
    </span>
  );
}
