import Link from "next/link";

import { AlertCount } from "@/types";

interface Props {
  count: AlertCount | undefined;
}

export function AlertBanner({ count }: Props) {
  if (!count) return null;
  return (
    <div className="rounded-xl border border-slate-300 bg-slate-100/75 p-3 text-sm text-slate-900">
      <div className="font-medium">{count.unread} active alerts</div>
      <div className="text-slate-700">
        High: {count.high} | Medium: {count.medium} | Low: {count.low}.{" "}
        <Link className="underline underline-offset-2" href="/dashboard">
          Review now
        </Link>
      </div>
    </div>
  );
}
