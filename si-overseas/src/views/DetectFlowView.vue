<script setup lang="ts">
import { computed, ref, watch, watchEffect, nextTick, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { keyForFaultCategory, faultCategoryLabel, afterSalesLabel } from '@/composables/faultCategories';
import { useDemoStore } from '@/composables/useDemoStore';
import { backendApi } from '@/api/backend';
import { formatDeviceTime, formatDurationHours, formatDurationText } from '@/utils/date';
import { compressImage } from '@/utils/image';
import type { FaultCategory } from '@/types/device';
import type { DetectRecord, VerdictPresentation, VerdictPresentationGuidance } from '@/types/record';

const implantFileIds = ref<(string | null)[]>([null, null, null]);
const implantFileNames = ref<(string | null)[]>([null, null, null]);
const implantUploading = ref<boolean[]>([false, false, false]);

const deviationFileIds = ref<(string | null)[]>([null, null, null, null]);
const deviationFileNames = ref<(string | null)[]>([null, null, null, null]);
const deviationFilePreviews = ref<(string | null)[]>([null, null, null, null]);
const deviationUploading = ref<boolean[]>([false, false, false, false]);

const props = defineProps<{
  sn: string;
}>();

const route = useRoute();
const router = useRouter();
const store = useDemoStore();
const phase = ref<'form' | 'inaccuracy-upload' | 'processing' | 'result'>('form');
const inaccuracyDeviationMode = ref(false);
const deviationImageCount = ref(0);
const deviationUploadError = ref('');
const implantPhotoCount = ref(0);
const uploadError = ref('');
const processingProgress = ref(0);
const processingComplete = ref(false);
const processingSessionId = ref('');
const activeRecordId = ref('');
const routeDeviceLoading = ref(false);
const routeDeviceError = ref('');
const routeRecordError = ref('');
const verdictDecision = ref<'adopt' | 'reject' | null>(null);
const rejectComment = ref('');
const rejectPanelOpen = ref(false);
const rejectSubmitted = ref(false);
const remoteDetectRecord = ref<any>(null);
const remoteDetectFinished = ref<boolean>(false);
const remoteDetectError = ref<any>(null);
const deviationUploadModalOpen = ref(false);
const deviationPreviewOpen = ref(false);
const deviationPreviewSrc = ref('');
const deviationPreviewName = ref('');
const PROCESSING_CIRCLE_CIRCUMFERENCE = 301.59;
const PROCESSING_MIN_VISIBLE_MS = 1400;
const IMPLANT_PROCESSING_MIN_VISIBLE_MS = 5000;
let processingProgressTimer: number | undefined;
let processingCompletionTimer: number | undefined;
let processingStartedAt = 0;
const faultCategories: FaultCategory[] = [
  'Data accuracy',
  'Sensor falling off',
  'Sensor Abnormal',
  'Application failure',
];

// 解析当前故障品类（供 watchEffect 与 selectedCategory 共用）。
// 注意：watchEffect 会在 setup 阶段同步执行，不能直接引用后面用 const 声明的 selectedCategory，
// 因此抽成函数声明（会被提升），避免 TDZ 报错。
function resolveSelectedCategory(): FaultCategory {
  const category = String(route.query.category ?? '');
  if (faultCategories.includes(category as FaultCategory)) return category as FaultCategory;
  return store.currentFault.value?.faultCategory ?? 'Data accuracy';
}

interface VisionScenario {
  scenario: string;
  matched: boolean;
  confidence: number;
  reason?: string;
}

interface VisionEvidence {
  vision?: {
    score?: number;
    final_scenario?: string;
    scenarios?: VisionScenario[];
  };
}

interface VerdictDisplayRow {
  k: string;
  v: string;
  cls: string;
  html?: boolean;
}

watchEffect(() => {
  if (!store.selectedDevice.value || store.selectedDevice.value.sn !== props.sn) {
    // 植入失败：设备未激活、接口查不到，不调用设备查询接口，直接用用户输入构造占位设备。
    if (resolveSelectedCategory() === 'Application failure') {
      store.selectUnactivatedDevice(props.sn);
      routeDeviceLoading.value = false;
      routeDeviceError.value = '';
      return;
    }
    routeDeviceLoading.value = true;
    routeDeviceError.value = '';
    void store.selectDeviceRemote(props.sn)
      .catch(err => {
        routeDeviceError.value = err instanceof Error ? err.message : 'Unable to load device.';
      })
      .finally(() => {
        routeDeviceLoading.value = false;
      });
  }
});

const device = computed(() => store.selectedDevice.value);
const selectedCategory = computed<FaultCategory>(() => resolveSelectedCategory());
const fault = computed(() => {
  if (store.currentFault.value) {
    return {
      ...store.currentFault.value,
      faultCategory: selectedCategory.value,
    };
  }
  // Fallback for backend devices that may not carry pre-assigned fault info.
  // This lets the page render while detection runs.
  if (device.value) {
    return {
      faultCategory: selectedCategory.value,
      faultSubtype: '',
      expectedAfterSales: 'Under Review' as const,
      notes: '',
    };
  }
  return null;
});
const isMappedCategory = computed(() => selectedCategory.value === store.currentFault.value?.faultCategory);
const isFromChat = computed(() => route.query.from === 'chat');
const isFromFaultQuery = computed(() => route.query.from === 'fault-query');
const isFromRecords = computed(() => route.query.from === 'records');
const isFromDeviceDetect = computed(() => route.query.from === 'device-detect');
const isFromMultiDetect = computed(() => route.query.from === 'multi-detect');
const isDetectRoute = computed(() => route.name === 'detect' || route.name === 'detect-new' || route.name === 'detect-record');
const queryFiles = computed(() => String(route.query.files ?? '').trim());
const isRouteAutoRunRequest = computed(() => route.name === 'detect-new' || route.query.run === '1' || !!queryFiles.value);
const hasRouteContext = computed(() => (
  route.name === 'detect-new'
  || route.name === 'detect-record'
  || !!route.query.category
  || !!route.query.record
  || !!route.query.session
  || !!route.query.from
  || !!route.query.run
  || !!queryFiles.value
));

const detectBackLabel = computed(() => {
  if (isFromMultiDetect.value) return 'Back to batch results';
  if (isFromRecords.value) return 'Back to Detection History';
  if (isFromChat.value) return 'Back to Device Detection';
  if (isFromDeviceDetect.value) {
    return String(route.query.q ?? '').trim() ? 'Back to matched devices' : 'Back to Device Detection';
  }
  if (isFromFaultQuery.value) return 'Back to lookup';
  return 'Back to Fault Query';
});

const routeSession = computed(() => {
  const sessionId = String(route.query.session ?? '');
  if (!sessionId) return undefined;
  return store.sessions.value.find(session => session.id === sessionId);
});
const processingStrokeDashoffset = computed(() => {
  const progress = Math.max(0, Math.min(100, processingProgress.value));
  return PROCESSING_CIRCLE_CIRCUMFERENCE - (progress / 100) * PROCESSING_CIRCLE_CIRCUMFERENCE;
});
const isDataDeviationCase = computed(() => (
  selectedCategory.value === 'Data accuracy'
  && !!store.currentFault.value?.faultSubtype.includes('Data Deviation')
));

function selectVerdictAdopt() {
  verdictDecision.value = 'adopt';
  rejectPanelOpen.value = false;
  rejectComment.value = '';
  rejectSubmitted.value = false;
  if (latestRecord.value) {
    void store.updateDetectRecordVerdictRemote(latestRecord.value.id, {
      verdictAdoption: 'Yes',
      verdictRejectionReason: '',
    });
  }
}

function selectVerdictReject() {
  verdictDecision.value = 'reject';
  rejectPanelOpen.value = true;
  rejectSubmitted.value = false;
}

function submitVerdictReject() {
  verdictDecision.value = 'reject';
  rejectSubmitted.value = true;
  rejectPanelOpen.value = false;
  if (latestRecord.value) {
    void store.updateDetectRecordVerdictRemote(latestRecord.value.id, {
      verdictAdoption: 'No',
      verdictRejectionReason: rejectComment.value.trim(),
    });
  }
}

function goToNewLookup() {
  router.push({ name: 'chat' });
}

function detectAnother() {
  router.replace({
    name: 'fault-query',
    params: { categoryKey: keyForFaultCategory(selectedCategory.value) },
    query: { fromDetect: '1' },
  });
}

function backFromDetect() {
  if (isFromChat.value) {
    const chatSessionId = String(route.query.session ?? '');
    router.replace({
      name: 'chat',
      query: chatSessionId ? { session: chatSessionId } : {},
    });
    return;
  }
  if (isFromRecords.value) {
    router.replace({ name: 'records' });
    return;
  }
  if (isFromMultiDetect.value) {
    const batchId = String(route.query.batch ?? '').trim();
    if (batchId) {
      router.replace({
        name: 'multi-detect',
        params: { batchId },
        query: { category: selectedCategory.value },
      });
    } else {
      router.replace({
        name: 'fault-query',
        params: { categoryKey: keyForFaultCategory(selectedCategory.value) },
        query: { fromDetect: '1' },
      });
    }
    return;
  }
  if (isFromDeviceDetect.value) {
    const q = String(route.query.q ?? '').trim();
    if (q) {
      router.replace({ name: 'detect-devices', query: { q, fromDetect: '1' } });
    } else {
      router.replace({ name: 'chat' });
    }
    return;
  }
  router.replace({
    name: 'fault-query',
    params: { categoryKey: keyForFaultCategory(selectedCategory.value) },
    query: isFromFaultQuery.value ? { fromDetect: '1' } : {},
  });
}

function backFromInaccuracyUpload() {
  if (isFromChat.value && latestRecord.value) {
    backFromDetect();
    return;
  }
  if (isFromRecords.value && latestRecord.value) {
    backFromDetect();
    return;
  }
  if (isFromDeviceDetect.value && latestRecord.value) {
    backFromDetect();
    return;
  }
  phase.value = 'form';
}
const routeRecordId = computed(() => String(route.params.recordId ?? route.query.record ?? ''));
function isTerminalDetectRecord(record: DetectRecord) {
  return !record.status || record.status === 'complete' || record.status === 'completed' || record.status === 'failed';
}

function recordMatchesCurrentRoute(record: DetectRecord) {
  return record.sn === props.sn && record.faultCategory === selectedCategory.value;
}

const latestCompletedRouteRecord = computed(() => store.records.value.find(record => (
  recordMatchesCurrentRoute(record) && isTerminalDetectRecord(record)
)));
const latestRecord = computed(() => {
  const explicitRecordId = activeRecordId.value
    || (phase.value === 'processing' ? '' : routeRecordId.value)
    || routeSession.value?.recordId
    || '';
  if (explicitRecordId) {
    return store.records.value.find(record => String(record.id) === String(explicitRecordId));
  }
  if (phase.value === 'processing') return undefined;
  return latestCompletedRouteRecord.value;
});

function restoreDeviceFromLatestRecord() {
  const record = latestRecord.value;
  if (!record) return false;
  if (device.value?.sn === record.sn) return true;
  store.restoreDetectRecord(record);
  return true;
}
function presentationMatchesRecord(presentation: VerdictPresentation, record: DetectRecord) {
  if (record.faultSubtype.includes('Review Required')) {
    return presentation.scenarioKey.includes('path_switching');
  }
  if (record.faultSubtype.includes('Data Deviation')) {
    return presentation.scenarioKey.includes('paired');
  }
  if (record.faultSubtype.includes('Persistent')) {
    return presentation.scenarioKey.includes('persistent_low');
  }
  if (record.faultSubtype.includes('No Fluctuation')) {
    return presentation.scenarioKey.includes('no_fluctuation');
  }
  return true;
}
const verdictPresentation = computed<VerdictPresentation | null>(() => {
  const record = latestRecord.value;
  if (!record?.presentation) return null;
  return presentationMatchesRecord(record.presentation, record) ? record.presentation : null;
});

const inaccuracyBackLabel = computed(() => {
  if (isFromChat.value && latestRecord.value) return 'Back to Device Detection';
  if (isFromRecords.value && latestRecord.value) return 'Back to Detection History';
  if (isFromDeviceDetect.value && latestRecord.value) {
    return String(route.query.q ?? '').trim() ? 'Back to matched devices' : 'Back to Device Detection';
  }
  return 'Back';
});

watch(() => latestRecord.value?.id, () => {
  if (latestRecord.value?.verdictAdoption === 'Yes') {
    verdictDecision.value = 'adopt';
    rejectComment.value = '';
    rejectPanelOpen.value = false;
    rejectSubmitted.value = false;
    return;
  }
  if (latestRecord.value?.verdictAdoption === 'No') {
    verdictDecision.value = 'reject';
    rejectComment.value = latestRecord.value.verdictRejectionReason;
    rejectPanelOpen.value = false;
    rejectSubmitted.value = true;
    return;
  }
  verdictDecision.value = null;
  rejectComment.value = '';
  rejectPanelOpen.value = false;
  rejectSubmitted.value = false;
}, { immediate: true });

const activeRuleLabel = computed(() => `Rule profile v${store.activeThresholdProfile.value.version}`);
const resultRuleLabel = computed(() => (
  latestRecord.value?.thresholdProfileVersion
    ? `Rule profile v${latestRecord.value.thresholdProfileVersion}`
    : activeRuleLabel.value
));
const verdictTone = computed(() => (
  latestRecord.value?.afterSales === 'Replacement Eligible' ? 'fault' : 'blocked'
));
const verdictBadge = computed(() => {
  const badge = verdictPresentation.value?.badge;
  if (badge && badge !== '/') return badge;
  return latestRecord.value?.afterSales === 'Replacement Eligible' ? 'WARRANTY ELIGIBLE' : 'NOT WARRANTY ELIGIBLE';
});
const categoryKey = computed(() => {
  if (selectedCategory.value === 'Data accuracy') return 'inaccuracy';
  if (selectedCategory.value === 'Sensor falling off') return 'detachment';
  if (selectedCategory.value === 'Sensor Abnormal') return 'sensor';
  return 'implant';
});
const isFault = computed(() => latestRecord.value?.conclusion === 'Issue Detected');
const verdictTitle = computed(() => {
  if (verdictPresentation.value?.title && verdictPresentation.value.title !== '/') return verdictPresentation.value.title;
  if (!latestRecord.value) return fault.value?.faultCategory ?? 'Verdict';
  if (categoryKey.value === 'inaccuracy') return latestRecord.value.faultSubtype === 'No qualifying curve pattern'
    ? 'No qualifying curve pattern detected'
    : latestRecord.value.faultSubtype;
  if (categoryKey.value === 'detachment') return isFault.value ? 'Fall-out detected' : 'Fall-out not detected';
  if (categoryKey.value === 'sensor') return isFault.value ? latestRecord.value.faultSubtype : 'No malfunction detected';
  return isFault.value ? 'Application failure detected' : 'No application failure detected';
});
const recommendationClass = computed(() => (
  latestRecord.value?.afterSales === 'Replacement Eligible' ? 'ok' : 'warn'
));
const recommendationCopy = computed(() => {
  if (!latestRecord.value) return '';
  if (latestRecord.value.afterSales === 'Replacement Eligible') {
    return 'You can continue to after-sales from this result.';
  }
  if (latestRecord.value.afterSales === 'Under Review') {
    return 'Pending review. Do not continue to after-sales yet.';
  }
  return 'Do not continue to after-sales from this result.';
});
const heroSummary = computed(() => {
  if (verdictPresentation.value?.summary && verdictPresentation.value.summary !== '/') {
    return formatReasonValue(verdictPresentation.value.summary);
  }
  if (!latestRecord.value) return '';
  if (categoryKey.value === 'inaccuracy') {
    if (latestRecord.value.faultSubtype.includes('Fraud')) return 'Evidence verification failed: Screen reproduction (fraudulent photo) detected.';
    if (latestRecord.value.faultSubtype.includes('Accuracy Within Normal Limits')) return 'Sensor accuracy is within acceptable limits. One or more CGM/BGM groups do not show significant deviation.';
    if (!isFault.value) return 'The initial curve analysis results alone cannot determine after-sales eligibility. Please proceed with the CGM/BGM image comparison process.';
    if (latestRecord.value.faultSubtype.includes('Persistent Low')) return 'The glucose curve has been low recently, please see "Basis for the Verdict" below for details';
    if (latestRecord.value.faultSubtype.includes('No Fluctuation')) return 'The recent blood glucose curve shows a long gentle range with minimal change. For details, see "Basis for the Verdict" below';
    if (latestRecord.value.faultSubtype.includes('Data Deviation')) {
      const wearHoursTotal = (device.value?.wearDays ?? 0) * 24 + (device.value?.wearHours ?? 0);
      const isWithin48 = wearHoursTotal < 48;
      if (isWithin48) {
        return isFault.value
          ? 'Device is within 48h of activation. The paired CGM and fingerstick screenshots hit the Large-bias check within 48h rule.'
          : 'The device is within 48h of activation. The current screenshot pairing is still within the allowed range.';
      } else {
        return isFault.value
          ? 'The device is after 48h of activation. The paired CGM and fingerstick screenshots hit the Accuracy check after 48h rule.'
          : 'Device snapshot is After 48h of activation. The reviewed CGM and fingerstick pairs stay inside the current review rule.';
      }
    }
    return 'The recent blood glucose curve showed repeated jumping points within the screening window.';
  }
  if (categoryKey.value === 'detachment') {
    return isFault.value
      ? 'The record shows a sensor fall-off pattern, and the device is already in an abnormal state.'
      : 'The current record does not show a confirmed sensor fall-off pattern.';
  }
  if (categoryKey.value === 'sensor') {
    if (!isFault.value) return 'No abnormal sensor status has been detected on this device; therefore, after-sales support cannot be provided.';
    if (latestRecord.value.faultSubtype.includes('Initialization')) return 'The device shows an abnormality during initialization.';
    if (latestRecord.value.faultSubtype.includes('Temporary')) return 'Temporary sensor abnormality detected. Please check again after 3 hours to confirm whether the device has returned to normal.';
    if (latestRecord.value.faultSubtype.includes('Probe')) return 'The current sensor has failed and cannot be reactivated.';
    return 'Keep wearing the device unless it has already fallen off or support instructs removal.';
  }
  return isFault.value
    ? 'The uploaded photos match an application-failure pattern.'
    : 'The current photo set does not show a clear application-failure pattern.';
});
const historyLookback = computed(() => {
  if (!latestRecord.value) return '';
  if (categoryKey.value === 'detachment' || categoryKey.value === 'implant') {
    return 'Not applicable';
  }
  const prior = store.visibleRecords.value.some(r => 
    r.sn === latestRecord.value?.sn && 
    r.id !== latestRecord.value?.id && 
    r.faultCategory === latestRecord.value?.faultCategory &&
    r.conclusion === 'Issue Detected'
  );
  return prior ? 'Seen before' : 'No prior record found';
});
const hasUploadedFiles = computed(() => {
  if (!latestRecord.value) return false;
  const evidence = latestRecord.value.evidence;
  if (!evidence) return false;
  const files = (evidence as any).file_ids || (evidence as any).fileIds;
  return Array.isArray(files) && files.length >= 4;
});

function formatReasonValue(val: string): string {
  if (!val || val === '/') return '';
  return formatDurationText(val);
}


function presentationReasonRows(presentation: VerdictPresentation): VerdictDisplayRow[] {
  const rows: VerdictDisplayRow[] = [];
  if (presentation.whatWeFound && presentation.whatWeFound !== '/') {
    rows.push({ k: 'What we found', v: formatReasonValue(presentation.whatWeFound), cls: 'subtle' });
  }
  if (presentation.whyThisResult && presentation.whyThisResult !== '/') {
    rows.push({ k: 'Judging after-sales standards', v: formatReasonValue(presentation.whyThisResult), cls: 'subtle' });
  }
  if (presentation.possibleCauses && presentation.possibleCauses !== '/') {
    rows.push({ k: 'Possible causes', v: formatReasonValue(presentation.possibleCauses), cls: 'subtle' });
  }
  return rows;
}

const reasonRows = computed<VerdictDisplayRow[]>(() => {
  if (verdictPresentation.value) {
    const rows = presentationReasonRows(verdictPresentation.value);
    if (rows.length > 0) return rows;
  }
  if (!latestRecord.value) return [];
  if (categoryKey.value === 'inaccuracy') {
    if (latestRecord.value.faultSubtype.includes('Fraud')) {
      return [
        {
          k: 'What we found',
          v: 'Evidence verification failed.<div style="font-size:0.85em;color:var(--text-muted);margin-top:4px;">Screen reproduction / fraud attempt was identified in the uploaded photos.</div>',
          cls: 'subtle',
        },
        {
          k: 'Judging after-sales standards',
          v: 'The claim was blocked by the security rule engine.<div style="font-size:0.85em;color:var(--text-muted);margin-top:4px;">Current review triggered security and reproducibility rules.</div>',
          cls: 'subtle',
        },
      ];
    }
    if (latestRecord.value.faultSubtype.includes('Accuracy Within Normal Limits')) {
      return [
        {
          k: 'What we found',
          v: 'CGM/BGM readings are within normal limits.<div style="font-size:0.85em;color:var(--text-muted);margin-top:4px;">One or more groups do not show significant deviation.</div>',
          cls: 'subtle',
        },
        {
          k: 'Judging after-sales standards',
          v: 'The paired comparison readings are too close to justify a replacement.<div style="font-size:0.85em;color:var(--text-muted);margin-top:4px;">Deviation does not exceed acceptable limits.</div>',
          cls: 'subtle',
        },
      ];
    }
    if (!isFault.value && latestRecord.value.faultSubtype.includes('Review Required')) {
      if (hasUploadedFiles.value) {
        const extra = latestRecord.value.reasonSummary ? ` ${formatReasonValue(latestRecord.value.reasonSummary)}` : '';
        return [
          {
            k: 'What we found',
            v: `Evidence verification failed.<div style="font-size:0.85em;color:var(--text-muted);margin-top:4px;">The uploaded CGM/BGM comparison images were blurry, unreadable or invalid.${extra}</div>`,
            cls: 'subtle',
          },
          {
            k: 'Judging after-sales standards',
            v: 'The rule engine requires clear, readable paired CGM/BGM screenshots.<div style="font-size:0.85em;color:var(--text-muted);margin-top:4px;">CGM and BGM screenshots must show clear comparison values.</div>',
            cls: 'subtle',
          },
        ];
      }
      return [
        {
          k: 'What we found',
          v: 'First-pass curve screening did not hit any after-sales pattern.<div style="font-size:0.85em;color:var(--text-muted);margin-top:4px;">No persistent low, flat-line, or jump-point detected.</div>',
          cls: 'subtle',
        },
        {
          k: 'Judging after-sales standards',
          v: 'First-round curve result is insufficient for direct replacement.<div style="font-size:0.85em;color:var(--text-muted);margin-top:4px;">The case must proceed to CGM/BGM image comparison.</div>',
          cls: 'subtle',
        },
      ];
    }
    if (latestRecord.value.faultSubtype.includes('Persistent Low')) {
      const rules = store.activeThresholdProfile.value.rules;
      const belowMmol = rules.inaccuracy.lowPersist.belowMmol;
      const minHours = rules.inaccuracy.lowPersist.minHours;
      const max24hMmol = rules.inaccuracy.lowPersist.max24hMmol;
      return [
        { k: 'What we found', v: formatReasonValue(`Persistent-low pattern was detected. Low 5.2 h below ${belowMmol} mmol/L, 24h peak 7.4 mmol/L after 48h`), cls: 'subtle' },
        { k: 'Judging after-sales standards', v: formatReasonValue(`Persistent-low after-sales rule is met. Low <= ${belowMmol} for ${minHours}h, 24h peak <= ${max24hMmol}. Current record meets all thresholds`), cls: 'subtle' },
        { k: 'Possible causes', v: 'Sensor has been scratched or bumped, causing it to loosen, or the electrode has not been fully inserted into the subcutaneous tissue.', cls: 'subtle' },
      ];
    }
    if (latestRecord.value.faultSubtype.includes('No Fluctuation')) {
      const rules = store.activeThresholdProfile.value.rules;
      const floorMmol = rules.inaccuracy.noFluctuation.floorMmol;
      const minHours = rules.inaccuracy.noFluctuation.minHours;
      const maxSwingMmol = rules.inaccuracy.noFluctuation.maxSwingMmol;
      return [
        { k: 'What we found', v: formatReasonValue('No-fluctuation pattern was detected. Flat 9.3h, Swing about 0.4 mmol/L. after 48h'), cls: 'subtle' },
        { k: 'Judging after-sales standards', v: formatReasonValue(`No-fluctuation after-sales rule is met. Needs >= ${floorMmol} for ${minHours}h, Swing <= ${maxSwingMmol}mmol/L. Current record matches the flat-line rule`), cls: 'subtle' },
        { k: 'Possible causes', v: '', cls: 'subtle' },
      ];
    }
    if (latestRecord.value.faultSubtype.includes('Jump')) {
      const rules = store.activeThresholdProfile.value.rules;
      const deltaMmol = rules.inaccuracy.jump.deltaMmol;
      const consecutive = rules.inaccuracy.jump.consecutive;
      return [
        { k: 'What we found', v: formatReasonValue('Jump-point pattern was detected. Max step 3.4 mmol/L, Consecutive jumps 3 after 48h'), cls: 'subtle' },
        { k: 'Judging after-sales standards', v: formatReasonValue(`Jump-point after-sales rule is met. Adjacent jump > ${deltaMmol}, At least ${consecutive} consecutive steps. Current record matches the jump rule`), cls: 'subtle' },
        { k: 'Possible causes', v: 'The tissue around the sensor moves, resulting in some changes in the soft needle in the implanted part, and small probability events such as sensor loosening cannot be ruled out in some specific cases', cls: 'subtle' },
      ];
    }
    if (latestRecord.value.faultSubtype.includes('Data Deviation') || latestRecord.value.faultSubtype.includes('Normal Limits')) {
      const wearHoursTotal = (device.value?.wearDays ?? 0) * 24 + (device.value?.wearHours ?? 0);
      const isWithin48 = wearHoursTotal < 48;
      const isEligible = latestRecord.value.afterSales === 'Replacement Eligible';
      const rules = store.activeThresholdProfile.value.rules;
      
      if (isWithin48) {
        const deviationMmol = rules.inaccuracy.deviation.within48hDeviationMmol;
        const pairCount = rules.inaccuracy.deviation.within48hPairCount;
        if (isEligible) {
          return [
            { k: 'What we found', v: formatReasonValue('OCR completed screenshot pair extraction. P1 5.5 vs 7.2, P2 6.1 vs 8.3. 2/2 pairs out of band. Timing valid'), cls: 'subtle' },
            { k: 'Judging after-sales standards', v: formatReasonValue(`Within-48h deviation rule is met. Abs diff <= ${deviationMmol} mmol/L, Reject at ${pairCount} failed pairs. Current pair set reaches reject threshold`), cls: 'subtle' },
            { k: 'Possible causes', v: 'CGM application creates a tiny wound. During healing, immune activity may affect nearby glucose and cause temporary reading deviations. This is the “adjustment period.” After it passes, readings usually become more stable and accurate.', cls: 'subtle' },
          ];
        } else {
          return [
            { k: 'What we found', v: formatReasonValue('OCR pairing completed; display whether each set of values is in band and whether the time is independent.'), cls: 'subtle' },
            { k: 'Judging after-sales standards', v: formatReasonValue(`Failure to meet the failure threshold of > ${deviationMmol} mmol/L required for at least ${pairCount} sets of comparison charts.`), cls: 'subtle' },
            { k: 'Possible causes', v: '', cls: 'subtle' },
          ];
        }
      } else {
        const after48hDeviationRangePct = rules.inaccuracy.deviation.after48hDeviationRangePct;
        if (isEligible) {
          return [
            { k: 'What we found', v: formatReasonValue('OCR completed screenshot pair extraction. P1 5.5 vs 7.2, P2 6.1 vs 8.3. 2/2 pairs out of band. Timing valid'), cls: 'subtle' },
            { k: 'Judging after-sales standards', v: formatReasonValue(`Accuracy check after 48h is met. Rule: 2/2 pairs must fail strict ${after48hDeviationRangePct}% consistency. Current pair set fails the strict ${after48hDeviationRangePct}% consistency check in both pairs.`), cls: 'subtle' },
            { k: 'Possible causes', v: 'CGM measures glucose in interstitial fluid, while BGM measures glucose in capillary blood. When glucose changes quickly, the difference between the two can be larger, so CGM accuracy cannot be assessed accurately.', cls: 'subtle' },
          ];
        } else {
          return [
            { k: 'What we found', v: formatReasonValue('OCR completed screenshot pair extraction. Stage After 48h of activation, P1 5.5 vs 5.8, P2 6.1 vs 6.3. All pairs stayed in band. Timing valid'), cls: 'subtle' },
            { k: 'Judging after-sales standards', v: formatReasonValue('OCR completed screenshot pair extraction.'), cls: 'subtle' },
            { k: 'Possible causes', v: 'The clinical evaluation of the accuracy of CGM is mainly evaluated through the "reference value 20/20% agreement rate", that is, when the monitoring value is > 4.4 mmol/L, the deviation from the reference value is within the range of ±20%; When the monitoring value is ≤ 4.4 mmol/L, the deviation is 1.1 mmol/L; The proportion of points deviating from the reference value is > 65%, which is the technical standard requirement of CGM.', cls: 'subtle' },
          ];
        }
      }
    }
  }
  if (categoryKey.value === 'detachment') {
    const status = device.value?.status || 'N/A';
    const lastUpload = device.value?.lastDataAt || 'N/A';
    return [
      {
        k: 'What we found',
        v: formatReasonValue(isFault.value
          ? 'Abnormal detachment-like state is present.'
          : `No confirmed detachment signal is present. State ${status}. Last Upload ${lastUpload}`),
        cls: 'subtle',
      },
      {
        k: 'Judging after-sales standards',
        v: formatReasonValue(isFault.value
          ? 'Detachment after-sales rule is met.'
          : `Detachment after-sales rule is not met. This path only accepts abnormal devices. Current state is ${status}`),
        cls: 'subtle',
      },
      { k: 'Possible causes', v: '', cls: 'subtle' },
    ];
  }
  if (categoryKey.value === 'sensor') {
    if (!isFault.value) {
      return [
        { k: 'What we found', v: formatReasonValue('The current device entered the sensor abnormality review, but no abnormal conclusion was formed; display the current stage, status / clasp status, and latest signal time.'), cls: 'subtle' },
        { k: 'Judging after-sales standards', v: formatReasonValue('The confirmed sensor abnormality rule is not hit.'), cls: 'subtle' },
        { k: 'Possible causes', v: '', cls: 'subtle' },
      ];
    }
    const init = latestRecord.value.faultSubtype.includes('Initialization');
    return [
      {
        k: 'What we found',
        v: formatReasonValue(init
          ? 'Initialization abnormality was detected on the current device.'
          : 'An abnormal status has been detected on the current device.'),
        cls: 'subtle',
      },
      {
        k: 'Judging after-sales standards',
        v: formatReasonValue(init
          ? 'The initialization-abnormality rule is met.'
          : 'The in-use sensor-fault rule is met. Sustained abnormality is outside the initialization stage.'),
        cls: 'subtle',
      },
      {
        k: 'Possible causes',
        v: formatReasonValue(init
          ? 'The guide needle may not have fully covered the soft needle after implantation, so the soft needle was not completely inserted under the skin and could not monitor glucose in interstitial fluid.'
          : 'This may be caused by certain low-probability situations, such as sensor loosening. It may also happen when the implanted site contains rich muscle tissue or when muscle stretching affects the sensor electrode, which then impacts data transmission.'),
        cls: 'subtle',
      },
    ];
  }
  const evidence = latestRecord.value.evidence as VisionEvidence | undefined;
  const vision = evidence?.vision;
  const finalScenario = vision?.final_scenario ?? 'None of the above';
  const scenarios = vision?.scenarios || [];

  let checklistHtml = '';
  if (scenarios.length > 0) {
    checklistHtml = `<div class="scenario-checklist-title" style="font-weight: 600; margin-top: 12px; margin-bottom: 6px;">Scenario checklist:</div>` +
      `<ul class="verdict-rich-list" style="margin-top: 4px;">` +
      scenarios.map(s => {
        const isCurrent = s.scenario === finalScenario;
        const icon = s.matched
          ? '<span style="color: #10b981; font-weight: bold; margin-right: 4px;">✓</span>'
          : '<span style="color: #ef4444; font-weight: bold; margin-right: 4px;">✗</span>';
        const matchText = s.matched ? 'Matched' : 'Unmatched';
        const badge = isCurrent ? ` <span style="background-color: #dbeafe; color: #1e40af; font-size: 0.75em; padding: 2px 6px; border-radius: 4px; font-weight: 500; margin-left: 6px;">Highest match</span>` : '';
        return `<li style="margin-bottom: 6px; list-style-type: none; padding-left: 0;">
          ${icon} <strong>${s.scenario}</strong>: ${matchText}${badge}
          <div style="font-size: 0.85em; color: #6b7280; margin-top: 2px; padding-left: 18px;">${s.reason || 'No specific reasons provided by model.'}</div>
        </li>`;
      }).join('') +
      `</ul>`;
  }

  const resultText = isFault.value
    ? `The uploaded photos match an application-failure pattern: <strong>${latestRecord.value.faultSubtype}</strong>.`
    : `No qualifying application-failure pattern was identified.`;

  const whyText = isFault.value
    ? `The VLM analyzed the uploaded photos and matched the <strong>${finalScenario}</strong> scenario, exceeding the replacement threshold.`
    : `The VLM analyzed the uploaded photos, but no scenario met the replacement or manual review threshold. The highest matched scenario was <strong>${finalScenario}</strong>.`;

  return [
    { k: 'What we found', v: `${resultText}<div style="font-size:0.85em;color:var(--text-muted);margin-top:4px;">Photo count: ${implantPhotoCount.value || 2}.</div>`, cls: 'subtle' },
    { k: 'Judging after-sales standards', v: `${whyText}${checklistHtml}`, cls: 'subtle' },
    { k: 'Possible causes', v: isFault.value ? 'Physical damage or insertion site characteristics.<div style="font-size:0.85em;color:var(--text-muted);margin-top:4px;">Sensor probe damaged during installation or site interfered with adhesive.</div>' : '', cls: 'subtle' },
  ];
});
function formatDateTime(isoString: string | null | undefined): string {
  if (!isoString) return '';
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return isoString;
    const Y = date.getFullYear();
    const M = String(date.getMonth() + 1).padStart(2, '0');
    const D = String(date.getDate()).padStart(2, '0');
    const h = String(date.getHours()).padStart(2, '0');
    const m = String(date.getMinutes()).padStart(2, '0');
    const s = String(date.getSeconds()).padStart(2, '0');
    return `${Y}-${M}-${D} ${h}:${m}:${s}`;
  } catch {
    return isoString;
  }
}

const deviceOverviewRows = computed(() => {
  const wearHours = (device.value?.wearDays ?? 0) * 24 + (device.value?.wearHours ?? 0);
  const wearWindow = `Worn ${formatDurationHours(wearHours)}`;
  const rows = [
    { k: 'Device Identifier', v: device.value?.sn ?? '', cls: 'mono' },
    { k: 'Activated', v: formatDateTime(device.value?.activatedAt) },
    { k: 'Worn time', v: wearWindow },
  ];
  return rows;
});

function presentationGuidanceItems(guidance: VerdictPresentationGuidance): VerdictDisplayRow[] {
  if (guidance.text) {
    return [{ k: 'Guidance', v: formatReasonValue(guidance.text), cls: 'subtle' }];
  }
  return [
    guidance.afterSalesStatus ? { k: 'After-sales status', v: formatReasonValue(guidance.afterSalesStatus), cls: 'subtle' } : null,
    guidance.why ? { k: 'Why', v: formatReasonValue(guidance.why), cls: 'subtle' } : null,
    (guidance.wearingAdvice || (guidance as any).wearingAdvice || (guidance as any).wearerAdvice) ? { k: 'Wearing advice', v: formatReasonValue(guidance.wearingAdvice || (guidance as any).wearingAdvice || (guidance as any).wearerAdvice), cls: 'subtle' } : null,
    guidance.nextAction ? { k: 'Next action', v: formatReasonValue(guidance.nextAction), cls: 'subtle' } : null,
  ].filter((item): item is VerdictDisplayRow => item !== null);
}

const nextStepItems = computed<VerdictDisplayRow[]>(() => {
  if (verdictPresentation.value) {
    const items = presentationGuidanceItems(verdictPresentation.value.guidance ?? {});
    if (items.length > 0) return items;
  }
  if (!latestRecord.value) return [];
  if (categoryKey.value === 'inaccuracy') {
    if (latestRecord.value.faultSubtype.includes('Fraud')) {
      return [
        { k: 'After-sales status', v: 'Do not continue to after-sales (replacement not allowed).', cls: 'subtle' },
        { k: 'Why', v: 'Evidence verification failed due to screen reproduction (fraud attempt) detected in the uploaded photos.', cls: 'subtle' },
        { k: 'Wearing advice', v: 'Wearer should keep the sensor in place unless removed, but this service request is rejected.', cls: 'subtle' },
        { k: 'Next action', v: 'Customer service agent terminates the request. No replacement path is recommended.', cls: 'subtle' },
      ];
    }
    if (latestRecord.value.faultSubtype.includes('Accuracy Within Normal Limits')) {
      return [
        { k: 'After-sales status', v: 'Do not continue to after-sales (replacement not allowed).', cls: 'subtle' },
        { k: 'Why', v: 'Sensor accuracy is within acceptable limits; deviations do not exceed the threshold.', cls: 'subtle' },
        { k: 'Wearing advice', v: 'Keep wearing the sensor and monitor readings. Perform another fingerstick comparison if deviation is suspected again.', cls: 'subtle' },
        { k: 'Next action', v: 'Customer service agent rejects the replacement request and guides user on normal wear.', cls: 'subtle' },
      ];
    }
    if (latestRecord.value.faultSubtype.includes('Persistent Low')) {
      return [
        { k: 'After-sales status', v: 'You can continue to after-sales from this result.', cls: 'subtle' },
        { k: 'Why', v: 'The first-pass CGM screening hit the persistent low rule for this record, so the issue can move forward without the paired screenshot branch.', cls: 'subtle' },
        { k: 'Wearing advice', v: 'Keep wearing the device unless it has already fallen off or support instructs removal.', cls: 'subtle' },
        { k: 'Next action', v: 'Continue to the after-sales application with this screening result.', cls: 'subtle' },
      ];
    }
    if (latestRecord.value.faultSubtype.includes('No Fluctuation')) {
      return [
        { k: 'After-sales status', v: 'You can continue to after-sales from this result.', cls: 'subtle' },
        { k: 'Why', v: 'The first-pass CGM screening hit the no fluctuation rule for this record, so the issue can move forward without the paired screenshot branch.', cls: 'subtle' },
        { k: 'Wearing advice', v: 'Keep wearing the device unless it has already fallen off or support instructs removal.', cls: 'subtle' },
        { k: 'Next action', v: 'Continue to the after-sales application with this screening result.', cls: 'subtle' },
      ];
    }
    if (latestRecord.value.faultSubtype.includes('Jump')) {
      return [
        { k: 'After-sales status', v: 'You can continue to after-sales from this result.', cls: 'subtle' },
        { k: 'Why', v: 'The first-pass CGM screening hit the jump points rule for this record, so the issue can move forward without the paired screenshot branch.', cls: 'subtle' },
        { k: 'Wearing advice', v: 'Keep wearing the device unless it has already fallen off or support instructs removal.', cls: 'subtle' },
        { k: 'Next action', v: 'Continue to the after-sales application with this screening result.', cls: 'subtle' },
      ];
    }
    if (latestRecord.value.faultSubtype.includes('Data Deviation')) {
      const wearHoursTotal = (device.value?.wearDays ?? 0) * 24 + (device.value?.wearHours ?? 0);
      const isWithin48 = wearHoursTotal < 48;
      const isEligible = latestRecord.value.afterSales === 'Replacement Eligible';
      const rules = store.activeThresholdProfile.value.rules;
      
      if (isWithin48) {
        const deviationMmol = rules.inaccuracy.deviation.within48hDeviationMmol;
        if (isEligible) {
          return [
            { k: 'After-sales status', v: 'You can continue to after-sales from this result.', cls: 'subtle' },
            { k: 'Why', v: `The paired CGM and fingerstick screenshots exceed the <= ${deviationMmol} mmol/L rule within the first 48 hours of wear.`, cls: 'subtle' },
            { k: 'Wearing advice', v: 'Guide users to continue wearing the device and monitoring the data, or guide them to remove it and make a replacement to them.', cls: 'subtle' },
            { k: 'Next action', v: 'If you decide to replace the device for the user, you can guide them to remove it.', cls: 'subtle' },
          ];
        } else {
          return [
            { k: 'Guidance', v: 'Cannot follow the data deviation path to enter after-sales service; if you still suspect the deviation, upload a more matching screenshot.', cls: 'subtle' },
          ];
        }
      } else {
        if (isEligible) {
          return [
            { k: 'After-sales status', v: 'You can continue to after-sales from this result.', cls: 'subtle' },
            { k: 'Why', v: 'Both sets of comparative data exceeded the set range and met the after-sales conditions.', cls: 'subtle' },
            { k: 'Wearing advice', v: 'Guide users to continue wearing the device and monitoring the data, or guide them to remove it and make a replacement to them.', cls: 'subtle' },
            { k: 'Next action', v: 'If you decide to replace the device for the user, you can guide them to remove it.', cls: 'subtle' },
          ];
        } else {
          return [
            { k: 'After-sales status', v: 'Do not continue to after-sales on the data-deviation path.', cls: 'subtle' },
            { k: 'Why', v: 'Neither of the two sets meets the condition that the comparison data exceeds the set range, so the current record does not meet this rule.', cls: 'subtle' },
            { k: 'Wearing advice', v: 'Continue normal wear guidance and keep the sensor in place unless support instructs removal.', cls: 'subtle' },
            { k: 'Next action', v: 'If mismatch is still a concern, upload a new set of timestamp-matched CGM and fingerstick screenshots for another review.', cls: 'subtle' },
          ];
        }
      }
    }
    if (!isFault.value && latestRecord.value.faultSubtype.includes('Review Required')) {
      return [
        { k: 'After-sales status', v: 'Pending first-round curve screening results (cannot enter after-sales yet).', cls: 'subtle' },
        { k: 'Why', v: 'The first-pass curve screening did not hit persistent low, flat-line, or jump-point.', cls: 'subtle' },
        { k: 'Wearing advice', v: 'Keep wearing the sensor while preparing the paired comparison screenshots.', cls: 'subtle' },
        { k: 'Next action', v: 'Agent triggers the blood sugar deviation check. User uploads two paired CGM/BGM screenshots to proceed on the deviation path.', cls: 'subtle' },
      ];
    }
  }
  if (latestRecord.value.afterSales === 'Replacement Eligible') {
    if (categoryKey.value === 'detachment') {
      return [
        { k: 'After-sales status', v: 'You can continue to after-sales from this result.', cls: 'subtle' },
        { k: 'Why', v: 'The current device matches the fall off rule.', cls: 'subtle' },
        { k: 'Wearing advice', v: 'Do not reattach the device if it has already fallen off.', cls: 'subtle' },
        { k: 'Next action', v: 'Continue to the after-sales application with this record.', cls: 'subtle' },
      ];
    }
    if (categoryKey.value === 'sensor') {
      const init = latestRecord.value.faultSubtype.includes('Initialization');
      return [
        { k: 'After-sales status', v: 'You can continue to after-sales from this result.', cls: 'subtle' },
        { k: 'Why', v: init
          ? 'The current device matches the initialization-abnormality rule, so this record supports after-sales on the sensor-abnormality path.'
          : 'The current device matches the in-use abnormality, so this record supports after-sales on the sensor-abnormality path.', cls: 'subtle' },
        { k: 'Wearing advice', v: init
          ? 'This device is no longer usable. Please guide the user to properly remove the sensor. Remind users to wear the sensors according to the video.'
          : 'This device is no longer usable. Please guide the user to properly remove the sensor.', cls: 'subtle' },
        { k: 'Next action', v: 'Provide after-sales service for this device.', cls: 'subtle' },
      ];
    }
    if (categoryKey.value === 'implant') {
      return [
        { k: 'After-sales status', v: 'You can continue to after-sales from this result.', cls: 'subtle' },
        { k: 'Why', v: `The VLM analyzed the uploaded photos and matched the ${latestRecord.value.faultSubtype} scenario, exceeding the replacement threshold.`, cls: 'subtle' },
        { k: 'Wearing advice', v: 'Guide users to continue wearing the device and monitoring the data, or guide them to remove it and make a replacement to them.', cls: 'subtle' },
        { k: 'Next action', v: 'If you decide to replace the device for the user, you can guide them to remove it.', cls: 'subtle' },
      ];
    }
    const why = 'The first-pass CGM screening hit the configured rule.';
    return [
      { k: 'After-sales status', v: 'Replacement allowed (eligible for after-sales).', cls: 'subtle' },
      { k: 'Why', v: why, cls: 'subtle' },
      { k: 'Wearing advice', v: 'User should properly remove the sensor and prepare for replacement. Wear the new sensor according to standard video guidance.', cls: 'subtle' },
      { k: 'Next action', v: 'Agent triggers the replacement dispatch. Guide the user to submit the formal replacement claim.', cls: 'subtle' },
    ];
  }
  if (latestRecord.value.afterSales === 'Not Eligible') {
    if (categoryKey.value === 'detachment') {
      return [
        { k: 'After-sales status', v: 'Do not continue to after-sales on the fall off path. If the user has provided a picture of the device falling off, please make a manual judgment.', cls: 'subtle' },
        { k: 'Why', v: 'The current record does not show the abnormal device state required by the fall off rule.', cls: 'subtle' },
        { k: 'Wearing advice', v: 'Keep monitoring the device status in the app. If the user has provided a picture of the device falling off, please make a manual judgment.', cls: 'subtle' },
        { k: 'Next action', v: 'If the user provides photos proving the detachment, please consider the after-sales policy to decide whether to replace the product.', cls: 'subtle' },
      ];
    }
    if (categoryKey.value === 'sensor') {
      return [
        { k: 'Guidance', v: 'No abnormal state of the device has been detected, please make a manual judgment based on the specific display of the screenshot on the homepage of the user APP.', cls: 'subtle' },
      ];
    }
  }
  return [
    { k: 'After-sales status', v: 'Do not continue to after-sales (replacement not allowed).', cls: 'subtle' },
    { k: 'Why', v: 'The current evidence does not match the after-sales rule.', cls: 'subtle' },
    { k: 'Wearing advice', v: 'Continue normal wear and monitoring unless symptoms change.', cls: 'subtle' },
    { k: 'Next action', v: 'Agent rejects the request. User may re-check issue or upload new evidence if needed.', cls: 'subtle' },
  ];
});
const pageId = computed(() => {
  if (phase.value === 'form') return 'page-detect-form';
  if (phase.value === 'inaccuracy-upload') return 'page-inaccuracy-upload';
  if (phase.value === 'processing') return 'page-processing';
  return 'page-result';
});

const categoryInfo = computed(() => {
  const category = selectedCategory.value;
  if (category === 'Data accuracy') {
    return {
      title: 'Data accuracy',
      subtitle: 'We will first run the first round of curve screening, and then decide whether to require blood glucose data comparison screenshots.',
      guidanceType: 'guidance-data',
      guidanceTitle: 'Required interaction',
      guidanceItems: [
        'Persistent low, no fluctuation, and jump-point checks run first.',
        'Data Deviation cases must collect two paired CGM/BGM image groups before review.',
      ],
      primaryLabel: 'Run automated curve screening',
    };
  }
  if (category === 'Application failure') {
    return {
      title: 'Application failure',
      subtitle: 'Upload at least two clear site photos. VLM infers the official application-failure sub-type automatically.',
      guidanceType: 'guidance-implant',
      guidanceTitle: 'Photo requirement',
      guidanceItems: [
        'At least two site photos are required before submission.',
        'No manual sub-type selection is needed for this path.',
      ],
      primaryLabel: 'Run detection',
    };
  }
  if (category === 'Sensor falling off') {
    return {
      title: 'Sensor falling off',
      subtitle: 'No supporting materials are shown. The result is judged directly from device status and sensor timing.',
      guidanceType: 'guidance-teal',
      guidanceTitle: 'Instant run',
      guidanceItems: [
        'Check abnormal device state, last upload, anomaly timeline, and wear window.',
        'No image upload is required for this scenario.',
      ],
      primaryLabel: 'Run detection',
    };
  }
  return {
    title: 'Sensor Abnormal',
    subtitle: 'Evaluate initialization, in-use abnormality, temporary recovery, and sensor failure paths.',
    guidanceType: 'guidance-teal',
    guidanceTitle: 'Instant run',
    guidanceItems: [
      'Check sensor status, initialization phase, anomaly timeline, and recovery status.',
      'No image upload is required for this scenario.',
    ],
    primaryLabel: 'Run detection',
  };
});
const implantUploadStatus = computed(() => {
  if (implantPhotoCount.value >= 2) return `${implantPhotoCount.value} photo(s) uploaded; minimum met (>=2 required for application-failure path).`;
  if (uploadError.value) return uploadError.value;
  return `${implantPhotoCount.value} / 2 minimum; add at least ${2 - implantPhotoCount.value} more photo(s) before running application-failure detection.`;
});
const deviationUploadStatus = computed(() => {
  if (deviationImageCount.value >= 4) return '2 / 2 CGM/BGM groups uploaded; minimum met.';
  if (deviationUploadError.value) return deviationUploadError.value;
  const remaining = 4 - deviationImageCount.value;
  return `${deviationImageCount.value} / 4 images uploaded; add ${remaining} more CGM/BGM image(s).`;
});

watch([selectedCategory, routeRecordId, () => route.query.session, () => device.value?.sn], () => {
  const session = routeSession.value;
  routeRecordError.value = '';
  clearProcessingTimers();
  inaccuracyDeviationMode.value = false;
  deviationImageCount.value = 0;
  deviationUploadError.value = '';
  implantPhotoCount.value = 0;
  uploadError.value = '';
  processingProgress.value = 0;
  processingComplete.value = false;
  processingSessionId.value = '';

  remoteDetectRecord.value = null;
  remoteDetectFinished.value = false;
  remoteDetectError.value = null;

  implantFileIds.value = [null, null, null];
  implantFileNames.value = [null, null, null];
  implantUploading.value = [false, false, false];
  deviationFileIds.value = [null, null, null, null];
  deviationFileNames.value = [null, null, null, null];
  deviationFilePreviews.value = [null, null, null, null];
  deviationUploading.value = [false, false, false, false];
  deviationUploadModalOpen.value = false;
  deviationPreviewOpen.value = false;
  deviationPreviewSrc.value = '';
  deviationPreviewName.value = '';

  activeRecordId.value = routeRecordId.value || session?.recordId || '';
  restoreDeviceFromLatestRecord();

  if (isDetectRoute.value && !hasRouteContext.value && !latestCompletedRouteRecord.value) {
    phase.value = 'form';
    void router.replace({
      name: 'fault-query',
      params: { categoryKey: keyForFaultCategory(selectedCategory.value) },
      query: { fromDetect: '1' },
    });
    return;
  }

  if (!device.value && !routeRecordId.value && !session) {
    phase.value = 'form';
    return;
  }

  // Populate files from query if redirecting from fault query page
  if (queryFiles.value) {
    const fileIds = queryFiles.value.split(',');
    if (selectedCategory.value === 'Data accuracy') {
      fileIds.forEach((id, idx) => {
        if (idx < deviationFileIds.value.length) {
          deviationFileIds.value[idx] = id;
          deviationFileNames.value[idx] = `uploaded_cgm_bgm_${idx + 1}.png`;
        }
      });
      deviationImageCount.value = fileIds.length;
      inaccuracyDeviationMode.value = true;
    } else if (selectedCategory.value === 'Application failure') {
      fileIds.forEach((id, idx) => {
        if (idx < implantFileIds.value.length) {
          implantFileIds.value[idx] = id;
          implantFileNames.value[idx] = `uploaded_implant_site_${idx + 1}.png`;
        }
      });
      implantPhotoCount.value = fileIds.length;
    }
  }

  if (!activeRecordId.value && !isRouteAutoRunRequest.value && latestCompletedRouteRecord.value) {
    activeRecordId.value = latestCompletedRouteRecord.value.id;
    restoreDeviceFromLatestRecord();
    phase.value = 'result';
    return;
  }

  if (route.query.from === 'fault-query' && !activeRecordId.value) {
    if (!device.value) {
      phase.value = 'form';
      return;
    }
    const activeSession = store.startDetectSession(props.sn, selectedCategory.value);
    beginProcessingSession(activeSession.id);
    const files = selectedCategory.value === 'Data accuracy'
      ? (deviationFileIds.value.filter(Boolean) as string[])
      : selectedCategory.value === 'Application failure'
        ? (implantFileIds.value.filter(Boolean) as string[])
        : [];
    void store.runDetectRemote(props.sn, selectedCategory.value, files).then(record => {
      completeProcessingWithResult(record);
    }).catch(() => {
      proceedToResult(null);
    });
    return;
  }

  if (session?.status === 'processing' && !activeRecordId.value) {
    beginProcessingSession(session.id);
    return;
  }

  if (routeRecordId.value) {
    if (store.backendOnline.value) {
      phase.value = latestRecord.value ? 'result' : 'form';
      routeDeviceLoading.value = true;
      backendApi.getDetection(routeRecordId.value)
        .then(record => {
          if (record) {
            store.restoreDetectRecord(record);
            phase.value = 'result';
          } else {
            routeRecordError.value = `Record with ID "${routeRecordId.value}" was not found.`;
          }
        })
        .catch(err => {
          routeRecordError.value = err instanceof Error ? err.message : 'Unable to load record.';
        })
        .finally(() => {
          routeDeviceLoading.value = false;
        });
    } else {
      const record = latestRecord.value;
      if (record) {
        phase.value = 'result';
      } else {
        routeRecordError.value = `Record with ID "${routeRecordId.value}" was not found in history.`;
      }
    }
    return;
  }

  phase.value = latestRecord.value ? 'result' : 'form';
}, { immediate: true });

watch(latestRecord, record => {
  if (record) {
    restoreDeviceFromLatestRecord();
  }
  if (record && phase.value !== 'processing') {
    phase.value = 'result';
  }
}, { immediate: true });

function triggerImplantUpload(index: number) {
  if (!store.backendOnline.value) {
    if (implantPhotoCount.value >= 3) return;
    implantPhotoCount.value += 1;
    implantFileIds.value[index] = `mock-implant-${Date.now()}`;
    implantFileNames.value[index] = `uploaded_implant_site_${index + 1}.jpg`;
    uploadError.value = '';
    return;
  }
  const input = document.getElementById(`implant-file-input-${index}`) as HTMLInputElement | null;
  if (input) {
    input.click();
  }
}

async function uploadImplantFileForIndex(file: File, index: number) {
  implantUploading.value[index] = true;
  uploadError.value = '';
  try {
    const compressed = await compressImage(file);
    const res = await backendApi.uploadFile(compressed);
    implantFileIds.value[index] = res.id;
    implantFileNames.value[index] = res.filename;
    implantPhotoCount.value = implantFileIds.value.filter(id => id !== null).length;
  } catch (err: any) {
    uploadError.value = err.message || 'Failed to upload photo.';
  } finally {
    implantUploading.value[index] = false;
  }
}

async function onImplantFileChange(event: Event, index: number) {
  const target = event.target as HTMLInputElement;
  if (!target.files || target.files.length === 0) return;
  const file = target.files[0];
  await uploadImplantFileForIndex(file, index);
  target.value = '';
}

async function handleImplantDrop(event: DragEvent, index: number) {
  const files = event.dataTransfer?.files;
  if (!files || files.length === 0) return;
  const file = files[0];
  if (!file.type.startsWith('image/')) {
    uploadError.value = 'Only image files are allowed.';
    return;
  }

  if (!store.backendOnline.value) {
    if (implantPhotoCount.value >= 3) return;
    implantPhotoCount.value += 1;
    uploadError.value = '';
    return;
  }

  await uploadImplantFileForIndex(file, index);
}

function triggerDeviationUpload(index: number) {
  if (deviationFileIds.value[index] || deviationFilePreviews.value[index]) return;
  if (!store.backendOnline.value) {
    if (deviationImageCount.value >= 4) return;
    deviationFileIds.value[index] = `mock-file-${Date.now()}`;
    deviationFileNames.value[index] = `uploaded_cgm_bgm_${index + 1}.png`;
    deviationImageCount.value = countDeviationUploads();
    deviationUploadError.value = '';
    return;
  }
  const input = (
    document.getElementById(`result-deviation-file-input-${index}`) ||
    document.getElementById(`deviation-file-input-${index}`)
  ) as HTMLInputElement | null;
  if (input) {
    input.click();
  }
}

function hasDeviationSlotImage(index: number) {
  return !!deviationFileIds.value[index] || !!deviationFilePreviews.value[index];
}

function openDeviationPreview(index: number) {
  const preview = deviationFilePreviews.value[index];
  if (!preview) return;
  deviationPreviewSrc.value = preview;
  deviationPreviewName.value = deviationFileNames.value[index] || `CGM/BGM image ${index + 1}`;
  deviationPreviewOpen.value = true;
}

function closeDeviationPreview() {
  deviationPreviewOpen.value = false;
  deviationPreviewSrc.value = '';
  deviationPreviewName.value = '';
}

function handleDeviationSlotClick(index: number) {
  if (hasDeviationSlotImage(index)) {
    openDeviationPreview(index);
    return;
  }
  triggerDeviationUpload(index);
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = event => {
      const result = event.target?.result;
      if (typeof result === 'string') {
        resolve(result);
        return;
      }
      reject(new Error('Unable to read selected image.'));
    };
    reader.onerror = () => reject(new Error('Unable to read selected image.'));
    reader.readAsDataURL(file);
  });
}

function countDeviationUploads() {
  return deviationFileIds.value.reduce((count, id, index) => (
    id || deviationFilePreviews.value[index] ? count + 1 : count
  ), 0);
}

async function uploadDeviationFileForIndex(file: File, index: number) {
  deviationUploading.value[index] = true;
  deviationUploadError.value = '';
  try {
    const preview = await readFileAsDataUrl(file);
    if (store.backendOnline.value) {
      const compressed = await compressImage(file);
      const res = await backendApi.uploadFile(compressed);
      deviationFileIds.value[index] = res.id;
      deviationFileNames.value[index] = res.filename;
    } else {
      deviationFileNames.value[index] = file.name;
    }
    deviationFilePreviews.value[index] = preview;
    deviationImageCount.value = countDeviationUploads();
  } catch (err: any) {
    deviationUploadError.value = err.message || 'Failed to upload image.';
  } finally {
    deviationUploading.value[index] = false;
  }
}

async function onDeviationFileChange(event: Event, index: number) {
  const target = event.target as HTMLInputElement;
  if (!target.files || target.files.length === 0) return;
  const file = target.files[0];
  await uploadDeviationFileForIndex(file, index);
  target.value = '';
}

async function handleDeviationDrop(event: DragEvent, index: number) {
  if (hasDeviationSlotImage(index)) return;
  const files = event.dataTransfer?.files;
  if (!files || files.length === 0) return;
  const file = files[0];
  if (!file.type.startsWith('image/')) {
    deviationUploadError.value = 'Only image files are allowed.';
    return;
  }

  if (!store.backendOnline.value) {
    if (deviationImageCount.value >= 4) return;
    deviationFileIds.value[index] = `mock-file-${Date.now()}`;
    deviationFileNames.value[index] = `uploaded_cgm_bgm_${index + 1}.png`;
    deviationImageCount.value = countDeviationUploads();
    deviationUploadError.value = '';
    return;
  }

  await uploadDeviationFileForIndex(file, index);
}

function removeDeviationSlotImage(index: number) {
  deviationFileIds.value[index] = null;
  deviationFileNames.value[index] = null;
  deviationFilePreviews.value[index] = null;
  deviationUploading.value[index] = false;
  deviationImageCount.value = Math.max(0, countDeviationUploads());
  deviationUploadError.value = '';
  closeDeviationPreview();
}

function openDeviationUploadModal() {
  inaccuracyDeviationMode.value = true;
  deviationUploadError.value = '';
  deviationUploadModalOpen.value = true;
}

function closeDeviationUploadModal() {
  deviationUploadModalOpen.value = false;
}

function finishDeviationUploadModal() {
  if (deviationImageCount.value < 4) {
    deviationUploadError.value = `${deviationImageCount.value} / 4 images uploaded; upload two CGM/BGM groups before running bias check.`;
    return;
  }
  deviationUploadModalOpen.value = false;
  submitInaccuracyDeviation();
}

function clearProcessingTimers() {
  if (processingProgressTimer) {
    window.clearInterval(processingProgressTimer);
    processingProgressTimer = undefined;
  }
  if (processingCompletionTimer) {
    window.clearTimeout(processingCompletionTimer);
    processingCompletionTimer = undefined;
  }
}

function proceedToResult(record: any) {
  clearProcessingTimers();
  processingComplete.value = false;
  if (record) {
    activeRecordId.value = record.id;
    if (processingSessionId.value) {
      store.completeDetectSession(processingSessionId.value, record);
    }
    replaceRouteWithResultRecord(record);
  }
  phase.value = 'result';
}

function replaceRouteWithResultRecord(record: DetectRecord) {
  if (!isDetectRoute.value) return;
  const nextQuery: Record<string, string> = {
    category: record.faultCategory,
  };
  const from = String(route.query.from ?? '').trim();
  const session = String(route.query.session ?? '').trim();
  const batch = String(route.query.batch ?? '').trim();
  const q = String(route.query.q ?? '').trim();
  if (from) nextQuery.from = from;
  if (session) nextQuery.session = session;
  if (batch) nextQuery.batch = batch;
  if (q) nextQuery.q = q;
  void router.replace({
    name: 'detect-record',
    params: { sn: record.sn, recordId: record.id },
    query: nextQuery,
  });
}

function finishProgressToComplete(onComplete: () => void) {
  if (processingProgressTimer) {
    window.clearInterval(processingProgressTimer);
    processingProgressTimer = undefined;
  }

  processingProgressTimer = window.setInterval(() => {
    if (processingProgress.value >= 100) {
      window.clearInterval(processingProgressTimer);
      processingProgressTimer = undefined;
      onComplete();
      return;
    }

    const remaining = 100 - processingProgress.value;
    processingProgress.value = Math.min(100, processingProgress.value + Math.max(4, remaining / 8));
  }, 80);
}

function finishCompletedRecord(record: any) {
  if (selectedCategory.value === 'Application failure' && phase.value === 'processing') {
    if (processingCompletionTimer) window.clearTimeout(processingCompletionTimer);
    finishProgressToComplete(() => {
      processingCompletionTimer = window.setTimeout(() => {
        processingComplete.value = true;
        processingCompletionTimer = window.setTimeout(() => {
          proceedToResult(record);
        }, 900);
      }, 250);
    });
    return;
  }

  if (phase.value === 'processing') {
    if (processingCompletionTimer) window.clearTimeout(processingCompletionTimer);
    finishProgressToComplete(() => {
      processingCompletionTimer = window.setTimeout(() => {
        proceedToResult(record);
      }, 450);
    });
    return;
  }

  proceedToResult(record);
}

function beginProcessingSession(sessionId: string) {
  clearProcessingTimers();
  processingStartedAt = Date.now();
  processingProgress.value = 1;
  processingComplete.value = false;
  processingSessionId.value = sessionId;
  phase.value = 'processing';
  processingProgressTimer = window.setInterval(() => {
    if (processingProgress.value >= 90) return;
    const step = processingProgress.value < 45 ? 3 : processingProgress.value < 75 ? 1.6 : 0.7;
    processingProgress.value = Math.min(90, processingProgress.value + step);
  }, 160);
}

function completeProcessingWithResult(record: any) {
  if (!record) {
    proceedToResult(record);
    return;
  }

  const elapsed = Date.now() - processingStartedAt;
  const minVisibleMs = selectedCategory.value === 'Application failure'
    ? IMPLANT_PROCESSING_MIN_VISIBLE_MS
    : PROCESSING_MIN_VISIBLE_MS;
  const remainingVisibleMs = Math.max(0, minVisibleMs - elapsed);
  if (remainingVisibleMs > 0 && phase.value === 'processing') {
    if (processingCompletionTimer) window.clearTimeout(processingCompletionTimer);
    processingCompletionTimer = window.setTimeout(() => {
      finishCompletedRecord(record);
    }, remainingVisibleMs);
    return;
  }

  finishCompletedRecord(record);
}

async function triggerRemoteDetect() {
  let fileIds: string[] = [];
  if (selectedCategory.value === 'Application failure') {
    fileIds = implantFileIds.value.filter((id): id is string => id !== null);
  } else if (inaccuracyDeviationMode.value && selectedCategory.value === 'Data accuracy') {
    fileIds = deviationFileIds.value.filter((id): id is string => id !== null);
  }

  remoteDetectRecord.value = null;
  remoteDetectFinished.value = false;
  remoteDetectError.value = null;

  try {
    const record = await store.runDetectRemote(props.sn, selectedCategory.value, fileIds);
    remoteDetectRecord.value = record;
    remoteDetectFinished.value = true;
    completeProcessingWithResult(record);
  } catch (err: any) {
    remoteDetectError.value = err;
    remoteDetectFinished.value = true;
    proceedToResult(null);
  }
}

async function startProcessing() {
  activeRecordId.value = '';
  const session = store.startDetectSession(props.sn, selectedCategory.value);
  beginProcessingSession(session.id);
  // Let Vue flush the DOM update (spinner) before the blocking API call starts
  await nextTick();
  void triggerRemoteDetect();
}

onBeforeUnmount(() => {
  clearProcessingTimers();
});


function runDetect() {
  if (selectedCategory.value === 'Application failure' && implantPhotoCount.value < 2) {
    uploadError.value = `0 / 2 minimum; add at least ${2 - implantPhotoCount.value} more photo(s) before running application-failure detection.`;
    return;
  }
  startProcessing();
}

function submitInaccuracyDeviation() {
  if (deviationImageCount.value < 4) {
    deviationUploadError.value = `${deviationImageCount.value} / 4 images uploaded; upload two CGM/BGM groups before running bias check.`;
    return;
  }
  inaccuracyDeviationMode.value = true;
  startProcessing();
}

function goToUploadFlow() {
  openDeviationUploadModal();
}
</script>

<template>
  <div v-if="isDetectRoute && device && fault && !routeRecordError" class="page active" :id="pageId">
    <div class="page-body">
      <div v-if="phase === 'form'" id="diag-form-shell" class="diag-form-shell" :class="{ 'implant-flow-shell': selectedCategory === 'Application failure' }">
        <div class="diag-form-header slide-up stagger-1">
          <button class="btn btn-ghost btn-sm detect-back--highlight" style="margin-bottom:12px" type="button" data-test="detect-back" @click="backFromDetect">&#8592; {{ detectBackLabel }}</button>
          <h1>{{ categoryInfo.title }}</h1>
          <p>{{ categoryInfo.subtitle }}</p>
        </div>
        <div class="guidance-box slide-up stagger-2" :class="categoryInfo.guidanceType">
          <h4>{{ categoryInfo.guidanceTitle }}</h4>
          <ul>
            <li v-for="item in categoryInfo.guidanceItems" :key="item">{{ item }}</li>
          </ul>
        </div>
        <div
          class="card detect-form-card slide-up stagger-3"
          :class="{ 'card-implant-glow': selectedCategory === 'Application failure' }"
        >
          <div class="card-body">
            <template v-if="selectedCategory === 'Data accuracy'">
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">Device Identifier</label>
                  <input class="form-input mono" type="text" :value="device.sn" readonly />
                </div>
                <div class="form-group">
                  <label class="form-label">Probe code</label>
                  <input class="form-input" type="text" :value="device.type" readonly />
                </div>
              </div>
              <div style="padding:16px 18px;border-radius:var(--radius-md);border:1px solid var(--border);background:var(--bg-elevated);margin-bottom:8px">
                <p style="font-size:0.85rem;color:var(--text-secondary);line-height:1.55">
                  We run <strong>persistent low</strong>, <strong>no fluctuation</strong>, and <strong>jump-point</strong> checks first. Data Deviation cases continue to two paired CGM/BGM image groups.
                </p>
              </div>
            </template>

            <template v-else-if="selectedCategory === 'Application failure'">
              <div class="implant-hero-bar">
                <div>
                  <div class="implant-model-pill">{{ device.type }}</div>
                  <div class="mono" style="margin-top:8px;font-size:0.9rem">{{ device.sn }}</div>
                </div>
                <div style="font-size:0.8rem;color:var(--text-muted);max-width:320px;line-height:1.55">
                  <strong>VLM</strong> will infer the application-failure sub-type from your photos. Upload <strong>at least two</strong> clear images; no manual sub-type selection.
                </div>
              </div>
              <p class="implant-section-title">Site photos <span class="implant-req-tag">Minimum 2</span></p>
              <div id="implant-photo-grid" class="implant-photo-grid">
                <button
                  v-for="(slot, index) in ['Photo slot A', 'Photo slot B', 'Photo slot C (optional)']"
                  :key="slot"
                  class="upload-zone implant-photo-slot"
                  :class="{ 'is-done': implantFileIds[index] || (!store.backendOnline.value && implantPhotoCount > index), 'is-uploading': implantUploading[index] }"
                  type="button"
                  @click="triggerImplantUpload(index)"
                  @dragover.prevent
                  @drop.prevent="handleImplantDrop($event, index)"
                >
                  <input
                    type="file"
                    :id="`implant-file-input-${index}`"
                    style="display: none"
                    accept="image/*"
                    @change="onImplantFileChange($event, index)"
                    @click.stop
                  />
                  <div class="upload-zone-icon">{{ implantUploading[index] ? 'Uploading...' : (implantFileIds[index] || (!store.backendOnline.value && implantPhotoCount > index)) ? 'Done' : 'Add' }}</div>
                  <p>{{ (implantFileIds[index] || (!store.backendOnline.value && implantPhotoCount > index)) ? 'Photo added' : slot }}</p>
                  <small>{{ implantFileIds[index] ? implantFileNames[index] : (!store.backendOnline.value && implantPhotoCount > index) ? 'uploaded_implant_site.jpg' : 'Tap to upload' }}</small>
                </button>
              </div>
              <p class="implant-upload-status" :class="{ 'is-ok': implantPhotoCount >= 2, 'upload-error-text': !!uploadError }">{{ implantUploadStatus }}</p>
            </template>

            <template v-else>
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">Device Identifier</label>
                  <input class="form-input mono" type="text" :value="device.sn" readonly />
                </div>
                <div class="form-group">
                  <label class="form-label">Probe code</label>
                  <input class="form-input" type="text" :value="device.type" readonly />
                </div>
              </div>
              <div class="detect-review-pack detect-light-surface">
                <div class="result-panel-head">
                  <span>{{ selectedCategory === 'Sensor falling off' ? 'Sensor review pack' : 'Sensor status review pack' }}</span>
                  <span class="result-tag-pill">No upload required</span>
                </div>
                <div class="detect-review-grid">
                  <div class="verdict-spec-row">
                    <div class="verdict-spec-k">Device state</div>
                    <div class="verdict-spec-v">{{ device.status }}</div>
                  </div>
                  <div class="verdict-spec-row">
                    <div class="verdict-spec-k">Last upload</div>
                    <div class="verdict-spec-v subtle">{{ formatDeviceTime(device.lastDataAt) }}</div>
                  </div>
                  <div class="verdict-spec-row">
                    <div class="verdict-spec-k">Wear window</div>
                    <div class="verdict-spec-v">Worn {{ formatDurationHours(device.wearDays * 24 + device.wearHours) }}</div>
                  </div>
                </div>
                <div class="bulk-card-note">
                  {{ selectedCategory === 'Sensor falling off'
                    ? 'This path checks abnormal device state, last upload, anomaly timing, and wear window before producing a verdict.'
                    : 'This path checks initialization phase, in-use abnormality, temporary recovery, and sensor-failure rules before producing a verdict.' }}
                </div>
              </div>
            </template>

            <div class="form-actions">
              <button class="btn btn-primary btn-lg" type="button" data-test="run-detect" @click="runDetect">{{ categoryInfo.primaryLabel }}</button>
              <button v-if="!isFromChat && !isFromRecords" class="btn btn-secondary" type="button" @click="backFromDetect">Cancel</button>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="phase === 'inaccuracy-upload'" class="diag-form-shell slide-up stagger-1">
        <button class="btn btn-ghost btn-sm" type="button" style="margin-bottom:14px" data-test="detect-back" @click="backFromInaccuracyUpload">&#8592; {{ inaccuracyBackLabel }}</button>
        <div class="diag-form-header">
          <h1>Blood sugar deviation judgment</h1>
          <p>Upload two paired CGM/BGM image groups before continuing to the deviation review.</p>
        </div>
        <div class="guidance-box guidance-amber">
          <h4>Required CGM/BGM evidence</h4>
          <ul>
            <li>Two paired CGM/BGM comparisons are required.</li>
            <li>Timestamps on CGM and BGM photos should match for each pair.</li>
            <li>After upload, the flow judges the accuracy check within 48h or after 48h rule.</li>
          </ul>
        </div>
        <div class="card">
          <div class="card-body">
            <div class="upload-grid upload-grid--tri">
              <button
                v-for="(label, index) in ['Group 1 CGM image', 'Group 1 BGM image', 'Group 2 CGM image', 'Group 2 BGM image']"
                :key="`${label}-${index}`"
                class="upload-zone"
                :class="{ 'is-done': deviationFileIds[index] || deviationFilePreviews[index] || (!store.backendOnline.value && deviationImageCount > index), 'is-uploading': deviationUploading[index] }"
                type="button"
                @click="handleDeviationSlotClick(index)"
                @dragover.prevent
                @drop.prevent="handleDeviationDrop($event, index)"
              >
                <input
                  type="file"
                  :id="`deviation-file-input-${index}`"
                  style="display: none"
                  accept="image/*"
                  @change="onDeviationFileChange($event, index)"
                  @click.stop
                />
                <div v-if="deviationFilePreviews[index]" class="detect-upload-preview">
                  <img :src="deviationFilePreviews[index]!" alt="Uploaded evidence preview" />
                  <button class="detect-upload-remove" type="button" aria-label="Remove image" @click.stop="removeDeviationSlotImage(index)">&times;</button>
                </div>
                <template v-else>
                  <div class="upload-zone-icon">{{ deviationUploading[index] ? 'Uploading...' : (deviationFileIds[index] || (!store.backendOnline.value && deviationImageCount > index)) ? 'Done' : 'Upload' }}</div>
                  <p>{{ (deviationFileIds[index] || (!store.backendOnline.value && deviationImageCount > index)) ? 'Image added' : label }}</p>
                  <small>{{ deviationFileIds[index] ? deviationFileNames[index] : (!store.backendOnline.value && deviationImageCount > index) ? 'uploaded_cgm_bgm_pair.jpg' : 'Tap to upload' }}</small>
                </template>
              </button>
            </div>
            <p class="implant-upload-status" :class="{ 'is-ok': deviationImageCount >= 4, 'upload-error-text': !!deviationUploadError }">{{ deviationUploadStatus }}</p>
            <div class="form-actions">
              <button class="btn btn-primary btn-lg" type="button" @click="submitInaccuracyDeviation">Run bias check</button>
              <button class="btn btn-secondary" type="button" @click="phase = 'form'">Cancel</button>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="phase === 'processing'" class="processing-shell">
        <div class="processing-card processing-card-clean">
          <div class="processing-left">
            <div v-if="processingComplete && selectedCategory === 'Application failure'" class="processing-complete-check" role="img" aria-label="Processing complete">
              <svg class="checkmark-svg" viewBox="0 0 52 52" xmlns="http://www.w3.org/2000/svg">
                <circle class="checkmark-circle" cx="26" cy="26" r="25" fill="none" />
                <path class="checkmark-check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8" />
              </svg>
            </div>
            <svg v-else class="processing-progress-ring" viewBox="0 0 120 120" role="img" :aria-label="`Processing ${Math.round(processingProgress)}%`">
              <defs>
                <linearGradient id="spinner-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#00b894" />
                  <stop offset="100%" stop-color="#00dec4" />
                </linearGradient>
              </defs>
              <circle class="spinner-track" cx="60" cy="60" r="48" fill="none" stroke-width="8" />
              <circle
                class="spinner-fill-determinate"
                cx="60"
                cy="60"
                r="48"
                fill="none"
                stroke-width="8"
                :stroke-dasharray="PROCESSING_CIRCLE_CIRCUMFERENCE"
                :stroke-dashoffset="processingStrokeDashoffset"
              />
            </svg>
            <div class="proc-eta">{{ processingComplete && selectedCategory === 'Application failure' ? 'Complete' : `Analyzing ${Math.round(processingProgress)}%` }}</div>
          </div>
          <div class="processing-right">
            <h2>{{ processingComplete && selectedCategory === 'Application failure' ? 'Implant analysis complete' : 'Analyzing device data...' }}</h2>
            <p>{{ processingComplete && selectedCategory === 'Application failure' ? 'VLM photo review finished. Preparing the application-failure verdict...' : 'Running checks and evaluating results. This may take 30-60 seconds for VLM-based analysis.' }}</p>
          </div>
        </div>
      </div>

      <section v-else-if="latestRecord" class="result-shell slide-up stagger-5">
        <div v-if="latestRecord.status === 'processing' || latestRecord.status === 'pending'" class="processing-card" style="margin: 20px auto; max-width: 600px;">
          <div class="processing-left">
            <svg class="processing-spinner" viewBox="0 0 120 120" role="img" aria-label="Processing">
              <defs>
                <linearGradient id="resuming-spinner-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#00b894" />
                  <stop offset="100%" stop-color="#00dec4" />
                </linearGradient>
              </defs>
              <circle class="spinner-track" cx="60" cy="60" r="48" fill="none" stroke-width="8" />
              <circle class="spinner-fill" cx="60" cy="60" r="48" fill="none" stroke-width="8" />
            </svg>
            <div class="proc-eta">Analyzing</div>
          </div>
          <div class="processing-right">
            <h2>Resuming detection...</h2>
            <p>We detected an ongoing analysis session for this device. Restoring progress and waiting for the final verdict from the server...</p>
          </div>
        </div>

        <div v-else class="verdict-page">
          <button class="btn btn-ghost btn-sm detect-back--highlight slide-up stagger-1" style="margin-bottom:10px" type="button" data-test="detect-back" @click="backFromDetect">&#8592; {{ detectBackLabel }}</button>
          <div class="verdict-bc slide-up stagger-1">
            Devices <span class="sep">/</span> <span class="mono">{{ device.sn }}</span> <span class="sep">/</span> <strong>{{ faultCategoryLabel(latestRecord.faultCategory) }}</strong>
          </div>

          <div class="verdict-page-layout">
            <div class="verdict-page-primary">
              <div class="verdict-hero slide-up stagger-2" :class="verdictTone">
                <div>
                  <div
                    class="verdict-hero-badge"
                    :class="{ 'verdict-hero-badge--fault': isFault, 'verdict-hero-badge--clear': !isFault }"
                  >
                    {{ verdictBadge }}
                  </div>
                  <h2 class="verdict-hero-title">{{ formatReasonValue(verdictTitle) }}</h2>
                  <div class="verdict-hero-summary">
                    <div class="verdict-hero-subline">{{ latestRecord.conclusion }} / {{ afterSalesLabel(latestRecord.afterSales) }} &bull; {{ resultRuleLabel }}</div>
                    <div class="verdict-hero-detail">{{ formatReasonValue(heroSummary) }}</div>
                    <div class="verdict-hero-history">{{ historyLookback }}</div>
                  </div>
                </div>
              </div>

              <div class="verdict-cards">
                <div class="verdict-card slide-up stagger-3">
	                  <div class="verdict-card-head">Basis for the verdict</div>
	                  <div v-for="row in reasonRows" :key="row.k" class="verdict-spec-row">
	                    <div class="verdict-spec-k">{{ row.k }}</div>
	                    <div v-if="row.html !== false" class="verdict-spec-v" :class="row.cls" v-html="formatReasonValue(row.v)"></div>
	                    <div v-else class="verdict-spec-v" :class="row.cls">{{ formatReasonValue(row.v) }}</div>
	                  </div>
	                </div>

                <div class="verdict-card slide-up stagger-4">
                  <div class="verdict-card-head">Device overview</div>
                  <div v-for="row in deviceOverviewRows" :key="row.k" class="verdict-spec-row">
                    <div class="verdict-spec-k">{{ row.k }}</div>
                    <div class="verdict-spec-v" :class="row.cls">{{ row.v }}</div>
                  </div>
                </div>

	                <div class="verdict-card verdict-card--span-2 slide-up stagger-5">
	                  <div class="verdict-card-head">Guidance</div>
	                  <ul class="verdict-card-list">
	                    <li v-for="item in nextStepItems" :key="`${item.k}-${item.v}`">
	                      <strong>{{ item.k }}:</strong> {{ formatReasonValue(item.v) }}
	                    </li>
	                  </ul>
	                </div>
	              </div>

              <div
                v-if="(!isFromChat && !isFromRecords) || (latestRecord.faultSubtype === 'Data Deviation Review Required' && !hasUploadedFiles)"
                class="verdict-footer-actions slide-up stagger-6"
              >
                <button
                  v-if="latestRecord.faultSubtype === 'Data Deviation Review Required' && !hasUploadedFiles"
                  class="btn btn-verdict-primary btn-lg"
                  type="button"
                  data-test="go-to-upload"
                  @click="goToUploadFlow"
                >
                  Upload comparison images
                </button>
                <template v-if="!isFromChat && !isFromRecords">
                  <button class="btn btn-verdict-primary btn-lg" type="button" data-test="detect-another" @click="detectAnother">Detect another</button>
                  <button class="btn btn-secondary btn-lg" type="button" data-test="new-lookup" @click="goToNewLookup">New lookup</button>
                </template>
              </div>
            </div>

            <aside class="verdict-review-rail slide-up stagger-3" data-test="verdict-review-rail">
              <div
                class="verdict-feedback"
                data-test="verdict-feedback"
                :class="{
                  'verdict-feedback--adopted': verdictDecision === 'adopt',
                  'verdict-feedback--rejected': verdictDecision === 'reject' && rejectSubmitted,
                }"
              >
                <p class="verdict-feedback-prompt">Use this verdict for the case?</p>
                <div class="verdict-feedback-actions">
                  <button
                    class="btn verdict-feedback-btn"
                    :class="{ 'verdict-feedback-btn--active': verdictDecision === 'adopt' }"
                    type="button"
                    data-test="verdict-adopt"
                    @click="selectVerdictAdopt"
                  >
                    Accept
                  </button>
                  <button
                    class="btn verdict-feedback-btn verdict-feedback-btn--reject"
                    :class="{ 'verdict-feedback-btn--active': verdictDecision === 'reject' }"
                    type="button"
                    data-test="verdict-reject"
                    @click="selectVerdictReject"
                  >
                    Reject
                  </button>
                </div>
                <div v-if="rejectPanelOpen && !rejectSubmitted" class="verdict-reject-panel">
                  <label class="verdict-reject-label" for="verdict-reject-comment">Rejection note</label>
                  <textarea
                    id="verdict-reject-comment"
                    v-model="rejectComment"
                    class="form-input verdict-reject-input"
                    rows="2"
                    placeholder="Optional: why this verdict was rejected"
                    data-test="verdict-reject-comment"
                  ></textarea>
                  <button
                    class="btn verdict-reject-submit"
                    type="button"
                    data-test="verdict-reject-submit"
                    @click="submitVerdictReject"
                  >
                    Submit
                  </button>
                </div>
                <p
                  v-if="rejectSubmitted"
                  class="verdict-feedback-toast verdict-feedback-toast--submitted"
                  role="status"
                  data-test="verdict-reject-submitted"
                >
                  Submitted; your rejection feedback has been recorded.
                </p>
                <p v-if="verdictDecision === 'adopt'" class="verdict-feedback-note verdict-feedback-note--adopt" data-test="verdict-adopt-note">
                  Accepted; marked as the recommended basis for this case.
                </p>
                <p v-else-if="verdictDecision === 'reject' && rejectSubmitted" class="verdict-feedback-note verdict-feedback-note--reject" data-test="verdict-reject-note">
                  Rejected{{ rejectComment.trim() ? `: ${rejectComment.trim()}` : '' }}.
                </p>
              </div>
            </aside>
          </div>
        </div>
      </section>

      <div v-if="deviationUploadModalOpen" class="detect-upload-modal-overlay" data-test="detect-upload-modal" @click.self="closeDeviationUploadModal">
        <section class="detect-upload-modal" role="dialog" aria-modal="true" aria-labelledby="detect-upload-modal-title">
          <header class="detect-upload-modal-header">
            <h3 id="detect-upload-modal-title">Upload visual evidence</h3>
            <button class="detect-upload-modal-close" type="button" aria-label="Close upload modal" @click="closeDeviationUploadModal">&times;</button>
          </header>

          <main class="detect-upload-modal-body">
            <p class="detect-upload-device">
              Device: <strong class="mono">{{ device.sn }}</strong>
            </p>
            <p v-if="deviationUploadError" class="form-error">{{ deviationUploadError }}</p>

            <div class="detect-upload-guidance">
              <h4>Required CGM/BGM evidence</h4>
              <ul>
                <li>Unless specified otherwise, please wait for 48 hours and perform data comparison under fasting conditions or 2 hours postprandial.</li>
                <li>4 comparison images (2 groups of paired CGM & BGM readings) are required.</li>
                <li>Ensure the timestamps and glucose values are legible.</li>
              </ul>
            </div>

            <div class="detect-upload-grid">
              <div
                v-for="(label, index) in ['Group 1 CGM image', 'Group 1 BGM image', 'Group 2 CGM image', 'Group 2 BGM image']"
                :key="`result-modal-data-${index}`"
                class="detect-upload-zone"
                :class="{ 'is-done': deviationFileIds[index] || deviationFilePreviews[index] || (!store.backendOnline.value && deviationImageCount > index), 'is-uploading': deviationUploading[index] }"
                role="button"
                tabindex="0"
                @click="handleDeviationSlotClick(index)"
                @keyup.enter="handleDeviationSlotClick(index)"
                @keyup.space="handleDeviationSlotClick(index)"
                @dragover.prevent
                @drop.prevent="handleDeviationDrop($event, index)"
              >
                <input
                  type="file"
                  :id="`result-deviation-file-input-${index}`"
                  style="display: none"
                  accept="image/*"
                  @change="onDeviationFileChange($event, index)"
                  @click.stop
                />
                <div v-if="deviationFilePreviews[index]" class="detect-upload-preview">
                  <img :src="deviationFilePreviews[index]!" alt="Uploaded evidence preview" />
                  <button class="detect-upload-remove" type="button" aria-label="Remove image" @click.stop="removeDeviationSlotImage(index)">&times;</button>
                </div>
                <template v-else>
                  <div class="detect-upload-icon">{{ deviationUploading[index] ? '...' : '+' }}</div>
                  <p>{{ deviationFileIds[index] || (!store.backendOnline.value && deviationImageCount > index) ? 'Image added' : label }}</p>
                  <small>{{ deviationFileNames[index] || (deviationFileIds[index] || (!store.backendOnline.value && deviationImageCount > index) ? 'uploaded_cgm_bgm_pair.jpg' : 'Click to upload') }}</small>
                </template>
              </div>
            </div>

            <p class="detect-upload-count">
              Uploaded: <strong>{{ deviationImageCount }}</strong> / 4 images
            </p>
          </main>

          <footer class="detect-upload-modal-actions">
            <button class="btn btn-primary" type="button" @click="finishDeviationUploadModal">Done</button>
          </footer>
        </section>
      </div>

      <div v-if="deviationPreviewOpen" class="image-preview-overlay" data-test="image-preview-modal" @click.self="closeDeviationPreview">
        <section class="image-preview-modal" role="dialog" aria-modal="true" aria-labelledby="image-preview-title">
          <header class="image-preview-header">
            <h3 id="image-preview-title">{{ deviationPreviewName }}</h3>
            <button class="detect-upload-modal-close" type="button" aria-label="Close image preview" @click="closeDeviationPreview">&times;</button>
          </header>
          <div class="image-preview-body">
            <img :src="deviationPreviewSrc" alt="Uploaded evidence full preview" />
          </div>
        </section>
      </div>
    </div>
  </div>
  <main v-else class="page active" id="page-detect-restore">
    <div class="page-body">
      <div class="processing-shell">
        <div class="processing-card processing-card-clean" :class="{ 'error-card': routeDeviceError || routeRecordError }">
          <div class="processing-left">
            <div v-if="routeDeviceError || routeRecordError" class="error-icon-wrapper" aria-label="Error status">
              <svg class="error-warning-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                <line x1="12" y1="9" x2="12" y2="13"></line>
                <line x1="12" y1="17" x2="12.01" y2="17"></line>
              </svg>
            </div>
            <svg v-else class="processing-spinner" viewBox="0 0 120 120" role="img" aria-label="Loading detection context">
              <defs>
                <linearGradient id="restore-spinner-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#00b894" />
                  <stop offset="100%" stop-color="#00dec4" />
                </linearGradient>
              </defs>
              <circle class="spinner-track" cx="60" cy="60" r="48" fill="none" stroke-width="8" />
              <circle class="spinner-fill" cx="60" cy="60" r="48" fill="none" stroke-width="8" />
            </svg>
            <div class="proc-eta">{{ (routeDeviceError || routeRecordError) ? 'Error' : routeDeviceLoading ? 'Loading' : 'Restoring' }}</div>
          </div>
          <div class="processing-right">
            <h2>{{ (routeDeviceError || routeRecordError) ? (routeDeviceError ? 'Device Not Found' : 'Record Not Found') : 'Restoring detection context...' }}</h2>
            <p>{{ routeDeviceError || routeRecordError || 'Loading the device and verdict state for this detection page.' }}</p>
            <div v-if="routeDeviceError || routeRecordError" class="error-actions" style="margin-top: 20px; display: flex; gap: 12px;">
              <button class="btn btn-primary" type="button" data-test="error-back-lookup" @click="goToNewLookup">
                Back to Device Detection
              </button>
              <button class="btn btn-secondary" type="button" data-test="error-back" @click="backFromDetect">
                Back
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </main>
</template>

<style scoped>
/* Highlighted "back to previous query" affordance — brand-green pill so the
   return path stands out from the plain ghost buttons around it. */
.detect-back--highlight {
  background: rgba(0, 168, 132, 0.09) !important;
  border: 1px solid rgba(0, 168, 132, 0.4) !important;
  color: #00806a !important;
  font-weight: 600 !important;
  padding: 6px 14px !important;
  border-radius: var(--radius-full, 9999px) !important;
}

.detect-back--highlight:hover {
  background: rgba(0, 168, 132, 0.16) !important;
  border-color: rgba(0, 168, 132, 0.6) !important;
}

.detect-review-pack {
  margin-bottom: 16px;
  padding: var(--card-padding);
}

.guidance-box.guidance-data {
  background: rgba(0, 168, 132, 0.05);
  border-left: 3px solid var(--accent);
}

.guidance-box.guidance-implant {
  background: rgba(246, 166, 35, 0.06);
  border-left: 3px solid #f6a623;
}

.detect-form-card,
.detect-light-surface {
  color: var(--text-primary);
}

.detect-form-card .form-label {
  color: var(--text-muted);
}

.detect-form-card .btn-secondary {
  background: rgba(15, 23, 42, 0.06);
  color: var(--text-primary);
  border-color: rgba(15, 23, 42, 0.08);
}

.detect-review-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
}

.processing-spinner {
  animation: processing-spin 1.2s linear infinite;
}

.spinner-fill {
  stroke: var(--accent);
  stroke-dasharray: 95 220;
  stroke-linecap: round;
}

.processing-complete-check {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 104px;
  height: 104px;
  border-radius: 50%;
  border: 8px solid var(--accent);
  color: var(--accent);
  font-size: 3rem;
  font-weight: 800;
}

@keyframes processing-spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

.verdict-page-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 200px;
  gap: var(--space-md);
  align-items: start;
}

.verdict-page-primary {
  min-width: 0;
}

.verdict-review-rail {
  position: sticky;
  top: 18px;
  align-self: start;
}

.verdict-hero-badge--fault {
  background: rgba(220, 38, 38, 0.14) !important;
  color: #b42318 !important;
  border: 1px solid rgba(220, 38, 38, 0.28) !important;
}

.verdict-hero-badge--clear {
  background: rgba(15, 23, 42, 0.08) !important;
  color: var(--text-secondary) !important;
  border: 1px solid rgba(15, 23, 42, 0.12) !important;
}

.verdict-feedback {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 16px;
  background: linear-gradient(155deg, rgba(255, 255, 255, 0.44), rgba(255, 255, 255, 0.2));
  transition:
    border-color 0.25s ease,
    box-shadow 0.25s ease;
}

.verdict-feedback--adopted {
  border-color: rgba(0, 168, 132, 0.38);
  box-shadow: 0 0 0 3px rgba(0, 168, 132, 0.12);
}

.verdict-feedback--rejected {
  border-color: rgba(217, 119, 6, 0.32);
  box-shadow: 0 0 0 3px rgba(246, 166, 35, 0.1);
}

.verdict-feedback-prompt {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.74rem;
  font-weight: 700;
  line-height: 1.35;
}

.verdict-feedback-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.verdict-feedback-btn {
  min-width: 0;
  padding: 7px 8px;
  font-size: 0.74rem;
  border: 1px solid rgba(15, 23, 42, 0.12);
  background: rgba(255, 255, 255, 0.5);
  color: var(--text-primary);
  font-weight: 800;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease,
    box-shadow 0.2s ease;
}

.verdict-feedback-btn:hover {
  transform: translateY(-1px);
  border-color: rgba(0, 168, 132, 0.28);
}

.verdict-feedback-btn--active {
  border-color: rgba(0, 168, 132, 0.45);
  background: rgba(0, 168, 132, 0.14);
  color: var(--accent);
  box-shadow: 0 0 0 4px rgba(0, 168, 132, 0.1);
}

.verdict-feedback-btn--reject.verdict-feedback-btn--active {
  border-color: rgba(217, 119, 6, 0.4);
  background: rgba(246, 166, 35, 0.14);
  color: #9a6700;
  box-shadow: 0 0 0 4px rgba(246, 166, 35, 0.12);
}

.verdict-reject-panel {
  display: grid;
  gap: 8px;
  padding: 10px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.04);
}

.verdict-reject-label {
  color: var(--text-muted);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.verdict-reject-input {
  min-height: 48px;
  resize: vertical;
  font-size: 0.78rem;
}

.verdict-feedback-toast {
  margin: 0;
  padding: 8px 10px;
  border-radius: 10px;
  font-size: 0.72rem;
  font-weight: 700;
  line-height: 1.4;
}

.verdict-feedback-toast--submitted {
  background: rgba(246, 166, 35, 0.14);
  border: 1px solid rgba(217, 119, 6, 0.28);
  color: #9a6700;
}

.verdict-reject-submit {
  justify-self: stretch;
  padding: 8px 12px;
  border: 1px solid rgba(217, 119, 6, 0.35);
  background: rgba(246, 166, 35, 0.16);
  color: #9a6700;
  font-size: 0.8rem;
  font-weight: 800;
}

.verdict-reject-submit:hover {
  background: rgba(246, 166, 35, 0.24);
}

.verdict-footer-actions :deep(.btn-verdict-primary) {
  background: linear-gradient(135deg, var(--blue), #6366f1) !important;
  color: #fff !important;
  border: none !important;
  box-shadow: 0 4px 20px rgba(78, 140, 255, 0.35) !important;
}

.verdict-footer-actions :deep(.btn-verdict-primary:hover) {
  filter: brightness(1.06);
  transform: translateY(-1px);
}

.verdict-footer-actions :deep(.btn-secondary.btn-lg) {
  background: rgba(15, 23, 42, 0.06) !important;
  color: var(--text-primary) !important;
  border: 1px solid rgba(15, 23, 42, 0.12) !important;
  font-weight: 600;
}

.verdict-footer-actions :deep(.btn-secondary.btn-lg:hover) {
  background: rgba(0, 168, 132, 0.08) !important;
  border-color: rgba(0, 168, 132, 0.22) !important;
}

.verdict-feedback-note {
  margin: 0;
  font-size: 0.76rem;
  line-height: 1.45;
  word-break: break-all;
  overflow-wrap: break-word;
}

.verdict-feedback-note--adopt {
  color: var(--accent);
  font-weight: 700;
}

.verdict-feedback-note--reject {
  color: #9a6700;
  font-weight: 700;
}

.detect-upload-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.34);
  backdrop-filter: blur(8px);
  animation: detect-upload-fade 0.2s ease-out;
}

.detect-upload-modal {
  width: min(580px, 100%);
  overflow: hidden;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 24px 58px rgba(15, 23, 42, 0.18);
  animation: detect-upload-scale 0.24s cubic-bezier(0.16, 1, 0.3, 1);
}

.detect-upload-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: var(--card-padding);
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.detect-upload-modal-header h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.25rem;
  font-weight: 800;
}

.detect-upload-modal-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--text-muted);
  font-size: 1.6rem;
  line-height: 1;
  cursor: pointer;
}

.detect-upload-modal-close:hover {
  background: rgba(15, 23, 42, 0.06);
  color: var(--text-primary);
}

.detect-upload-modal-body {
  padding: var(--card-padding);
}

.detect-upload-device {
  margin: 0 0 16px;
  color: var(--text-secondary);
  font-size: 0.92rem;
}

.detect-upload-guidance {
  margin-bottom: 20px;
  padding: 14px 16px;
  border: 1px solid rgba(245, 158, 11, 0.22);
  border-radius: 16px;
  background: rgba(245, 158, 11, 0.09);
}

.detect-upload-guidance h4 {
  margin: 0 0 6px;
  color: #b45309;
  font-size: var(--text-sm);
  font-weight: 800;
}

.detect-upload-guidance ul {
  margin: 0;
  padding-left: 20px;
  color: #78350f;
  font-size: var(--text-xs);
  line-height: 1.55;
}

.detect-upload-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.detect-upload-zone {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 128px;
  padding: var(--card-padding);
  border: 2px dashed rgba(15, 23, 42, 0.16);
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.02);
  color: var(--text-primary);
  text-align: center;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    transform 0.2s ease;
}

.detect-upload-zone:hover,
.detect-upload-zone:focus-visible {
  border-color: rgba(0, 168, 132, 0.45);
  background: rgba(0, 168, 132, 0.04);
  outline: none;
  transform: translateY(-1px);
}

.detect-upload-zone.is-done {
  border-color: rgba(34, 197, 94, 0.55);
  border-style: solid;
  background: rgba(34, 197, 94, 0.04);
}

.detect-upload-zone.is-uploading {
  pointer-events: none;
  opacity: 0.72;
}

.detect-upload-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  margin: 0 auto 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  font-weight: 800;
}

.detect-upload-zone p {
  margin: 0 0 4px;
  color: var(--text-primary);
  font-size: 0.9rem;
  font-weight: 800;
}

.detect-upload-zone small {
  color: var(--text-muted);
  font-size: 0.76rem;
}

.detect-upload-preview {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 92px;
}

.detect-upload-preview img {
  max-width: 100%;
  max-height: 96px;
  border-radius: 10px;
  object-fit: contain;
}

.detect-upload-remove {
  position: absolute;
  top: -10px;
  right: -10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 999px;
  background: #ef4444;
  color: #ffffff;
  font-size: 1rem;
  font-weight: 800;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(220, 38, 38, 0.24);
}

.detect-upload-count {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.image-preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.36);
  backdrop-filter: blur(12px);
}

.image-preview-modal {
  width: min(920px, 96vw);
  max-height: 92vh;
  overflow: hidden;
  border: 1px solid rgba(0, 168, 132, 0.18);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 24px 58px rgba(15, 23, 42, 0.2);
}

.image-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.07);
  background:
    linear-gradient(135deg, rgba(0, 168, 132, 0.08), rgba(0, 168, 132, 0.02)),
    rgba(255, 255, 255, 0.88);
}

.image-preview-header h3 {
  margin: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 0.96rem;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.image-preview-body {
  display: flex;
  align-items: center;
  justify-content: center;
  max-height: calc(92vh - 58px);
  padding: 18px;
  background: rgba(15, 23, 42, 0.025);
}

.image-preview-body img {
  display: block;
  max-width: 100%;
  max-height: calc(92vh - 94px);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 12px 34px rgba(15, 23, 42, 0.12);
  object-fit: contain;
}

.detect-upload-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-md);
  padding: var(--card-padding);
  border-top: 1px solid rgba(15, 23, 42, 0.06);
}

@keyframes detect-upload-fade {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes detect-upload-scale {
  from {
    opacity: 0;
    transform: scale(0.96);
  }

  to {
    opacity: 1;
    transform: scale(1);
  }
}

/* Redesigned Processing Screen */
.processing-shell {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 40px 20px;
  width: 100%;
}

.processing-card {
  text-align: left;
  max-width: 720px;
  width: 100%;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.72) 0%, rgba(255, 255, 255, 0.45) 100%) !important;
  border: 1px solid rgba(255, 255, 255, 0.6) !important;
  border-radius: 24px !important;
  padding: 44px 48px !important;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.72) !important;
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 16px 40px;
  align-items: start;
  backdrop-filter: blur(20px) saturate(1.35) !important;
  -webkit-backdrop-filter: blur(20px) saturate(1.35) !important;
  position: relative;
  overflow: hidden;
}

.processing-card-clean {
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: center !important;
  text-align: center !important;
  padding: 56px 48px !important;
  max-width: 600px !important;
}

.processing-card-clean .processing-right {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-top: 24px;
}

.processing-card-clean .processing-progress {
  width: 100%;
  min-width: 320px;
  max-width: 400px;
  margin: 16px auto 0;
}

.processing-step-text {
  font-size: 14px;
  color: #64748b;
  margin-top: 14px;
  font-family: var(--font-mono, monospace);
  font-weight: 500;
  letter-spacing: -0.01em;
  background: linear-gradient(90deg, #475569 0%, #64748b 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  display: inline-block;
  opacity: 0.9;
}

/* Subtle background glow effect for processing card */
.processing-card::before {
  content: '';
  position: absolute;
  top: -100px;
  left: -100px;
  width: 250px;
  height: 250px;
  background: radial-gradient(circle, rgba(0, 184, 148, 0.08) 0%, transparent 70%);
  z-index: 0;
  pointer-events: none;
}

.processing-left, .processing-right {
  position: relative;
  z-index: 1;
}

.processing-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.processing-spinner,
.processing-progress-ring {
  width: 110px !important;
  height: 110px !important;
  filter: drop-shadow(0 0 6px rgba(0, 184, 148, 0.25));
  transform-origin: center;
}

.processing-spinner {
  animation: spin 1.2s linear infinite;
}

.processing-progress-ring {
  transform: rotate(-90deg);
}

.spinner-track {
  stroke: rgba(15, 23, 42, 0.04) !important;
  stroke-width: 5px !important;
}

.spinner-fill {
  stroke: url(#spinner-grad) !important;
  stroke-width: 5.5px !important;
  stroke-linecap: round !important;
  stroke-dasharray: 280;
  animation: dash 1.5s ease-in-out infinite;
  transform-origin: center;
}

.spinner-fill-determinate {
  stroke: url(#spinner-grad) !important;
  stroke-width: 5.5px !important;
  stroke-linecap: round !important;
  transform-origin: center;
  transition: stroke-dashoffset 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

/* For the resuming status page */
.processing-card svg.processing-spinner circle.spinner-fill {
  stroke: url(#resuming-spinner-grad) !important;
}

@keyframes spin {
  0%   { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@keyframes dash {
  0% { stroke-dashoffset: 280; }
  50% { stroke-dashoffset: 75; transform: rotate(135deg); }
  100% { stroke-dashoffset: 280; transform: rotate(450deg); }
}

/* Draw Checkmark Animation */
.processing-complete-check {
  width: 110px;
  height: 110px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.checkmark-svg {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  display: block;
  stroke-width: 4.5;
  stroke: #00b894;
  stroke-miterlimit: 10;
  animation: fill .4s ease-in-out .4s forwards;
}

.checkmark-circle {
  stroke-dasharray: 166;
  stroke-dashoffset: 166;
  stroke-width: 4.5;
  stroke-miterlimit: 10;
  stroke: #00b894;
  fill: none;
  animation: stroke 0.6s cubic-bezier(0.65, 0, 0.45, 1) forwards;
}

.checkmark-check {
  transform-origin: 50% 50%;
  stroke-dasharray: 48;
  stroke-dashoffset: 48;
  stroke-width: 4.5;
  stroke-linecap: round;
  stroke: #00b894;
  animation: stroke 0.3s cubic-bezier(0.65, 0, 0.45, 1) 0.8s forwards;
}

@keyframes stroke {
  100% { stroke-dashoffset: 0; }
}

@keyframes fill {
  100% { box-shadow: inset 0px 0px 0px 36px rgba(0, 184, 148, 0.08); }
}

.proc-eta {
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
  margin-top: 18px;
  text-shadow: 0 0 8px rgba(0, 184, 148, 0.15);
}

.processing-right h2 {
  font-family: var(--font-brand);
  font-size: 1.45rem;
  font-weight: 800;
  margin-bottom: 10px;
  letter-spacing: -0.02em;
  color: #0f172a;
}

.processing-right > p {
  color: #475569;
  font-size: 0.9rem;
  margin-bottom: 24px;
  line-height: 1.6;
}

.processing-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 28px !important;
  background: rgba(15, 23, 42, 0.02);
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(15, 23, 42, 0.04);
}

.proc-step {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 12px;
  border-radius: 10px;
  font-size: var(--text-sm);
  color: #64748b;
  font-weight: 500;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  background: transparent;
  border: 1px solid transparent;
}

.proc-step.active {
  color: #0f172a;
  background: rgba(255, 255, 255, 0.75) !important;
  border: 1px solid rgba(0, 184, 148, 0.15) !important;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.02);
  font-weight: 600;
}

.proc-step.done {
  color: #94a3b8;
}

.proc-step-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.step-icon-done {
  color: #00b894;
  font-size: 1.05rem;
  font-weight: bold;
}

.step-icon-active-pulse {
  display: inline-block;
  width: 8px;
  height: 8px;
  background-color: var(--accent);
  border-radius: 50%;
  position: relative;
}

.step-icon-active-pulse::after {
  content: '';
  position: absolute;
  top: -4px; left: -4px; right: -4px; bottom: -4px;
  border: 2px solid var(--accent);
  border-radius: 50%;
  animation: pulse-ring 1.5s cubic-bezier(0.24, 0, 0.38, 1) infinite;
}

@keyframes pulse-ring {
  0% { transform: scale(0.6); opacity: 1; }
  100% { transform: scale(1.6); opacity: 0; }
}

.step-icon-pending {
  width: 7px;
  height: 7px;
  border: 2px solid #cbd5e1;
  border-radius: 50%;
  background: transparent;
}

.proc-step-text {
  flex: 1;
}

.processing-card .processing-progress {
  grid-column: 1 / -1;
  margin-top: 12px;
  height: 6px;
  background: rgba(15, 23, 42, 0.04);
  border-radius: 999px;
  overflow: hidden;
  position: relative;
}

.processing-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #00b894 0%, #00dec4 100%) !important;
  border-radius: 999px;
  box-shadow: 0 0 8px rgba(0, 184, 148, 0.35);
  transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
}

.processing-progress-bar::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.4), transparent);
  animation: progress-shimmer 1.8s infinite;
}

@keyframes progress-shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

/* Premium Buttons Styling */
.verdict-footer-actions {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-top: 24px;
}

/* Overriding .btn-verdict-primary inside .verdict-footer-actions */
.verdict-footer-actions :deep(.btn-verdict-primary),
.verdict-footer-actions .btn-verdict-primary {
  background: linear-gradient(135deg, #00b894 0%, #008f72 100%) !important;
  color: #ffffff !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  font-family: var(--font-brand), sans-serif !important;
  font-size: 0.95rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.02em !important;
  padding: 12px 28px !important;
  height: auto !important;
  border-radius: 14px !important;
  box-shadow: 0 8px 24px rgba(0, 143, 114, 0.28) !important;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
  cursor: pointer !important;
}

.verdict-footer-actions :deep(.btn-verdict-primary:hover),
.verdict-footer-actions .btn-verdict-primary:hover {
  background: linear-gradient(135deg, #00cd9b 0%, #00a884 100%) !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 12px 30px rgba(0, 143, 114, 0.38) !important;
}

.verdict-footer-actions :deep(.btn-verdict-primary:active),
.verdict-footer-actions .btn-verdict-primary:active {
  transform: translateY(0) !important;
  box-shadow: 0 4px 12px rgba(0, 143, 114, 0.2) !important;
}

/* Overriding .btn-secondary.btn-lg inside .verdict-footer-actions */
.verdict-footer-actions :deep(.btn-secondary.btn-lg),
.verdict-footer-actions .btn-secondary.btn-lg {
  background: rgba(255, 255, 255, 0.8) !important;
  color: #0f172a !important;
  border: 1px solid rgba(15, 23, 42, 0.14) !important;
  font-family: var(--font-brand), sans-serif !important;
  font-size: 0.95rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.02em !important;
  padding: 12px 28px !important;
  height: auto !important;
  border-radius: 14px !important;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04) !important;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
  cursor: pointer !important;
}

.verdict-footer-actions :deep(.btn-secondary.btn-lg:hover),
.verdict-footer-actions .btn-secondary.btn-lg:hover {
  background: #ffffff !important;
  border-color: rgba(15, 23, 42, 0.28) !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06) !important;
}

.verdict-footer-actions :deep(.btn-secondary.btn-lg:active),
.verdict-footer-actions .btn-secondary.btn-lg:active {
  transform: translateY(0) !important;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04) !important;
}

@media (max-width: 640px) {
  .processing-card {
    grid-template-columns: 1fr;
    text-align: center;
    padding: 36px 28px !important;
  }
  .processing-left { padding-top: 0; margin-bottom: 12px; }
  .processing-steps { text-align: left; }
  .processing-right h2 { text-align: center; }
  .processing-right > p { text-align: center; }
}

@media (max-width: 960px) {
  .verdict-page-layout {
    grid-template-columns: 1fr;
  }

  .verdict-review-rail {
    position: static;
    order: -1;
  }
}

@media (max-width: 760px) {
  .detect-review-grid {
    grid-template-columns: 1fr;
  }

  .detect-upload-grid {
    grid-template-columns: 1fr;
  }
}

.error-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 96px;
  border-radius: 50%;
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.error-warning-icon {
  width: 48px;
  height: 48px;
}

.processing-card.error-card {
  border-color: rgba(239, 68, 68, 0.2);
}

@media (max-width: 480px) {
  .verdict-page-layout {
    grid-template-columns: 1fr;
  }

  .verdict-review-rail {
    position: static;
  }

  .upload-grid--tri {
    grid-template-columns: 1fr;
  }

  .verdict-hero-title {
    font-size: var(--text-xl);
  }

  .verdict-spec-row {
    flex-direction: column;
    gap: 2px;
  }

  .form-actions {
    flex-direction: column;
  }

  .form-actions .btn {
    width: 100%;
  }

  .detect-upload-modal {
    inset: 0 !important;
    border-radius: 0 !important;
    width: 100% !important;
    height: 100% !important;
    display: flex;
    flex-direction: column;
  }

  .detect-upload-modal-body {
    flex: 1;
    overflow-y: auto;
  }

  .processing-card {
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: var(--space-md);
  }

  .verdict-footer-actions {
    flex-direction: column;
  }

  .verdict-footer-actions .btn {
    width: 100%;
  }

  .diag-form-shell {
    padding: 0;
  }

  .form-row {
    flex-direction: column;
  }
}
</style>
