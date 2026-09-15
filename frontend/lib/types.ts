export type VehicleTelemetry = {
  vehicle_id: string;
  lat: number;
  lng: number;
  speed?: number;
  status: string;
};

export type VehiclesState = Record<string, VehicleTelemetry>;

export type FleetSnapshotMessage = {
  type: "snapshot";
  vehicles: VehicleTelemetry[];
};

export type FleetUpdateMessage = {
  type: "update";
  vehicles: VehicleTelemetry[];
  removed?: string[];
};

export type FleetMessage = FleetSnapshotMessage | FleetUpdateMessage;
