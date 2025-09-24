"use client";

import { useState } from "react";
import { approveDevice, quarantineDevice } from "@/lib/api";

export function DeviceActions({ deviceId }: { deviceId: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const run = async (action: "approve" | "quarantine") => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      if (action === "approve") {
        await approveDevice(deviceId);
        setMessage("Device approved");
      } else {
        await quarantineDevice(deviceId, "manual from console");
        setMessage("Device quarantined");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={() => run("approve")}
        disabled={loading}
        className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
      >
        Approve
      </button>
      <button
        onClick={() => run("quarantine")}
        disabled={loading}
        className="rounded bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-500 disabled:opacity-50"
      >
        Quarantine
      </button>
      {error && <p className="text-sm text-rose-400">{error}</p>}
      {message && <p className="text-sm text-emerald-400">{message}</p>}
    </div>
  );
}
