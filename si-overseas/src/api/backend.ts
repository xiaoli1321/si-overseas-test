import type { AccountProfile } from '@/types/account';
import type { Device, FaultCategory } from '@/types/device';
import type { DetectRecord, DetectSession } from '@/types/record';
import type { ThresholdProfile } from '@/types/threshold';
import type { ChatSession, ChatMessage } from '@/types/chat';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';
const USE_BACKEND = import.meta.env.MODE !== 'test' && import.meta.env.VITE_USE_BACKEND !== 'false';
const TOKEN_STORAGE_KEY = 'si-overseas-api-token';

export interface BackendBatchRun {
  id: string;
  batchId: string;
  faultCategory: FaultCategory;
  totalCount: number;
  successCount: number;
  failedCount: number;
  status: 'pending' | 'processing' | 'complete' | 'completed' | 'failed';
  records: DetectRecord[];
  sessions: DetectSession[];
}

export interface AgentClassifyResult {
  faultCategory: FaultCategory | null;
  intentType?: 'fault_category' | 'other_cgm' | 'unrelated' | 'unknown';
  confidence: number;
  message: string;
  manualReview: boolean;
  source?: string;
  fallbackUsed?: boolean;
}

export interface ChatTurnResult {
  userMessage: ChatMessage;
  assistantMessage: ChatMessage;
}

export interface CreateUserPayload {
  email: string;
  password: string;
  role?: AccountProfile['role'];
  distributorName: string;
}

export interface ManagedUser {
  id: string;
  email: string;
  role: string;
  dealerName: string;
  createdAt: string | null;
}

export interface ResetPasswordResult {
  id: string;
  email: string;
  password: string;
}

export interface DashboardData {
  totals: {
    logins: number;
    deviceQueries: number;
    batchQueries: number;
    batchDevices: number;
    diagnoses: number;
    records: number;
  };
  verdicts: { eligible: number; notEligible: number; underReview: number };
  adoption: { adopted: number; rejected: number };
  queryUsage: { single: number; batch: number; search: number };
  byFaultCategory: Array<{ category: string; count: number }>;
  byAccount: Array<{
    accountId: string;
    email: string;
    dealerName: string;
    logins: number;
    queries: number;
    batchDevices: number;
    diagnoses: number;
    adopted: number;
    rejected: number;
  }>;
}

interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}

export function backendEnabled() {
  return USE_BACKEND;
}

function getStoredToken() {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY) ?? '';
  } catch {
    return '';
  }
}

function setStoredToken(token: string) {
  try {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    // Storage can be unavailable in restricted browser contexts.
  }
}

export function trackBackendEvent(eventName: string, source: string, properties: Record<string, unknown> = {}) {
  if (!USE_BACKEND) return;
  void request<{ id: number }>('/api/v1/analytics/events', {
    method: 'POST',
    body: JSON.stringify({ eventName, source, properties }),
  }).catch(() => {
    // Analytics must never block the user workflow.
  });
}

let isUnauthorizedDispatched = false;

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const { timeoutMs = 15000, ...options } = init;
  const headers = new Headers(options.headers);
  if (!headers.has('Content-Type') && options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  const token = getStoredToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      signal: controller.signal,
    });
  } catch (err: any) {
    if (err.name === 'AbortError') {
      const error = new Error('Request timeout');
      (error as any).isNetworkError = true;
      throw error;
    }
    const error = new Error('Network error or server is down');
    (error as any).isNetworkError = true;
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }

  if (response.status === 401 && path !== '/api/v1/auth/login') {
    try {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      window.localStorage.removeItem('si-overseas-current-user');
    } catch {
      // Storage can be unavailable in restricted browser contexts.
    }
    if (!isUnauthorizedDispatched) {
      isUnauthorizedDispatched = true;
      window.dispatchEvent(new CustomEvent('auth-unauthorized'));
    }
    const error = new Error('Session expired, please log in again.');
    (error as any).isValidationError = true;
    throw error;
  }

  const payload = await response.json().catch(() => null) as Envelope<T> | null;
  if (!response.ok || !payload || payload.code !== 0) {
    const errMsg = payload?.message ?? `Request failed: ${response.status}`;
    const error = new Error(errMsg);
    if (!response.ok && response.status >= 500) {
      (error as any).isNetworkError = true;
    } else {
      (error as any).isValidationError = true;
    }
    throw error;
  }
  return payload.data;
}

export const backendApi = {
  enabled: backendEnabled,

  async login(email: string, password: string): Promise<AccountProfile> {
    isUnauthorizedDispatched = false;
    const data = await request<{ access_token: string; user: AccountProfile }>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    setStoredToken(data.access_token);
    trackBackendEvent('login', 'auth', { email });
    return data.user;
  },

  me(): Promise<AccountProfile> {
    return request<AccountProfile>('/api/v1/auth/me');
  },

  createUser(payload: CreateUserPayload): Promise<AccountProfile> {
    return request<AccountProfile>('/api/v1/auth/users', {
      method: 'POST',
      body: JSON.stringify({
        email: payload.email,
        password: payload.password,
        role: payload.role ?? 'dealer',
        distributorName: payload.distributorName,
      }),
    });
  },

  /** Manager-only: list the accounts the current manager has provisioned. */
  getUsers(): Promise<ManagedUser[]> {
    return request<ManagedUser[]>('/api/v1/auth/users');
  },

  /** Manager-only: reset a managed account's password; returns the new plaintext once. */
  resetUserPassword(userId: string, password?: string): Promise<ResetPasswordResult> {
    return request<ResetPasswordResult>(
      `/api/v1/auth/users/${encodeURIComponent(userId)}/reset-password`,
      {
        method: 'POST',
        body: JSON.stringify(password ? { password } : {}),
      },
    );
  },

  /** Manager-only: aggregated operations dashboard from telemetry + records. */
  getDashboard(): Promise<DashboardData> {
    return request<DashboardData>('/api/v1/analytics/dashboard');
  },

  getDevice(sn: string): Promise<Device> {
    return request<Device>(`/api/v1/devices/${encodeURIComponent(sn)}`);
  },

  async searchDevices(keyword: string): Promise<Device[]> {
    const matches = await request<Device[]>('/api/v1/devices/search', {
      method: 'POST',
      body: JSON.stringify({ query: keyword }),
    });
    trackBackendEvent('device.search', 'device_search', { queryLength: keyword.length, resultCount: matches.length });
    return matches;
  },

  classify(message: string): Promise<AgentClassifyResult> {
    return request<AgentClassifyResult>('/api/v1/agent/classify', {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
  },

  getThreshold(): Promise<ThresholdProfile> {
    return request<ThresholdProfile>('/api/v1/thresholds/current');
  },

  async saveThreshold(profile: ThresholdProfile): Promise<ThresholdProfile> {
    const saved = await request<ThresholdProfile>('/api/v1/thresholds', {
      method: 'POST',
      body: JSON.stringify(profile),
    });
    trackBackendEvent('threshold.save', 'thresholds', { version: saved.version });
    return saved;
  },

  async resetThreshold(): Promise<ThresholdProfile> {
    const reset = await request<ThresholdProfile>('/api/v1/thresholds/reset', { method: 'POST' });
    trackBackendEvent('threshold.reset', 'thresholds', { version: reset.version });
    return reset;
  },

  getThresholdHistory(): Promise<ThresholdProfile[]> {
    return request<ThresholdProfile[]>('/api/v1/thresholds/history');
  },

  async rollbackThreshold(version: number, remark?: string): Promise<ThresholdProfile> {
    const rolled = await request<ThresholdProfile>(`/api/v1/thresholds/rollback/${version}`, {
      method: 'POST',
      headers: remark ? { 'Content-Type': 'application/json' } : undefined,
      body: remark ? JSON.stringify({ remark }) : undefined,
    });
    trackBackendEvent('threshold.rollback', 'thresholds', { version: rolled.version, rolledBackTo: version });
    return rolled;
  },

  updateThresholdRemark(version: number, remark: string): Promise<ThresholdProfile> {
    return request<ThresholdProfile>(`/api/v1/thresholds/history/${version}/remark`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ remark }),
    });
  },

  hideThreshold(version: number): Promise<ThresholdProfile> {
    return request<ThresholdProfile>(`/api/v1/thresholds/history/${version}`, {
      method: 'DELETE',
    });
  },

  async createDetection(sn: string, faultCategory: FaultCategory, fileIds: string[] = []): Promise<DetectRecord> {
    const record = await request<DetectRecord>('/api/v1/detections', {
      method: 'POST',
      body: JSON.stringify({ serialNo: sn, faultCategory, fileIds }),
    });
    trackBackendEvent('detection.create', 'detect_flow', { sn, faultCategory, fileCount: fileIds.length, recordId: record.id });
    return record;
  },

  getDetection(recordId: string): Promise<DetectRecord> {
    return request<DetectRecord>(`/api/v1/detections/${encodeURIComponent(recordId)}`);
  },

  async createBatch(serialNos: string[], faultCategory: FaultCategory, deviceFiles?: Record<string, string[]>): Promise<BackendBatchRun> {
    const batch = await request<BackendBatchRun>('/api/v1/detections/batch', {
      method: 'POST',
      body: JSON.stringify({ serialNos, faultCategory, deviceFiles }),
    });
    trackBackendEvent('batch.create', 'fault_query', { faultCategory, totalCount: serialNos.length, batchId: batch.batchId });
    return batch;
  },

  getBatch(batchId: string): Promise<BackendBatchRun> {
    const id = batchId.replace(/^MULTI-/, '');
    return request<BackendBatchRun>(`/api/v1/batch-tasks/${encodeURIComponent(id)}`);
  },

  /** @deprecated Use getRecordsPage() for server-side pagination */
  async getRecords(): Promise<DetectRecord[]> {
    let allItems: DetectRecord[] = [];
    let currentPage = 1;
    const pageSize = 100;
    while (currentPage <= 100) {
      const page = await request<{ items: DetectRecord[] }>(`/api/v1/records?page=${currentPage}&page_size=${pageSize}`);
      allItems = [...allItems, ...page.items];
      if (page.items.length < pageSize) {
        break;
      }
      currentPage += 1;
    }
    trackBackendEvent('records.view', 'records', { resultCount: allItems.length });
    return allItems;
  },

  async getRecordsPage(params: {
    page?: number;
    pageSize?: number;
    faultCategory?: string;
    conclusion?: string;
    serialNo?: string;
    dateFrom?: string;
    dateTo?: string;
    accountId?: string;
  } = {}): Promise<{ items: DetectRecord[]; total: number; page: number; pageSize: number }> {
    const qs = new URLSearchParams();
    qs.set('page', String(params.page ?? 1));
    qs.set('page_size', String(params.pageSize ?? 20));
    if (params.faultCategory) qs.set('fault_category', params.faultCategory);
    if (params.conclusion) qs.set('conclusion', params.conclusion);
    if (params.serialNo) qs.set('serial_no', params.serialNo);
    if (params.dateFrom) qs.set('date_from', params.dateFrom);
    if (params.dateTo) qs.set('date_to', params.dateTo);
    if (params.accountId) qs.set('account_id', params.accountId);
    const data = await request<{ items: DetectRecord[]; total: number; page: number; page_size: number }>(
      `/api/v1/records?${qs.toString()}`
    );
    trackBackendEvent('records.view', 'records', { page: data.page, total: data.total });
    return { items: data.items, total: data.total, page: data.page, pageSize: data.page_size };
  },

  getRecordsStats(): Promise<{ total: number; allowed: number; notAllowed: number; pending: number }> {
    return request<{ total: number; allowed: number; notAllowed: number; pending: number }>('/api/v1/records/stats');
  },

  exportRecordsCsvUrl(params: {
    faultCategory?: string;
    conclusion?: string;
    serialNo?: string;
    dateFrom?: string;
    dateTo?: string;
    accountId?: string;
  } = {}): string {
    const qs = new URLSearchParams();
    if (params.faultCategory) qs.set('fault_category', params.faultCategory);
    if (params.conclusion) qs.set('conclusion', params.conclusion);
    if (params.serialNo) qs.set('serial_no', params.serialNo);
    if (params.dateFrom) qs.set('date_from', params.dateFrom);
    if (params.dateTo) qs.set('date_to', params.dateTo);
    if (params.accountId) qs.set('account_id', params.accountId);
    const token = getStoredToken();
    if (token) qs.set('token', token);
    const query = qs.toString();
    return `${API_BASE_URL}/api/v1/records/export${query ? `?${query}` : ''}`;
  },

  async updateFeedback(recordId: string, verdictAdoption: 'Yes' | 'No' | 'Not recorded', verdictRejectionReason = ''): Promise<DetectRecord> {
    const record = await request<DetectRecord>(`/api/v1/records/${encodeURIComponent(recordId)}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ verdictAdoption, verdictRejectionReason }),
    });
    trackBackendEvent('feedback.update', 'records', { recordId, verdictAdoption });
    return record;
  },

  async deleteRecord(recordId: string): Promise<{ id: string; isVisibleInWorkbench: boolean }> {
    const res = await request<{ id: string; isVisibleInWorkbench: boolean }>(`/api/v1/records/${encodeURIComponent(recordId)}`, {
      method: 'DELETE',
    });
    trackBackendEvent('records.delete', 'records', { recordId });
    return res;
  },

  async batchDeleteRecords(recordIds: string[]): Promise<{ deletedIds: string[] }> {
    const res = await request<{ deletedIds: string[] }>('/api/v1/records/batch-delete', {
      method: 'POST',
      body: JSON.stringify({ recordIds }),
    });
    trackBackendEvent('records.batchDelete', 'records', { count: recordIds.length });
    return res;
  },

  listChatSessions(): Promise<ChatSession[]> {
    return request<ChatSession[]>('/api/v1/agent/chats');
  },

  createChatSession(id: string, title: string): Promise<ChatSession> {
    return request<ChatSession>('/api/v1/agent/chats', {
      method: 'POST',
      body: JSON.stringify({ id, title }),
    });
  },

  getChatSession(sessionId: string): Promise<ChatSession> {
    return request<ChatSession>(`/api/v1/agent/chats/${encodeURIComponent(sessionId)}`);
  },

  updateChatSession(sessionId: string, title: string): Promise<ChatSession> {
    return request<ChatSession>(`/api/v1/agent/chats/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    });
  },

  deleteChatSession(sessionId: string): Promise<{ success: boolean }> {
    return request<{ success: boolean }>(`/api/v1/agent/chats/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
    });
  },

  async sendChatMessage(sessionId: string, message: { id: string; role: string; content: string; options?: any }): Promise<ChatMessage> {
    const saved = await request<ChatMessage>(`/api/v1/agent/chats/${encodeURIComponent(sessionId)}/messages`, {
      method: 'POST',
      body: JSON.stringify(message),
    });
    trackBackendEvent('chat.message', 'agent_chat', { sessionId, role: message.role });
    return saved;
  },

  async sendChatTurn(sessionId: string, message: { id: string; assistantId: string; content: string }): Promise<ChatTurnResult> {
    const turn = await request<ChatTurnResult>(`/api/v1/agent/chats/${encodeURIComponent(sessionId)}/turns`, {
      method: 'POST',
      body: JSON.stringify(message),
    });
    trackBackendEvent('chat.turn', 'agent_chat', {
      sessionId,
    });
    return turn;
  },

  async uploadFile(file: File): Promise<{ id: string; filename: string; public_url: string }> {
    const formData = new FormData();
    formData.append('file', file);
    const uploaded = await request<{ id: string; filename: string; public_url: string }>('/api/v1/files/upload', {
      method: 'POST',
      body: formData,
    });
    trackBackendEvent('file.upload', 'file_upload', { filename: uploaded.filename, size: file.size, type: file.type });
    return uploaded;
  },
};
