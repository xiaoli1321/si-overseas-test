import type { AfterSalesResult, Device, FaultCategory } from './device';
import type { ThresholdProfile } from './threshold';
import type { OrganizationType } from './account';

export type VerdictAdoption = 'Yes' | 'No' | 'Not recorded';
export type DetectRecordStatus = 'pending' | 'processing' | 'complete' | 'completed' | 'failed';

export interface VerdictPresentationGuidance {
  text?: string;
  afterSalesStatus?: string;
  why?: string;
  wearingAdvice?: string;
  nextAction?: string;
}

export interface VerdictPresentation {
  templateVersion: string;
  scenarioKey: string;
  badge: string;
  title: string;
  summary: string;
  whatWeFound: string;
  whyThisResult: string;
  possibleCauses: string;
  supportingMaterials: string | string[];
  guidance: VerdictPresentationGuidance;
}

export interface DetectRecord {
  id: string;
  sn: string;
  email: string;
  initiatorEmail: string;
  initiatorName: string;
  dealerId: string;
  dealerName: string;
  organizationName: string;
  organizationType: OrganizationType;
  region: string;
  deviceType: Device['type'];
  faultCategory: FaultCategory;
  faultSubtype: string;
  conclusion: 'Issue Detected' | 'No Issue';
  afterSales: AfterSalesResult;
  timestamp: string;
  thresholdProfileVersion?: number;
  thresholdSnapshot?: ThresholdProfile;
  reasonSummary: string;
  verdictAdoption: VerdictAdoption;
  verdictRejectionReason: string;
  status?: DetectRecordStatus;
  errorMessage?: string | null;
  evidence?: unknown;
  presentation?: VerdictPresentation | null;
  batchId?: string | null;
}

export interface DetectSession {
  id: string;
  sn: string;
  faultCategory: FaultCategory;
  status: 'processing' | 'complete';
  startedAt: string;
  updatedAt: string;
  recordId?: string;
  source?: 'single' | 'multi';
  batchId?: string;
  stepLabel?: string;
  progress?: number;
}

export interface DashboardStats {
  total: number;
  allowed: number;
  notAllowed: number;
  pending: number;
}
