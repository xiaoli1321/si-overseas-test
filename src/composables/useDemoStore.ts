import { computed, ref, watch } from 'vue';
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
import type { Device, FaultCategory, FaultMapping } from '@/types/device';
import type { DashboardStats, DetectRecord, DetectSession, VerdictAdoption } from '@/types/record';
import type { ThresholdProfile, ThresholdRules } from '@/types/threshold';
import type { AccountProfile } from '@/types/account';

const CURRENT_USER_STORAGE_KEY = 'si-overseas-current-user';
const RECORDS_STORAGE_KEY = 'si-overseas-detect-records';

function loadStoredCurrentUser() {
  try {
    return window.localStorage.getItem(CURRENT_USER_STORAGE_KEY) || CUSTOMER_EMAIL;
  } catch {
    return CUSTOMER_EMAIL;
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
    verdictAdoption: record.verdictAdoption ?? 'Not recorded',
    verdictRejectionReason: record.verdictRejectionReason ?? '',
  };
}

const searchResults = ref<Device[]>([]);
const records = ref<DetectRecord[]>(loadStoredRecords());
const sessions = ref<DetectSession[]>([]);
const currentUser = ref(loadStoredCurrentUser());
const selectedDevice = ref<Device | null>(null);
const activeThresholdProfile = ref<ThresholdProfile>(loadStoredThresholdProfile());

const currentAccount = computed(() => resolveAccountProfile(currentUser.value));
const canManageThresholds = computed(() => true);
const visibleRecords = computed(() => {
  const account = currentAccount.value;
  return records.value.filter(record => record.dealerId === account.dealerId);
});

const dashboard = computed<DashboardStats>(() => ({
  total: visibleRecords.value.length,
  allowed: visibleRecords.value.filter(record => record.afterSales === 'Warranty Eligible').length,
  notAllowed: visibleRecords.value.filter(record => record.afterSales === 'Not Eligible').length,
  pending: visibleRecords.value.filter(record => record.afterSales === 'Under Review').length,
}));

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

function findExactDeviceBySn(query: string): Device | undefined {
  const needle = normalizeSnQuery(query);
  if (!needle) return undefined;
  const device = MOCK_DEVICES.find(item => normalizeSnQuery(item.sn) === needle);
  return device ? { ...device } : undefined;
}

function getFaultForSn(sn: string): FaultMapping | undefined {
  return MOCK_DEVICE_BY_SN.get(sn)?.fault;
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

function selectDevice(sn: string): Device {
  const device = MOCK_DEVICE_BY_SN.get(sn);
  if (!device) throw new Error(`Unknown SN: ${sn}`);
  selectedDevice.value = { ...device };
  return selectedDevice.value;
}

function recordId(sn: string, index: number) {
  return `FD-${String(index).padStart(4, '0')}-${sn.slice(-4)}`;
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
  return device.fault.notes;
}

function dataInaccuracyDemoMetrics(device: Device) {
  const subtype = device.fault.faultSubtype;

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
  return device.fault.expectedAfterSales;
}

function evaluateDataInaccuracy(device: Device, profile: ThresholdProfile): InaccuracyDecision {
  const rules = profile.rules.inaccuracy;
  const metrics = dataInaccuracyDemoMetrics(device);

  if (!metrics) {
    if (device.fault.faultSubtype.includes('Data Deviation')) {
      return {
        faultSubtype: device.fault.faultSubtype,
        conclusion: 'Issue Detected',
        afterSales: device.fault.expectedAfterSales,
        reasonSummary: `Data Deviation uses profile v${profile.version}: two paired CGM/BGM image groups are required and have been collected for this mock review. ${device.fault.notes}`,
      };
    }

    return {
      faultSubtype: 'Data deviation detected',
      conclusion: 'No Issue',
      afterSales: 'Not Eligible',
      reasonSummary: `Data deviation requires two paired CGM/BGM image groups. Active rule profile v${profile.version} is available for the next paired review.`,
    };
  }

  if (metrics.pattern === 'low') {
    const r = rules.lowPersist;
    const hit = metrics.lowestMmol <= r.belowMmol
      && metrics.lowHours >= r.minHours
      && metrics.peak24hMmol <= r.max24hMmol;
    return {
      faultSubtype: hit ? device.fault.faultSubtype : 'No qualifying curve pattern',
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
      faultSubtype: hit ? device.fault.faultSubtype : 'No qualifying curve pattern',
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
    faultSubtype: hit ? device.fault.faultSubtype : 'No qualifying curve pattern',
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
    reasonSummary: `${category} is not supported by this mock device. The Excel-mapped scenario for ${device.sn} is ${device.fault.faultCategory}, so after-sales is not recommended for this selected path.`,
  };
}

function buildDetectDecision(device: Device, profile: ThresholdProfile, selectedCategory = device.fault.faultCategory): InaccuracyDecision {
  if (selectedCategory !== device.fault.faultCategory) {
    return unsupportedCategoryDecision(device, selectedCategory);
  }

  if (selectedCategory === 'Data accuracy') {
    return evaluateDataInaccuracy(device, profile);
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
  const device = MOCK_DEVICE_BY_SN.get(sn);
  if (!device) throw new Error(`Unknown SN: ${sn}`);
  if (selectedCategory !== device.fault.faultCategory) return true;
  if (device.fault.faultSubtype.includes('Data Deviation')) return true;

  const firstPass = buildDetectDecision(device, activeThresholdProfile.value, selectedCategory);
  return firstPass.conclusion === 'No Issue'
    && firstPass.afterSales === 'Not Eligible'
    && (
      device.fault.faultSubtype.includes('Persistent Low')
      || device.fault.faultSubtype.includes('No Fluctuation')
      || device.fault.faultSubtype.includes('Jump')
    );
}

function buildDeviationReviewRecord(device: Device): DetectRecord {
  const profile = cloneThresholdProfile(activeThresholdProfile.value);
  const initiator = resolveAccountProfile(currentUser.value);
  return {
    id: recordId(device.sn, records.value.length + 1),
    sn: device.sn,
    email: device.email,
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
    afterSales: device.fault.expectedAfterSales,
    timestamp: new Date().toISOString(),
    thresholdProfileVersion: profile.version,
    thresholdSnapshot: profile,
    reasonSummary: `First-pass curve screening did not confirm persistent low, no fluctuation, or jump-point under profile v${profile.version}. Two paired CGM/BGM image groups were collected for data-deviation review. ${device.fault.notes}`,
    verdictAdoption: 'Not recorded',
    verdictRejectionReason: '',
  };
}

function buildDetectRecord(input: {
  device: Device;
  selectedCategory?: FaultCategory;
  initiatorEmail: string;
  id: string;
  timestamp: string;
  profile: ThresholdProfile;
}): DetectRecord {
  const decision = buildDetectDecision(input.device, input.profile, input.selectedCategory);
  const initiator = resolveAccountProfile(input.initiatorEmail);

  return {
    id: input.id,
    sn: input.device.sn,
    email: input.device.email,
    initiatorEmail: initiator.email,
    initiatorName: initiator.displayName,
    dealerId: initiator.dealerId,
    dealerName: initiator.dealerName,
    organizationName: initiator.organizationName,
    organizationType: initiator.organizationType,
    region: initiator.region,
    deviceType: input.device.type,
    faultCategory: input.selectedCategory ?? input.device.fault.faultCategory,
    faultSubtype: decision.faultSubtype,
    conclusion: decision.conclusion,
    afterSales: decision.afterSales,
    timestamp: input.timestamp,
    thresholdProfileVersion: input.profile.version,
    thresholdSnapshot: cloneThresholdProfile(input.profile),
    reasonSummary: decision.reasonSummary,
    verdictAdoption: 'Not recorded',
    verdictRejectionReason: '',
  };
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
      sn: 'P2251212813RVK19',
      category: 'Application failure',
      timestamp: '2026-05-22T08:20:00.000Z',
    },
    {
      account: CUSTOMER_EMAIL,
      sn: 'P2251212814SWL27',
      category: 'Data accuracy',
      timestamp: '2026-05-23T14:05:00.000Z',
    },
  ];

  return seeds.map((seed, index) => {
    const device = MOCK_DEVICE_BY_SN.get(seed.sn);
    if (!device) throw new Error(`Unknown seed SN: ${seed.sn}`);
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

function appendDetectRecord(device: Device, selectedCategory = device.fault.faultCategory): DetectRecord {
  const thresholdSnapshot = cloneThresholdProfile(activeThresholdProfile.value);
  const record = buildDetectRecord({
    device,
    selectedCategory,
    initiatorEmail: currentUser.value,
    id: recordId(device.sn, records.value.length + 1),
    timestamp: new Date().toISOString(),
    profile: thresholdSnapshot,
  });
  records.value = [record, ...records.value];
  return record;
}

function startDetectSession(sn: string, faultCategory: FaultCategory, options: DetectSessionOptions = {}): DetectSession {
  const device = MOCK_DEVICE_BY_SN.get(sn);
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
    stepLabel: 'Complete',
    progress: 100,
    updatedAt: record.timestamp,
  };
  sessions.value = sessions.value.map(session => (
    session.id === sessionId ? updated : session
  ));
  return updated;
}

function runDetect(sn: string, selectedCategory?: FaultCategory): DetectRecord {
  const device = MOCK_DEVICE_BY_SN.get(sn);
  if (!device) throw new Error(`Unknown SN: ${sn}`);
  selectedDevice.value = { ...device };
  return appendDetectRecord(device, selectedCategory);
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

function restoreDetectRecord(record: DetectRecord): DetectRecord {
  const device = MOCK_DEVICE_BY_SN.get(record.sn);
  if (device) selectedDevice.value = { ...device };
  const normalized = normalizeDetectRecord(record);
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
    if (record.id !== recordId) return record;
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

function ensureDefaultDetectRecords(): DetectRecord[] {
  const defaultRecords = buildDefaultDetectRecords();
  const existingIds = new Set(records.value.map(record => record.id));
  const missingDefaults = defaultRecords.filter(record => !existingIds.has(record.id));
  if (missingDefaults.length) {
    records.value = [...missingDefaults, ...records.value];
  }
  return records.value;
}

function saveThresholdProfile(input: { rules: ThresholdRules }): ThresholdProfile {
  assertValidThresholdRules(input.rules);
  const nextProfile: ThresholdProfile = {
    version: activeThresholdProfile.value.version + 1,
    savedAt: new Date().toISOString(),
    rules: cloneThresholdRules(input.rules),
  };
  activeThresholdProfile.value = nextProfile;
  persistThresholdProfile(nextProfile);
  return cloneThresholdProfile(nextProfile);
}

function resetThresholdProfile(): ThresholdProfile {
  const nextProfile: ThresholdProfile = {
    ...cloneThresholdProfile(defaultThresholdProfile),
    version: activeThresholdProfile.value.version + 1,
    savedAt: new Date().toISOString(),
  };
  activeThresholdProfile.value = nextProfile;
  persistThresholdProfile(nextProfile);
  return cloneThresholdProfile(nextProfile);
}

function resetDemoState() {
  searchResults.value = [];
  records.value = [];
  sessions.value = [];
  currentUser.value = CUSTOMER_EMAIL;
  try {
    window.localStorage.removeItem(CURRENT_USER_STORAGE_KEY);
    window.localStorage.removeItem(RECORDS_STORAGE_KEY);
    window.localStorage.removeItem('si-overseas-accounts');
  } catch {
    // Ignore unavailable demo storage during reset.
  }
  selectedDevice.value = null;
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

export function useDemoStore() {
  return {
    CUSTOMER_EMAIL,
    canManageThresholds,
    currentAccount,
    currentFault,
    currentUser,
    dashboard,
    defaultThresholdProfile,
    records,
    visibleRecords,
    sessions,
    searchResults,
    selectedDevice,
    activeThresholdProfile,
    appendDetectRecord,
    clearRecords,
    clearSessions,
    completeDetectSession,
    findAccountByEmail,
    getFaultForSn,
    ensureDefaultDetectRecords,
    requiresDataDeviationReview,
    resetDemoState,
    resetThresholdProfile,
    restoreDetectRecord,
    runMultiDeviceDetect,
    runDataDeviationReview,
    runDetect,
    startDetectSession,
    updateDetectSession,
    updateDetectRecordVerdict,
    findExactDeviceBySn,
    saveThresholdProfile,
    searchDeviceMatches,
    searchBySn,
    searchBySnLines,
    selectDevice,
    validateAccountCredentials,
  };
}
