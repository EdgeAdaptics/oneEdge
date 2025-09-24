import { DeviceTable } from "@/components/device-table";
import { fetchDevices } from "@/lib/api";

export const revalidate = 0;

export default async function DevicesPage() {
  const devices = await fetchDevices();
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-slate-100">Devices</h2>
      <DeviceTable devices={devices} />
    </div>
  );
}
