"use client";

import { useEffect, useRef } from "react";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { VehicleTelemetry, VehiclesState } from "@/lib/types";
import { iconForVehicle, kindFromVehicleId, VEHICLE_LEGEND } from "@/lib/vehicleIcons";

type FleetMapProps = {
  center: [number, number];
  vehicles: VehiclesState;
};

function VehicleMarker({ vehicle }: { vehicle: VehicleTelemetry }) {
  const markerRef = useRef<L.Marker | null>(null);
  const position: L.LatLngExpression = [vehicle.lat, vehicle.lng];
  const kind = kindFromVehicleId(vehicle.vehicle_id);

  useEffect(() => {
    markerRef.current?.setLatLng([vehicle.lat, vehicle.lng]);
  }, [vehicle.lat, vehicle.lng]);

  return (
    <Marker
      ref={markerRef}
      position={position}
      icon={iconForVehicle(vehicle.vehicle_id)}
    >
      <Popup>
        <div>
          <strong>{vehicle.vehicle_id}</strong>
          <div className="capitalize">{kind}</div>
          <div>Status: {vehicle.status}</div>
        </div>
      </Popup>
    </Marker>
  );
}

export default function FleetMap({ center, vehicles }: FleetMapProps) {
  return (
    <div className="relative h-full w-full">
      <MapContainer
        center={center}
        zoom={12}
        className="h-full w-full"
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {Object.values(vehicles).map((vehicle) => (
          <VehicleMarker key={vehicle.vehicle_id} vehicle={vehicle} />
        ))}
      </MapContainer>
      <ul className="pointer-events-none absolute bottom-6 left-3 z-[1000] m-0 list-none rounded-md bg-white/90 p-2 text-xs text-zinc-800 shadow">
        {VEHICLE_LEGEND.filter((item) => item.kind !== "vehicle").map((item) => (
          <li key={item.kind} className="flex items-center gap-2 py-0.5">
            <span
              className="inline-block h-3 w-3 rounded-full"
              style={{ background: item.color }}
            />
            {item.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
