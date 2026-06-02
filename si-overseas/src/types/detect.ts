import type { Device, FaultCategory } from './device';
import type { DetectRecord } from './record';

export interface DetectDraft {
  device: Device;
  category: FaultCategory;
  evidenceReady: boolean;
}

export interface DetectResult {
  device: Device;
  record: DetectRecord;
}
