"use client";

import Link from "next/link";
import { useActiveSeasonId, useWorkflowState } from "@/lib/hooks/useSeasons";

export function WorkflowShell() {
  const seasonId = useActiveSeasonId();
  const { data: workflow } = useWorkflowState(seasonId);

  if (!workflow) return null;

  const { steps, next_step, season_name } = workflow;

  return (
    <div className="border-b border-slate-200 bg-white">
      <div className="mx-auto max-w-[1440px] px-6 py-3">
        <div className="flex items-center justify-between gap-4">
          {/* Season label */}
          <span className="shrink-0 text-xs font-semibold text-slate-500 uppercase tracking-wide">
            {season_name}
          </span>

          {/* Step bar */}
          <ol className="flex flex-1 items-center justify-center gap-0 min-w-0">
            {steps.map((step, idx) => {
              const isLast = idx === steps.length - 1;
              return (
                <li key={step.step} className="flex items-center">
                  {/* Step circle */}
                  <div className="flex flex-col items-center">
                    <div
                      className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold select-none transition-colors ${
                        step.is_complete
                          ? "bg-slate-900 text-white"
                          : step.is_current
                          ? "bg-blue-600 text-white ring-2 ring-blue-200"
                          : "bg-slate-100 text-slate-400"
                      }`}
                      title={step.description}
                    >
                      {step.is_complete ? (
                        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        step.step
                      )}
                    </div>
                    <span
                      className={`mt-1 text-[10px] whitespace-nowrap font-medium ${
                        step.is_complete
                          ? "text-slate-600"
                          : step.is_current
                          ? "text-blue-700"
                          : "text-slate-400"
                      }`}
                    >
                      {step.label}
                    </span>
                  </div>
                  {/* Connector line */}
                  {!isLast && (
                    <div
                      className={`mx-2 h-px w-8 sm:w-12 transition-colors ${
                        step.is_complete ? "bg-slate-900" : "bg-slate-200"
                      }`}
                    />
                  )}
                </li>
              );
            })}
          </ol>

          {/* Next action CTA */}
          {next_step ? (
            <Link
              href={next_step.action_url}
              className="shrink-0 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition-colors whitespace-nowrap"
            >
              {next_step.action_label}
            </Link>
          ) : (
            <span className="shrink-0 rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
              ✓ Season complete
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
