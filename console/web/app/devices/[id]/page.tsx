import { DeviceActions } from "@/components/device-actions";
import { fetchDevice } from "@/lib/api";
import type { Metadata } from "next";

type DevicePageProps = {
  params: { id: string };
};

export async function generateMetadata({ params }: DevicePageProps): Promise<Metadata> {
  return {
    title: `Device ${params.id} — oneEdge`
  };
}

export default async function DevicePage({ params }: DevicePageProps) {
  const device = await fetchDevice(params.id);
  return (
    <div className="space-y-6">
      <div className="card">
        <h2 className="text-xl font-semibold text-slate-100">{device.display_name || device.id}</h2>
        <p className="mt-1 text-sm text-slate-400">{device.spiffe_id}</p>
        <dl className="mt-4 grid gap-3 md:grid-cols-2 text-sm text-slate-300">
          <div>
            <dt className="text-slate-400">Status</dt>
            <dd className="font-medium capitalize">{device.status}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Quarantine Reason</dt>
            <dd>{device.quarantine_reason || "-"}</dd>
          </div>
        </dl>
      </div>
      <div className="card space-y-4">
        <h3 className="text-lg font-semibold">Actions</h3>
        <DeviceActions deviceId={device.id} />
      </div>
    </div>
  );
}
