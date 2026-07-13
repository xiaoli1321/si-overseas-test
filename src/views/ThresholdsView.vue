<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { completeThresholdRules } from '@/composables/thresholdProfile';
import { useDemoStore } from '@/composables/useDemoStore';
import type { ThresholdRules } from '@/types/threshold';

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
  icon: string;
  iconStyle: string;
  title: string;
  subtitle: string;
  fields: ThresholdField[];
}

const store = useDemoStore();
const activeModal = ref<ThresholdModal | null>(null);
const initialSnapshot = ref('');
const errors = reactive<Partial<Record<FieldKey, string>>>({});

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

const groups: ThresholdGroup[] = [
  {
    key: 'persistentLow',
    icon: 'L',
    iconStyle: 'background:rgba(255,176,32,0.1);color:var(--amber)',
    title: 'Data accuracy / Persistent Low',
    subtitle: 'Thresholds for sustained low glucose.',
    fields: [
      { key: 'lowBelowMmol', label: 'Minimum glucose value (mmol/L)', hint: 'Low-glucose floor for the persistent-low rule.', step: '0.1', min: 2, max: 10 },
      { key: 'lowMinHours', label: 'Duration (hours)', hint: 'Minimum duration before the condition is met.', step: '1', min: 1, max: 24, integer: true },
      { key: 'lowPeak24hMmol', label: 'Maximum glucose value (mmol/L)', hint: '24-hour peak cap for the persistent-low rule.', step: '0.1', min: 2, max: 20 },
    ],
  },
  {
    key: 'noFluctuation',
    icon: '~',
    iconStyle: 'background:rgba(78,140,255,0.1);color:var(--blue)',
    title: 'Data accuracy / No Fluctuation',
    subtitle: 'Thresholds for flat glucose traces.',
    fields: [
      { key: 'flatMinHours', label: 'Duration (hours)', hint: 'Review window for the no-fluctuation rule.', step: '1', min: 1, max: 24, integer: true },
      { key: 'flatFloorMmol', label: 'Minimum glucose value (mmol/L)', hint: 'Glucose floor for the review window.', step: '0.1', min: 1, max: 20 },
      { key: 'flatMaxSwingMmol', label: 'Fluctuation value (mmol/L)', hint: 'Maximum allowed movement inside the review window.', step: '0.1', min: 0.1, max: 10 },
    ],
  },
  {
    key: 'jumpPoints',
    icon: 'J',
    iconStyle: 'background:rgba(167,139,250,0.1);color:var(--purple)',
    title: 'Data accuracy / Jump Points',
    subtitle: 'Thresholds for adjacent glucose jumps.',
    fields: [
      { key: 'jumpDeltaMmol', label: 'Glucose jump value (mmol/L)', hint: 'A value exceeding this threshold between two consecutive readings is counted as a jump point.', step: '0.1', min: 0.1, max: 20 },
      { key: 'jumpConsecutive', label: 'Occurrence count', hint: 'The number of consecutive jump points required to meet the criteria.', step: '1', min: 1, max: 10, integer: true },
    ],
  },
  {
    key: 'deviationWithin48h',
    icon: '48',
    iconStyle: 'background:rgba(0,212,170,0.1);color:var(--accent)',
    title: 'Data accuracy / Data Deviation Within 48h',
    subtitle: 'Thresholds for comparison groups collected inside the first 48 hours.',
    fields: [
      { key: 'within48hDeviationMmol', label: 'Glucose deviation value (mmol/L)', hint: 'Deviation threshold for each comparison group.', step: '0.1', min: 0.1, max: 20 },
      { key: 'within48hPairCount', label: 'Glucose comparison group count', hint: 'Number of comparison groups required.', step: '1', min: 1, max: 10, integer: true },
      { key: 'within48hQualifiedPairCount', label: 'Qualified comparison group count', hint: 'Number of comparison groups that must meet the deviation rule.', step: '1', min: 1, max: 10, integer: true },
    ],
  },
  {
    key: 'deviationAfter48h',
    icon: 'A',
    iconStyle: 'background:rgba(0,168,132,0.1);color:var(--accent)',
    title: 'Data accuracy / Data Deviation After 48h',
    subtitle: 'Thresholds for comparison groups collected after 48 hours.',
    fields: [
      { key: 'after48hDeviationRangePct', label: 'Glucose deviation range (%)', hint: 'Allowed deviation range after the first 48 hours.', step: '1', min: 1, max: 100 },
      { key: 'after48hPairCount', label: 'Glucose comparison group count', hint: 'Number of comparison groups required after 48 hours.', step: '1', min: 1, max: 10, integer: true },
      { key: 'after48hQualifiedPairCount', label: 'Qualified comparison group count', hint: 'Number of comparison groups that must meet the deviation rule.', step: '1', min: 1, max: 10, integer: true },
      { key: 'after48hWearDays', label: 'Wear days', hint: 'Enter 0 if there is no minimum wear-days threshold.', step: '1', min: 0, max: 30, integer: true },
    ],
  },
  {
    key: 'deviceAbnormal',
    icon: 'D',
    iconStyle: 'background:rgba(78,140,255,0.1);color:var(--blue)',
    title: 'Sensor Malfunction',
    subtitle: 'Thresholds for sensor malfunction.',
    fields: [
      { key: 'abnormalWearDays', label: 'Wear days', hint: 'Enter 0 if there is no minimum wear-days threshold.', step: '1', min: 0, max: 30, integer: true },
      { key: 'temporaryAbnormalHours', label: 'Temporary abnormal duration (hours)', hint: 'The temporary abnormal state must persist longer than this value to be considered valid.', step: '1', min: 1, max: 24, integer: true },
    ],
  },
  {
    key: 'detachment',
    icon: 'F',
    iconStyle: 'background:rgba(255,176,32,0.1);color:var(--amber)',
    title: 'Sensor Falling Off',
    subtitle: 'Thresholds for detachment rules.',
    fields: [
      { key: 'detachedStatusValue', label: 'Detachment status value', hint: 'Enter 1 for detached and 0 for not detached.', step: '1', min: 0, max: 1, integer: true },
      { key: 'detachmentWearDays', label: 'Wear days', hint: 'Enter 0 if there is no minimum wear-days threshold.', step: '1', min: 0, max: 30, integer: true },
    ],
  },
  {
    key: 'applicationFailure',
    icon: 'I',
    iconStyle: 'background:rgba(167,139,250,0.1);color:var(--purple)',
    title: 'Application Failure',
    subtitle: 'Thresholds for application failure review.',
    fields: [
      { key: 'applicationPhotoCount', label: 'Device photo count', hint: 'Number of device photos required for review.', step: '1', min: 2, max: 10, integer: true },
      { key: 'applicationAfterSalesScore', label: 'After-sales score threshold', hint: 'After-sales service is recommended when the score reaches or exceeds this value.', step: '1', min: 1, max: 10, integer: true },
      { key: 'applicationManualReviewScore', label: 'Manual review score threshold', hint: 'Manual review is recommended when the score reaches or exceeds this value but remains below the after-sales threshold.', step: '1', min: 1, max: 10, integer: true },
    ],
  },
];

function profileToForm(profileRules: ThresholdRules): ThresholdForm {
  const r = completeThresholdRules(profileRules);
  return {
    lowBelowMmol: r.inaccuracy.lowPersist.belowMmol,
    lowMinHours: r.inaccuracy.lowPersist.minHours,
    lowPeak24hMmol: r.inaccuracy.lowPersist.max24hMmol,
    flatMinHours: r.inaccuracy.noFluctuation.minHours,
    flatFloorMmol: r.inaccuracy.noFluctuation.floorMmol,
    flatMaxSwingMmol: r.inaccuracy.noFluctuation.maxSwingMmol,
    jumpDeltaMmol: r.inaccuracy.jump.deltaMmol,
    jumpConsecutive: r.inaccuracy.jump.consecutive,
    within48hDeviationMmol: r.inaccuracy.deviation.within48hDeviationMmol,
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
  return {
    inaccuracy: {
      lowPersist: {
        belowMmol: form.lowBelowMmol,
        minHours: form.lowMinHours,
        max24hMmol: form.lowPeak24hMmol,
      },
      noFluctuation: {
        floorMmol: form.flatFloorMmol,
        minHours: form.flatMinHours,
        maxSwingMmol: form.flatMaxSwingMmol,
      },
      jump: {
        deltaMmol: form.jumpDeltaMmol,
        consecutive: form.jumpConsecutive,
      },
      deviation: {
        within48hDeviationMmol: form.within48hDeviationMmol,
        within48hPairCount: form.within48hPairCount,
        within48hQualifiedPairCount: form.within48hQualifiedPairCount,
        after48hDeviationRangePct: form.after48hDeviationRangePct,
        after48hPairCount: form.after48hPairCount,
        after48hQualifiedPairCount: form.after48hQualifiedPairCount,
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
      photoCount: form.applicationPhotoCount,
      afterSalesScore: form.applicationAfterSalesScore,
      manualReviewScore: form.applicationManualReviewScore,
    },
  };
}

function syncFromActiveProfile() {
  Object.assign(form, profileToForm(store.activeThresholdProfile.value.rules));
  initialSnapshot.value = JSON.stringify(form);
  Object.keys(errors).forEach(key => delete errors[key as FieldKey]);
}

watch(store.activeThresholdProfile, syncFromActiveProfile, { immediate: true });

const dirty = computed(() => JSON.stringify(form) !== initialSnapshot.value);
const modalTitle = computed(() => {
  if (!activeModal.value) return '';
  return activeModal.value.kind === 'reset-confirm'
    ? 'Reset condition settings?'
    : activeModal.value.title;
});
const modalDescription = computed(() => {
  if (!activeModal.value) return '';
  return activeModal.value.kind === 'reset-confirm'
    ? 'This will restore all values to the default profile.'
    : activeModal.value.message;
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
    errors[field.key] = `Please enter a value between ${field.min} and ${field.max}.`;
    return false;
  }
  delete errors[field.key];
  return true;
}

function validateAll() {
  const invalid: FieldKey[] = [];
  for (const group of groups) {
    for (const field of group.fields) {
      if (!validateField(field)) invalid.push(field.key);
    }
  }

  if (form.within48hQualifiedPairCount > form.within48hPairCount) {
    errors.within48hQualifiedPairCount = 'The number of qualified groups cannot exceed the number of comparison groups.';
    invalid.push('within48hQualifiedPairCount');
  }
  if (form.after48hQualifiedPairCount > form.after48hPairCount) {
    errors.after48hQualifiedPairCount = 'The number of qualified groups cannot exceed the number of comparison groups.';
    invalid.push('after48hQualifiedPairCount');
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

function save() {
  const invalid = validateAll();
  if (invalid.length) {
    focusField(invalid[0]);
    return;
  }

  store.saveThresholdProfile({ rules: formToRules() });
  activeModal.value = {
    kind: 'success',
    title: 'Settings saved',
    message: 'The updated values will be used for future detection runs.',
  };
}

function reset() {
  activeModal.value = { kind: 'reset-confirm' };
}

function confirmReset() {
  store.resetThresholdProfile();
  activeModal.value = {
    kind: 'success',
    title: 'Settings reset',
    message: 'Default values have been restored.',
  };
}

function closeModal() {
  activeModal.value = null;
}
</script>

<template>
  <div class="page active" id="page-thresholds">
    <div class="page-body">
      <section v-if="!store.canManageThresholds.value" class="threshold-locked slide-up stagger-1">
        <h1>Threshold settings are managed by your dealer administrator.</h1>
        <p>
          {{ store.currentAccount.value.organizationName }} can use the current dealer rule profile for detection,
          but cannot edit after-sales thresholds.
        </p>
      </section>
      <template v-else>
      <div class="thresholds-hero slide-up stagger-1">
        <h2>After-sales condition settings</h2>
        <p>
          Edit the values used by self-service detection rules.
        </p>
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
          <button class="btn btn-secondary" type="button" @click="reset">Reset to Defaults</button>
          <button class="btn btn-primary" type="button" :disabled="!dirty" @click="save">
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
          <div class="threshold-group-icon" :style="group.iconStyle">{{ group.icon }}</div>
          <h3>{{ group.title }}</h3>
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
          <div class="modal-actions threshold-modal-actions">
            <template v-if="activeModal.kind === 'reset-confirm'">
              <button class="btn btn-secondary" type="button" @click="closeModal">Cancel</button>
              <button class="btn btn-primary" type="button" @click="confirmReset">Reset</button>
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
  gap: 12px;
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

.threshold-modal {
  display: grid;
  gap: 14px;
  width: min(420px, calc(100vw - 32px));
  padding: 24px;
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
  gap: 10px;
}
</style>
