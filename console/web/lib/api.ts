export type Device = {
  id: string;
  spiffe_id: string;
  display_name?: string;
  status: string;
  labels?: Record<string, unknown>;
  quarantine_reason?: string;
  last_seen?: string;
};

export type FleetMetrics = {
  total: number;
  online: number;
  quarantined: number;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const message = await res.text();
    throw new Error(message || res.statusText);
  }
  return res.json() as Promise<T>;
}

export async function fetchMetrics(): Promise<FleetMetrics> {
  const res = await fetch(`${API_URL}/v1/metrics/fleet`, { next: { revalidate: 5 } });
  return handle<FleetMetrics>(res);
}

export async function fetchDevices(): Promise<Device[]> {
  const res = await fetch(`${API_URL}/v1/devices`, { cache: "no-store" });
  return handle<Device[]>(res);
}

export async function fetchDevice(id: string): Promise<Device> {
  const res = await fetch(`${API_URL}/v1/devices/${id}`, { cache: "no-store" });
  return handle<Device>(res);
}

export async function quarantineDevice(id: string, reason: string) {
  const res = await fetch(`${API_URL}/v1/devices/${id}:quarantine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason })
  });
  return handle<Device>(res);
}

export async function approveDevice(id: string) {
  const res = await fetch(`${API_URL}/v1/devices/${id}:approve`, { method: "POST" });
  return handle<Device>(res);
}
