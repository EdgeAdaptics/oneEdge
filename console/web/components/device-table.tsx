import Link from "next/link";
import type { Device } from "@/lib/api";

export function DeviceTable({ devices }: { devices: Device[] }) {
  if (!devices.length) {
    return <p className="text-slate-400">No devices registered yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="table">
        <thead>
          <tr>
            <th className="px-4 py-3 text-left">Name</th>
            <th className="px-4 py-3 text-left">SPIFFE ID</th>
            <th className="px-4 py-3 text-left">Status</th>
            <th className="px-4 py-3 text-left">Quarantine</th>
          </tr>
        </thead>
        <tbody>
          {devices.map((device) => (
            <tr key={device.id}>
              <td className="px-4 py-3 text-sm">
                <Link href={`/devices/${device.id}`} className="text-primary hover:underline">
                  {device.display_name || device.id.slice(0, 8)}
                </Link>
              </td>
              <td className="px-4 py-3 text-xs text-slate-400">{device.spiffe_id}</td>
              <td className="px-4 py-3 text-sm capitalize">{device.status}</td>
              <td className="px-4 py-3 text-xs text-slate-400">{device.quarantine_reason || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
