"use client";

import { SimulationResult } from "@/types";

interface Props {
  simulation: SimulationResult | null;
}

export function ScenarioSimulator({ simulation }: Props) {
  if (!simulation) return null;
  return (
    <div className="mt-1 text-xs text-slate-600">
      {simulation.weeks_cover} weeks cover · ~{Math.round(simulation.projected_sellthrough_eow * 100)}% sell-through
      {simulation.fills_display_capacity ? " · Fills display capacity" : ""}
    </div>
  );
}
