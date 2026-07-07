<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { keyForFaultCategory } from '@/composables/faultCategories';
import { useDemoStore } from '@/composables/useDemoStore';
import { formatDeviceTime, formatDurationHours, formatDurationText } from '@/utils/date';
import type { Device, FaultCategory } from '@/types/device';
import type { DetectRecord, DetectSession } from '@/types/record';

const props = defineProps<{
  batchId: string;
}>();

const route = useRoute();
const router = useRouter();
const store = useDemoStore();
const timers: number[] = [];

const batchSteps = [
  'Retrieving device information',
  'Fetching glucose curve data',
  'Running batch rule checks',
  'Generating conclusion',
];

interface Row {
  session: DetectSession;
  device?: Device;
  record?: DetectRecord;
}

function defaultStepLabel(session: Pick<DetectSession, 'status' | 'stepLabel' | 'progress'>) {
  if (session.status === 'complete') return 'Complete';
  return session.stepLabel ?? batchSteps[0];
}

function defaultProgress(session: Pick<DetectSession, 'status' | 'progress'>) {
  if (session.status === 'complete') return 100;
  return session.progress ?? 10;
}

function visualStepIndex(input: Pick<DetectSession, 'status' | 'stepLabel' | 'progress'>) {
  if (input.status === 'complete') return batchSteps.length;

  const explicitIndex = batchSteps.indexOf(input.stepLabel ?? '');
  if (explicitIndex >= 0) return explicitIndex;

  const progress = defaultProgress(input);
  if (progress >= 80) return 3;
  if (progress >= 60) return 2;
  if (progress >= 40) return 1;
  return 0;
}

const sessions = computed(() => store.sessions.value.filter(session => session.batchId === props.batchId));
const selectedCategory = computed<FaultCategory>(() => {
  const queryCategory = String(route.query.category ?? '');
  if (queryCategory) return queryCategory as FaultCategory;
  return sessions.value[0]?.faultCategory ?? 'Data accuracy';
});

// Local state for smooth visual progress steps animation
const visualSessions = ref<Array<{
  id: string;
  sn: string;
  faultCategory: string;
  status: 'processing' | 'complete';
  stepLabel: string;
  progress: number;
  recordId?: string;
}>>([]);

watch(() => props.batchId, () => {
  clearTimers();
  visualSessions.value = [];
}, { immediate: true });

watch(sessions, (newSessions) => {
  if (newSessions.length === 0) {
    visualSessions.value = [];
    return;
  }

  const hadVisualSessions = visualSessions.value.length > 0;
  visualSessions.value = newSessions.map(session => {
    const existing = visualSessions.value.find(item => item.id === session.id);
    if (!existing) {
      return {
        id: session.id,
        sn: session.sn,
        faultCategory: session.faultCategory,
        status: session.status as 'processing' | 'complete',
        stepLabel: defaultStepLabel(session),
        progress: defaultProgress(session),
        recordId: session.recordId,
      };
    }

    if (session.status === 'complete') {
      return {
        ...existing,
        status: 'complete',
        stepLabel: session.stepLabel ?? 'Complete',
        progress: 100,
        recordId: session.recordId ?? existing.recordId,
      };
    }

    const storeProgress = defaultProgress(session);
    const storeStepIndex = visualStepIndex(session);
    const visualProgress = existing.progress;
    const visualIndex = visualStepIndex(existing);
    const nextProgress = Math.max(visualProgress, storeProgress);
    const shouldAdvanceLabel = storeStepIndex > visualIndex || (storeStepIndex === visualIndex && storeProgress >= visualProgress);

    return {
      ...existing,
      sn: session.sn,
      faultCategory: session.faultCategory,
      status: 'processing',
      stepLabel: shouldAdvanceLabel ? defaultStepLabel(session) : existing.stepLabel,
      progress: nextProgress,
      recordId: session.recordId ?? existing.recordId,
    };
  });

  if (!hadVisualSessions) {
    startProcessingTimers();
  }
}, { immediate: true });

const rows = computed<Row[]>(() => visualSessions.value.map(session => ({
  session: session as any,
  device: store.findCachedDeviceBySn(session.sn),
  record: session.recordId ? store.records.value.find(record => String(record.id) === String(session.recordId)) : undefined,
})));
const completedCount = computed(() => visualSessions.value.filter(row => row.status === 'complete').length);
const eligibleCount = computed(() => rows.value.filter(row => row.record?.afterSales === 'Replacement Eligible').length);
const notEligibleCount = computed(() => rows.value.filter(row => row.record?.afterSales === 'Not Eligible').length);
const summaryCopy = computed(() => `${completedCount.value}/${rows.value.length} complete`);

function rowProgress(session: DetectSession) {
  return defaultProgress(session);
}

function rowStep(session: DetectSession) {
  return defaultStepLabel(session);
}

function formatWearTime(device?: Device): string {
  return `Worn ${formatDurationHours((device?.wearDays ?? 0) * 24 + (device?.wearHours ?? 0))}`;
}

async function advanceVisualSession(sessionId: string) {
  const session = visualSessions.value.find(item => item.id === sessionId);
  if (!session || session.status === 'complete') return;

  const currentStepIndex = visualStepIndex(session as any);
  const nextStepIndex = currentStepIndex + 1;
  if (nextStepIndex >= batchSteps.length) {
    if (store.backendOnline.value) {
      const storeSession = store.sessions.value.find(s => s.id === sessionId);
      if (storeSession && storeSession.status === 'complete' && storeSession.recordId) {
        session.status = 'complete';
        session.stepLabel = 'Complete';
        session.progress = 100;
        session.recordId = storeSession.recordId;
        clearCompletedVisualTimers();
      }
    } else {
      const record = store.runDetect(session.sn, selectedCategory.value);
      store.completeDetectSession(session.id, record);
      session.status = 'complete';
      session.stepLabel = 'Complete';
      session.progress = 100;
      session.recordId = record.id;
      clearCompletedVisualTimers();
    }
    return;
  }

  session.stepLabel = batchSteps[nextStepIndex];
  session.progress = Math.min(95, Math.round(((nextStepIndex + 1) / (batchSteps.length + 1)) * 100));
}

function startProcessingTimers() {
  for (const session of visualSessions.value) {
    if (session.status === 'complete') continue;
    const timer = window.setInterval(() => advanceVisualSession(session.id), 900);
    timers.push(timer);
  }

  if (store.backendOnline.value) {
    const pollTimer = window.setInterval(() => {
      void store.refreshBatchRemote(props.batchId).then(clearCompletedVisualTimers);
    }, 1000);
    timers.push(pollTimer);
    void store.refreshBatchRemote(props.batchId).then(clearCompletedVisualTimers);
  }
}

function clearCompletedVisualTimers() {
  if (visualSessions.value.every(session => session.status === 'complete')) {
    clearTimers();
  }
}

function clearTimers() {
  while (timers.length) {
    const timer = timers.pop();
    if (timer) window.clearInterval(timer);
  }
}

function openResult(row: Row) {
  if (!row.record) return;
  store.restoreDetectRecord(row.record);
  router.push({
    name: 'detect-record',
    params: { sn: row.session.sn, recordId: row.record.id },
    query: {
      category: selectedCategory.value,
      from: 'multi-detect',
      batch: props.batchId,
    },
  });
}

function backToQuery() {
  router.replace({
    name: 'fault-query',
    params: { categoryKey: keyForFaultCategory(selectedCategory.value) },
    query: { fromBatch: '1' },
  });
}

function openRecords() {
  router.push({ name: 'records' });
}

onBeforeUnmount(clearTimers);
</script>

<template>
  <main class="page active" id="page-multi-detect" data-test="multi-detect-page">
    <div class="page-body multi-detect-page">
      <section class="multi-hero fault-query-shell slide-up stagger-1">
        <button class="fault-query-back" type="button" @click="backToQuery">
          <span aria-hidden="true">&larr;</span> Back to selected devices
        </button>
        <div class="multi-hero-grid">
          <div>
            <p class="multi-kicker">Same fault multi-device run</p>
            <h1>{{ selectedCategory }}</h1>
            <p>All selected devices are being checked against the same fault type. Device-level rows show activation time, telemetry context, service-card status, processing progress, and final verdict.</p>
          </div>
          <div class="multi-summary" data-test="multi-summary">
            <article>
              <span>Devices</span>
              <strong>{{ rows.length }}</strong>
            </article>
            <article :class="{ 'progress-all-complete': completedCount === rows.length && rows.length > 0 }">
              <span>Progress</span>
              <strong>{{ summaryCopy }}</strong>
            </article>
            <article>
              <span>Eligible</span>
              <strong>{{ eligibleCount }}</strong>
            </article>
            <article>
              <span>Not eligible</span>
              <strong>{{ notEligibleCount }}</strong>
            </article>
          </div>
        </div>
      </section>

      <section v-if="!rows.length" class="fault-query-shell multi-empty">
        No multi-device session was found for this run.
      </section>

      <section v-else class="multi-device-list">
        <article v-for="row in rows" :key="row.session.id" class="multi-device-row fault-query-shell" :class="{ 'is-complete': row.session.status === 'complete' }" data-test="multi-device-row">
          <div class="multi-device-head">
            <div>
              <strong class="mono">{{ row.session.sn }}</strong>
              <span class="badge" :class="row.session.status === 'complete' ? 'badge-green' : 'badge-blue'">
                <svg v-if="row.session.status === 'complete'" class="badge-icon" viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                </svg>
                <svg v-else class="badge-icon spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-opacity="0.2"></circle>
                  <path d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor"></path>
                </svg>
                {{ row.session.status === 'complete' ? 'Complete' : 'Processing' }}
              </span>
              <span class="multi-device-activation">
                <span class="multi-device-activated">Activated</span>
                <span class="multi-device-activated-time">{{ formatDeviceTime(row.device?.activatedAt) }}</span>
              </span>
            </div>
            <button v-if="row.record" class="btn btn-primary btn-sm" type="button" data-test="open-multi-result" @click="openResult(row)">Open result</button>
          </div>

          <div class="multi-device-grid">
            <div class="multi-fact">
              <span>Mapped scenario</span>
              <strong>{{ row.device?.fault?.faultCategory ?? 'Unknown' }}</strong>
            </div>
            <div class="multi-fact">
              <span>Device state</span>
              <strong>{{ row.device?.status ?? 'Unknown' }}</strong>
            </div>
            <div class="multi-fact">
              <span>Wear time</span>
              <strong>{{ formatWearTime(row.device) }}</strong>
            </div>
            <div class="multi-fact">
              <span>Last upload</span>
              <strong>{{ formatDeviceTime(row.device?.lastDataAt) }}</strong>
            </div>
            <div class="multi-fact">
              <span>Expected after-sales</span>
              <strong>{{ row.device?.fault?.expectedAfterSales ?? 'Unknown' }}</strong>
            </div>
          </div>

          <div class="multi-progress">
            <div>
              <span>
                <svg v-if="row.session.status === 'complete'" class="inline-success-icon" viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                </svg>
                {{ rowStep(row.session) }}
              </span>
              <strong>{{ rowProgress(row.session) }}%</strong>
            </div>
            <div class="processing-progress">
              <div class="processing-progress-bar" :style="{ width: `${rowProgress(row.session)}%` }"></div>
            </div>
          </div>

          <div v-if="row.record" class="multi-result-detail">
            <strong>{{ row.record.conclusion }} / {{ row.record.afterSales }}</strong>
            <p>{{ formatDurationText(row.record.reasonSummary) }}</p>
          </div>
        </article>
      </section>

      <div class="multi-actions">
        <button class="btn btn-secondary" type="button" @click="backToQuery">Add more devices</button>
        <button class="btn btn-primary" type="button" :disabled="completedCount === 0" @click="openRecords">Open Detection History</button>
      </div>
    </div>
  </main>
</template>

<style scoped>
.multi-detect-page {
  display: grid;
  gap: 16px;
}

.multi-hero,
.multi-device-row,
.multi-empty {
  padding: 22px;
  border-radius: 24px;
}

.fault-query-back {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  width: max-content;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--text-xs);
  font-weight: 700;
  cursor: pointer;
}

.multi-hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 420px);
  gap: var(--space-lg);
  align-items: end;
  margin-top: 14px;
}

.multi-kicker {
  margin: 0 0 8px;
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.multi-hero h1 {
  margin: 0;
  font-family: 'Sora', sans-serif;
  font-size: clamp(1.8rem, 4vw, 3rem);
  line-height: 1.04;
}

.multi-hero p {
  max-width: 720px;
  margin: 10px 0 0;
  color: var(--text-secondary);
  line-height: 1.55;
}

.multi-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-sm);
}

.multi-summary article,
.multi-fact {
  display: grid;
  gap: 5px;
  padding: 12px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.34);
}

.multi-summary span,
.multi-fact span {
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 800;
  text-transform: uppercase;
}

.multi-summary strong {
  font-size: 1.35rem;
}

.multi-device-list {
  display: grid;
  gap: var(--space-md);
}

.multi-device-row {
  display: grid;
  gap: 14px;
}

.multi-device-head,
.multi-device-head > div,
.multi-progress > div:first-child,
.multi-actions {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.multi-device-head {
  justify-content: space-between;
  min-width: 0;
}

.multi-device-head > div {
  min-width: 0;
  flex-wrap: wrap;
}

.multi-device-activated {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 7px;
  padding: 6px 10px;
  border: 1px solid rgba(0, 168, 132, 0.18);
  border-radius: var(--radius-sm);
  background:
    linear-gradient(135deg, rgba(0, 168, 132, 0.14), rgba(0, 168, 132, 0.055));
  color: #047857;
  font-size: 0.86rem;
  font-weight: 800;
  overflow-wrap: anywhere;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.62),
    0 8px 20px rgba(0, 168, 132, 0.08);
  white-space: nowrap;
}

.multi-device-activation {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  max-width: 100%;
  flex-wrap: wrap;
}

.multi-device-activated::before {
  content: "";
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--accent);
  box-shadow: 0 0 0 3px rgba(0, 168, 132, 0.12);
}

.multi-device-activated-time {
  min-width: 0;
  overflow-wrap: anywhere;
}

.multi-device-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-sm);
}

.multi-fact strong {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 0.9rem;
}

.multi-progress {
  display: grid;
  gap: 8px;
  margin-top: 4px;
}

.multi-progress > div:first-child {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--text-secondary);
  font-size: 0.88rem;
}

.multi-progress > div:first-child span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}

.multi-progress > div:first-child strong {
  font-family: var(--font-mono, monospace);
  font-size: 0.95rem;
  font-weight: 700;
}

.is-complete .multi-progress > div:first-child span {
  color: #10b981;
}

.is-complete .multi-progress > div:first-child strong {
  color: #10b981;
}

.processing-progress {
  height: 8px;
  background: rgba(15, 23, 42, 0.05);
  border-radius: 999px;
  overflow: hidden;
  position: relative;
  border: 1px solid rgba(15, 23, 42, 0.02);
}

.processing-progress-bar {
  height: 100%;
  border-radius: 999px;
  transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  background: linear-gradient(90deg, #3b82f6 0%, #60a5fa 100%);
}

.is-complete .processing-progress-bar {
  background: linear-gradient(90deg, #10b981 0%, #34d399 100%) !important;
  box-shadow: 0 0 10px rgba(16, 185, 129, 0.2);
}

.processing-progress-bar::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.35), transparent);
  animation: progress-shimmer 1.8s infinite;
}

@keyframes progress-shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.inline-success-icon {
  width: 15px;
  height: 15px;
  color: #10b981;
  flex-shrink: 0;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  border-radius: 9999px;
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1;
  text-transform: capitalize;
  border: 1px solid transparent;
}

.badge-green {
  background: rgba(34, 197, 94, 0.15) !important;
  color: #166534 !important;
  border-color: rgba(34, 197, 94, 0.3) !important;
}

.badge-blue {
  background: rgba(59, 130, 246, 0.15) !important;
  color: #1e40af !important;
  border-color: rgba(59, 130, 246, 0.3) !important;
}

.badge-gray {
  background: rgba(148, 163, 184, 0.15) !important;
  color: #475569 !important;
  border-color: rgba(148, 163, 184, 0.3) !important;
}

.badge-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.badge-icon.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.progress-all-complete {
  background: rgba(34, 197, 94, 0.1) !important;
  border-color: rgba(34, 197, 94, 0.25) !important;
  box-shadow: 0 0 10px rgba(34, 197, 94, 0.1);
}

.progress-all-complete strong {
  color: #166534 !important;
  font-weight: 800 !important;
}

.multi-result-detail {
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.04);
}

.multi-result-detail p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  line-height: 1.5;
}

.multi-actions {
  justify-content: flex-end;
}

@media (max-width: 900px) {
  .multi-hero-grid,
  .multi-device-grid {
    grid-template-columns: 1fr;
  }

  .multi-device-head,
  .multi-actions {
    align-items: stretch;
    flex-direction: column;
  }
}

@media (max-width: 480px) {
  .bulk-status-row {
    flex-direction: column;
    gap: var(--space-sm);
    padding: var(--card-padding);
  }

  .bulk-summary {
    flex-direction: column;
    gap: var(--space-sm);
  }
}
</style>
