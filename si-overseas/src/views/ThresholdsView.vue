<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import {
  APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT,
  DATA_DEVIATION_REQUIRED_PAIR_COUNT,
  completeThresholdRules,
} from '@/composables/thresholdProfile';
import { useDemoStore } from '@/composables/useDemoStore';
import type { GlucoseUnitPreference, ThresholdRules } from '@/types/threshold';
import { formatGlucoseDelta, toDisplayGlucose, toMmol } from '@/utils/glucoseUnit';

type FieldKey =
  | 'lowBelowMmol'
  | 'lowMinHours'
  | 'lowPeak24hMmol'
  | 'flatMinHours'
  | 'flatFloorMmol'
  | 'flatMaxSwingMmol'
  | 'jumpDeltaMmol'
  | 'jumpConsecutive'
  | 'within48hDeviationMmol'
  | 'within48hPairCount'
  | 'within48hQualifiedPairCount'
  | 'after48hDeviationRangePct'
  | 'after48hPairCount'
  | 'after48hQualifiedPairCount'
  | 'after48hWearDays'
  | 'abnormalWearDays'
  | 'temporaryAbnormalHours'
  | 'detachedStatusValue'
  | 'detachmentWearDays'
  | 'applicationPhotoCount'
  | 'applicationAfterSalesScore'
  | 'applicationManualReviewScore';

type ThresholdForm = Record<FieldKey, number>;
type ThresholdModal =
  | { kind: 'reset-confirm' }
  | { kind: 'save-confirm' }
  | { kind: 'rollback-confirm'; version: number }
  | { kind: 'delete-confirm'; version: number }
  | { kind: 'success'; title: string; message: string };

interface ThresholdField {
  key: FieldKey;
  label: string;
  hint: string;
  step: string;
  min: number;
  max: number;
  integer?: boolean;
}

interface ThresholdGroup {
  key: string;
  scope: string;
  tone: 'amber' | 'blue' | 'purple' | 'teal';
  title: string;
  subtitle: string;
  fields: ThresholdField[];
}

const store = useDemoStore();
const selectedGlucoseUnit = ref<GlucoseUnitPreference>('mmol/L');
const activeProfileGlucoseUnit = computed<GlucoseUnitPreference>(() => (
  store.activeThresholdProfile.value.display?.glucoseUnit === 'mg/dL' ? 'mg/dL' : 'mmol/L'
));
const glucoseUnit = computed<GlucoseUnitPreference>(() => selectedGlucoseUnit.value);
const activeModal = ref<ThresholdModal | null>(null);
const initialSnapshot = ref('');
const errors = reactive<Partial<Record<FieldKey, string>>>({});

const showHistoryDrawer = ref(false);
const historyList = ref<any[]>([]);
const loadingHistory = ref(false);
const comparingVersion = ref<any | null>(null);

const saveRemark = ref('');
const editingRemarkVersion = ref<number | null>(null);
const editingRemarkText = ref('');

const form = reactive<ThresholdForm>({
  lowBelowMmol: 2.8,
  lowMinHours: 4,
  lowPeak24hMmol: 7.8,
  flatMinHours: 8,
  flatFloorMmol: 4.5,
  flatMaxSwingMmol: 1.0,
  jumpDeltaMmol: 3.0,
  jumpConsecutive: 3,
  within48hDeviationMmol: 7.0,
  within48hPairCount: 2,
  within48hQualifiedPairCount: 2,
  after48hDeviationRangePct: 20,
  after48hPairCount: 2,
  after48hQualifiedPairCount: 2,
  after48hWearDays: 2,
  abnormalWearDays: 0,
  temporaryAbnormalHours: 3,
  detachedStatusValue: 1,
  detachmentWearDays: 0,
  applicationPhotoCount: 2,
  applicationAfterSalesScore: 8,
  applicationManualReviewScore: 5,
});

const glucoseFieldKeys = new Set<FieldKey>([
  'lowBelowMmol',
  'lowPeak24hMmol',
  'flatFloorMmol',
  'flatMaxSwingMmol',
  'jumpDeltaMmol',
  'within48hDeviationMmol',
]);

function glucoseField(
  key: FieldKey,
  label: string,
  hint: string,
  minMmol: number,
  maxMmol: number,
): ThresholdField {
  const unit = glucoseUnit.value;
  return {
    key,
    label: `${label} (${unit})`,
    hint,
    step: '0.1',
    min: toDisplayGlucose(minMmol, unit),
    max: toDisplayGlucose(maxMmol, unit),
  };
}

const groups = computed<ThresholdGroup[]>(() => [
  {
    key: 'persistentLow',
    scope: 'Data accuracy',
    tone: 'amber',
    title: 'Persistent low glucose',
    subtitle: 'Thresholds for sustained low glucose.',
    fields: [
      glucoseField('lowBelowMmol', 'Minimum glucose value', 'Low-glucose floor for the persistent-low rule.', 2, 10),
      { key: 'lowMinHours', label: 'Duration (hours)', hint: 'Minimum duration before the condition is met.', step: '1', min: 1, max: 24, integer: true },
      glucoseField('lowPeak24hMmol', 'Maximum glucose value', '24-hour peak cap for the persistent-low rule.', 2, 20),
    ],
  },
  {
    key: 'noFluctuation',
    scope: 'Data accuracy',
    tone: 'amber',
    title: 'No fluctuation',
    subtitle: 'Thresholds for flat glucose traces.',
    fields: [
      { key: 'flatMinHours', label: 'Duration (hours)', hint: 'Review window for the no-fluctuation rule.', step: '1', min: 1, max: 24, integer: true },
      glucoseField('flatFloorMmol', 'Minimum glucose value', 'Glucose floor for the review window.', 1, 20),
      glucoseField('flatMaxSwingMmol', 'Fluctuation value', 'Maximum allowed movement inside the review window.', 0.1, 10),
    ],
  },
  {
    key: 'jumpPoints',
    scope: 'Data accuracy',
    tone: 'amber',
    title: 'Sudden Glucose Changes',
    subtitle: 'Thresholds for adjacent sudden glucose changes.',
    fields: [
      glucoseField('jumpDeltaMmol', 'Minimum Glucose Difference', 'Adjacent readings above this difference count as sudden glucose changes.', 0.1, 20),
      { key: 'jumpConsecutive', label: 'Occurrence count', hint: 'Consecutive sudden glucose changes needed before the condition is met.', step: '1', min: 1, max: 10, integer: true },
    ],
  },
  {
    key: 'deviationWithin48h',
    scope: 'Data accuracy',
    tone: 'amber',
    title: 'Data deviation within 48h',
    subtitle: 'Thresholds for comparison groups collected inside the first 48 hours.',
    fields: [
      glucoseField('within48hDeviationMmol', 'Glucose deviation value', 'Deviation threshold for each comparison group.', 0.1, 20),
    ],
  },
  {
    key: 'deviationAfter48h',
    scope: 'Data accuracy',
    tone: 'amber',
    title: 'Data deviation after 48h',
    subtitle: 'Thresholds for comparison groups collected after 48 hours.',
    fields: [
      { key: 'after48hDeviationRangePct', label: 'Glucose deviation range (%)', hint: 'Allowed deviation range after the first 48 hours.', step: '1', min: 1, max: 100 },
      { key: 'after48hWearDays', label: 'Wear days', hint: 'Use 0 when no wear-day gate is needed.', step: '1', min: 0, max: 30, integer: true },
    ],
  },
  {
    key: 'deviceAbnormal',
    scope: 'Device behavior',
    tone: 'blue',
    title: 'Sensor Malfunction',
    subtitle: 'Thresholds for sensor malfunctions.',
    fields: [
      { key: 'abnormalWearDays', label: 'Wear days', hint: 'Use 0 when no wear-day gate is needed.', step: '1', min: 0, max: 30, integer: true },
      { key: 'temporaryAbnormalHours', label: 'Temporary abnormal duration (hours)', hint: 'Temporary abnormal status must last longer than this value before it qualifies.', step: '1', min: 1, max: 24, integer: true },
    ],
  },
  {
    key: 'detachment',
    scope: 'Sensor status',
    tone: 'purple',
    title: 'Sensor Falling Off',
    subtitle: 'Thresholds for detachment rules.',
    fields: [
      { key: 'detachedStatusValue', label: 'Detachment status value', hint: 'Use 1 for detached and 0 for not detached.', step: '1', min: 0, max: 1, integer: true },
      { key: 'detachmentWearDays', label: 'Wear days', hint: 'Use 0 when no wear-day gate is needed.', step: '1', min: 0, max: 30, integer: true },
    ],
  },
  {
    key: 'applicationFailure',
    scope: 'Application evidence',
    tone: 'teal',
    title: 'Application Failure',
    subtitle: 'Thresholds for application failure review.',
    fields: [
      { key: 'applicationAfterSalesScore', label: 'After-sales score threshold', hint: 'Score at or above this value recommends after-sales.', step: '1', min: 1, max: 10, integer: true },
      { key: 'applicationManualReviewScore', label: 'Manual review score threshold', hint: 'Score at or above this value but below the after-sales threshold recommends manual review.', step: '1', min: 1, max: 10, integer: true },
    ],
  },
]);

function profileToForm(profileRules: ThresholdRules): ThresholdForm {
  const r = completeThresholdRules(profileRules);
  const unit = glucoseUnit.value;
  return {
    lowBelowMmol: toDisplayGlucose(r.inaccuracy.lowPersist.belowMmol, unit),
    lowMinHours: r.inaccuracy.lowPersist.minHours,
    lowPeak24hMmol: toDisplayGlucose(r.inaccuracy.lowPersist.max24hMmol, unit),
    flatMinHours: r.inaccuracy.noFluctuation.minHours,
    flatFloorMmol: toDisplayGlucose(r.inaccuracy.noFluctuation.floorMmol, unit),
    flatMaxSwingMmol: toDisplayGlucose(r.inaccuracy.noFluctuation.maxSwingMmol, unit),
    jumpDeltaMmol: toDisplayGlucose(r.inaccuracy.jump.deltaMmol, unit),
    jumpConsecutive: r.inaccuracy.jump.consecutive,
    within48hDeviationMmol: toDisplayGlucose(r.inaccuracy.deviation.within48hDeviationMmol, unit),
    within48hPairCount: r.inaccuracy.deviation.within48hPairCount,
    within48hQualifiedPairCount: r.inaccuracy.deviation.within48hQualifiedPairCount,
    after48hDeviationRangePct: r.inaccuracy.deviation.after48hDeviationRangePct,
    after48hPairCount: r.inaccuracy.deviation.after48hPairCount,
    after48hQualifiedPairCount: r.inaccuracy.deviation.after48hQualifiedPairCount,
    after48hWearDays: r.inaccuracy.deviation.after48hWearDays,
    abnormalWearDays: r.deviceAbnormal.wearDays,
    temporaryAbnormalHours: r.deviceAbnormal.temporaryAbnormalHours,
    detachedStatusValue: r.detachment.detachedStatusValue,
    detachmentWearDays: r.detachment.wearDays,
    applicationPhotoCount: r.applicationFailure.photoCount,
    applicationAfterSalesScore: r.applicationFailure.afterSalesScore,
    applicationManualReviewScore: r.applicationFailure.manualReviewScore,
  };
}

function formToRules(): ThresholdRules {
  const unit = glucoseUnit.value;
  return {
    inaccuracy: {
      lowPersist: {
        belowMmol: toMmol(form.lowBelowMmol, unit),
        minHours: form.lowMinHours,
        max24hMmol: toMmol(form.lowPeak24hMmol, unit),
      },
      noFluctuation: {
        floorMmol: toMmol(form.flatFloorMmol, unit),
        minHours: form.flatMinHours,
        maxSwingMmol: toMmol(form.flatMaxSwingMmol, unit),
      },
      jump: {
        deltaMmol: toMmol(form.jumpDeltaMmol, unit),
        consecutive: form.jumpConsecutive,
      },
      deviation: {
        within48hDeviationMmol: toMmol(form.within48hDeviationMmol, unit),
        within48hPairCount: DATA_DEVIATION_REQUIRED_PAIR_COUNT,
        within48hQualifiedPairCount: DATA_DEVIATION_REQUIRED_PAIR_COUNT,
        after48hDeviationRangePct: form.after48hDeviationRangePct,
        after48hPairCount: DATA_DEVIATION_REQUIRED_PAIR_COUNT,
        after48hQualifiedPairCount: DATA_DEVIATION_REQUIRED_PAIR_COUNT,
        after48hWearDays: form.after48hWearDays,
      },
    },
    deviceAbnormal: {
      wearDays: form.abnormalWearDays,
      temporaryAbnormalHours: form.temporaryAbnormalHours,
    },
    detachment: {
      detachedStatusValue: form.detachedStatusValue,
      wearDays: form.detachmentWearDays,
    },
    applicationFailure: {
      photoCount: APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT,
      afterSalesScore: form.applicationAfterSalesScore,
      manualReviewScore: form.applicationManualReviewScore,
    },
  };
}

function syncFromActiveProfile() {
  selectedGlucoseUnit.value = activeProfileGlucoseUnit.value;
  Object.assign(form, profileToForm(store.activeThresholdProfile.value.rules));
  initialSnapshot.value = currentSnapshot();
  Object.keys(errors).forEach(key => delete errors[key as FieldKey]);
}

watch(store.activeThresholdProfile, syncFromActiveProfile, { immediate: true });

function currentSnapshot() {
  return JSON.stringify({ glucoseUnit: glucoseUnit.value, form });
}

const dirty = computed(() => currentSnapshot() !== initialSnapshot.value);
const modalTitle = computed(() => {
  if (!activeModal.value) return '';
  if (activeModal.value.kind === 'reset-confirm') {
    return 'Reset condition settings?';
  }
  if (activeModal.value.kind === 'save-confirm') {
    return 'Save condition settings?';
  }
  if (activeModal.value.kind === 'rollback-confirm') {
    return 'Restore historical version?';
  }
  if (activeModal.value.kind === 'delete-confirm') {
    return 'Delete historical version?';
  }
  return activeModal.value.title;
});
const modalDescription = computed(() => {
  if (!activeModal.value) return '';
  if (activeModal.value.kind === 'reset-confirm') {
    return 'This will restore all values to the default profile.';
  }
  if (activeModal.value.kind === 'save-confirm') {
    return 'You are about to save changes. You can optionally add a version name or description below:';
  }
  if (activeModal.value.kind === 'rollback-confirm') {
    return `You are about to restore Version v${activeModal.value.version}. You can optionally enter a remark or version name below:`;
  }
  if (activeModal.value.kind === 'delete-confirm') {
    return `Version v${activeModal.value.version} will be removed from the history list. This action cannot be undone from this page.`;
  }
  return activeModal.value.message;
});
const modalRole = computed(() => activeModal.value?.kind === 'success' ? 'alertdialog' : 'dialog');

function validateField(field: ThresholdField) {
  const value = form[field.key];
  if (!Number.isFinite(value)) {
    errors[field.key] = 'Enter a valid number.';
    return false;
  }
  if (field.integer && !Number.isInteger(value)) {
    errors[field.key] = 'Use a whole number.';
    return false;
  }
  if (value < field.min || value > field.max) {
    errors[field.key] = `Enter a value from ${field.min} to ${field.max}.`;
    return false;
  }
  delete errors[field.key];
  return true;
}

function validateAll() {
  const invalid: FieldKey[] = [];
  for (const group of groups.value) {
    for (const field of group.fields) {
      if (!validateField(field)) invalid.push(field.key);
    }
  }

  if (form.within48hQualifiedPairCount > form.within48hPairCount) {
    form.within48hQualifiedPairCount = DATA_DEVIATION_REQUIRED_PAIR_COUNT;
    form.within48hPairCount = DATA_DEVIATION_REQUIRED_PAIR_COUNT;
  }
  if (form.after48hQualifiedPairCount > form.after48hPairCount) {
    form.after48hQualifiedPairCount = DATA_DEVIATION_REQUIRED_PAIR_COUNT;
    form.after48hPairCount = DATA_DEVIATION_REQUIRED_PAIR_COUNT;
  }
  if (form.applicationManualReviewScore > form.applicationAfterSalesScore) {
    errors.applicationManualReviewScore = 'Manual review score cannot exceed after-sales score.';
    invalid.push('applicationManualReviewScore');
  }

  return invalid;
}

function focusField(key: FieldKey) {
  document.getElementById(`threshold-${key}`)?.focus();
}

async function updateGlucoseUnitPreference(unit: GlucoseUnitPreference) {
  if (unit === glucoseUnit.value) return;
  const currentRules = formToRules();
  selectedGlucoseUnit.value = unit;
  Object.assign(form, profileToForm(currentRules));
}

function triggerSave() {
  const invalid = validateAll();
  if (invalid.length) {
    focusField(invalid[0]);
    return;
  }
  saveRemark.value = '';
  activeModal.value = { kind: 'save-confirm' };
}

async function confirmSave() {
  await store.saveThresholdProfileRemote({
    rules: formToRules(),
    display: { glucoseUnit: glucoseUnit.value },
  }, saveRemark.value);
  activeModal.value = {
    kind: 'success',
    title: 'Settings saved',
    message: 'The updated values will be used for future detect runs.',
  };
}

function reset() {
  activeModal.value = { kind: 'reset-confirm' };
}

async function confirmReset() {
  await store.resetThresholdProfileRemote();
  activeModal.value = {
    kind: 'success',
    title: 'Settings reset',
    message: 'Default values have been restored.',
  };
}

function closeModal() {
  activeModal.value = null;
}

async function fetchHistory() {
  loadingHistory.value = true;
  try {
    historyList.value = await store.getThresholdHistoryRemote();
  } catch (err) {
    console.error('Failed to fetch threshold history', err);
  } finally {
    loadingHistory.value = false;
  }
}

watch(showHistoryDrawer, (visible) => {
  if (visible) {
    void fetchHistory();
    comparingVersion.value = null;
  }
});

function triggerRollback(version: number) {
  saveRemark.value = '';
  activeModal.value = { kind: 'rollback-confirm', version };
}

async function confirmRollback() {
  if (activeModal.value?.kind !== 'rollback-confirm') return;
  const version = activeModal.value.version;
  try {
    await store.rollbackThresholdRemote(version, saveRemark.value);
    showHistoryDrawer.value = false;
    activeModal.value = {
      kind: 'success',
      title: 'Rollback successful',
      message: `Successfully restored threshold settings to version ${version}.`,
    };
  } catch (err) {
    console.error('Failed to rollback threshold', err);
    activeModal.value = {
      kind: 'success',
      title: 'Rollback failed',
      message: 'An error occurred while reverting to the selected version.',
    };
  }
}

function startEditingRemark(ver: any) {
  editingRemarkVersion.value = ver.version;
  editingRemarkText.value = ver.remark || '';
}

async function saveRemarkEdit(version: number) {
  try {
    await store.updateThresholdRemarkRemote(version, editingRemarkText.value);
    const found = historyList.value.find(p => p.version === version);
    if (found) {
      found.remark = editingRemarkText.value;
    }
    editingRemarkVersion.value = null;
  } catch (err) {
    console.error('Failed to edit remark', err);
  }
}

function deleteVersion(version: number) {
  activeModal.value = { kind: 'delete-confirm', version };
}

async function confirmDeleteVersion() {
  if (activeModal.value?.kind !== 'delete-confirm') return;
  const version = activeModal.value.version;
  try {
    await store.hideThresholdRemote(version);
    historyList.value = historyList.value.filter(p => p.version !== version);
    activeModal.value = null;
  } catch (err) {
    console.error('Failed to delete version', err);
    activeModal.value = {
      kind: 'success',
      title: 'Delete failed',
      message: 'An error occurred while deleting the selected historical version.',
    };
  }
}

function getDiff(targetRules: any) {
  const currentRules = formToRules();
  const diffs: { path: string; from: any; to: any }[] = [];

  if (targetRules.inaccuracy?.lowPersist && currentRules.inaccuracy?.lowPersist) {
    const t = targetRules.inaccuracy.lowPersist;
    const c = currentRules.inaccuracy.lowPersist;
    if (t.belowMmol !== c.belowMmol) diffs.push({ path: 'Persistent Low / Floor', from: formatGlucoseDelta(t.belowMmol, glucoseUnit.value), to: formatGlucoseDelta(c.belowMmol, glucoseUnit.value) });
    if (t.minHours !== c.minHours) diffs.push({ path: 'Persistent Low / Duration', from: `${t.minHours}h`, to: `${c.minHours}h` });
    if (t.max24hMmol !== c.max24hMmol) diffs.push({ path: 'Persistent Low / 24h Peak', from: formatGlucoseDelta(t.max24hMmol, glucoseUnit.value), to: formatGlucoseDelta(c.max24hMmol, glucoseUnit.value) });
  }
  
  if (targetRules.inaccuracy?.noFluctuation && currentRules.inaccuracy?.noFluctuation) {
    const t = targetRules.inaccuracy.noFluctuation;
    const c = currentRules.inaccuracy.noFluctuation;
    if (t.floorMmol !== c.floorMmol) diffs.push({ path: 'No Fluctuation / Floor', from: formatGlucoseDelta(t.floorMmol, glucoseUnit.value), to: formatGlucoseDelta(c.floorMmol, glucoseUnit.value) });
    if (t.minHours !== c.minHours) diffs.push({ path: 'No Fluctuation / Duration', from: `${t.minHours}h`, to: `${c.minHours}h` });
    if (t.maxSwingMmol !== c.maxSwingMmol) diffs.push({ path: 'No Fluctuation / Swing', from: formatGlucoseDelta(t.maxSwingMmol, glucoseUnit.value), to: formatGlucoseDelta(c.maxSwingMmol, glucoseUnit.value) });
  }

  if (targetRules.inaccuracy?.jump && currentRules.inaccuracy?.jump) {
    const t = targetRules.inaccuracy.jump;
    const c = currentRules.inaccuracy.jump;
    if (t.deltaMmol !== c.deltaMmol) diffs.push({ path: 'Sudden Glucose Changes / Minimum Difference', from: formatGlucoseDelta(t.deltaMmol, glucoseUnit.value), to: formatGlucoseDelta(c.deltaMmol, glucoseUnit.value) });
    if (t.consecutive !== c.consecutive) diffs.push({ path: 'Sudden Glucose Changes / Occurrences', from: t.consecutive, to: c.consecutive });
  }

  if (targetRules.inaccuracy?.deviation && currentRules.inaccuracy?.deviation) {
    const t = targetRules.inaccuracy.deviation;
    const c = currentRules.inaccuracy.deviation;
    if (t.within48hDeviationMmol !== c.within48hDeviationMmol) diffs.push({ path: '48h Deviation / Value', from: formatGlucoseDelta(t.within48hDeviationMmol, glucoseUnit.value), to: formatGlucoseDelta(c.within48hDeviationMmol, glucoseUnit.value) });
    if (t.after48hDeviationRangePct !== c.after48hDeviationRangePct) diffs.push({ path: 'Post-48h Deviation / Range', from: `${t.after48hDeviationRangePct}%`, to: `${c.after48hDeviationRangePct}%` });
  }

  if (targetRules.deviceAbnormal && currentRules.deviceAbnormal) {
    const t = targetRules.deviceAbnormal;
    const c = currentRules.deviceAbnormal;
    if (t.temporaryAbnormalHours !== c.temporaryAbnormalHours) diffs.push({ path: 'Sensor Malfunction / Duration', from: `${t.temporaryAbnormalHours}h`, to: `${c.temporaryAbnormalHours}h` });
    if (t.wearDays !== c.wearDays) diffs.push({ path: 'Sensor Malfunction / Wear Days', from: t.wearDays, to: c.wearDays });
  }

  if (targetRules.detachment && currentRules.detachment) {
    const t = targetRules.detachment;
    const c = currentRules.detachment;
    if (t.wearDays !== c.wearDays) diffs.push({ path: 'Falling Off / Wear Days', from: t.wearDays, to: c.wearDays });
  }

  if (targetRules.applicationFailure && currentRules.applicationFailure) {
    const t = targetRules.applicationFailure;
    const c = currentRules.applicationFailure;
    if (t.afterSalesScore !== c.afterSalesScore) diffs.push({ path: 'App Failure / Replacement Score', from: t.afterSalesScore, to: c.afterSalesScore });
    if (t.manualReviewScore !== c.manualReviewScore) diffs.push({ path: 'App Failure / Review Score', from: t.manualReviewScore, to: c.manualReviewScore });
  }

  return diffs;
}

function formatDate(iso: string | null) {
  if (!iso) return 'Unknown Date';
  try {
    const d = new Date(iso);
    const month = d.getMonth() + 1;
    const day = d.getDate();
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    const seconds = String(d.getSeconds()).padStart(2, '0');
    return `${month}/${day}  ${hours}:${minutes}:${seconds}`;
  } catch {
    return iso;
  }
}

function getRestoredFromLabel(restoredFromVersion: number): string {
  const source = historyList.value.find(p => p.version === restoredFromVersion);
  if (source && source.remark) {
    return source.remark;
  }
  return `Version v${restoredFromVersion}`;
}
</script>

<template>
  <div class="page active" id="page-thresholds">
    <div class="page-body">
      <section v-if="!store.canManageThresholds.value" class="threshold-locked slide-up stagger-1">
        <h1>Threshold settings are managed by your dealer administrator.</h1>
        <p>
          {{ store.currentAccount.value.organizationName }} can use the current dealer rule profile for detect,
          but cannot edit after-sales thresholds.
        </p>
      </section>
      <template v-else>
      <div class="thresholds-hero slide-up stagger-1">
        <h2>After-sales Rule Settings</h2>
        <p>
          Configure the thresholds used by self-service detection rules.
        </p>
        <div class="unit-selector" aria-label="Blood glucose unit">
          <span>Blood glucose unit</span>
          <div class="unit-segmented" role="group" aria-label="Blood glucose unit">
            <button
              class="unit-segment"
              :class="{ 'unit-segment--active': glucoseUnit === 'mmol/L' }"
              type="button"
              @click="updateGlucoseUnitPreference('mmol/L')"
            >
              mmol/L
            </button>
            <button
              class="unit-segment"
              :class="{ 'unit-segment--active': glucoseUnit === 'mg/dL' }"
              type="button"
              @click="updateGlucoseUnitPreference('mg/dL')"
            >
              mg/dL
            </button>
          </div>
        </div>
        <div class="threshold-scopes">
          <span class="badge badge-amber">Data accuracy</span>
          <span class="badge badge-blue">Sensor Malfunction</span>
          <span class="badge badge-purple">Sensor Falling Off</span>
          <span class="badge badge-teal">Application Failure</span>
        </div>
      </div>

      <div class="thresholds-header slide-up stagger-2">
        <div>
          <h1 style="font-size:1.15rem">Configurable fields</h1>
          <p class="threshold-subtitle">
            Only fields that can be configured are shown.
          </p>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <button class="btn btn-secondary btn-history" type="button" @click="showHistoryDrawer = true">Version History</button>
          <button class="btn btn-secondary btn-reset" type="button" @click="reset">Reset to Defaults</button>
          <button class="btn btn-primary" type="button" :disabled="!dirty" @click="triggerSave">
            {{ dirty ? 'Save Changes' : 'Saved' }}
          </button>
        </div>
      </div>

      <div
        v-for="(group, idx) in groups"
        :key="group.key"
        class="threshold-group slide-up"
        :class="`stagger-${Math.min(idx + 3, 6)}`"
      >
        <div class="threshold-group-header">
          <div class="threshold-group-title">
            <span class="threshold-group-scope" :class="`threshold-group-scope--${group.tone}`">
              {{ group.scope }}
            </span>
            <h3 :class="`threshold-group-heading--${group.tone}`">{{ group.title }}</h3>
          </div>
        </div>
        <p class="threshold-subtitle">{{ group.subtitle }}</p>
        <div class="threshold-items threshold-items--compact">
          <div v-for="field in group.fields" :key="field.key" class="threshold-item">
            <label :for="`threshold-${field.key}`">{{ field.label }}</label>
            <input
              :id="`threshold-${field.key}`"
              v-model.number="form[field.key]"
              class="form-input"
              :class="{ 'is-invalid': errors[field.key] }"
              type="number"
              :step="field.step"
              :min="field.min"
              :max="field.max"
              @blur="validateField(field)"
              @input="validateField(field)"
            />
            <div class="hint">{{ field.hint }}</div>
            <div v-if="errors[field.key]" class="field-message is-error">{{ errors[field.key] }}</div>
          </div>
        </div>
      </div>

      <!-- Version History Drawer -->
      <div v-if="showHistoryDrawer" class="drawer-overlay show" @click.self="showHistoryDrawer = false">
        <aside class="drawer slide-in-right">
          <div class="drawer-header">
            <h3>Version History</h3>
            <button class="btn-close" type="button" @click="showHistoryDrawer = false">&times;</button>
          </div>
          
          <div class="drawer-body">
            <div v-if="loadingHistory" class="loading-state">
              <span class="spinner"></span> Loading history...
            </div>
            
            <div v-else-if="!historyList.length" class="empty-state">
              No version history found.
            </div>
            
            <div v-else class="history-list">
              <div
                v-for="ver in historyList"
                :key="ver.version"
                class="history-card"
                :class="{ active: ver.version === store.activeThresholdProfile.value.version }"
              >
                <div class="history-card-header">
                  <div class="version-tag-wrapper">
                    <span v-if="editingRemarkVersion !== ver.version" class="version-title-display">
                      <span class="version-tag-text">{{ ver.remark || `Version v${ver.version}` }}</span>
                      <button class="btn-edit-remark" type="button" @click="startEditingRemark(ver)" title="Edit Version Name">✏️</button>
                    </span>
                    <div v-else class="history-card-remark-edit">
                      <input
                        v-model="editingRemarkText"
                        class="form-input remark-edit-input"
                        type="text"
                        placeholder="Enter version name..."
                        @keyup.enter="saveRemarkEdit(ver.version)"
                      />
                      <div class="edit-actions">
                        <button class="btn-save-remark" type="button" @click="saveRemarkEdit(ver.version)">Save</button>
                        <button class="btn-cancel-remark" type="button" @click="editingRemarkVersion = null">Cancel</button>
                      </div>
                    </div>
                  </div>
                  <div v-if="ver.version === store.activeThresholdProfile.value.version" class="status-badge active">Active</div>
                  <div v-else class="status-badge archived">Archived</div>
                </div>
                
                <div class="history-card-meta">
                  Saved: {{ formatDate(ver.savedAt) }}
                </div>

                <!-- Restored Source Badge -->
                <div v-if="ver.restoredFrom" class="restore-source-badge">
                  Restored from {{ getRestoredFromLabel(ver.restoredFrom) }}
                </div>
                
                <div class="history-card-actions">
                  <button
                    v-if="ver.version !== store.activeThresholdProfile.value.version"
                    class="btn btn-primary btn-sm"
                    type="button"
                    @click="triggerRollback(ver.version)"
                  >
                    Restore
                  </button>
                  
                  <button
                    class="btn btn-secondary btn-sm"
                    type="button"
                    @click="comparingVersion = comparingVersion?.version === ver.version ? null : ver"
                  >
                    {{ comparingVersion?.version === ver.version ? 'Hide Diff' : 'Compare' }}
                  </button>

                  <button
                    v-if="ver.version !== store.activeThresholdProfile.value.version"
                    class="btn btn-danger btn-sm"
                    type="button"
                    @click="deleteVersion(ver.version)"
                  >
                    Delete
                  </button>
                </div>
                
                <!-- Diff View -->
                <div v-if="comparingVersion?.version === ver.version" class="diff-section">
                  <h4 class="diff-title">Configuration Differences</h4>
                  <div v-if="!getDiff(ver.rules).length" class="diff-no-change">
                    No differences found between this version and your unsaved form changes.
                  </div>
                  <ul v-else class="diff-list">
                    <li v-for="d in getDiff(ver.rules)" :key="d.path" class="diff-item">
                      <span class="diff-path">{{ d.path }}:</span>
                      <span class="diff-old">{{ d.from }}</span>
                      <span class="diff-arrow">&rarr;</span>
                      <span class="diff-new">{{ d.to }}</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>

      <div v-if="activeModal" class="modal-overlay threshold-modal-overlay" role="presentation" @click.self="closeModal">
        <section
          class="modal threshold-modal"
          :role="modalRole"
          aria-modal="true"
          aria-labelledby="threshold-modal-title"
          aria-describedby="threshold-modal-description"
        >
          <h2 id="threshold-modal-title">{{ modalTitle }}</h2>
          <p id="threshold-modal-description">{{ modalDescription }}</p>
          
          <div v-if="activeModal.kind === 'save-confirm' || activeModal.kind === 'rollback-confirm'" class="modal-input-group">
            <input
              v-model="saveRemark"
              class="form-input modal-remark-input"
              type="text"
              placeholder="e.g. Standard Distributor Profile"
              @keyup.enter="activeModal.kind === 'save-confirm' ? confirmSave() : confirmRollback()"
            />
          </div>

          <div class="modal-actions threshold-modal-actions">
            <template v-if="activeModal.kind === 'reset-confirm'">
              <button class="btn btn-secondary" type="button" @click="closeModal">Cancel</button>
              <button class="btn btn-primary" type="button" @click="confirmReset">Reset</button>
            </template>
            <template v-else-if="activeModal.kind === 'save-confirm'">
              <button class="btn btn-secondary" type="button" @click="closeModal">Cancel</button>
              <button class="btn btn-primary" type="button" @click="confirmSave">Save</button>
            </template>
            <template v-else-if="activeModal.kind === 'rollback-confirm'">
              <button class="btn btn-secondary" type="button" @click="closeModal">Cancel</button>
              <button class="btn btn-primary" type="button" @click="confirmRollback">Restore</button>
            </template>
            <template v-else-if="activeModal.kind === 'delete-confirm'">
              <button class="btn btn-secondary" type="button" @click="closeModal">Cancel</button>
              <button class="btn btn-danger" type="button" data-test="threshold-delete-confirm" @click="confirmDeleteVersion">Delete</button>
            </template>
            <button v-else class="btn btn-primary" type="button" @click="closeModal">Got it</button>
          </div>
        </section>
      </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.threshold-locked {
  display: grid;
  gap: var(--space-md);
  padding: 28px;
  border: 1px solid var(--border);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.84);
}

.threshold-locked h1,
.threshold-locked p {
  margin: 0;
}

.threshold-locked p {
  color: var(--text-secondary);
  line-height: 1.55;
}

.unit-selector {
  display: flex;
  align-items: center;
  gap: 12px;
  width: fit-content;
  margin-top: 14px;
  color: var(--text-secondary);
  font-size: 0.88rem;
  font-weight: 650;
}

.unit-segmented {
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(68px, 1fr));
  gap: 3px;
  padding: 3px;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78);
}

.unit-segment {
  min-height: 32px;
  border: 0;
  border-radius: 6px;
  padding: 0 11px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font: inherit;
  font-size: 0.82rem;
  font-weight: 750;
  letter-spacing: 0;
}

.unit-segment:hover {
  color: var(--text-primary);
  background: rgba(15, 23, 42, 0.045);
}

.unit-segment--active {
  color: #8a5300;
  background: rgba(255, 176, 32, 0.18);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

.threshold-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.4) !important;
  backdrop-filter: blur(8px) !important;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1100 !important;
}

.threshold-modal {
  display: grid;
  gap: 14px;
  width: min(420px, calc(100vw - 32px));
  padding: var(--card-padding);
}

.threshold-modal h2,
.threshold-modal p {
  margin: 0;
}

.threshold-modal p {
  color: var(--text-secondary);
  line-height: 1.55;
}

.threshold-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
}

.threshold-group-header {
  align-items: flex-start;
  gap: 0;
  margin-bottom: 10px;
  padding-bottom: 12px;
}

.threshold-group-title {
  display: grid;
  gap: 7px;
  min-width: 0;
}

.threshold-group-title h3 {
  margin: 0;
  line-height: 1.25;
}

.threshold-group-heading--amber {
  color: #9a5b00;
}

.threshold-group-heading--blue {
  color: #2755b8;
}

.threshold-group-heading--purple {
  color: #5b3ab8;
}

.threshold-group-heading--teal {
  color: #00725c;
}

.threshold-group-scope {
  width: fit-content;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: var(--radius-full, 999px);
  padding: 4px 9px;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1;
}

.threshold-group-scope--amber {
  background: rgba(255, 176, 32, 0.12);
  border-color: rgba(255, 176, 32, 0.22);
  color: #9a5b00;
}

.threshold-group-scope--blue {
  background: rgba(78, 140, 255, 0.1);
  border-color: rgba(78, 140, 255, 0.2);
  color: #2755b8;
}

.threshold-group-scope--purple {
  background: rgba(167, 139, 250, 0.11);
  border-color: rgba(167, 139, 250, 0.22);
  color: #5b3ab8;
}

.threshold-group-scope--teal {
  background: rgba(0, 168, 132, 0.11);
  border-color: rgba(0, 168, 132, 0.22);
  color: #00725c;
}

/* Drawer & Overlay */
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
  visibility: visible !important;
}

.drawer {
  width: min(460px, 100vw);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: -10px 0 30px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  height: 100%;
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--card-padding);
  border-bottom: 1px solid var(--border);
}

.drawer-header h3 {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 600;
}

.btn-close {
  background: none;
  border: none;
  font-size: 1.8rem;
  cursor: pointer;
  color: var(--text-secondary);
  line-height: 1;
}

.btn-close:hover {
  color: var(--text-primary);
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--card-padding);
}

/* History Cards */
.history-list {
  display: grid;
  gap: 16px;
  align-content: start;
}

.version-tag-wrapper {
  flex: 1;
  min-width: 0;
}

.version-title-display {
  display: flex;
  align-items: center;
  gap: 6px;
}

.version-tag-text {
  font-weight: 600;
  font-size: 1rem;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-card {
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 16px;
  background: white;
  transition: all 0.25s ease;
  display: grid;
  gap: var(--space-sm);
}

.history-card.active {
  border-color: var(--accent);
  background: rgba(0, 212, 170, 0.02);
  box-shadow: 0 4px 12px rgba(0, 212, 170, 0.05);
}

.history-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.version-tag {
  font-weight: 600;
  font-size: 1rem;
  color: var(--text-primary);
}

.status-badge {
  font-size: 0.75rem;
  font-weight: 500;
  padding: 3px 8px;
  border-radius: 99px;
}

.status-badge.active {
  background: rgba(0, 212, 170, 0.1);
  color: var(--accent);
}

.status-badge.archived {
  background: rgba(100, 116, 139, 0.08);
  color: var(--text-secondary);
}

.history-card-meta {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.history-card-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.btn-sm {
  padding: 6px 12px;
  font-size: var(--text-xs);
  border-radius: 8px;
}

/* Diff Section */
.diff-section {
  border-top: 1px dashed var(--border);
  padding-top: 12px;
  margin-top: 8px;
}

.diff-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.diff-no-change {
  font-size: 0.8rem;
  color: var(--text-secondary);
  font-style: italic;
}

.diff-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 6px;
}

.diff-item {
  font-size: var(--text-xs);
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.diff-path {
  color: var(--text-secondary);
}

.diff-old {
  color: #ef4444;
  text-decoration: line-through;
  background: #fee2e2;
  padding: 1px 4px;
  border-radius: 4px;
}

.diff-arrow {
  color: var(--text-secondary);
}

.diff-new {
  color: #10b981;
  background: #d1fae5;
  padding: 1px 4px;
  border-radius: 4px;
}

/* Spinner */
.spinner {
  display: inline-block;
  width: 1rem;
  height: 1rem;
  border: 2px solid rgba(0, 0, 0, 0.1);
  border-radius: 50%;
  border-top-color: var(--text-primary);
  animation: spin 1s linear infinite;
  margin-right: 6px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Animation */
.slide-in-right {
  animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes slideIn {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

/* Custom Remark Styles */
.history-card-remark {
  margin-top: 8px;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.remark-text {
  background: rgba(15, 23, 42, 0.04);
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.remark-empty {
  font-style: italic;
  opacity: 0.6;
}

.btn-edit-remark {
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px;
  font-size: 0.85rem;
  opacity: 0.5;
  transition: opacity 0.2s;
}

.btn-edit-remark:hover {
  opacity: 1;
}

.history-card-remark-edit {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.remark-edit-input {
  width: 100%;
  padding: 6px 10px !important;
  font-size: 0.85rem !important;
  border-radius: 8px !important;
}

.edit-actions {
  display: flex;
  gap: 8px;
}

.btn-save-remark,
.btn-cancel-remark {
  font-size: 0.8rem;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: #ffffff;
  cursor: pointer;
}

.btn-save-remark {
  background: rgba(0, 168, 132, 0.1);
  border-color: rgba(0, 168, 132, 0.2);
  color: var(--accent);
  font-weight: 600;
}

/* Restored Badge */
.restore-source-badge {
  display: inline-block;
  margin-top: 6px;
  font-size: 0.78rem;
  color: #d97706;
  background: #fef3c7;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
  width: fit-content;
}

/* Modal styling */
.modal-input-group {
  margin: 16px 0;
}

.modal-remark-input {
  width: 100%;
  padding: 10px 14px !important;
  border-radius: 12px !important;
}

/* Danger Button */
.btn-danger {
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.85) 0%, rgba(220, 38, 38, 0.75) 100%) !important;
  border: 1px solid rgba(255, 255, 255, 0.45) !important;
  color: white !important;
}

.btn-danger:hover {
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.95) 0%, rgba(220, 38, 38, 0.85) 100%) !important;
}

@media (max-width: 768px) {
  .threshold-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .threshold-grid {
    grid-template-columns: 1fr;
  }

  .threshold-page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-md);
  }

  .threshold-version-drawer {
    inset: 0 !important;
    border-radius: 0 !important;
    width: 100% !important;
  }
}
</style>
