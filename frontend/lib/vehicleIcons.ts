import L from "leaflet";

export type FleetVehicleKind =
  | "tractor"
  | "fuel"
  | "truck"
  | "harvester"
  | "vehicle";

const KIND_META: Record<
  FleetVehicleKind,
  { label: string; color: string; glyph: string }
> = {
  tractor: {
    label: "Tractor",
    color: "#3f7d3a",
    glyph: `<circle cx="7" cy="16.5" r="3.6"/><circle cx="18" cy="17.5" r="2.4"/><rect x="8.5" y="10" width="11" height="5.5" rx="1"/><rect x="13" y="5.5" width="6.5" height="5" rx="1"/>`,
  },
  fuel: {
    label: "Fuel tanker",
    color: "#c27a12",
    glyph: `<rect x="2" y="9" width="5.5" height="6" rx="0.8"/><ellipse cx="15" cy="12.2" rx="7" ry="3.6"/><circle cx="6" cy="17.5" r="2"/><circle cx="16.5" cy="17.5" r="2"/>`,
  },
  truck: {
    label: "Truck",
    color: "#2b5f9e",
    glyph: `<rect x="2" y="8.5" width="6" height="7" rx="0.8"/><rect x="8" y="7" width="14" height="8.5" rx="1"/><circle cx="7" cy="17.5" r="2"/><circle cx="17.5" cy="17.5" r="2"/>`,
  },
  harvester: {
    label: "Harvester",
    color: "#b45309",
    glyph: `<rect x="1" y="11" width="8" height="4" rx="0.6"/><rect x="8" y="7" width="13" height="8" rx="1.2"/><circle cx="8" cy="17.5" r="2.2"/><circle cx="18" cy="17.5" r="2.2"/>`,
  },
  vehicle: {
    label: "Vehicle",
    color: "#334155",
    glyph: `<path d="M4 14.5h16l-1.4-4.2A2 2 0 0 0 16.7 9H7.3a2 2 0 0 0-1.9 1.3L4 14.5z"/><rect x="5" y="14.5" width="14" height="2.2" rx="0.4"/><circle cx="7.5" cy="17.4" r="1.8"/><circle cx="16.5" cy="17.4" r="1.8"/>`,
  },
};

const iconCache = new Map<FleetVehicleKind, L.DivIcon>();

export function kindFromVehicleId(vehicleId: string): FleetVehicleKind {
  const prefix = vehicleId.split("-")[0]?.toLowerCase() ?? "";
  if (prefix in KIND_META) {
    return prefix as FleetVehicleKind;
  }
  return "vehicle";
}

function markerHtml(kind: FleetVehicleKind): string {
  const { color, glyph } = KIND_META[kind];
  return `<div class="fleet-pin" style="background:${color}">
    <svg viewBox="0 0 24 24" width="22" height="22" fill="#fff" aria-hidden="true">${glyph}</svg>
  </div>`;
}

export function iconForVehicle(vehicleId: string): L.DivIcon {
  const kind = kindFromVehicleId(vehicleId);
  const cached = iconCache.get(kind);
  if (cached) {
    return cached;
  }

  const icon = L.divIcon({
    className: "vehicle-marker",
    html: markerHtml(kind),
    iconSize: [36, 36],
    iconAnchor: [18, 18],
    popupAnchor: [0, -18],
  });
  iconCache.set(kind, icon);
  return icon;
}

export const VEHICLE_LEGEND = (
  Object.entries(KIND_META) as [FleetVehicleKind, (typeof KIND_META)[FleetVehicleKind]][]
).map(([kind, meta]) => ({
  kind,
  label: meta.label,
  color: meta.color,
}));
