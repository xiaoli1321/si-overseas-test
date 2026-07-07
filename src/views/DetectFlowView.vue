<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch, watchEffect } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { keyForFaultCategory } from '@/composables/faultCategories';
import { useDemoStore } from '@/composables/useDemoStore';
import type { FaultCategory } from '@/types/device';

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
const processingStep = ref(0);
const processingComplete = ref(false);
const processingSessionId = ref('');
const activeRecordId = ref('');
const verdictDecision = ref<'adopt' | 'reject' | null>(null);
const rejectComment = ref('');
const rejectPanelOpen = ref(false);
const rejectSubmitted = ref(false);
let processingTimer: number | undefined;
let processingCompletionTimer: number | undefined;
const faultCategories: FaultCategory[] = [
  'Data accuracy',
  'Sensor falling off',
  'Sensor Abnormal',
  'Application failure',
];

watchEffect(() => {
  if (!store.selectedDevice.value || store.selectedDevice.value.sn !== props.sn) {
    store.selectDevice(props.sn);
  }
});

const device = computed(() => store.selectedDevice.value);
const selectedCategory = computed<FaultCategory>(() => {
  const category = String(route.query.category ?? '');
  if (faultCategories.includes(category as FaultCategory)) return category as FaultCategory;
  return store.currentFault.value?.faultCategory ?? 'Data accuracy';
});
const fault = computed(() => store.currentFault.value
  ? {
      ...store.currentFault.value,
      faultCategory: selectedCategory.value,
    }
  : null);
const isMappedCategory = computed(() => selectedCategory.value === store.currentFault.value?.faultCategory);
const isFromChat = computed(() => route.query.from === 'chat');
const isFromFaultQuery = computed(() => route.query.from === 'fault-query');
const isFromRecords = computed(() => route.query.from === 'records');
const isFromDeviceDetect = computed(() => route.query.from === 'device-detect');

const detectBackLabel = computed(() => {
  if (isFromRecords.value) return 'Back to Detect records';
  if (isFromChat.value) return 'Back to Device detect';
  if (isFromDeviceDetect.value) {
    return String(route.query.q ?? '').trim() ? 'Back to matched devices' : 'Back to Device detect';
  }
  if (isFromFaultQuery.value) return 'Back to lookup';
  return 'Back to Fault Query';
});

const routeSession = computed(() => {
  const sessionId = String(route.query.session ?? '');
  if (!sessionId) return undefined;
  return store.sessions.value.find(session => session.id === sessionId);
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
    store.updateDetectRecordVerdict(latestRecord.value.id, {
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
    store.updateDetectRecordVerdict(latestRecord.value.id, {
      verdictAdoption: 'No',
      verdictRejectionReason: rejectComment.value.trim(),
    });
  }
}

function goToNewLookup() {
  router.push({ name: 'chat' });
}

function detectAnother() {
  router.push({
    name: 'fault-query',
    params: { categoryKey: keyForFaultCategory(selectedCategory.value) },
  });
}

function backFromDetect() {
  if (isFromChat.value) {
    const chatSessionId = String(route.query.session ?? '');
    router.push({
      name: 'chat',
      query: chatSessionId ? { session: chatSessionId } : {},
    });
    return;
  }
  if (isFromRecords.value) {
    router.push({ name: 'records' });
    return;
  }
  if (isFromDeviceDetect.value) {
    const q = String(route.query.q ?? '').trim();
    if (q) {
      router.push({ name: 'detect-devices', query: { q } });
    } else {
      router.push({ name: 'chat' });
    }
    return;
  }
  router.push({
    name: 'fault-query',
    params: { categoryKey: keyForFaultCategory(selectedCategory.value) },
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
const routeRecordId = computed(() => String(route.query.record ?? ''));
const latestRecord = computed(() => store.records.value.find(record => (
  record.id === (activeRecordId.value || routeRecordId.value || routeSession.value?.recordId)
)));

const inaccuracyBackLabel = computed(() => {
  if (isFromChat.value && latestRecord.value) return 'Back to Device detect';
  if (isFromRecords.value && latestRecord.value) return 'Back to Detect records';
  if (isFromDeviceDetect.value && latestRecord.value) {
    return String(route.query.q ?? '').trim() ? 'Back to matched devices' : 'Back to Device detect';
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
});

const activeRuleLabel = computed(() => `Rule profile v${store.activeThresholdProfile.value.version}`);
const resultRuleLabel = computed(() => (
  latestRecord.value
    ? `Rule profile v${latestRecord.value.thresholdProfileVersion}`
    : activeRuleLabel.value
));
const verdictTone = computed(() => (
  latestRecord.value?.afterSales === 'Replacement Eligible' ? 'fault' : 'blocked'
));
const verdictBadge = computed(() => (
  latestRecord.value?.afterSales === 'Replacement Eligible' ? 'WARRANTY ELIGIBLE' : 'NOT WARRANTY ELIGIBLE'
));
const categoryKey = computed(() => {
  if (selectedCategory.value === 'Data accuracy') return 'inaccuracy';
  if (selectedCategory.value === 'Sensor falling off') return 'detachment';
  if (selectedCategory.value === 'Sensor Abnormal') return 'sensor';
  return 'implant';
});
const isFault = computed(() => latestRecord.value?.conclusion === 'Issue Detected');
const verdictTitle = computed(() => {
  if (!latestRecord.value) return fault.value?.faultCategory ?? 'Verdict';
  if (categoryKey.value === 'inaccuracy') return latestRecord.value.faultSubtype === 'No qualifying curve pattern'
    ? 'No qualifying curve pattern detected'
    : latestRecord.value.faultSubtype;
  if (categoryKey.value === 'detachment') return isFault.value ? 'Fall-out detected' : 'Fall-out not detected';
  if (categoryKey.value === 'sensor') return isFault.value ? latestRecord.value.faultSubtype : 'No abnormality detected';
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
  if (!latestRecord.value) return '';
  if (categoryKey.value === 'inaccuracy') {
    if (!isFault.value) return 'Cannot directly enter after-sales based on the first-round curve result. Continue with the CGM/BGM image comparison step.';
    if (latestRecord.value.faultSubtype.includes('Persistent Low')) return 'The recent glucose curve shows a persistent-low pattern. See Basis for the Verdict below for the rule details.';
    if (latestRecord.value.faultSubtype.includes('No Fluctuation')) return 'The recent glucose curve stays unusually flat for a sustained period. See Basis for the Verdict below for the rule details.';
    return 'The recent glucose curve shows repeated jump points within the screening window.';
  }
  if (categoryKey.value === 'detachment') {
    return isFault.value
      ? 'The record shows a sensor fall-out pattern and the device is already in an abnormal state.'
      : 'The current record does not show a confirmed sensor fall-out pattern.';
  }
  if (categoryKey.value === 'sensor') {
    if (!isFault.value) return 'No abnormal sensor status is currently detected on this device, so after-sales support is not available.';
    if (latestRecord.value.faultSubtype.includes('Initialization')) return 'The device shows an abnormality during the initialization stage.';
    if (latestRecord.value.faultSubtype.includes('Temporary')) return 'Temporary sensor abnormality. Check again in 3 hours to see whether the device returns to normal.';
    if (latestRecord.value.faultSubtype.includes('Probe')) return 'The current sensor has failed and cannot be reactivated.';
    return 'An abnormal sensor status has been detected outside initialization.';
  }
  return isFault.value
    ? 'The uploaded photos match an application-failure pattern.'
    : 'The current photo set does not show a clear application-failure pattern.';
});
const historyLookback = computed(() => {
  if (!latestRecord.value) return '';
  if (categoryKey.value === 'detachment' || categoryKey.value === 'implant') return 'History lookback: Not applicable.';
  if (categoryKey.value === 'sensor') return 'History lookback: no prior sensor abnormality record.';
  if (latestRecord.value.faultSubtype.includes('Persistent Low')) return 'History lookback: no prior persistent low record.';
  if (latestRecord.value.faultSubtype.includes('No Fluctuation')) return 'History lookback: no prior no-fluctuation record.';
  if (latestRecord.value.faultSubtype.includes('Jump')) return 'History lookback: no prior jump-point record.';
  return 'History lookback: Not applicable.';
});
const reasonRows = computed(() => {
  if (!latestRecord.value) return [];
  if (categoryKey.value === 'inaccuracy') {
    if (!isFault.value) {
      return [
        {
          k: 'What we found',
          v: 'The first-pass curve screening did not hit a qualifying after-sales pattern.<ul class="verdict-rich-list"><li>Current review did not hit <strong>persistent low</strong>, <strong>no fluctuation</strong>, or <strong>jump-point</strong>.</li></ul>',
          cls: 'subtle',
        },
        {
          k: 'Why this result',
          v: 'The first-round curve result is not enough to support after-sales by itself.<ul class="verdict-rich-list"><li>This is a path switch rather than a final rejection.</li><li>The case should continue to the CGM/BGM image comparison step.</li></ul>',
          cls: 'subtle',
        },
      ];
    }
    if (latestRecord.value.faultSubtype.includes('Persistent Low')) {
      return [
        { k: 'What we found', v: 'Persistent-low pattern was detected.<ul class="verdict-rich-list"><li>Low duration is above the configured threshold.</li><li>24h peak stays inside the allowed peak cap.</li></ul>', cls: 'subtle' },
        { k: 'Why this result', v: 'The persistent-low after-sales rule is met.<ul class="verdict-rich-list"><li>Current record meets all thresholds.</li></ul>', cls: 'subtle' },
        { k: 'Possible causes', v: 'Possible causes can be shown cautiously.<ul class="verdict-rich-list"><li>The sensor may have been scratched or bumped and loosened.</li><li>The electrode may not have been fully inserted into the subcutaneous tissue.</li></ul>', cls: 'subtle' },
      ];
    }
    if (latestRecord.value.faultSubtype.includes('No Fluctuation')) {
      return [
        { k: 'What we found', v: 'No-fluctuation pattern was detected.<ul class="verdict-rich-list"><li>The curve stays unusually flat for a sustained period.</li></ul>', cls: 'subtle' },
        { k: 'Why this result', v: 'The no-fluctuation after-sales rule is met.<ul class="verdict-rich-list"><li>Current record matches the flat-line rule.</li></ul>', cls: 'subtle' },
        { k: 'Possible causes', v: 'Possible causes can be shown cautiously.<ul class="verdict-rich-list"><li>An unusually flat curve may reflect a sensor-reading issue.</li></ul>', cls: 'subtle' },
      ];
    }
    return [
      { k: 'What we found', v: 'Jump-point pattern was detected.<ul class="verdict-rich-list"><li>Repeated jump points appear within the screening window.</li></ul>', cls: 'subtle' },
      { k: 'Why this result', v: 'The jump-point after-sales rule is met.<ul class="verdict-rich-list"><li>Adjacent jumps and consecutive-step rules are met.</li></ul>', cls: 'subtle' },
      { k: 'Possible causes', v: 'Possible causes can be shown cautiously.<ul class="verdict-rich-list"><li>Tissue movement around the sensor may have changed the position of the soft needle.</li><li>Low-probability events such as sensor loosening cannot be ruled out.</li></ul>', cls: 'subtle' },
    ];
  }
  if (categoryKey.value === 'detachment') {
    return [
      { k: 'What we found', v: `${isFault.value ? 'An abnormal detachment-like state is present.' : 'No confirmed detachment signal is present.'}<ul class="verdict-rich-list"><li>Current state: <strong>${device.value?.status}</strong>.</li><li>Last upload: <strong>${device.value?.lastDataAt}</strong>.</li></ul>`, cls: 'subtle' },
      { k: 'Why this result', v: `${isFault.value ? 'The fall-out after-sales rule is met.' : 'The fall-out after-sales rule is not met.'}<ul class="verdict-rich-list"><li>${isFault.value ? 'This path requires an abnormal device state with recent abnormal telemetry, and the current record matches that rule.' : 'This path only accepts abnormal devices, and the current state does not meet that requirement.'}</li></ul>`, cls: 'subtle' },
      ...(isFault.value ? [{ k: 'Possible causes', v: 'Possible causes can be shown cautiously.<ul class="verdict-rich-list"><li>Collision, scratching, sweat, or other handling may have loosened the sensor.</li></ul>', cls: 'subtle' }] : []),
    ];
  }
  if (categoryKey.value === 'sensor') {
    if (!isFault.value) {
      return [
        { k: 'What we found', v: 'The current record entered sensor-abnormality review but did not form an abnormal conclusion.', cls: 'subtle' },
        { k: 'Why this result', v: 'The confirmed sensor-abnormality rule is not hit.<ul class="verdict-rich-list"><li>No abnormal sensor status is currently detected on this device.</li></ul>', cls: 'subtle' },
      ];
    }
    return [
      { k: 'What we found', v: `${latestRecord.value.faultSubtype} was detected.<ul class="verdict-rich-list"><li>The abnormality is present in the current sensor state.</li></ul>`, cls: 'subtle' },
      { k: 'Why this result', v: 'The supported sensor-abnormality rule is met.<ul class="verdict-rich-list"><li>The current record can proceed on the sensor-abnormality path.</li></ul>', cls: 'subtle' },
      { k: 'Possible causes', v: 'Possible causes can be shown cautiously.<ul class="verdict-rich-list"><li>Sensor loosening, insertion-site motion, or probe failure may contribute depending on subtype.</li></ul>', cls: 'subtle' },
    ];
  }
  return [
    { k: 'What we found', v: `${isFault.value ? 'The uploaded photos match an application-failure pattern.' : 'The current photo set does not show a clear application-failure pattern.'}<ul class="verdict-rich-list"><li>Photo count: <strong>${implantPhotoCount.value || 2}</strong>.</li></ul>`, cls: 'subtle' },
    { k: 'Why this result', v: `${isFault.value ? 'The application-failure review rule is met.' : 'The current evidence does not meet the application-failure pass rule.'}<ul class="verdict-rich-list"><li>${isFault.value ? 'Minimum photo count and material-score requirements are satisfied.' : 'The current evidence is more consistent with insufficient evidence than a confirmed application-failure subtype.'}</li></ul>`, cls: 'subtle' },
    ...(isFault.value ? [{ k: 'Possible causes', v: 'Possible causes must follow the confirmed subtype.<ul class="verdict-rich-list"><li>Photo evidence should remain attached to the after-sales application.</li></ul>', cls: 'subtle' }] : []),
  ];
});
const deviceOverviewRows = computed(() => [
  { k: 'Device ID', v: device.value?.sn ?? '', cls: 'mono' },
  { k: 'Model', v: device.value?.type ?? '' },
  { k: 'Activated', v: device.value?.activatedAt ?? '' },
  { k: 'Worn time', v: `Worn ${device.value?.wearDays ?? 0}d ${device.value?.wearHours ?? 0}h` },
]);
const nextStepItems = computed(() => {
  if (!latestRecord.value) return [];
  if (categoryKey.value === 'inaccuracy' && !isFault.value) {
    return [
      '<strong>After-sales status:</strong> Do not continue to after-sales from the first-round curve result.',
      '<strong>Why:</strong> The first-pass curve screening did not hit persistent low, no fluctuation, or jump-point.',
      '<strong>Wearer advice:</strong> Keep following normal wear guidance while preparing the CGM/BGM image comparison.',
      '<strong>Next action:</strong> Enter the blood sugar deviation judgment and collect two paired CGM/BGM image groups for comparison.',
    ];
  }
  if (latestRecord.value.afterSales === 'Replacement Eligible') {
    const why = categoryKey.value === 'detachment'
      ? 'The device is already in an abnormal state and the fall-out rule is satisfied by the current telemetry.'
      : categoryKey.value === 'sensor'
        ? 'The current record matches the supported sensor-abnormality rule for this path.'
        : categoryKey.value === 'implant'
          ? 'VLM review formed a supported application-failure result.'
          : 'The first-pass CGM screening hit the configured rule for this record.';
    return [
      '<strong>After-sales status:</strong> You can continue to after-sales from this result.',
      `<strong>Why:</strong> ${why}`,
      '<strong>Wearer advice:</strong> Keep the current evidence available and follow normal wear guidance unless support instructs removal.',
      '<strong>Next action:</strong> Continue to the after-sales application with this record.',
    ];
  }
  return [
    '<strong>After-sales status:</strong> Do not continue to after-sales from this result.',
    '<strong>Why:</strong> The current evidence does not match the after-sales rule for this path.',
    '<strong>Wearer advice:</strong> Continue normal wear guidance unless symptoms change.',
    '<strong>Next action:</strong> Re-check the issue path or upload new evidence if needed.',
  ];
});
const pageId = computed(() => {
  if (phase.value === 'form') return 'page-detect-form';
  if (phase.value === 'inaccuracy-upload') return 'page-inaccuracy-upload';
  if (phase.value === 'processing') return 'page-processing';
  return 'page-result';
});
const processingProgress = computed(() => `${Math.min(100, Math.round((processingStep.value / Math.max(1, processingSteps.value.length)) * 100))}%`);
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
      primaryLabel: 'Run implant detect',
    };
  }
  if (category === 'Sensor falling off') {
    return {
      title: 'Sensor falling off',
      subtitle: 'No supporting materials are shown. The result is judged directly from device status and telemetry timing.',
      guidanceType: 'guidance-teal',
      guidanceTitle: 'Instant run',
      guidanceItems: [
        'Check abnormal device state, last upload, anomaly timeline, and wear window.',
        'No image upload is required for this scenario.',
      ],
      primaryLabel: 'Run detect',
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
    primaryLabel: 'Run detect',
  };
});
const implantUploadStatus = computed(() => {
  if (implantPhotoCount.value >= 2) return `${implantPhotoCount.value} photo(s) uploaded; minimum met (>=2 required for application-failure path).`;
  if (uploadError.value) return uploadError.value;
  return `${implantPhotoCount.value} / 2 minimum; add at least ${2 - implantPhotoCount.value} more photo(s) before running application-failure detect.`;
});
const deviationUploadStatus = computed(() => {
  if (deviationImageCount.value >= 4) return '2 / 2 CGM/BGM groups uploaded; minimum met.';
  if (deviationUploadError.value) return deviationUploadError.value;
  const remaining = 4 - deviationImageCount.value;
  return `${deviationImageCount.value} / 4 images uploaded; add ${remaining} more CGM/BGM image(s).`;
});
const processingSteps = computed(() => {
  const base = ['Retrieving device information', 'Fetching glucose curve data', 'Filtering valid time ranges'];
  if (selectedCategory.value === 'Data accuracy') {
    if (inaccuracyDeviationMode.value) {
      return [...base, 'Reading CGM/BGM pair images', 'Matching timestamps across CGM and BGM', 'Estimating CGM vs BGM bias', 'Generating conclusion'];
    }
    return [...base, 'Running persistent low detection', 'Scanning for flat-line patterns', 'Checking jump point anomalies', 'Generating conclusion'];
  }
  if (selectedCategory.value === 'Sensor falling off') {
    return [...base, 'Check abnormal device state (fall-off intake)', 'Load last upload & anomaly timeline', 'Verify service card on file', 'Build verdict'];
  }
  if (selectedCategory.value === 'Sensor Abnormal') {
    return [...base, 'Checking sensor status', 'Evaluating initialization phase', 'Analyzing anomaly timeline', 'Determining recovery status', 'Generating conclusion'];
  }
  return [
    'Retrieving device & ticket bundle',
    'Verifying activation in CGM core',
    `Ingesting ${implantPhotoCount.value || 2} site photo(s) (minimum 2)`,
    'Running VLM classification on implant photos',
    'Correlating VLM sub-type with fault rules',
    'Checking after-sales service card on file',
    'Generating conclusion',
  ];
});

watch([selectedCategory, routeRecordId, () => route.query.session], () => {
  const session = routeSession.value;
  inaccuracyDeviationMode.value = false;
  deviationImageCount.value = 0;
  deviationUploadError.value = '';
  implantPhotoCount.value = 0;
  uploadError.value = '';
  processingComplete.value = false;
  processingSessionId.value = '';
  activeRecordId.value = routeRecordId.value || session?.recordId || '';
  if (session?.status === 'processing' && !activeRecordId.value) {
    beginProcessingWithSession(session.id);
    return;
  }
  phase.value = latestRecord.value ? 'result' : 'form';
}, { immediate: true });

watch(latestRecord, record => {
  if (record && phase.value !== 'processing') {
    phase.value = 'result';
  }
}, { immediate: true });

function addImplantPhoto() {
  if (implantPhotoCount.value >= 3) return;
  implantPhotoCount.value += 1;
  uploadError.value = '';
}

function addDeviationImage() {
  if (deviationImageCount.value >= 4) return;
  deviationImageCount.value += 1;
  deviationUploadError.value = '';
}

function completeDetect() {
  const record = inaccuracyDeviationMode.value && selectedCategory.value === 'Data accuracy'
    ? store.runDataDeviationReview(props.sn)
    : store.runDetect(props.sn, selectedCategory.value);
  activeRecordId.value = record.id;
  if (processingSessionId.value) {
    store.completeDetectSession(processingSessionId.value, record);
  }
  phase.value = 'result';
}

function clearProcessingTimers() {
  if (processingTimer) window.clearInterval(processingTimer);
  if (processingCompletionTimer) window.clearTimeout(processingCompletionTimer);
  processingTimer = undefined;
  processingCompletionTimer = undefined;
}

function beginProcessingWithSession(sessionId: string) {
  if (phase.value === 'processing' && processingSessionId.value === sessionId) return;
  clearProcessingTimers();
  processingStep.value = 0;
  processingComplete.value = false;
  processingSessionId.value = sessionId;
  phase.value = 'processing';
  processingTimer = window.setInterval(() => {
    processingStep.value += 1;
    if (processingStep.value >= processingSteps.value.length) {
      if (processingTimer) window.clearInterval(processingTimer);
      processingTimer = undefined;
      processingComplete.value = true;
      processingCompletionTimer = window.setTimeout(completeDetect, 800);
    }
  }, 1200);
}

function startProcessing() {
  const session = store.startDetectSession(props.sn, selectedCategory.value);
  beginProcessingWithSession(session.id);
}

onBeforeUnmount(() => {
  clearProcessingTimers();
});

function runDetect() {
  if (selectedCategory.value === 'Application failure' && implantPhotoCount.value < 2) {
    uploadError.value = `0 / 2 minimum; add at least ${2 - implantPhotoCount.value} more photo(s) before running application-failure detect.`;
    return;
  }
  if (selectedCategory.value === 'Data accuracy' && store.requiresDataDeviationReview(props.sn, selectedCategory.value)) {
    phase.value = 'inaccuracy-upload';
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
</script>

<template>
  <div v-if="device && fault" class="page active" :id="pageId">
    <div class="page-body">
      <div v-if="phase === 'form'" id="diag-form-shell" class="diag-form-shell" :class="{ 'implant-flow-shell': selectedCategory === 'Application failure' }">
        <div class="diag-form-header slide-up stagger-1">
          <button class="btn btn-ghost btn-sm" style="margin-bottom:12px" type="button" data-test="detect-back" @click="backFromDetect">&#8592; {{ detectBackLabel }}</button>
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
                  <label class="form-label">Sensor serial</label>
                  <input class="form-input mono" type="text" :value="device.sn" readonly />
                </div>
                <div class="form-group">
                  <label class="form-label">Model</label>
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
                  :class="{ 'is-done': implantPhotoCount > index }"
                  type="button"
                  @click="addImplantPhoto"
                >
                  <div class="upload-zone-icon">{{ implantPhotoCount > index ? 'Done' : 'Add' }}</div>
                  <p>{{ implantPhotoCount > index ? 'Photo added' : slot }}</p>
                  <small>{{ implantPhotoCount > index ? 'mock_implant_site.jpg' : 'Tap to upload' }}</small>
                </button>
              </div>
              <p class="implant-upload-status" :class="{ 'is-ok': implantPhotoCount >= 2, 'upload-error-text': !!uploadError }">{{ implantUploadStatus }}</p>
            </template>

            <template v-else>
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">Sensor serial</label>
                  <input class="form-input mono" type="text" :value="device.sn" readonly />
                </div>
                <div class="form-group">
                  <label class="form-label">Model</label>
                  <input class="form-input" type="text" :value="device.type" readonly />
                </div>
              </div>
              <div class="detect-review-pack detect-light-surface">
                <div class="result-panel-head">
                  <span>{{ selectedCategory === 'Sensor falling off' ? 'Telemetry review pack' : 'Sensor status review pack' }}</span>
                  <span class="result-tag-pill">No upload required</span>
                </div>
                <div class="detect-review-grid">
                  <div class="verdict-spec-row">
                    <div class="verdict-spec-k">Device state</div>
                    <div class="verdict-spec-v">{{ device.status }}</div>
                  </div>
                  <div class="verdict-spec-row">
                    <div class="verdict-spec-k">Last upload</div>
                    <div class="verdict-spec-v subtle">{{ device.lastDataAt }}</div>
                  </div>
                  <div class="verdict-spec-row">
                    <div class="verdict-spec-k">Wear window</div>
                    <div class="verdict-spec-v">Worn {{ device.wearDays }}d {{ device.wearHours }}h</div>
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
                :class="{ 'is-done': deviationImageCount > index }"
                type="button"
                @click="addDeviationImage"
              >
                <div class="upload-zone-icon">{{ deviationImageCount > index ? 'Done' : 'Upload' }}</div>
                <p>{{ deviationImageCount > index ? 'Image added' : label }}</p>
                <small>{{ deviationImageCount > index ? 'mock_cgm_bgm_pair.jpg' : 'Tap to upload' }}</small>
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
        <div class="processing-card">
          <div class="processing-left">
            <svg v-if="!processingComplete" class="processing-spinner" viewBox="0 0 120 120" role="img" aria-label="Processing">
              <circle class="spinner-track" cx="60" cy="60" r="48" fill="none" stroke-width="8" />
              <circle class="spinner-fill" cx="60" cy="60" r="48" fill="none" stroke-width="8" />
            </svg>
            <div v-else class="processing-complete-check" role="img" aria-label="Processing complete">Done</div>
            <div class="proc-eta">{{ processingComplete ? 'Complete' : 'Analyzing' }}</div>
          </div>
          <div class="processing-right">
            <h2>Analyzing device data</h2>
            <p id="processing-subtitle">Streaming telemetry, rule packs, and optional vision checks for a full verdict.</p>
            <div id="processing-steps" class="processing-steps">
              <div v-for="(step, index) in processingSteps" :key="step" class="proc-step" :class="{ done: processingComplete || index < processingStep, active: !processingComplete && index === processingStep }">
                <div class="proc-step-icon">{{ processingComplete || index < processingStep ? 'Done' : index === processingStep ? 'Now' : 'Next' }}</div>
                <div>{{ step }}</div>
              </div>
            </div>
            <div class="processing-progress"><div id="processing-bar" class="processing-progress-bar" :style="{ width: processingProgress }"></div></div>
          </div>
        </div>
      </div>

      <section v-else-if="latestRecord" class="result-shell slide-up stagger-5">
        <div class="verdict-page">
          <button class="btn btn-ghost btn-sm slide-up stagger-1" style="margin-bottom:10px" type="button" data-test="detect-back" @click="backFromDetect">&#8592; {{ detectBackLabel }}</button>
          <div class="verdict-bc slide-up stagger-1">
            Devices <span class="sep">/</span> <span class="mono">{{ device.sn }}</span> <span class="sep">/</span> <strong>{{ latestRecord.faultCategory }}</strong>
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
                  <h2 class="verdict-hero-title">{{ verdictTitle }}</h2>
                  <div class="verdict-hero-summary">
                    <div class="verdict-hero-subline">{{ latestRecord.conclusion }} / {{ latestRecord.afterSales }}</div>
                    <div class="verdict-hero-detail">{{ heroSummary }}</div>
                    <div class="verdict-hero-history">{{ historyLookback }}</div>
                  </div>
                </div>
              </div>

              <div class="verdict-cards">
                <div class="verdict-card slide-up stagger-3">
                  <div class="verdict-card-head">Basis for the verdict</div>
                  <div v-for="row in reasonRows" :key="row.k" class="verdict-spec-row">
                    <div class="verdict-spec-k">{{ row.k }}</div>
                    <div class="verdict-spec-v" :class="row.cls" v-html="row.v"></div>
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
                    <li v-for="item in nextStepItems" :key="item" v-html="item"></li>
                  </ul>
                </div>
              </div>

              <div v-if="!isFromChat && !isFromRecords" class="verdict-footer-actions slide-up stagger-6">
                <button class="btn btn-verdict-primary btn-lg" type="button" data-test="detect-another" @click="detectAnother">Detect another</button>
                <button class="btn btn-secondary btn-lg" type="button" data-test="new-lookup" @click="goToNewLookup">New lookup</button>
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
                    Adopt
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
                  Adopted; marked as the recommended basis for this case.
                </p>
                <p v-else-if="verdictDecision === 'reject' && rejectSubmitted" class="verdict-feedback-note verdict-feedback-note--reject" data-test="verdict-reject-note">
                  Rejected{{ rejectComment.trim() ? `: ${rejectComment.trim()}` : '' }}.
                </p>
              </div>
            </aside>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.detect-review-pack {
  margin-bottom: 16px;
  padding: 18px 20px;
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
  gap: 12px;
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
}

.verdict-feedback-note--adopt {
  color: var(--accent);
  font-weight: 700;
}

.verdict-feedback-note--reject {
  color: #9a6700;
  font-weight: 700;
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
}
</style>
