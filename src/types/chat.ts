import type { FaultCategory } from './device';
import type { DetectRecord } from './record';

export interface ChatAttachment {
  id: string;
  name: string;
  type: string;
}

export type ChatSnStatus = 'found' | 'missing' | 'unknown';
export type ChatImageStatus = 'not_required' | 'missing' | 'ready' | 'judged';

export interface ChatJudgmentInsight {
  scenarioSummary: string;
  sn: string;
  snStatus: ChatSnStatus;
  imageStatus: ChatImageStatus;
  imageSummary?: string;
  faultCategory?: FaultCategory;
}

export interface ChatFaultOption {
  category: FaultCategory;
  title: string;
  copy: string;
  key: string;
}

export interface ChatResultSummary {
  sn: string;
  faultCategory: FaultCategory;
  recordId: string;
  sessionId: string;
  conclusion: DetectRecord['conclusion'];
  afterSales: DetectRecord['afterSales'];
  title: string;
  summary: string;
  record: DetectRecord;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  attachments?: ChatAttachment[];
  result?: ChatResultSummary;
  insight?: ChatJudgmentInsight;
  options?: ChatFaultOption[];
  isStreaming?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
}

export interface JudgeCaseResult {
  content: string;
  insight: ChatJudgmentInsight;
  options: ChatFaultOption[];
  result?: ChatResultSummary;
}
