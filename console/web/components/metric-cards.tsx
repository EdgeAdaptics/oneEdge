"use client";

import { useEffect, useState } from "react";
import type { FleetMetrics } from "@/lib/api";

const initialMetrics: FleetMetrics = { total: 0, online: 0, quarantined: 0 };

export function MetricCards({ bootstrap }: { bootstrap: FleetMetrics }) {
  const [metrics, setMetrics] = useState<FleetMetrics>(bootstrap ?? initialMetrics);

  useEffect(() => {
    const source = new EventSource(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080"}/v1/events/stream`);
    source.addEventListener("device.quarantine", () => {
      setMetrics((prev) => ({ ...prev, quarantined: prev.quarantined + 1 }));
    });
    source.addEventListener("device.approved", () => {
      setMetrics((prev) => ({ ...prev, quarantined: Math.max(prev.quarantined - 1, 0) }));
    });
    source.addEventListener("device.registered", () => {
      setMetrics((prev) => ({ ...prev, total: prev.total + 1 }));
    });
    return () => source.close();
  }, []);

  useEffect(() => {
    setMetrics(bootstrap);
  }, [bootstrap]);

  const cards = [
    { label: "Total", value: metrics.total },
    { label: "Online", value: metrics.online },
    { label: "Quarantined", value: metrics.quarantined }
  ];

  return (
    <div className="grid gap-4 md:grid-cols-3">
      {cards.map((card) => (
        <div key={card.label} className="card">
          <p className="text-sm uppercase tracking-wide text-slate-400">{card.label}</p>
          <p className="mt-2 text-3xl font-semibold text-slate-100">{card.value}</p>
        </div>
      ))}
    </div>
  );
}
