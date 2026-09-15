"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import type { FleetMessage, VehiclesState } from "@/lib/types";

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/fleet";
const LAX_CENTER: [number, number] = [33.9416, -118.4085];

const FleetMap = dynamic(() => import("@/components/FleetMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center bg-zinc-900 text-zinc-300">
      Loading map…
    </div>
  ),
});

function isFleetMessage(value: unknown): value is FleetMessage {
  if (!value || typeof value !== "object") {
    return false;
  }
  const message = value as { type?: unknown };
  return message.type === "snapshot" || message.type === "update";
}

export default function Dashboard() {
  const [vehicles, setVehicles] = useState<VehiclesState>({});

  useEffect(() => {
    const ws = new WebSocket(WS_URL);

    ws.onmessage = (event) => {
      try {
        const parsed: unknown = JSON.parse(event.data);
        if (!isFleetMessage(parsed)) {
          return;
        }

        if (parsed.type === "snapshot") {
          const next: VehiclesState = {};
          for (const vehicle of parsed.vehicles ?? []) {
            if (vehicle?.vehicle_id) {
              next[vehicle.vehicle_id] = vehicle;
            }
          }
          setVehicles(next);
          return;
        }

        setVehicles((previous) => {
          const next = { ...previous };
          for (const vehicle of parsed.vehicles ?? []) {
            if (vehicle?.vehicle_id) {
              next[vehicle.vehicle_id] = vehicle;
            }
          }
          for (const vehicleId of parsed.removed ?? []) {
            delete next[vehicleId];
          }
          return next;
        });
      } catch {
        // Ignore malformed frames so one bad payload cannot drop the socket.
      }
    };

    return () => {
      ws.close();
    };
  }, []);

  return (
    <div className="h-screen w-screen">
      <FleetMap center={LAX_CENTER} vehicles={vehicles} />
    </div>
  );
}
