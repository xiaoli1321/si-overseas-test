export interface LowPersistThresholds {
  belowMmol: number;
  minHours: number;
  max24hMmol: number;
}

export interface NoFluctuationThresholds {
  floorMmol: number;
  minHours: number;
  maxSwingMmol: number;
}

export interface JumpThresholds {
  deltaMmol: number;
  consecutive: number;
}

export interface DeviationThresholds {
  within48hDeviationMmol: number;
  within48hPairCount: number;
  within48hQualifiedPairCount: number;
  after48hDeviationRangePct: number;
  after48hPairCount: number;
  after48hQualifiedPairCount: number;
  after48hWearDays: number;
}

export interface InaccuracyThresholdRules {
  lowPersist: LowPersistThresholds;
  noFluctuation: NoFluctuationThresholds;
  jump: JumpThresholds;
  deviation: DeviationThresholds;
}

export interface DeviceAbnormalThresholdRules {
  wearDays: number;
  temporaryAbnormalHours: number;
}

export interface DetachmentThresholdRules {
  detachedStatusValue: number;
  wearDays: number;
}

export interface ApplicationFailureThresholdRules {
  photoCount: number;
  afterSalesScore: number;
  manualReviewScore: number;
}

export interface ThresholdRules {
  inaccuracy: InaccuracyThresholdRules;
  deviceAbnormal?: DeviceAbnormalThresholdRules;
  detachment?: DetachmentThresholdRules;
  applicationFailure?: ApplicationFailureThresholdRules;
}

export type GlucoseUnitPreference = 'mmol/L' | 'mg/dL';

export interface ThresholdDisplaySettings {
  glucoseUnit: GlucoseUnitPreference;
}

export interface ThresholdProfile {
  version: number;
  savedAt: string | null;
  rules: ThresholdRules;
  display?: ThresholdDisplaySettings;
  remark?: string | null;
  restoredFrom?: number | null;
  isHidden?: boolean;
}

export interface ThresholdValidationIssue {
  field: string;
  message: string;
}
