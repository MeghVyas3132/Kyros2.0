"use client";

import { StatusBadge } from "@/components/shared/StatusBadge";

interface Props {
  rows: Array<Record<string, unknown>>;
}

export function StylePerformanceTable({ rows }: Props) {
  return (
    <div className="overflow-auto rounded-xl border border-slate-300 bg-white/95 shadow-sm">
      <table className="min-w-full text-sm">
        <thead className="sticky top-0 bg-slate-100 text-left text-xs uppercase tracking-wide text-slate-600">
          <tr>
            <th className="px-3 py-2">Style</th>
            <th className="px-3 py-2">Category</th>
            <th className="px-3 py-2">ROS</th>
            <th className="px-3 py-2">Sell-through</th>
            <th className="px-3 py-2">Cover</th>
            <th className="px-3 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx} className="border-t border-slate-200 hover:bg-slate-50/70">
              <td className="px-3 py-2 font-medium">{String(row.style_name ?? "")}</td>
              <td className="px-3 py-2">{String(row.category ?? "")}</td>
              <td className="px-3 py-2">{Number(row.ros_7d ?? 0).toFixed(2)}</td>
              <td className="px-3 py-2">{Math.round(Number(row.sell_through_pct ?? 0) * 100)}%</td>
              <td className="px-3 py-2">{Number(row.stock_cover_days ?? 0).toFixed(1)}d</td>
              <td className="px-3 py-2">
                <StatusBadge label={String(row.style_status ?? "WATCH")} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
