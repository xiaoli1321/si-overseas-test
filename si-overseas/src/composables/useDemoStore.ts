import { computed, ref, watch } from 'vue';
import { backendApi, backendEnabled, type BackendBatchRun } from '@/api/backend';
import { cloneAccountProfile, MOCK_ACCOUNT_PROFILES, resolveAccountProfile } from '@/mocks/accounts';
import { CUSTOMER_EMAIL, MOCK_DEVICE_BY_SN, MOCK_DEVICES } from '@/mocks/devices';
import {
  assertValidThresholdRules,
  clearStoredThresholdProfile,
  cloneThresholdProfile,
  cloneThresholdRules,
  defaultThresholdProfile,
  loadStoredThresholdProfile,
  persistThresholdProfile,
} from '@/composables/thresholdProfile';
import type { Device, DeviceStatus, FaultCategory, FaultMapping } from '@/types/device';
import type { DashboardStats, DetectRecord, DetectSession, VerdictAdoption, VerdictPresentation } from '@/types/record';
import type { ThresholdDisplaySettings, ThresholdProfile, ThresholdRules } from '@/types/threshold';
import type { AccountProfile } from '@/types/account';

const CURRENT_USER_STORAGE_KEY = 'si-overseas-current-user';
const RECORDS_STORAGE_KEY = 'si-overseas-detect-records';

function loadStoredCurrentUser() {
  try {
    return window.localStorage.getItem(CURRENT_USER_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

function loadStoredRecords(): DetectRecord[] {
  try {
    const raw = window.localStorage.getItem(RECORDS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(normalizeDetectRecord) : [];
  } catch {
    return [];
  }
}

function normalizeEmail(value: string) {
  return value.trim().toLowerCase();
}

function normalizeDetectRecord(record: DetectRecord): DetectRecord {
  return {
    ...record,
    id: record.id !== undefined && record.id !== null ? String(record.id) : record.id,
    faultSubtype: record.faultSubtype ?? '',
    verdictAdoption: record.verdictAdoption ?? 'Not recorded',
    verdictRejectionReason: record.verdictRejectionReason ?? '',
  };
}

function isTerminalRecord(record: DetectRecord): boolean {
  return record.status === 'complete' || record.status === 'completed' || record.status === 'failed';
}

function isProcessingRecord(record: DetectRecord): boolean {
  return record.status === 'pending' || record.status === 'processing';
}

function delay(ms: number) {
  return new Promise(resolve => window.setTimeout(resolve, ms));
}

// === Core global state ===
// Device matches returned by the current search or filter.
const searchResults = ref<Device[]>([]);
// Device cache keyed by SN to avoid reloading the same device across views.
const deviceCache = ref<Record<string, Device>>({});
// Saved or loaded diagnosis history records.
const records = ref<DetectRecord[]>(loadStoredRecords());
// Active workspace diagnosis sessions, including single-device and batch groups.
const sessions = ref<DetectSession[]>([]);
// Email account for the currently signed-in user.
const currentUser = ref(loadStoredCurrentUser());
const currentAccountProfile = ref<AccountProfile | null>(null);
// Currently selected device for diagnosis.
const selectedDevice = ref<Device | null>(null);
// Active metric threshold profile.
const activeThresholdProfile = ref<ThresholdProfile>(loadStoredThresholdProfile());
// Backend API connection state for online mode versus local mock mode.
const backendOnline = ref(backendEnabled());
// Remote stats cache for online mode.
const remoteStats = ref<{ total: number; allowed: number; notAllowed: number; pending: number } | null>(null);
let remoteStatsRequest: Promise<void> | null = null;
let remoteStatsRequestId = 0;

// === Computed values ===
// Resolve the account and role profile from the current email address.
const currentAccount = computed(() => currentAccountProfile.value ?? resolveAccountProfile(currentUser.value));
const canCreateUsers = computed(() => currentAccount.value.role === 'manager');
// Manager accounts (Sibionics internal) see cross-account views: the account
// center and the per-account column/filter on Detection History.
const isManager = computed(() => currentAccount.value.role === 'manager');
const canManageThresholds = computed(() => true);
// Diagnosis records visible to the current dealer account.
const visibleRecords = computed(() => {
  const account = currentAccount.value;
  return records.value.filter(record => record.dealerId === account.dealerId);
});

const dashboard = computed<DashboardStats>(() => {
  if (backendOnline.value && remoteStats.value) {
    return remoteStats.value;
  }
  return {
    total: visibleRecords.value.length,
    allowed: visibleRecords.value.filter(record => record.afterSales === 'Replacement Eligible').length,
    notAllowed: visibleRecords.value.filter(record => record.afterSales === 'Not Eligible').length,
    pending: visibleRecords.value.filter(record => record.afterSales === 'Under Review').length,
  };
});

const currentFault = computed(() => selectedDevice.value?.fault);

watch(currentUser, value => {
  try {
    window.localStorage.setItem(CURRENT_USER_STORAGE_KEY, value);
  } catch {
    // Demo storage can be unavailable in private or restricted browser contexts.
  }
});

watch(records, value => {
  try {
    window.localStorage.setItem(RECORDS_STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Demo storage can be unavailable in private or restricted browser contexts.
  }
}, { deep: true });

function normalizeSnQuery(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9]/g, '');
}

function cacheKeyForSn(value: string) {
  return normalizeSnQuery(value).toUpperCase();
}

function cacheDevice(device: Device): Device {
  const copy = { ...device };
  deviceCache.value = {
    ...deviceCache.value,
    [cacheKeyForSn(device.sn)]: copy,
  };
  return { ...copy };
}

function cacheDevices(devices: Device[]): Device[] {
  return devices.map(cacheDevice);
}

function findCachedDeviceBySn(query: string): Device | undefined {
  const cached = deviceCache.value[cacheKeyForSn(query)];
  return cached ? { ...cached } : undefined;
}

function deviceFromRecordEvidence(record: DetectRecord): Device | undefined {
  const evidenceDevice = (record as DetectRecord & { evidence?: { device?: any } }).evidence?.device;
  if (!evidenceDevice?.sn) return undefined;

  const sn = evidenceDevice.sn;
  const existing = findCachedDeviceBySn(sn);

  // Adapt snake_case or partial evidence fields to camelCase frontend Device format
  const wearDaysRaw = evidenceDevice.wear_days !== undefined ? evidenceDevice.wear_days : evidenceDevice.wearDays;
  const wearDays = typeof wearDaysRaw === 'number' ? Math.floor(wearDaysRaw) : 0;
  const wearHours = evidenceDevice.wearHours !== undefined ? evidenceDevice.wearHours : (typeof wearDaysRaw === 'number' ? Math.round((wearDaysRaw - wearDays) * 24) : 0);

  let status: DeviceStatus = 'wearing';
  if (evidenceDevice.status) {
    status = evidenceDevice.status;
  } else if (evidenceDevice.device_status !== undefined) {
    const ds = Number(evidenceDevice.device_status);
    status = (ds === 4 || ds === 5 || ds === 6) ? 'abnormal' : 'wearing';
  }

  const type = evidenceDevice.type || evidenceDevice.device_type || 'GS1';
  const activatedAt = evidenceDevice.activatedAt
    || evidenceDevice.activated_at
    || evidenceDevice.activated
    || evidenceDevice.enable_time
    || existing?.activatedAt
    || '';
  const lastDataAt = evidenceDevice.lastDataAt
    || evidenceDevice.last_data_at
    || evidenceDevice.last_upload
    || evidenceDevice.latest_upload_at
    || existing?.lastDataAt
    || '';
  let fault = evidenceDevice.fault || existing?.fault || null;

  if (!fault && record.status === 'complete' && record.faultCategory) {
    fault = {
      faultCategory: record.faultCategory as FaultCategory,
      faultSubtype: record.faultSubtype || '',
      expectedAfterSales: record.afterSales as any,
      notes: record.reasonSummary || '',
    };
  }

  const merged: Device = {
    sn,
    type,
    status,
    activatedAt,
    wearDays,
    wearHours,
    lastDataAt,
    hasServiceCard: evidenceDevice.hasServiceCard !== undefined ? evidenceDevice.hasServiceCard : existing?.hasServiceCard,
    fault,
    email: existing?.email,
  };

  return cacheDevice(merged);
}

function searchDeviceMatches(query: string): Device[] {
  const needle = normalizeSnQuery(query);
  if (!needle) return [];
  return MOCK_DEVICES
    .filter(device => normalizeSnQuery(device.sn).includes(needle))
    .map(device => ({ ...device }));
}

function searchBySn(query: string): Device[] {
  searchResults.value = searchDeviceMatches(query);
  return searchResults.value;
}

async function searchBySnRemote(query: string): Promise<Device[]> {
  if (!backendOnline.value) return searchBySn(query);
  try {
    const matches = await backendApi.searchDevices(query);
    searchResults.value = cacheDevices(matches);
    return searchResults.value;
  } catch {
    searchResults.value = [];
    return [];
  }
}

function searchBySnLines(lines: string[]): Device[] {
  const seen = new Set<string>();
  const matches: Device[] = [];

  for (const line of lines) {
    for (const device of searchDeviceMatches(line)) {
      if (seen.has(device.sn)) continue;
      seen.add(device.sn);
      matches.push(device);
    }
  }

  searchResults.value = matches;
  return matches;
}

async function searchBySnLinesRemote(lines: string[]): Promise<Device[]> {
  const terms = lines.map(line => line.trim()).filter(Boolean);
  if (!backendOnline.value) return searchBySnLines(terms);
  try {
    const matches = await backendApi.searchDevices(terms.join('\n'));
    searchResults.value = cacheDevices(matches);
    return searchResults.value;
  } catch {
    searchResults.value = [];
    return [];
  }
}

function findExactDeviceBySn(query: string): Device | undefined {
  const needle = normalizeSnQuery(query);
  if (!needle) return undefined;
  const cached = findCachedDeviceBySn(query);
  if (cached) return cached;
  const device = MOCK_DEVICES.find(item => normalizeSnQuery(item.sn) === needle);
  return device ? { ...device } : undefined;
}

async function findExactDeviceBySnRemote(query: string): Promise<Device | undefined> {
  if (!backendOnline.value) return findExactDeviceBySn(query);
  try {
    return cacheDevice(await backendApi.getDevice(query));
  } catch {
    return undefined;
  }
}

function getFaultForSn(sn: string): FaultMapping | undefined {
  return MOCK_DEVICE_BY_SN.get(sn)?.fault ?? undefined;
}

function findAccountByEmail(email: string): AccountProfile | undefined {
  const normalized = normalizeEmail(email);
  const account = MOCK_ACCOUNT_PROFILES.find(profile => normalizeEmail(profile.email) === normalized);
  return account ? cloneAccountProfile(account) : undefined;
}

function validateAccountCredentials(email: string, password: string): boolean {
  const account = findAccountByEmail(email);
  return Boolean(account && account.password === password);
}

async function loginRemote(email: string, password: string): Promise<boolean> {
  if (!backendOnline.value) {
    if (!validateAccountCredentials(email, password)) return false;
    const account = findAccountByEmail(email);
    currentAccountProfile.value = account ?? null;
    currentUser.value = account?.email ?? email;
    return true;
  }
  try {
    const account = await backendApi.login(email, password);
    currentAccountProfile.value = account;
    currentUser.value = account.email;
    await loadRemoteBootstrap();
    return true;
  } catch (err: any) {
    if (err && err.isNetworkError) {
      return false;
    }
    return false;
  }
}

async function createUserRemote(
  email: string,
  password: string,
  distributorName: string,
  role?: AccountProfile['role'],
): Promise<AccountProfile> {
  if (!backendOnline.value) {
    throw new Error('Backend is required to create users.');
  }
  const payload = {
    email,
    password,
    distributorName,
    ...(role ? { role } : {}),
  };
  return await backendApi.createUser(payload);
}

function selectDevice(sn: string): Device {
  const device = MOCK_DEVICE_BY_SN.get(sn);
  if (!device) throw new Error(`Unknown SN: ${sn}`);
  selectedDevice.value = { ...device };
  return selectedDevice.value;
}

async function selectDeviceRemote(sn: string): Promise<Device> {
  if (!backendOnline.value) return selectDevice(sn);
  const cached = findCachedDeviceBySn(sn);
  if (cached) {
    selectedDevice.value = { ...cached };
  }
  try {
    const device = await backendApi.getDevice(sn);
    selectedDevice.value = cacheDevice(device);
    return selectedDevice.value;
  } catch {
    if (selectedDevice.value?.sn === sn) return selectedDevice.value;
    const mock = MOCK_DEVICE_BY_SN.get(sn);
    if (mock) {
      selectedDevice.value = { ...mock };
      return selectedDevice.value;
    }
    throw new Error(`Unknown SN: ${sn}`);
  }
}

// 植入失败 (Application failure) 场景：设备通常尚未激活，海外设备接口查询不到（返回为空）。
// 因此不调用查询接口，直接信任用户输入的 SN / deviceName，构造一份占位设备用于展示与后续检测。
function buildUnactivatedDevice(sn: string): Device {
  const normalized = sn.trim().toUpperCase();
  return cacheDevice({
    sn: normalized,
    type: 'GS1',
    status: 'wearing',
    activatedAt: '',
    wearDays: 0,
    wearHours: 0,
    lastDataAt: '',
    hasServiceCard: null,
    fault: null,
  });
}

function selectUnactivatedDevice(sn: string): Device {
  const device = buildUnactivatedDevice(sn);
  selectedDevice.value = device;
  return device;
}

function recordId(sn: string, index: number) {
  return `FD-${String(index).padStart(4, '0')}-${sn.slice(-4)}`;
}

function nextRecordId(sn: string) {
  const maxIndex = records.value.reduce((max, record) => {
    const match = /^FD-(\d+)-/.exec(record.id);
    return match ? Math.max(max, Number(match[1])) : max;
  }, 0);
  let nextIndex = maxIndex + 1;
  let nextId = recordId(sn, nextIndex);
  const existingIds = new Set(records.value.map(record => record.id));
  while (existingIds.has(nextId)) {
    nextIndex += 1;
    nextId = recordId(sn, nextIndex);
  }
  return nextId;
}

function demoRecordId(sn: string, index: number) {
  return `FD-DEMO-${String(index).padStart(4, '0')}-${sn.slice(-4)}`;
}

function sessionId(sn: string, index: number) {
  return `DS-${String(index).padStart(4, '0')}-${sn.slice(-4)}`;
}

type DetectSessionOptions = Pick<DetectSession, 'source' | 'batchId' | 'stepLabel' | 'progress'>;
type DetectSessionPatch = Partial<Pick<DetectSession, 'stepLabel' | 'progress' | 'status' | 'recordId'>>;

interface InaccuracyDecision {
  faultSubtype: string;
  conclusion: DetectRecord['conclusion'];
  afterSales: DetectRecord['afterSales'];
  reasonSummary: string;
}

function defaultReasonForDevice(device: Device): string {
  return device.fault?.notes ?? 'No mapped fault';
}

function dataInaccuracyDemoMetrics(device: Device) {
  const subtype = device.fault?.faultSubtype;
  if (!subtype) return null;

  if (subtype.includes('Persistent Low')) {
    return {
      pattern: 'low' as const,
      lowHours: 5.2,
      lowestMmol: 2.7,
      peak24hMmol: 7.4,
    };
  }

  if (subtype.includes('No Fluctuation')) {
    return {
      pattern: 'nofluc' as const,
      flatHours: 9.3,
      floorMmol: 4.8,
      swingMmol: 0.4,
    };
  }

  if (subtype.includes('Jump')) {
    return {
      pattern: 'jump' as const,
      maxJumpMmol: 4.2,
      maxConsecutive: 5,
    };
  }

  return null;
}

function afterSalesForHit(device: Device, hit: boolean): DetectRecord['afterSales'] {
  if (!hit) return 'Not Eligible';
  return device.fault?.expectedAfterSales ?? 'Not Eligible';
}

function evaluateDataInaccuracy(device: Device, profile: ThresholdProfile, fileIds?: string[]): InaccuracyDecision {
  const rules = profile.rules.inaccuracy;
  const metrics = dataInaccuracyDemoMetrics(device);

  if (!metrics) {
    if (device.fault?.faultSubtype?.includes('Data Deviation') || !device.fault) {
      if (fileIds && fileIds.length >= 4) {
        const confirmsDeviation = device.sn === 'P2251212823BFV10'
          || device.sn === 'P2251212824CGW21'
          || (device.fault?.faultSubtype?.includes('Data Deviation') ?? false)
          || !device.fault;

        if (confirmsDeviation) {
          const cgm1 = 5.5, bgm1 = 7.2; // 30.9% deviation
          const cgm2 = 6.1, bgm2 = 8.3; // 36.1% deviation
          const reasons = [
            'All 2 groups of CGM/BGM comparison readings confirm significant deviation.',
            `Group 1: CGM reading ${cgm1.toFixed(1)} mmol/L, BGM reading ${bgm1.toFixed(1)} mmol/L. Actual relative deviation 30.9% (configured threshold >= 20.0%). Result: abnormal deviation`,
            `Group 2: CGM reading ${cgm2.toFixed(1)} mmol/L, BGM reading ${bgm2.toFixed(1)} mmol/L. Actual relative deviation 36.1% (configured threshold >= 20.0%). Result: abnormal deviation`
          ];
          return {
            faultSubtype: 'Data Deviation Detected',
            conclusion: 'Issue Detected',
            afterSales: device.hasServiceCard ? (device.fault?.expectedAfterSales ?? 'Not Eligible') : 'Not Eligible',
            reasonSummary: reasons.join('\n'),
          };
        }
      }
      
      return {
        faultSubtype: 'Data Deviation Review Required',
        conclusion: 'No Issue',
        afterSales: 'Under Review',
        reasonSummary: 'Curve screening did not match automatic rules; paired CGM/BGM evidence is required.',
      };
    }

    if (fileIds && fileIds.length >= 4) {
      const cgm1 = 5.6, bgm1 = 5.8; // 3.6% deviation
      const cgm2 = 6.0, bgm2 = 6.2; // 3.3% deviation
      const reasons = [
        'One or more groups of CGM/BGM comparison readings do not show significant deviation.',
        `Group 1: CGM reading ${cgm1.toFixed(1)} mmol/L, BGM reading ${bgm1.toFixed(1)} mmol/L. Actual relative deviation 3.6% (configured threshold >= 20.0%). Result: normal deviation`,
        `Group 2: CGM reading ${cgm2.toFixed(1)} mmol/L, BGM reading ${bgm2.toFixed(1)} mmol/L. Actual relative deviation 3.3% (configured threshold >= 20.0%). Result: normal deviation`
      ];
      return {
        faultSubtype: 'Accuracy Within Normal Limits',
        conclusion: 'No Issue',
        afterSales: 'Not Eligible',
        reasonSummary: reasons.join('\n'),
      };
    }

    return {
      faultSubtype: 'Data Deviation Review Required',
      conclusion: 'No Issue',
      afterSales: 'Under Review',
      reasonSummary: 'Curve screening did not match automatic rules; paired CGM/BGM evidence is required.',
    };
  }

  if (metrics.pattern === 'low') {
    const r = rules.lowPersist;
    const hit = metrics.lowestMmol <= r.belowMmol
      && metrics.lowHours >= r.minHours
      && metrics.peak24hMmol <= r.max24hMmol;
    return {
      faultSubtype: hit ? (device.fault?.faultSubtype ?? 'No qualifying curve pattern') : 'No qualifying curve pattern',
      conclusion: hit ? 'Issue Detected' : 'No Issue',
      afterSales: afterSalesForHit(device, hit),
      reasonSummary: hit
        ? `Persistent Low meets profile v${profile.version}: ${metrics.lowHours}h below ${r.belowMmol} mmol/L with 24h peak ${metrics.peak24hMmol} mmol/L <= ${r.max24hMmol} mmol/L; threshold duration is ${r.minHours}h.`
        : `Persistent Low does not meet profile v${profile.version}: ${metrics.lowHours}h below ${r.belowMmol} mmol/L with 24h peak ${metrics.peak24hMmol} mmol/L; required duration is ${r.minHours}h and 24h peak cap is ${r.max24hMmol} mmol/L.`,
    };
  }

  if (metrics.pattern === 'nofluc') {
    const r = rules.noFluctuation;
    const hit = metrics.floorMmol >= r.floorMmol
      && metrics.flatHours >= r.minHours
      && metrics.swingMmol <= r.maxSwingMmol;
    return {
      faultSubtype: hit ? (device.fault?.faultSubtype ?? 'No qualifying curve pattern') : 'No qualifying curve pattern',
      conclusion: hit ? 'Issue Detected' : 'No Issue',
      afterSales: afterSalesForHit(device, hit),
      reasonSummary: hit
        ? `No Fluctuation meets profile v${profile.version}: ${metrics.flatHours}h >= ${r.minHours}h, floor ${metrics.floorMmol} mmol/L >= ${r.floorMmol} mmol/L, swing ${metrics.swingMmol} mmol/L <= ${r.maxSwingMmol} mmol/L.`
        : `No Fluctuation does not meet profile v${profile.version}: ${metrics.flatHours}h, floor ${metrics.floorMmol} mmol/L, swing ${metrics.swingMmol} mmol/L; current thresholds are ${r.minHours}h, ${r.floorMmol} mmol/L floor, and ${r.maxSwingMmol} mmol/L max swing.`,
    };
  }

  const r = rules.jump;
  const hit = metrics.maxJumpMmol > r.deltaMmol && metrics.maxConsecutive >= r.consecutive;
  return {
    faultSubtype: hit ? (device.fault?.faultSubtype ?? 'No qualifying curve pattern') : 'No qualifying curve pattern',
    conclusion: hit ? 'Issue Detected' : 'No Issue',
    afterSales: afterSalesForHit(device, hit),
    reasonSummary: hit
      ? `Jump Points meets profile v${profile.version}: max jump ${metrics.maxJumpMmol} mmol/L > ${r.deltaMmol} mmol/L and ${metrics.maxConsecutive} consecutive jumps >= ${r.consecutive}.`
      : `Jump Points does not meet profile v${profile.version}: max jump ${metrics.maxJumpMmol} mmol/L and ${metrics.maxConsecutive} consecutive jumps; thresholds are > ${r.deltaMmol} mmol/L and >= ${r.consecutive}.`,
  };
}

function unsupportedCategoryDecision(device: Device, category: FaultCategory): InaccuracyDecision {
  return {
    faultSubtype: `${category} not detected`,
    conclusion: 'No Issue',
    afterSales: 'Not Eligible',
    reasonSummary: `${category} is not supported by this mock device. The Excel-mapped scenario for ${device.sn} is ${device.fault?.faultCategory ?? 'None'}, so after-sales is not recommended for this selected path.`,
  };
}

function buildDetectDecision(
  device: Device,
  profile: ThresholdProfile,
  selectedCategory?: FaultCategory,
  fileIds?: string[]
): InaccuracyDecision {
  const category = selectedCategory ?? device.fault?.faultCategory ?? 'Data accuracy';

  if (!device.fault) {
    if (category === 'Data accuracy') {
      return evaluateDataInaccuracy(device, profile, fileIds);
    }
    return {
      faultSubtype: `${category} not detected`,
      conclusion: 'No Issue',
      afterSales: 'Not Eligible',
      reasonSummary: `No fault detected for device ${device.sn}.`,
    };
  }

  if (category !== device.fault.faultCategory) {
    return unsupportedCategoryDecision(device, category);
  }

  if (category === 'Data accuracy') {
    return evaluateDataInaccuracy(device, profile, fileIds);
  }

  return {
    faultSubtype: device.fault.faultSubtype,
    conclusion: device.fault.expectedAfterSales === 'Not Eligible' ? 'No Issue' : 'Issue Detected',
    afterSales: device.fault.expectedAfterSales,
    reasonSummary: defaultReasonForDevice(device),
  };
}

function requiresDataDeviationReview(sn: string, selectedCategory: FaultCategory): boolean {
  if (selectedCategory !== 'Data accuracy') return false;
  const device = findCachedDeviceBySn(sn) ?? (selectedDevice.value?.sn === sn ? selectedDevice.value : undefined) ?? MOCK_DEVICE_BY_SN.get(sn);
  if (!device) throw new Error(`Unknown SN: ${sn}`);
  if (!device.fault) return true;
  if (selectedCategory !== device.fault.faultCategory) return true;
  if (device.fault.faultSubtype?.includes('Data Deviation')) return true;

  const firstPass = buildDetectDecision(device, activeThresholdProfile.value, selectedCategory);
  return firstPass.conclusion === 'No Issue'
    && (firstPass.afterSales === 'Not Eligible' || firstPass.afterSales === 'Under Review')
    && (
      device.fault.faultSubtype?.includes('Persistent Low')
      || device.fault.faultSubtype?.includes('No Fluctuation')
      || device.fault.faultSubtype?.includes('Jump')
    );
}

function buildDeviationReviewRecord(device: Device): DetectRecord {
  const profile = cloneThresholdProfile(activeThresholdProfile.value);
  const initiator = resolveAccountProfile(currentUser.value);
  return {
    id: nextRecordId(device.sn),
    sn: device.sn,
    email: device.email ?? '',
    initiatorEmail: initiator.email,
    initiatorName: initiator.displayName,
    dealerId: initiator.dealerId,
    dealerName: initiator.dealerName,
    organizationName: initiator.organizationName,
    organizationType: initiator.organizationType,
    region: initiator.region,
    deviceType: device.type,
    faultCategory: 'Data accuracy',
    faultSubtype: 'Data Deviation Detected',
    conclusion: 'Issue Detected',
    afterSales: device.fault?.expectedAfterSales ?? 'Under Review',
    timestamp: new Date().toISOString(),
    thresholdProfileVersion: profile.version,
    thresholdSnapshot: profile,
    reasonSummary: `First-pass curve screening did not confirm persistent low, no fluctuation, or jump-point under profile v${profile.version}. Two paired CGM/BGM image groups were collected for data-deviation review. ${device.fault?.notes ?? ''}`,
    verdictAdoption: 'Not recorded',
    verdictRejectionReason: '',
  };
}

function mockPresentationForRecord(record: DetectRecord, device?: Device): VerdictPresentation | null {
  const base = {
    templateVersion: 'frontend-mock-standard-cases-v1',
    supportingMaterials: 'Not displayed' as string | string[],
  };
  if (record.faultCategory === 'Data accuracy') {
    if (record.faultSubtype.includes('Persistent Low')) {
      const rules = activeThresholdProfile.value.rules;
      const belowMmol = rules.inaccuracy.lowPersist.belowMmol;
      const minHours = rules.inaccuracy.lowPersist.minHours;
      const max24hMmol = rules.inaccuracy.lowPersist.max24hMmol;
      return {
        ...base,
        scenarioKey: 'data_accuracy.first_pass.persistent_low',
        badge: 'WARRANTY ELIGIBLE',
        title: 'Persistent Low Glucose Detected',
        summary: 'The glucose curve has been low recently, please see "Basis for the Verdict" below for details',
        whatWeFound: `Persistent-low pattern was detected. Low 5.2 h below ${belowMmol} mmol/L, 24h peak 7.4 mmol/L after 48h`,
        whyThisResult: `Persistent-low after-sales rule is met. Low <= ${belowMmol} for ${minHours}h, 24h peak <= ${max24hMmol}. Current record meets all thresholds`,
        possibleCauses: 'Sensor has been scratched or bumped, causing it to loosen, or the electrode has not been fully inserted into the subcutaneous tissue.',
        guidance: {
          afterSalesStatus: 'You can continue to after-sales from this result.',
          why: 'The first-pass CGM screening hit the persistent low rule for this record, so the issue can move forward without the paired screenshot branch.',
          wearingAdvice: 'Keep wearing the device unless it has already fallen off or support instructs removal.',
          nextAction: 'Continue to the after-sales application with this screening result.',
        },
      };
    }
    if (record.faultSubtype.includes('No Fluctuation')) {
      const rules = activeThresholdProfile.value.rules;
      const floorMmol = rules.inaccuracy.noFluctuation.floorMmol;
      const minHours = rules.inaccuracy.noFluctuation.minHours;
      const maxSwingMmol = rules.inaccuracy.noFluctuation.maxSwingMmol;
      return {
        ...base,
        scenarioKey: 'data_accuracy.first_pass.no_fluctuation',
        badge: 'WARRANTY ELIGIBLE',
        title: 'No Fluctuation Detected',
        summary: 'The recent blood glucose curve shows a long gentle range with minimal change. For details, see "Basis for the Verdict" below',
        whatWeFound: 'No-fluctuation pattern was detected. Flat 9.3h, Swing about 0.4 mmol/L. after 48h',
        whyThisResult: `No-fluctuation after-sales rule is met. Needs >= ${floorMmol} for ${minHours}h, Swing <= ${maxSwingMmol}mmol/L. Current record matches the flat-line rule`,
        possibleCauses: '',
        guidance: {
          afterSalesStatus: 'You can continue to after-sales from this result.',
          why: 'The first-pass CGM screening hit the no fluctuation rule for this record, so the issue can move forward without the paired screenshot branch.',
          wearingAdvice: 'Keep wearing the device unless it has already fallen off or support instructs removal.',
          nextAction: 'Continue to the after-sales application with this screening result.',
        },
      };
    }
    if (record.faultSubtype.includes('Jump')) {
      const rules = activeThresholdProfile.value.rules;
      const deltaMmol = rules.inaccuracy.jump.deltaMmol;
      const consecutive = rules.inaccuracy.jump.consecutive;
      return {
        ...base,
        scenarioKey: 'data_accuracy.first_pass.jump_points',
        badge: 'WARRANTY ELIGIBLE',
        title: 'Glucose Jump Pattern Detected',
        summary: 'The recent blood glucose curve showed repeated jumping points within the screening window.',
        whatWeFound: 'Jump-point pattern was detected. Max step 3.4 mmol/L, Consecutive jumps 3 after 48h',
        whyThisResult: `Jump-point after-sales rule is met. Adjacent jump > ${deltaMmol}, At least ${consecutive} consecutive steps. Current record matches the jump rule`,
        possibleCauses: 'The tissue around the sensor moves, resulting in some changes in the soft needle in the implanted part, and small probability events such as sensor loosening cannot be ruled out in some specific cases',
        guidance: {
          afterSalesStatus: 'You can continue to after-sales from this result.',
          why: 'The first-pass CGM screening hit the jump points rule for this record, so the issue can move forward without the paired screenshot branch.',
          wearingAdvice: 'Keep wearing the device unless it has already fallen off or support instructs removal.',
          nextAction: 'Continue to the after-sales application with this screening result.',
        },
      };
    }
    if (record.faultSubtype.includes('Data Deviation')) {
      const wearHoursTotal = (device?.wearDays ?? 0) * 24 + (device?.wearHours ?? 0);
      const isWithin48 = wearHoursTotal < 48;
      const isEligible = record.afterSales === 'Replacement Eligible';
      const rules = activeThresholdProfile.value.rules;
      
      if (record.afterSales === 'Under Review') {
        return {
          ...base,
          scenarioKey: 'data_accuracy.first_pass.path_switching',
          badge: '/',
          title: '/',
          summary: '/',
          whatWeFound: '/',
          whyThisResult: '/',
          possibleCauses: '/',
          guidance: {
            text: 'Cannot directly enter after-sales based on the first round curve results; Enter the blood sugar deviation judgment and continue taking screenshots for comparison.',
          },
        };
      }
      
      if (isWithin48) {
        const deviationMmol = rules.inaccuracy.deviation.within48hDeviationMmol;
        const pairCount = rules.inaccuracy.deviation.within48hPairCount;
        if (isEligible) {
          return {
            ...base,
            scenarioKey: 'data_accuracy.paired.within_48_outside_range',
            badge: 'WARRANTY ELIGIBLE',
            title: 'Data deviation detected',
            summary: 'Device is within 48h of activation. The paired CGM and fingerstick screenshots hit the Large-bias check within 48h rule.',
            whatWeFound: 'OCR completed screenshot pair extraction. P1 5.5 vs 7.2, P2 6.1 vs 8.3. 2/2 pairs out of band. Timing valid',
            whyThisResult: `Within-48h deviation rule is met. Abs diff <= ${deviationMmol} mmol/L, Reject at ${pairCount} failed pairs. Current pair set reaches reject threshold`,
            possibleCauses: 'CGM application creates a tiny wound. During healing, immune activity may affect nearby glucose and cause temporary reading deviations. This is the “adjustment period.” After it passes, readings usually become more stable and accurate.',
            supportingMaterials: ['Pair 1 - CGM screenshot', 'Pair 1 - meter photo', 'Pair 2 - CGM screenshot', 'Pair 2 - meter photo', 'Screenshot timing'],
            guidance: {
              afterSalesStatus: 'You can continue to after-sales from this result.',
              why: `The paired CGM and fingerstick screenshots exceed the <= ${deviationMmol} mmol/L rule within the first 48 hours of wear.`,
              wearingAdvice: 'Guide users to continue wearing the device and monitoring the data, or guide them to remove it and make a replacement to them.',
              nextAction: 'If you decide to replace the device for the user, you can guide them to remove it.',
            },
          };
        } else {
          return {
            ...base,
            scenarioKey: 'data_accuracy.paired.within_48_within_range',
            badge: 'NOT WARRANTY ELIGIBLE',
            title: 'Accuracy check within 48h not detected',
            summary: 'The device is within 48h of activation. The current screenshot pairing is still within the allowed range.',
            whatWeFound: 'OCR pairing completed; display whether each set of values is in band and whether the time is independent.',
            whyThisResult: `Failure to meet the failure threshold of > ${deviationMmol} mmol/L required for at least ${pairCount} sets of comparison charts.`,
            possibleCauses: '',
            supportingMaterials: ['Pair 1 - CGM screenshot', 'Pair 1 - meter photo', 'Pair 2 - CGM screenshot', 'Pair 2 - meter photo', 'Screenshot timing'],
            guidance: {
              text: 'Cannot follow the data deviation path to enter after-sales service; if you still suspect the deviation, upload a more matching screenshot.',
            },
          };
        }
      } else {
        const after48hDeviationRangePct = rules.inaccuracy.deviation.after48hDeviationRangePct;
        if (isEligible) {
          return {
            ...base,
            scenarioKey: 'data_accuracy.paired.after_48_outside_range',
            badge: 'WARRANTY ELIGIBLE',
            title: 'Data deviation detected',
            summary: 'The device is after 48h of activation. The paired CGM and fingerstick screenshots hit the Accuracy check after 48h rule.',
            whatWeFound: 'OCR completed screenshot pair extraction. P1 5.5 vs 7.2, P2 6.1 vs 8.3. 2/2 pairs out of band. Timing valid',
            whyThisResult: `Accuracy check after 48h is met. Rule: 2/2 pairs must fail strict ${after48hDeviationRangePct}% consistency. Current pair set fails the strict ${after48hDeviationRangePct}% consistency check in both pairs.`,
            possibleCauses: 'CGM measures glucose in interstitial fluid, while BGM measures glucose in capillary blood. When glucose changes quickly, the difference between the two can be larger, so CGM accuracy cannot be assessed accurately.',
            supportingMaterials: ['Pair 1 - CGM screenshot', 'Pair 1 - meter photo', 'Pair 2 - CGM screenshot', 'Pair 2 - meter photo', 'Screenshot timing'],
            guidance: {
              afterSalesStatus: 'You can continue to after-sales from this result.',
              why: 'Both sets of comparative data exceeded the set range and met the after-sales conditions.',
              wearingAdvice: 'Guide users to continue wearing the device and monitoring the data, or guide them to remove it and make a replacement to them.',
              nextAction: 'If you decide to replace the device for the user, you can guide them to remove it.',
            },
          };
        } else {
          return {
            ...base,
            scenarioKey: 'data_accuracy.paired.after_48_within_range',
            badge: 'NOT WARRANTY ELIGIBLE',
            title: 'Accuracy check after 48h not detected',
            summary: 'Device snapshot is After 48h of activation. The reviewed CGM and fingerstick pairs stay inside the current review rule.',
            whatWeFound: 'OCR completed screenshot pair extraction. Stage After 48h of activation, P1 5.5 vs 5.8, P2 6.1 vs 6.3. All pairs stayed in band. Timing valid',
            whyThisResult: 'OCR completed screenshot pair extraction.',
            possibleCauses: 'The clinical evaluation of the accuracy of CGM is mainly evaluated through the "reference value 20/20% agreement rate", that is, when the monitoring value is > 4.4 mmol/L, the deviation from the reference value is within the range of ±20%; When the monitoring value is ≤ 4.4 mmol/L, the deviation is 1.1 mmol/L; The proportion of points deviating from the reference value is > 65%, which is the technical standard requirement of CGM.',
            supportingMaterials: ['Pair 1 - CGM screenshot', 'Pair 1 - meter photo', 'Pair 2 - CGM screenshot', 'Pair 2 - meter photo', 'Screenshot timing'],
            guidance: {
              afterSalesStatus: 'Do not continue to after-sales on the data-deviation path.',
              why: 'Neither of the two sets meets the condition that the comparison data exceeds the set range, so the current record does not meet this rule.',
              wearingAdvice: 'Continue normal wear guidance and keep the sensor in place unless support instructs removal.',
              nextAction: 'If mismatch is still a concern, upload a new set of timestamp-matched CGM and fingerstick screenshots for another review.',
            },
          };
        }
      }
    }
    return null;
  }
  if (record.faultCategory === 'Sensor falling off') {
    const detected = record.afterSales === 'Replacement Eligible';
    return {
      ...base,
      scenarioKey: detected ? 'fall_off.detected' : 'fall_off.not_detected',
      badge: detected ? 'WARRANTY ELIGIBLE' : 'NOT WARRANTY ELIGIBLE',
      title: detected ? 'Fall off detected' : 'Fall off not detected',
      summary: detected
        ? 'The record shows a sensor fall-off pattern, and the device is already in an abnormal state.'
        : 'The current record does not show a confirmed sensor fall-off pattern.',
      whatWeFound: detected
        ? 'Abnormal detachment-like state is present.'
        : `No confirmed detachment signal is present. State ${device?.status ?? 'N/A'}. Last Upload ${device?.lastDataAt ?? 'N/A'}`,
      whyThisResult: detected
        ? 'Detachment after-sales rule is met.'
        : `Detachment after-sales rule is not met. This path only accepts abnormal devices. Current state is ${device?.status ?? 'N/A'}`,
      possibleCauses: '',
      guidance: detected
        ? {
            afterSalesStatus: 'You can continue to after-sales from this result.',
            why: 'The current device matches the fall off rule.',
            wearingAdvice: 'Do not reattach the device if it has already fallen off.',
            nextAction: 'Continue to the after-sales application with this record.',
          }
        : {
            afterSalesStatus: 'Do not continue to after-sales on the fall off path. If the user has provided a picture of the device falling off, please make a manual judgment.',
            why: 'The current record does not show the abnormal device state required by the fall off rule.',
            wearingAdvice: 'Keep monitoring the device status in the app. If the user has provided a picture of the device falling off, please make a manual judgment.',
            nextAction: 'If the user provides photos proving the detachment, please consider the after-sales policy to decide whether to replace the product.',
          },
    };
  }
  if (record.faultCategory === 'Sensor Abnormal') {
    const detected = record.afterSales === 'Replacement Eligible';
    const init = record.faultSubtype.includes('Initialization');
    const waiting = record.faultSubtype === 'Waiting Recovery';
    const lowRecovery = record.faultSubtype === 'Low Recovery Possibility';

    let scenarioKey = 'sensor_abnormal.no_abnormality';
    let badge = 'NOT WARRANTY ELIGIBLE';
    let title = 'No malfunction detected';
    let summary = 'No abnormal sensor status has been detected on this device; therefore, after-sales support cannot be provided.';
    let whatWeFound = 'The current device entered the sensor abnormality review, but no abnormal conclusion was formed; display the current stage, status / clasp status, and latest signal time.';
    let whyThisResult = 'The confirmed sensor abnormality rule is not hit.';
    let possibleCauses = '';
    let guidance: any = {
      text: 'No abnormal state of the device has been detected, please make a manual judgment based on the specific display of the screenshot on the homepage of the user APP.',
    };

    if (waiting) {
      scenarioKey = 'sensor_abnormal.waiting_recovery';
      badge = 'PENDING REVIEW';
      title = 'Temporary sensor abnormality';
      summary = 'Temporary sensor abnormality, please check again in 3 hours to see whether it has returned to normal.';
      whatWeFound = 'A temporary abnormal sensor status was detected.';
      whyThisResult = 'This meets the rule of waiting 3 hours to check whether the device returns to normal. The device is currently recovering on its own, so please wait patiently for 3 hours and observe whether it returns to normal.';
      possibleCauses = 'This may be a rare issue caused by scratching or impact that loosens the sensor. It may also occur when muscle tissue at the insertion site is relatively abundant and muscle stretching affects the sensor electrode, which then impacts data transmission, so the system identifies it as abnormal.';
      guidance = {
        afterSalesStatus: 'Do not go to after-sales yet.',
        why: 'The device is still inside the recovery observation window, so the current result is not a confirmed fault.',
        wearingAdvice: 'Please advise the user to continue wearing the device and wait at least 3 hours to check if the condition has returned to normal.',
        nextAction: 'Wait for the recovery window to pass, then run detection again.',
      };
    } else if (detected) {
      badge = 'WARRANTY ELIGIBLE';
      if (init) {
        scenarioKey = 'sensor_abnormal.gs1_initialization';
        title = 'Initialization abnormality';
        summary = 'The device shows an abnormality during initialization.';
        whatWeFound = 'Initialization abnormality was detected on the current device.';
        whyThisResult = 'The initialization-abnormality rule is met.';
        possibleCauses = 'The guide needle may not have fully covered the soft needle after implantation, so the soft needle was not completely inserted under the skin and could not monitor glucose in interstitial fluid.';
        guidance = {
          afterSalesStatus: 'You can continue to after-sales from this result.',
          why: 'The current device matches the initialization-abnormality rule, so this record supports after-sales on the sensor-abnormality path.',
          wearingAdvice: 'This device is no longer usable. Please guide the user to properly remove the sensor. Remind users to wear the sensors according to the video.',
          nextAction: 'Provide after-sales service for this device.',
        };
      } else if (lowRecovery) {
        scenarioKey = 'sensor_abnormal.low_recovery_possibility';
        title = 'Abnormal after Warm-up';
        summary = 'Keep wearing the device unless it has already fallen off or support instructs removal.';
        whatWeFound = 'An abnormal status has been detected on the current device.';
        whyThisResult = 'The recovery observation period has passed and the sensor did not recover. Sustained abnormality is outside the initialization stage.';
        possibleCauses = 'This may be caused by certain low-probability situations, such as sensor loosening. It may also happen when the implanted site contains rich muscle tissue or when muscle stretching affects the sensor electrode, which then impacts data transmission.';
        guidance = {
          afterSalesStatus: 'You can continue to after-sales from this result.',
          why: 'The current device matches the low recovery possibility abnormality, so this record supports after-sales on the sensor-abnormality path.',
          wearingAdvice: 'This device is no longer usable. Please guide the user to properly remove the sensor. Remind users to avoid scratching or rubbing the device, and to avoid collisions and strenuous exercise.',
          nextAction: 'Provide after-sales service for this device.',
        };
      } else {
        scenarioKey = 'sensor_abnormal.gs1_after_warmup';
        title = 'Abnormal after Warm-up';
        summary = 'Keep wearing the device unless it has already fallen off or support instructs removal.';
        whatWeFound = 'An abnormal status has been detected on the current device.';
        whyThisResult = 'The in-use sensor-fault rule is met. Sustained abnormality is outside the initialization stage.';
        possibleCauses = 'This may be caused by certain low-probability situations, such as sensor loosening. It may also happen when the implanted site contains rich muscle tissue or when muscle stretching affects the sensor electrode, which then impacts data transmission.';
        guidance = {
          afterSalesStatus: 'You can continue to after-sales from this result.',
          why: 'The current device matches the in-use abnormality, so this record supports after-sales on the sensor-abnormality path.',
          wearingAdvice: 'This device is no longer usable. Please guide the user to properly remove the sensor. Remind users to avoid scratching or rubbing the device, and to avoid collisions and strenuous exercise.',
          nextAction: 'Provide after-sales service for this device.',
        };
      }
    }

    return {
      ...base,
      scenarioKey,
      badge,
      title,
      summary,
      whatWeFound,
      whyThisResult,
      possibleCauses,
      guidance,
    };
  }
  return null;
}

function mockVisionAnalysisForImplant(expectedAfterSales: string, fileIds?: string[]): any {
  const fileList = fileIds && fileIds.length > 0 ? fileIds : ['photo_1.png', 'photo_2.png'];
  
  let scenarios: any[] = [];
  let score = 0.0;
  let finalScenario = 'None of the above';
  
  if (expectedAfterSales === 'Replacement Eligible') {
    score = 8.5;
    finalScenario = 'Exposed Electrodes';
    scenarios = [
      { scenario: 'Assembly failed', matched: false, confidence: 0.0, reason: 'Assembly appears normal.' },
      { scenario: 'Guiding needle retention', matched: false, confidence: 0.0, reason: 'Needle withdrew successfully.' },
      { scenario: 'Exposed Electrodes', matched: true, confidence: 8.5, reason: 'Clear evidence of exposed needle/electrode outside the body.' },
      { scenario: 'Adhesive detaching', matched: false, confidence: 0.0, reason: 'Adhesive is fully attached.' },
      { scenario: 'Implanter damage', matched: false, confidence: 0.0, reason: 'No structural damage to implanter.' },
      { scenario: 'None of the above', matched: false, confidence: 0.0, reason: 'Qualifying scenario matched.' },
    ];
  } else if (expectedAfterSales === 'Under Review') {
    score = 5.8;
    finalScenario = 'Adhesive detaching';
    scenarios = [
      { scenario: 'Assembly failed', matched: false, confidence: 0.0, reason: 'Assembly appears normal.' },
      { scenario: 'Guiding needle retention', matched: false, confidence: 0.0, reason: 'Needle withdrew successfully.' },
      { scenario: 'Exposed Electrodes', matched: false, confidence: 0.0, reason: 'No exposed electrode.' },
      { scenario: 'Adhesive detaching', matched: true, confidence: 5.8, reason: 'Adhesive shows partial detaching/lifting at borders.' },
      { scenario: 'Implanter damage', matched: false, confidence: 0.0, reason: 'No structural damage to implanter.' },
      { scenario: 'None of the above', matched: false, confidence: 0.0, reason: 'Qualifying scenario matched.' },
    ];
  } else {
    score = 3.2;
    finalScenario = 'None of the above';
    scenarios = [
      { scenario: 'Assembly failed', matched: false, confidence: 0.0, reason: 'Assembly appears normal.' },
      { scenario: 'Guiding needle retention', matched: false, confidence: 0.0, reason: 'Needle withdrew successfully.' },
      { scenario: 'Exposed Electrodes', matched: false, confidence: 0.0, reason: 'No exposed electrode.' },
      { scenario: 'Adhesive detaching', matched: false, confidence: 0.0, reason: 'Adhesive is fully attached.' },
      { scenario: 'Implanter damage', matched: false, confidence: 0.0, reason: 'No structural damage to implanter.' },
      { scenario: 'None of the above', matched: true, confidence: 1.0, reason: 'No implantation failure pattern detected.' },
    ];
  }

  return {
    fileIds: fileList,
    file_ids: fileList,
    vision: {
      model_name: 'qwen2.5-vl-7b-instruct',
      prompt_version: 'v2',
      source: 'offline_mock',
      score: score,
      scenarios: scenarios,
      final_scenario: finalScenario,
      final_confidence: score,
      features: {
        is_cgm_device_present: true,
        is_reproduced_photo: false,
        needle_exposed: finalScenario === 'Exposed Electrodes',
        adhesive_detached: finalScenario === 'Adhesive detaching',
        implanter_damage: finalScenario === 'Implanter damage',
      }
    }
  };
}

function buildDetectRecord(input: {
  device: Device;
  selectedCategory?: FaultCategory;
  initiatorEmail: string;
  id: string;
  timestamp: string;
  profile: ThresholdProfile;
  fileIds?: string[];
}): DetectRecord {
  const decision = buildDetectDecision(input.device, input.profile, input.selectedCategory, input.fileIds);
  const initiator = resolveAccountProfile(input.initiatorEmail);
  const category = input.selectedCategory ?? input.device.fault?.faultCategory ?? 'Data accuracy';

  let evidence: any = undefined;
  if (category === 'Application failure') {
    evidence = mockVisionAnalysisForImplant(decision.afterSales, input.fileIds);
  } else if (input.fileIds && input.fileIds.length > 0) {
    evidence = { fileIds: input.fileIds, file_ids: input.fileIds };
  }

  const record: DetectRecord = {
    id: input.id,
    sn: input.device.sn,
    email: input.device.email ?? '',
    initiatorEmail: initiator.email,
    initiatorName: initiator.displayName,
    dealerId: initiator.dealerId,
    dealerName: initiator.dealerName,
    organizationName: initiator.organizationName,
    organizationType: initiator.organizationType,
    region: initiator.region,
    deviceType: input.device.type,
    faultCategory: category,
    faultSubtype: decision.faultSubtype,
    conclusion: decision.conclusion,
    afterSales: decision.afterSales,
    timestamp: input.timestamp,
    thresholdProfileVersion: input.profile.version,
    thresholdSnapshot: cloneThresholdProfile(input.profile),
    reasonSummary: decision.reasonSummary,
    verdictAdoption: 'Not recorded',
    verdictRejectionReason: '',
    evidence,
  };
  record.presentation = mockPresentationForRecord(record, input.device);
  return record;
}

function buildDefaultDetectRecords(): DetectRecord[] {
  const profile = cloneThresholdProfile(defaultThresholdProfile);
  const seeds: Array<{
    account: string;
    sn: string;
    category?: FaultCategory;
    timestamp: string;
  }> = [
    {
      account: CUSTOMER_EMAIL,
      sn: 'P2251212809MRF71',
      category: 'Sensor falling off',
      timestamp: '2026-05-20T09:15:00.000Z',
    },
    {
      account: CUSTOMER_EMAIL,
      sn: 'P2251212817VZP56',
      category: 'Sensor falling off',
      timestamp: '2026-05-21T10:40:00.000Z',
    },
    {
      account: CUSTOMER_EMAIL,
      sn: 'P2251212810NSG88',
      category: 'Sensor Abnormal',
      timestamp: '2026-05-22T11:55:00.000Z',
    },
    {
      account: CUSTOMER_EMAIL,
      sn: 'P2251212818WAQ64',
      category: 'Sensor Abnormal',
      timestamp: '2026-05-23T14:30:00.000Z',
    },
  ];
  return seeds.map((seed, index) => {
    const device = MOCK_DEVICE_BY_SN.get(seed.sn);
    if (!device) throw new Error(`Seed SN unknown: ${seed.sn}`);
    return buildDetectRecord({
      device,
      selectedCategory: seed.category,
      initiatorEmail: seed.account,
      id: demoRecordId(seed.sn, index + 1),
      timestamp: seed.timestamp,
      profile,
    });
  }).reverse();
}

function appendDetectRecord(device: Device, selectedCategory?: FaultCategory, fileIds?: string[]): DetectRecord {
  const resolvedCategory = selectedCategory ?? device.fault?.faultCategory ?? 'Data accuracy';
  const thresholdSnapshot = cloneThresholdProfile(activeThresholdProfile.value);
  const record = buildDetectRecord({
    device,
    selectedCategory: resolvedCategory,
    initiatorEmail: currentUser.value,
    id: nextRecordId(device.sn),
    timestamp: new Date().toISOString(),
    profile: thresholdSnapshot,
    fileIds,
  });
  records.value = [record, ...records.value];
  return record;
}
function startDetectSession(sn: string, faultCategory: FaultCategory, options: DetectSessionOptions = {}): DetectSession {
  const device = findCachedDeviceBySn(sn) ?? (selectedDevice.value?.sn === sn ? selectedDevice.value : undefined) ?? MOCK_DEVICE_BY_SN.get(sn);
  if (!device) throw new Error(`Unknown SN: ${sn}`);
  const now = new Date().toISOString();
  const session: DetectSession = {
    id: sessionId(sn, sessions.value.length + 1),
    sn,
    faultCategory,
    status: 'processing',
    startedAt: now,
    updatedAt: now,
    source: options.source ?? 'single',
    batchId: options.batchId,
    stepLabel: options.stepLabel,
    progress: options.progress,
  };
  sessions.value = [session, ...sessions.value];
  return session;
}

function updateDetectSession(sessionId: string, patch: DetectSessionPatch): DetectSession | undefined {
  const existing = sessions.value.find(session => session.id === sessionId);
  if (!existing) return undefined;
  const updated: DetectSession = {
    ...existing,
    ...patch,
    updatedAt: new Date().toISOString(),
  };
  sessions.value = sessions.value.map(session => (
    session.id === sessionId ? updated : session
  ));
  return updated;
}

function completeDetectSession(sessionId: string, record: DetectRecord): DetectSession | undefined {
  const existing = sessions.value.find(session => session.id === sessionId);
  if (!existing) return undefined;
  const updated: DetectSession = {
    ...existing,
    status: 'complete',
    recordId: record.id,
    stepLabel: record.status === 'failed' ? 'Failed' : 'Complete',
    progress: 100,
    updatedAt: record.timestamp,
  };
  sessions.value = sessions.value.map(session => (
    session.id === sessionId ? updated : session
  ));
  return updated;
}

function upsertRemoteRecords(nextRecords: DetectRecord[]): DetectRecord[] {
  const normalizedRecords = nextRecords.map(normalizeDetectRecord);
  const nextIds = new Set(normalizedRecords.map(record => record.id));
  records.value = [
    ...normalizedRecords,
    ...records.value.filter(record => !nextIds.has(record.id)),
  ];
  return normalizedRecords;
}

function sessionIdForRemoteRecord(record: DetectRecord): string {
  return `DS-REMOTE-${record.id}`;
}

function sessionFromRemoteRecord(record: DetectRecord): DetectSession {
  const isTerminal = isTerminalRecord(record);
  return {
    id: sessionIdForRemoteRecord(record),
    sn: record.sn,
    faultCategory: record.faultCategory,
    status: isTerminal ? 'complete' : 'processing',
    startedAt: record.timestamp,
    updatedAt: record.timestamp,
    recordId: record.id,
    source: record.batchId ? 'multi' : 'single',
    batchId: record.batchId ?? undefined,
    stepLabel: isTerminal ? (record.status === 'failed' ? 'Failed' : 'Complete') : 'Processing',
    progress: isTerminal ? 100 : 50,
  };
}

function upsertRemoteSession(record: DetectRecord): DetectSession {
  const normalized = normalizeDetectRecord(record);
  const existing = sessions.value.find(session => (
    (session.recordId && String(session.recordId) === String(normalized.id))
    || session.id === sessionIdForRemoteRecord(normalized)
    || (
      !session.recordId
      && session.source === 'single'
      && session.status === 'processing'
      && session.sn === normalized.sn
      && session.faultCategory === normalized.faultCategory
    )
  ));
  const next: DetectSession = existing
    ? {
        ...existing,
        status: isTerminalRecord(normalized) ? 'complete' : 'processing',
        recordId: normalized.id,
        source: normalized.batchId ? 'multi' : (existing.source ?? 'single'),
        batchId: normalized.batchId ?? existing.batchId,
        stepLabel: isTerminalRecord(normalized) ? (normalized.status === 'failed' ? 'Failed' : 'Complete') : (existing.stepLabel ?? 'Processing'),
        progress: isTerminalRecord(normalized) ? 100 : Math.max(existing.progress ?? 0, 50),
        updatedAt: new Date().toISOString(),
      }
    : sessionFromRemoteRecord(normalized);
  sessions.value = [
    next,
    ...sessions.value.filter(session => session.id !== next.id),
  ];
  return next;
}

function restoreProcessingSessionsFromRecords(remoteRecords: DetectRecord[]) {
  const processingSessions = remoteRecords
    .filter(isProcessingRecord)
    .map(sessionFromRemoteRecord);
  const processingRecordIds = new Set(processingSessions.map(session => session.recordId));
  sessions.value = [
    ...processingSessions,
    ...sessions.value.filter(session => !session.recordId || !processingRecordIds.has(session.recordId)),
  ];
}

async function pollDetectionUntilTerminal(initialRecord: DetectRecord): Promise<DetectRecord> {
  let latest = normalizeDetectRecord(initialRecord);
  for (let attempt = 0; attempt < 60 && !isTerminalRecord(latest); attempt += 1) {
    await delay(1000);
    try {
      const next = normalizeDetectRecord(await backendApi.getDetection(latest.id));
      upsertRemoteRecords([next]);
      upsertRemoteSession(next);
      latest = next;
    } catch {
      // Transient failure — keep polling with the last known state
      console.warn('[pollDetectionUntilTerminal] getDetection failed, retrying', latest.id);
    }
  }
  if (!isTerminalRecord(latest)) {
    throw new Error('Detection timed out after 30s. The result may still be processing on the server.');
  }
  return latest;
}

function runDetect(sn: string, selectedCategory?: FaultCategory, fileIds?: string[]): DetectRecord {
  const device = MOCK_DEVICE_BY_SN.get(sn);
  if (!device) throw new Error(`Unknown SN: ${sn}`);
  selectedDevice.value = { ...device };
  return appendDetectRecord(device, selectedCategory, fileIds);
}

async function runDetectRemote(sn: string, selectedCategory?: FaultCategory, fileIds: string[] = []): Promise<DetectRecord> {
  if (!backendOnline.value) return runDetect(sn, selectedCategory, fileIds);
  const category = selectedCategory ?? currentFault.value?.faultCategory ?? 'Data accuracy';
  try {
    const initialRecord = normalizeDetectRecord(await backendApi.createDetection(
      sn,
      category,
      fileIds,
    ));
    upsertRemoteRecords([initialRecord]);
    upsertRemoteSession(initialRecord);
    const record = await pollDetectionUntilTerminal(initialRecord);
    upsertRemoteRecords([record]);
    upsertRemoteSession(record);
    // 植入失败：设备未激活、接口查不到，不调用设备查询接口，沿用已构造的占位设备
    if (category === 'Application failure') {
      selectedDevice.value = buildUnactivatedDevice(sn);
    } else {
      const device = await findExactDeviceBySnRemote(sn);
      if (device) selectedDevice.value = { ...device };
    }
    return record;
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'unknown error';
    throw new Error(`Backend detection request failed: ${msg}`);
  }
}

function runDataDeviationReview(sn: string): DetectRecord {
  const device = MOCK_DEVICE_BY_SN.get(sn);
  if (!device) throw new Error(`Unknown SN: ${sn}`);
  selectedDevice.value = { ...device };
  const record = buildDeviationReviewRecord(device);
  records.value = [record, ...records.value];
  return record;
}

function runMultiDeviceDetect(sns: string[], faultCategory: FaultCategory): DetectRecord[] {
  return sns.map(sn => runDetect(sn, faultCategory));
}

function applyRemoteBatch(batch: BackendBatchRun): BackendBatchRun {
  batch.records.forEach(deviceFromRecordEvidence);
  sessions.value = [
    ...batch.sessions,
    ...sessions.value.filter(session => session.batchId !== batch.batchId),
  ];
  upsertRemoteRecords(batch.records.filter(isTerminalRecord));
  return batch;
}

async function runMultiDeviceDetectRemote(
  sns: string[],
  faultCategory: FaultCategory,
  deviceFiles?: Record<string, string[]>,
): Promise<BackendBatchRun | undefined> {
  if (!backendOnline.value) {
    return undefined;
  }
  try {
    return applyRemoteBatch(await backendApi.createBatch(sns, faultCategory, deviceFiles));
  } catch {
    throw new Error('Backend batch detection request failed.');
  }
}

async function refreshBatchRemote(batchId: string): Promise<BackendBatchRun | undefined> {
  if (!backendOnline.value) return undefined;
  return applyRemoteBatch(await backendApi.getBatch(batchId));
}

function restoreDetectRecord(record: DetectRecord): DetectRecord {
  const normalized = normalizeDetectRecord(record);
  const device = findCachedDeviceBySn(normalized.sn)
    ?? (selectedDevice.value?.sn === normalized.sn ? selectedDevice.value : undefined)
    ?? MOCK_DEVICE_BY_SN.get(normalized.sn)
    ?? deviceFromRecordEvidence(normalized)
    ?? cacheDevice({
      sn: normalized.sn,
      type: normalized.deviceType || 'GS1',
      status: normalized.conclusion === 'Issue Detected' ? 'abnormal' : 'wearing',
      activatedAt: normalized.timestamp,
      wearDays: 0,
      wearHours: 0,
      lastDataAt: normalized.timestamp,
      hasServiceCard: null,
      fault: {
        faultCategory: normalized.faultCategory,
        faultSubtype: normalized.faultSubtype || '',
        expectedAfterSales: normalized.afterSales,
        notes: normalized.reasonSummary || '',
      },
    });
  const restoredDevice = cacheDevice({
    ...device,
    fault: {
      faultCategory: normalized.faultCategory,
      faultSubtype: normalized.faultSubtype || '',
      expectedAfterSales: normalized.afterSales,
      notes: normalized.reasonSummary || '',
    },
  });
  selectedDevice.value = { ...restoredDevice };
  records.value = [
    normalized,
    ...records.value.filter(item => item.id !== record.id),
  ];
  return normalized;
}

function updateDetectRecordVerdict(recordId: string, input: {
  verdictAdoption: VerdictAdoption;
  verdictRejectionReason?: string;
}): DetectRecord | undefined {
  let updatedRecord: DetectRecord | undefined;
  records.value = records.value.map(record => {
    if (String(record.id) !== String(recordId)) return record;
    updatedRecord = {
      ...record,
      verdictAdoption: input.verdictAdoption,
      verdictRejectionReason: input.verdictAdoption === 'No'
        ? (input.verdictRejectionReason ?? '')
        : '',
    };
    return updatedRecord;
  });
  return updatedRecord;
}

async function updateDetectRecordVerdictRemote(recordId: string, input: {
  verdictAdoption: VerdictAdoption;
  verdictRejectionReason?: string;
}): Promise<DetectRecord | undefined> {
  if (!backendOnline.value) return updateDetectRecordVerdict(recordId, input);
  try {
    const record = normalizeDetectRecord(await backendApi.updateFeedback(
      recordId,
      input.verdictAdoption,
      input.verdictRejectionReason ?? '',
    ));
    records.value = records.value.map(item => item.id === record.id ? record : item);
    void refreshRemoteStats();
    return record;
  } catch {
    return updateDetectRecordVerdict(recordId, input);
  }
}

function ensureDefaultDetectRecords(): DetectRecord[] {
  const defaultRecords = buildDefaultDetectRecords();
  const existingIds = new Set(records.value.map(record => record.id));
  const missingDefaults = defaultRecords.filter(record => !existingIds.has(record.id));
  if (missingDefaults.length) {
    records.value = [...missingDefaults, ...records.value];
  }
  return records.value;
}

async function fetchRemoteStats(): Promise<void> {
  if (!backendOnline.value) {
    remoteStatsRequestId += 1;
    remoteStatsRequest = null;
    remoteStats.value = null;
    return;
  }
  if (remoteStatsRequest) return remoteStatsRequest;

  const requestId = ++remoteStatsRequestId;
  remoteStatsRequest = (async () => {
    try {
      const stats = await backendApi.getRecordsStats();
      if (requestId === remoteStatsRequestId) {
        remoteStats.value = stats;
      }
    } catch {
      // Fallback
    } finally {
      if (requestId === remoteStatsRequestId) {
        remoteStatsRequest = null;
      }
    }
  })();
  return remoteStatsRequest;
}

async function refreshRemoteStats(): Promise<void> {
  if (remoteStatsRequest) {
    await remoteStatsRequest;
  }
  return fetchRemoteStats();
}

async function loadRemoteBootstrap(): Promise<void> {
  if (!backendOnline.value) return;
  try {
    void fetchRemoteStats();
    currentAccountProfile.value = await backendApi.me();
    const profile = await backendApi.getThreshold();
    activeThresholdProfile.value = cloneThresholdProfile(profile);

    // Records are loaded on-demand by the Records page (server-side pagination).
    // No need to fetch records on login.
  } catch {
    records.value = [];
  }
}

function loadLocalThresholdHistory(): ThresholdProfile[] {
  try {
    const raw = window.localStorage.getItem('si-overseas-threshold-history');
    if (raw) return JSON.parse(raw);
  } catch {}
  return [cloneThresholdProfile(activeThresholdProfile.value)];
}

function saveLocalThresholdHistory(history: ThresholdProfile[]) {
  try {
    window.localStorage.setItem('si-overseas-threshold-history', JSON.stringify(history));
  } catch {}
}

function saveThresholdProfile(input: { rules: ThresholdRules; display?: ThresholdDisplaySettings }, remark?: string): ThresholdProfile {
  assertValidThresholdRules(input.rules);
  const history = loadLocalThresholdHistory();
  const nextProfile: ThresholdProfile = {
    version: activeThresholdProfile.value.version + 1,
    savedAt: new Date().toISOString(),
    rules: cloneThresholdRules(input.rules),
    display: input.display ?? cloneThresholdProfile(activeThresholdProfile.value).display,
    remark: remark || null,
  };
  activeThresholdProfile.value = nextProfile;
  persistThresholdProfile(nextProfile);

  history.unshift(cloneThresholdProfile(nextProfile));
  saveLocalThresholdHistory(history);

  return cloneThresholdProfile(nextProfile);
}

async function saveThresholdProfileRemote(input: { rules: ThresholdRules; display?: ThresholdDisplaySettings }, remark?: string): Promise<ThresholdProfile> {
  if (!backendOnline.value) return saveThresholdProfile(input, remark);
  assertValidThresholdRules(input.rules);
  const nextProfile: ThresholdProfile = {
    version: activeThresholdProfile.value.version + 1,
    savedAt: new Date().toISOString(),
    rules: cloneThresholdRules(input.rules),
    display: input.display ?? cloneThresholdProfile(activeThresholdProfile.value).display,
    remark: remark || null,
  };
  const saved = await backendApi.saveThreshold(nextProfile);
  activeThresholdProfile.value = saved;
  persistThresholdProfile(saved);
  return cloneThresholdProfile(saved);
}

function resetThresholdProfile(): ThresholdProfile {
  const history = loadLocalThresholdHistory();
  const nextProfile: ThresholdProfile = {
    ...cloneThresholdProfile(defaultThresholdProfile),
    version: activeThresholdProfile.value.version + 1,
    savedAt: new Date().toISOString(),
    remark: 'Reset to defaults',
  };
  activeThresholdProfile.value = nextProfile;
  persistThresholdProfile(nextProfile);

  history.unshift(cloneThresholdProfile(nextProfile));
  saveLocalThresholdHistory(history);

  return cloneThresholdProfile(nextProfile);
}

async function resetThresholdProfileRemote(): Promise<ThresholdProfile> {
  if (!backendOnline.value) return resetThresholdProfile();
  const profile = await backendApi.resetThreshold();
  activeThresholdProfile.value = profile;
  persistThresholdProfile(profile);
  return cloneThresholdProfile(profile);
}

async function getThresholdHistoryRemote(): Promise<ThresholdProfile[]> {
  if (!backendOnline.value) {
    const history = loadLocalThresholdHistory();
    if (!history.some(p => p.version === activeThresholdProfile.value.version)) {
      history.unshift(cloneThresholdProfile(activeThresholdProfile.value));
      saveLocalThresholdHistory(history);
    }
    return history.filter(p => !p.isHidden);
  }
  return await backendApi.getThresholdHistory();
}

async function rollbackThresholdRemote(version: number, remark?: string): Promise<ThresholdProfile> {
  if (!backendOnline.value) {
    const history = loadLocalThresholdHistory();
    const target = history.find(p => p.version === version);
    if (!target) {
      throw new Error(`Version ${version} not found in local history.`);
    }
    const nextProfile: ThresholdProfile = {
      ...cloneThresholdProfile(target),
      version: activeThresholdProfile.value.version + 1,
      savedAt: new Date().toISOString(),
      remark: remark || `Restored from Version ${version}`,
      restoredFrom: version,
    };
    activeThresholdProfile.value = nextProfile;
    persistThresholdProfile(nextProfile);
    history.unshift(cloneThresholdProfile(nextProfile));
    saveLocalThresholdHistory(history);
    return cloneThresholdProfile(nextProfile);
  }
  const rolled = await backendApi.rollbackThreshold(version, remark);
  activeThresholdProfile.value = rolled;
  persistThresholdProfile(rolled);
  return cloneThresholdProfile(rolled);
}

async function updateThresholdRemarkRemote(version: number, remark: string): Promise<ThresholdProfile> {
  if (!backendOnline.value) {
    const history = loadLocalThresholdHistory();
    const target = history.find(p => p.version === version);
    if (!target) {
      throw new Error(`Version ${version} not found in local history.`);
    }
    target.remark = remark;
    saveLocalThresholdHistory(history);
    if (activeThresholdProfile.value.version === version) {
      activeThresholdProfile.value.remark = remark;
      persistThresholdProfile(activeThresholdProfile.value);
    }
    return cloneThresholdProfile(target);
  }
  const updated = await backendApi.updateThresholdRemark(version, remark);
  if (activeThresholdProfile.value.version === version) {
    activeThresholdProfile.value = updated;
    persistThresholdProfile(updated);
  }
  return cloneThresholdProfile(updated);
}

async function hideThresholdRemote(version: number): Promise<ThresholdProfile> {
  if (!backendOnline.value) {
    const history = loadLocalThresholdHistory();
    const targetIndex = history.findIndex(p => p.version === version);
    if (targetIndex === -1) {
      throw new Error(`Version ${version} not found in local history.`);
    }
    const target = history[targetIndex];
    target.isHidden = true;
    history.splice(targetIndex, 1);
    saveLocalThresholdHistory(history);
    return cloneThresholdProfile(target);
  }
  const hidden = await backendApi.hideThreshold(version);
  return cloneThresholdProfile(hidden);
}

function resetDemoState() {
  searchResults.value = [];
  deviceCache.value = {};
  records.value = [];
  sessions.value = [];
  currentUser.value = CUSTOMER_EMAIL;
  currentAccountProfile.value = null;
  try {
    window.localStorage.removeItem(CURRENT_USER_STORAGE_KEY);
    window.localStorage.removeItem(RECORDS_STORAGE_KEY);
    window.localStorage.removeItem('si-overseas-accounts');
  } catch {
    // Ignore unavailable demo storage during reset.
  }
  selectedDevice.value = null;
  remoteStatsRequestId += 1;
  remoteStatsRequest = null;
  remoteStats.value = null;
  backendOnline.value = backendEnabled();
  document.documentElement.removeAttribute('data-theme');
  activeThresholdProfile.value = cloneThresholdProfile(defaultThresholdProfile);
  clearStoredThresholdProfile();
}

function clearRecords() {
  records.value = [];
}

function clearSessions() {
  sessions.value = [];
}

const TOKEN_STORAGE_KEY = 'si-overseas-api-token';

function logout() {
  currentUser.value = '';
  currentAccountProfile.value = null;
  remoteStatsRequestId += 1;
  remoteStatsRequest = null;
  remoteStats.value = null;
  try {
    window.localStorage.removeItem(CURRENT_USER_STORAGE_KEY);
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    window.localStorage.removeItem('si-agent-chat-v1');
  } catch {
    // Ignore unavailable storage during logout.
  }
}

export function useDemoStore() {
  return {
    CUSTOMER_EMAIL,
    canCreateUsers,
    isManager,
    canManageThresholds,
    currentAccount,
    currentAccountProfile,
    currentFault,
    currentUser,
    dashboard,
    defaultThresholdProfile,
    records,
    visibleRecords,
    sessions,
    searchResults,
    deviceCache,
    selectedDevice,
    activeThresholdProfile,
    backendOnline,
    remoteStats,
    fetchRemoteStats,
    refreshRemoteStats,
    appendDetectRecord,
    clearRecords,
    clearSessions,
    completeDetectSession,
    findAccountByEmail,
    findCachedDeviceBySn,
    findExactDeviceBySnRemote,
    getFaultForSn,
    ensureDefaultDetectRecords,
    loadRemoteBootstrap,
    createUserRemote,
    loginRemote,
    logout,
    requiresDataDeviationReview,
    resetDemoState,
    resetThresholdProfile,
    resetThresholdProfileRemote,
    getThresholdHistoryRemote,
    rollbackThresholdRemote,
    updateThresholdRemarkRemote,
    hideThresholdRemote,
    restoreDetectRecord,
    runMultiDeviceDetect,
    runMultiDeviceDetectRemote,
    runDataDeviationReview,
    runDetect,
    runDetectRemote,
    startDetectSession,
    refreshBatchRemote,
    updateDetectSession,
    updateDetectRecordVerdict,
    updateDetectRecordVerdictRemote,
    findExactDeviceBySn,
    saveThresholdProfile,
    saveThresholdProfileRemote,
    searchDeviceMatches,
    searchBySn,
    searchBySnRemote,
    searchBySnLinesRemote,
    searchBySnLines,
    selectDevice,
    selectDeviceRemote,
    buildUnactivatedDevice,
    selectUnactivatedDevice,
    validateAccountCredentials,
  };
}
