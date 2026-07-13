export type DeviceType = 'GS1';

export type DeviceStatus = 'Wearing' | 'Completed' | 'Abnormal';

export type FaultCategory =
  | 'Data accuracy'
  | 'Sensor falling off'
  | 'Sensor Malfunction'
  | 'Application failure';

export type AfterSalesResult = 'Warranty Eligible' | 'Not Eligible' | 'Under Review';

export interface FaultMapping {
  faultCategory: FaultCategory;
  faultSubtype: string;
  expectedAfterSales: AfterSalesResult;
  notes: string;
}

export interface Device {
  email: string;
  sn: string;
  type: DeviceType;
  status: DeviceStatus;
  activatedAt: string;
  wearDays: number;
  wearHours: number;
  lastDataAt: string;
  hasServiceCard: boolean;
  fault: FaultMapping;
}
