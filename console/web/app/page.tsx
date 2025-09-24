import { fetchMetrics } from "@/lib/api";
import { MetricCards } from "@/components/metric-cards";

export default async function OverviewPage() {
  const metrics = await fetchMetrics();
  return (
    <div className="space-y-8">
      <MetricCards bootstrap={metrics} />
      <section className="card">
        <h2 className="text-lg font-semibold text-slate-100">Live Events</h2>
        <p className="mt-2 text-sm text-slate-400">
          Events from Envoy/OPA will appear here during runtime (wired through SSE).
        </p>
        <ul className="mt-4 space-y-2 text-sm text-slate-300">
          <li>Device quarantine and approvals refresh these metrics in near real-time.</li>
          <li>Use the Devices tab to inspect fleet members and take actions.</li>
        </ul>
      </section>
    </div>
  );
}
