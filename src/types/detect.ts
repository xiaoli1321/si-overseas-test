import type { Device } from './device';
import type { DetectRecord } from './record';

export interface DetectDraft {
  device: Device;
  category: Device['fault']['faultCategory'];
  evidenceReady: boolean;
}

export interface DetectResult {
  device: Device;
  record: DetectRecord;
}
