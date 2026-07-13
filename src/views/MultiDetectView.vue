<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { keyForFaultCategory } from '@/composables/faultCategories';
import { useDemoStore } from '@/composables/useDemoStore';
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

const sessions = computed(() => store.sessions.value.filter(session => session.batchId === props.batchId));
const selectedCategory = computed<FaultCategory>(() => {
  const queryCategory = String(route.query.category ?? '');
  if (queryCategory) return queryCategory as FaultCategory;
  return sessions.value[0]?.faultCategory ?? 'Data accuracy';
});
const rows = computed<Row[]>(() => sessions.value.map(session => ({
  session,
  device: store.findExactDeviceBySn(session.sn),
  record: session.recordId ? store.records.value.find(record => record.id === session.recordId) : undefined,
})));
const completedCount = computed(() => rows.value.filter(row => row.session.status === 'complete').length);
const eligibleCount = computed(() => rows.value.filter(row => row.record?.afterSales === 'Warranty Eligible').length);
const notEligibleCount = computed(() => rows.value.filter(row => row.record?.afterSales === 'Not Eligible').length);
const summaryCopy = computed(() => `${completedCount.value}/${rows.value.length} complete`);

function rowProgress(session: DetectSession) {
  return session.progress ?? (session.status === 'complete' ? 100 : 10);
}

function rowStep(session: DetectSession) {
  return session.stepLabel ?? (session.status === 'complete' ? 'Complete' : batchSteps[0]);
}

function isOnSelectedPath(device?: Device) {
  return device?.fault.faultCategory === selectedCategory.value;
}

function advanceSession(sessionId: string) {
  const session = store.sessions.value.find(item => item.id === sessionId);
  if (!session || session.status === 'complete') return;

  const currentStepIndex = Math.max(0, batchSteps.indexOf(rowStep(session)));
  const nextStepIndex = currentStepIndex + 1;
  if (nextStepIndex >= batchSteps.length) {
    const record = store.runDetect(session.sn, selectedCategory.value);
    store.completeDetectSession(session.id, record);
    clearCompletedTimers();
    return;
  }

  const progress = Math.min(95, Math.round(((nextStepIndex + 1) / (batchSteps.length + 1)) * 100));
  store.updateDetectSession(session.id, {
    stepLabel: batchSteps[nextStepIndex],
    progress,
  });
}

function startProcessingTimers() {
  for (const session of sessions.value) {
    if (session.status === 'complete') continue;
    const timer = window.setInterval(() => advanceSession(session.id), 900);
    timers.push(timer);
  }
}

function clearCompletedTimers() {
  if (sessions.value.some(session => session.status === 'processing')) return;
  clearTimers();
}

function clearTimers() {
  while (timers.length) {
    const timer = timers.pop();
    if (timer) window.clearInterval(timer);
  }
}

function openResult(row: Row) {
  if (!row.record) return;
  router.push({
    name: 'detect',
    params: { sn: row.session.sn },
    query: {
      category: selectedCategory.value,
      record: row.record.id,
      from: 'records',
    },
  });
}

function backToQuery() {
  router.push({
    name: 'fault-query',
    params: { categoryKey: keyForFaultCategory(selectedCategory.value) },
  });
}

function openRecords() {
  router.push({ name: 'records' });
}

onMounted(startProcessingTimers);
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
            <p>All selected devices are being checked against the same fault type. Device-level rows show mapping, sensor context, service-card status, processing progress, and final verdict.</p>
          </div>
          <div class="multi-summary" data-test="multi-summary">
            <article>
              <span>Devices</span>
              <strong>{{ rows.length }}</strong>
            </article>
            <article>
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
        <article v-for="row in rows" :key="row.session.id" class="multi-device-row fault-query-shell" data-test="multi-device-row">
          <div class="multi-device-head">
            <div>
              <strong class="mono">{{ row.session.sn }}</strong>
              <span class="badge" :class="row.session.status === 'complete' ? 'badge-green' : 'badge-blue'">
                {{ row.session.status === 'complete' ? 'Complete' : 'Processing' }}
              </span>
              <span class="badge" :class="isOnSelectedPath(row.device) ? 'badge-green' : 'badge-gray'">
                {{ isOnSelectedPath(row.device) ? 'On selected path' : 'Other mapping' }}
              </span>
            </div>
            <button v-if="row.record" class="btn btn-primary btn-sm" type="button" data-test="open-multi-result" @click="openResult(row)">Open result</button>
          </div>

          <div class="multi-device-grid">
            <div class="multi-fact">
              <span>Mapped scenario</span>
              <strong>{{ row.device?.fault.faultCategory ?? 'Unknown' }}</strong>
            </div>
            <div class="multi-fact">
              <span>Device state</span>
              <strong>{{ row.device?.status ?? 'Unknown' }}</strong>
            </div>
            <div class="multi-fact">
              <span>Wear time</span>
              <strong>Worn {{ row.device?.wearDays ?? 0 }}d {{ row.device?.wearHours ?? 0 }}h</strong>
            </div>
            <div class="multi-fact">
              <span>Last upload</span>
              <strong>{{ row.device?.lastDataAt ?? 'Unknown' }}</strong>
            </div>
            <div class="multi-fact">
              <span>Expected after-sales</span>
              <strong>{{ row.device?.fault.expectedAfterSales ?? 'Unknown' }}</strong>
            </div>
          </div>

          <div class="multi-progress">
            <div>
              <span>{{ rowStep(row.session) }}</span>
              <strong>{{ rowProgress(row.session) }}%</strong>
            </div>
            <div class="processing-progress">
              <div class="processing-progress-bar" :style="{ width: `${rowProgress(row.session)}%` }"></div>
            </div>
          </div>

          <div v-if="row.record" class="multi-result-detail">
            <strong>{{ row.record.conclusion }} / {{ row.record.afterSales }}</strong>
            <p>{{ row.record.reasonSummary }}</p>
          </div>
        </article>
      </section>

      <div class="multi-actions">
        <button class="btn btn-secondary" type="button" @click="backToQuery">Add more devices</button>
        <button class="btn btn-primary" type="button" :disabled="completedCount === 0" @click="openRecords">Open detection records</button>
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
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
}

.multi-hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 420px);
  gap: 18px;
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
  gap: 10px;
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
  gap: 12px;
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
  gap: 10px;
}

.multi-device-head {
  justify-content: space-between;
}

.multi-device-head > div {
  flex-wrap: wrap;
}

.multi-device-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.multi-fact strong {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 0.9rem;
}

.multi-progress {
  display: grid;
  gap: 8px;
}

.multi-progress > div:first-child {
  justify-content: space-between;
  color: var(--text-secondary);
  font-size: 0.86rem;
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
</style>
