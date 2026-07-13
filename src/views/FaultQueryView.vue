<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import DeviceCard from '@/components/detect/DeviceCard.vue';
import { faultMetaForKey } from '@/composables/faultCategories';
import { useDemoStore } from '@/composables/useDemoStore';
import type { Device } from '@/types/device';
import type { DetectRecord } from '@/types/record';

const props = defineProps<{
  categoryKey: string;
}>();

interface PendingLine {
  line: string;
  message: string;
}

interface MultiResultRow {
  sn: string;
  sessionId: string;
  status: 'processing' | 'complete';
  stepLabel: string;
  progress: number;
  record?: DetectRecord;
}

const router = useRouter();
const route = useRoute();
const store = useDemoStore();
const snInput = ref('');
const candidates = ref<Device[]>([]);
const pendingLines = ref<PendingLine[]>([]);
const selectedDevices = ref<Device[]>([]);
const resultRows = ref<MultiResultRow[]>([]);
const activeBatchId = ref('');
const timers: number[] = [];

const meta = computed(() => faultMetaForKey(props.categoryKey));
const selectedPathMatches = computed(() => (
  selectedDevices.value.filter(device => device.fault.faultCategory === meta.value.category).length
));
const otherPathMatches = computed(() => selectedDevices.value.length - selectedPathMatches.value);
const runButtonLabel = computed(() => {
  if (selectedDevices.value.length <= 1) return 'Run detection';
  return `Run detection for ${selectedDevices.value.length} devices`;
});
const batchComplete = computed(() => (
  resultRows.value.length > 0 && resultRows.value.every(row => row.status === 'complete')
));

const batchSteps = [
  'Retrieving device information',
  'Fetching glucose curve data',
  'Running batch rule checks',
  'Generating conclusion',
];

function addSelectedDevice(device: Device) {
  if (selectedDevices.value.some(item => item.sn === device.sn)) return;
  selectedDevices.value = [...selectedDevices.value, device];
}

function removeSelectedDevice(sn: string) {
  selectedDevices.value = selectedDevices.value.filter(device => device.sn !== sn);
}

function parseLines() {
  return snInput.value
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean);
}

function addCandidate(sn: string) {
  const device = candidates.value.find(item => item.sn === sn);
  if (!device) return;
  addSelectedDevice(device);
  candidates.value = candidates.value.filter(item => item.sn !== device.sn);
}

function resolveLine(line: string, index: number, autoAddUniqueFuzzy: boolean) {
  const exact = store.findExactDeviceBySn(line);
  if (exact) {
    addSelectedDevice(exact);
    return;
  }

  const matches = store.searchDeviceMatches(line);
  if (!matches.length) {
    pendingLines.value.push({ line, message: `Line ${index + 1}: ${line} was not found.` });
    return;
  }

  if (matches.length === 1 && autoAddUniqueFuzzy) {
    addSelectedDevice(matches[0]);
    return;
  }

  if (matches.length === 1) {
    candidates.value = matches;
    return;
  }

  pendingLines.value.push({ line, message: `Line ${index + 1}: ${line} matches ${matches.length} devices. Select the intended SN below.` });
  candidates.value = matches;
}

function search() {
  const lines = parseLines();
  candidates.value = [];
  pendingLines.value = [];
  if (!lines.length) return;

  const isMultiLine = lines.length > 1;
  lines.forEach((line, index) => resolveLine(line, index, isMultiLine));
  snInput.value = '';
}

function openSingleDevice(device: Device) {
  store.selectDevice(device.sn);
  router.push({
    name: 'detect',
    params: { sn: device.sn },
    query: {
      category: meta.value.category,
      from: 'fault-query',
    },
  });
}

function runSelected() {
  if (!selectedDevices.value.length) return;
  if (selectedDevices.value.length === 1) {
    openSingleDevice(selectedDevices.value[0]);
    return;
  }

  clearTimers();
  const batchId = `MULTI-${Date.now()}`;
  activeBatchId.value = batchId;
  selectedDevices.value.forEach(device => {
    store.startDetectSession(device.sn, meta.value.category, {
      source: 'multi',
      batchId,
      stepLabel: batchSteps[0],
      progress: 10,
    });
  });
  router.push({
    name: 'multi-detect',
    params: { batchId },
    query: { category: meta.value.category },
  });
}

function startProcessing() {
  for (const row of resultRows.value) {
    const timer = window.setInterval(() => advanceRow(row.sessionId), 900);
    timers.push(timer);
  }
}

function advanceRow(sessionId: string) {
  const index = resultRows.value.findIndex(row => row.sessionId === sessionId);
  const row = resultRows.value[index];
  if (!row || row.status === 'complete') return;

  const currentStepIndex = Math.max(0, batchSteps.indexOf(row.stepLabel));
  const nextStepIndex = currentStepIndex + 1;
  if (nextStepIndex >= batchSteps.length) {
    const record = store.runDetect(row.sn, meta.value.category);
    store.completeDetectSession(row.sessionId, record);
    resultRows.value[index] = {
      ...row,
      status: 'complete',
      stepLabel: 'Complete',
      progress: 100,
      record,
    };
    if (resultRows.value.every(item => item.status === 'complete')) clearTimers();
    return;
  }

  const stepLabel = batchSteps[nextStepIndex];
  const progress = Math.min(95, Math.round(((nextStepIndex + 1) / (batchSteps.length + 1)) * 100));
  store.updateDetectSession(row.sessionId, { stepLabel, progress });
  resultRows.value[index] = { ...row, stepLabel, progress };
}

function openResult(row: MultiResultRow) {
  if (!row.record) return;
  router.push({
    name: 'detect',
    params: { sn: row.sn },
    query: {
      category: meta.value.category,
      record: row.record.id,
      from: 'records',
    },
  });
}

function openRecords() {
  router.push({ name: 'records' });
}

function clearTimers() {
  while (timers.length) {
    const timer = timers.pop();
    if (timer) window.clearInterval(timer);
  }
}

function restoreBatch(batchId: string) {
  const sessions = store.sessions.value.filter(session => session.batchId === batchId);
  if (!sessions.length) return;
  activeBatchId.value = batchId;
  const devices = sessions
    .map(session => store.findExactDeviceBySn(session.sn))
    .filter((device): device is Device => !!device);
  selectedDevices.value = devices;
  resultRows.value = sessions.map(session => {
    const record = session.recordId
      ? store.records.value.find(item => item.id === session.recordId)
      : undefined;
    return {
      sn: session.sn,
      sessionId: session.id,
      status: session.status,
      stepLabel: session.stepLabel ?? (session.status === 'complete' ? 'Complete' : batchSteps[0]),
      progress: session.progress ?? (session.status === 'complete' ? 100 : 10),
      record,
    };
  });
}

watch(() => route.query.batch, value => {
  const batchId = String(value ?? '');
  if (batchId) restoreBatch(batchId);
}, { immediate: true });

onBeforeUnmount(clearTimers);
</script>

<template>
  <main class="page active" id="page-fault-query">
    <div class="page-body fault-query-page">
      <div class="fault-query-layout slide-up stagger-1">
        <aside class="fault-query-rail fault-query-shell">
          <button class="fault-query-back" type="button" @click="router.push({ name: 'chat' })">
            <span aria-hidden="true">&larr;</span> Device detection
          </button>

          <p class="fault-query-kicker">Check path</p>
          <h1 class="fault-query-rail-title">{{ meta.title }}</h1>
          <p class="fault-query-rail-copy">{{ meta.queryCopy }}</p>

          <div class="fault-query-checklist">
            <p class="fault-query-checklist-label">What this path evaluates</p>
            <ul>
              <li v-for="tag in meta.tags" :key="tag.label" :class="`fault-path-tag--${tag.kind}`">
                <span class="fault-path-tag-kind">{{ tag.kind }}</span>
                <span>{{ tag.label }}</span>
              </li>
            </ul>
          </div>

          <p class="fault-query-rail-note">
            Add one or more devices. Every selected device will be checked against this same fault type.
          </p>
        </aside>

        <section class="fault-query-main">
          <header class="fault-query-main-head">
            <div>
              <p class="fault-query-kicker">Device lookup</p>
              <h2>Add devices by serial number</h2>
            </div>
            <div v-if="selectedDevices.length" class="fault-query-stats" aria-label="Selected device summary">
              <span class="fault-query-stat">{{ selectedDevices.length }} selected</span>
              <span class="fault-query-stat fault-query-stat--accent">{{ selectedPathMatches }} on path</span>
              <span v-if="otherPathMatches" class="fault-query-stat fault-query-stat--warn">{{ otherPathMatches }} other mapping</span>
            </div>
          </header>

          <form class="fault-query-command fault-query-shell" @submit.prevent="search">
            <label class="fault-query-command-label" for="fault-sn-input">
              <span>Serial number</span>
              <span>Paste a full SN, an SN fragment, or multiple lines. Unique matches are added to the selected devices list.</span>
            </label>
            <div class="fault-query-command-row">
              <textarea
                id="fault-sn-input"
                v-model="snInput"
                class="form-input mono fault-query-sn-input"
                rows="3"
                placeholder="P2251212806JND44"
                aria-label="Fault SN lookup input"
                autocomplete="off"
                spellcheck="false"
              ></textarea>
              <button class="btn btn-primary btn-lg fault-query-submit" type="submit" :disabled="!snInput.trim()">
                Add device
              </button>
            </div>
          </form>

          <section class="fault-query-shell selected-devices-panel" data-test="selected-devices">
            <div class="selected-devices-head">
              <div>
                <p class="fault-query-kicker">Selected devices</p>
                <h3>Selected devices</h3>
              </div>
              <button
                class="btn btn-primary btn-lg"
                type="button"
                data-test="run-selected"
                :disabled="!selectedDevices.length"
                @click="runSelected"
              >
                {{ runButtonLabel }}
              </button>
            </div>

            <p v-if="!selectedDevices.length" class="selected-empty">No devices selected yet.</p>
            <div v-else class="selected-device-list">
              <article
                v-for="device in selectedDevices"
                :key="device.sn"
                class="selected-device-row"
                data-test="selected-device-row"
              >
                <div>
                  <strong class="mono">{{ device.sn }}</strong>
                  <span class="badge" :class="device.fault.faultCategory === meta.category ? 'badge-green' : 'badge-gray'">
                    {{ device.fault.faultCategory === meta.category ? 'On path' : 'Other mapping' }}
                  </span>
                </div>
                <span>{{ device.type }} · Worn {{ device.wearDays }}d {{ device.wearHours }}h</span>
                <button class="btn btn-ghost btn-sm" type="button" data-test="remove-selected-device" @click="removeSelectedDevice(device.sn)">Remove</button>
              </article>
            </div>
          </section>

          <section v-if="pendingLines.length" class="fault-query-shell fault-query-pending" data-test="pending-lines">
            <strong>Needs confirmation</strong>
            <p v-for="item in pendingLines" :key="`${item.line}-${item.message}`">{{ item.message }}</p>
          </section>

          <section v-if="resultRows.length" class="fault-query-shell multi-results-panel">
            <div class="selected-devices-head">
              <div>
                <p class="fault-query-kicker">Run status</p>
                <h3>{{ batchComplete ? 'Multi-device results complete' : 'Running selected devices' }}</h3>
              </div>
              <button class="btn btn-secondary btn-sm" type="button" :disabled="!batchComplete" @click="openRecords">Open detection records</button>
            </div>
            <div class="multi-result-list">
              <article v-for="row in resultRows" :key="row.sessionId" class="multi-result-row" data-test="multi-result-row">
                <div class="multi-result-head">
                  <strong class="mono">{{ row.sn }}</strong>
                  <span class="badge" :class="row.status === 'complete' ? 'badge-green' : 'badge-blue'">
                    {{ row.status === 'complete' ? 'Complete' : 'Processing' }}
                  </span>
                </div>
                <p>{{ row.stepLabel }} · {{ row.progress }}%</p>
                <div class="processing-progress">
                  <div class="processing-progress-bar" :style="{ width: `${row.progress}%` }"></div>
                </div>
                <button v-if="row.record" class="btn btn-primary btn-sm" type="button" @click="openResult(row)">Open result</button>
              </article>
            </div>
          </section>

          <section v-if="candidates.length" class="fault-query-results">
            <div class="fault-query-results-head">
              <h3>Matching candidates</h3>
              <p>Select the intended device to add it to <strong>{{ meta.title }}</strong>.</p>
            </div>
            <div class="fault-query-device-list">
              <DeviceCard
                v-for="device in candidates"
                :key="device.sn"
                data-test="candidate-device"
                :device="device"
                :selected-path-category="meta.category"
                @open="addCandidate"
              />
            </div>
          </section>
        </section>
      </div>
    </div>
  </main>
</template>

<style scoped>
.fault-query-page {
  width: 100%;
}

.fault-query-layout {
  display: grid;
  grid-template-columns: minmax(220px, 300px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
  width: 100%;
}

.fault-query-rail,
.fault-query-command,
.fault-query-pending,
.selected-devices-panel,
.multi-results-panel {
  border-radius: 28px;
}

.fault-query-rail {
  display: grid;
  align-content: start;
  gap: 14px;
  padding: 18px 18px 20px;
  min-width: 0;
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
  transition: color 0.2s ease;
}

.fault-query-back:hover {
  color: var(--accent);
}

.fault-query-kicker {
  margin: 0;
  color: var(--text-muted);
  font-family: 'Outfit', sans-serif;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.fault-query-rail-title {
  margin: 0;
  font-family: 'Sora', sans-serif;
  font-size: clamp(1.55rem, 2.6vw, 2.15rem);
  font-weight: 700;
  line-height: 1.08;
  letter-spacing: -0.03em;
}

.fault-query-rail-copy,
.fault-query-rail-note {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.55;
}

.fault-query-checklist {
  display: grid;
  gap: 10px;
  padding-top: 4px;
}

.fault-query-checklist-label {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.fault-query-checklist ul {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.fault-query-checklist li {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 10px;
  align-items: start;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.28);
  border: 1px solid rgba(15, 23, 42, 0.08);
  font-size: 0.84rem;
  line-height: 1.4;
}

.fault-path-tag-kind {
  display: inline-flex;
  margin-top: 1px;
  padding: 3px 7px;
  border-radius: var(--radius-full);
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.fault-path-tag--check .fault-path-tag-kind {
  background: rgba(0, 168, 132, 0.12);
  color: var(--accent);
}

.fault-path-tag--material .fault-path-tag-kind {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}

.fault-path-tag--outcome .fault-path-tag-kind {
  background: rgba(15, 23, 42, 0.08);
  color: var(--text-secondary);
}

.fault-query-main {
  display: grid;
  gap: 16px;
  align-content: start;
  min-width: 0;
}

.fault-query-main-head,
.selected-devices-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.fault-query-main-head {
  padding: 0 4px;
}

.fault-query-main-head h2,
.selected-devices-head h3 {
  margin: 6px 0 0;
  font-family: 'Sora', sans-serif;
  font-size: clamp(1.35rem, 2.4vw, 2.15rem);
  font-weight: 700;
  line-height: 1.05;
  letter-spacing: -0.03em;
}

.selected-devices-head h3 {
  font-size: 1.25rem;
}

.fault-query-stats {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.fault-query-stat {
  display: inline-flex;
  padding: 7px 11px;
  border-radius: var(--radius-full);
  background: rgba(15, 23, 42, 0.06);
  color: var(--text-secondary);
  font-size: 0.72rem;
  font-weight: 800;
}

.fault-query-stat--accent {
  background: rgba(0, 168, 132, 0.12);
  color: var(--accent);
}

.fault-query-stat--warn {
  background: rgba(246, 166, 35, 0.14);
  color: #8a5a00;
}

.fault-query-command,
.fault-query-pending,
.selected-devices-panel,
.multi-results-panel {
  display: grid;
  gap: 14px;
  padding: 22px;
}

.fault-query-command-label {
  display: grid;
  gap: 6px;
}

.fault-query-command-label span:first-child {
  color: var(--text-muted);
  font-size: 0.74rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.fault-query-command-label span:last-child,
.fault-query-results-head p,
.selected-empty,
.fault-query-pending p {
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.5;
}

.fault-query-command-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: stretch;
}

.fault-query-sn-input {
  min-height: 86px;
  padding: 16px 18px;
  font-size: 1rem;
  border-radius: 18px;
  resize: vertical;
}

.fault-query-submit {
  min-width: 132px;
}

.fault-query-results,
.selected-device-list,
.multi-result-list {
  display: grid;
  gap: 12px;
}

.fault-query-results-head h3 {
  margin: 0;
  font-family: 'Sora', sans-serif;
  font-size: 1.2rem;
  font-weight: 700;
}

.fault-query-results-head p,
.fault-query-pending p,
.selected-empty {
  margin: 0;
}

.fault-query-device-list {
  display: grid;
  gap: 10px;
}

.selected-device-row,
.multi-result-row {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.32);
}

.selected-device-row {
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) auto;
  align-items: center;
}

.selected-device-row > div,
.multi-result-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.selected-device-row > span,
.multi-result-row p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.86rem;
}

.multi-result-head {
  justify-content: space-between;
}

.multi-result-row .btn {
  justify-self: start;
}

@media (max-width: 960px) {
  .fault-query-layout {
    grid-template-columns: 1fr;
  }

  .fault-query-main-head,
  .selected-devices-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .fault-query-stats {
    justify-content: flex-start;
  }

  .fault-query-command-row,
  .selected-device-row {
    grid-template-columns: 1fr;
  }
}
</style>
