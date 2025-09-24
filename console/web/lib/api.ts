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
  try {
    const res = await fetch(`${API_URL}/v1/metrics/fleet`, { next: { revalidate: 5 } });
    return await handle<FleetMetrics>(res);
  } catch (error) {
    if (process.env.NODE_ENV === "production") {
      console.warn("metrics fetch failed; falling back to defaults", error);
    }
    return { total: 0, online: 0, quarantined: 0 };
  }
}

export async function fetchDevices(): Promise<Device[]> {
  try {
    const res = await fetch(`${API_URL}/v1/devices`, { cache: "no-store" });
    return await handle<Device[]>(res);
  } catch (error) {
    if (process.env.NODE_ENV === "production") {
      console.warn("device list fetch failed; returning empty list", error);
    }
    return [];
  }
}

export async function fetchDevice(id: string): Promise<Device> {
  try {
    const res = await fetch(`${API_URL}/v1/devices/${id}`, { cache: "no-store" });
    return await handle<Device>(res);
  } catch (error) {
    if (process.env.NODE_ENV === "production") {
      console.warn(`device fetch failed for ${id}; returning placeholder`, error);
    }
    return {
      id,
      spiffe_id: "unknown",
      status: "unknown"
    };
  }
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
