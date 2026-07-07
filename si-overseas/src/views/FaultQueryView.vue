<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import DeviceCard from '@/components/detect/DeviceCard.vue';
import { backendApi, trackBackendEvent } from '@/api/backend';
import { faultMetaForKey } from '@/composables/faultCategories';
import {
  APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT,
  APPLICATION_FAILURE_TOTAL_PHOTO_SLOTS,
} from '@/composables/thresholdProfile';
import { useDemoStore } from '@/composables/useDemoStore';
import { formatDeviceTime, formatDurationHours } from '@/utils/date';
import { compressImage } from '@/utils/image';
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

const deviceImages = ref<Record<string, number>>({});
const showUploadModal = ref(false);
const uploadModalSn = ref('');

function formatWearTime(device: Device): string {
  return formatDurationHours(device.wearDays * 24 + device.wearHours);
}
const deviceImageFiles = ref<Record<string, (string | null)[]>>({});
const deviceImagePreviews = ref<Record<string, (string | null)[]>>({});
const uploadError = ref('');
const fileInputRef = ref<HTMLInputElement | null>(null);
const currentUploadingIndex = ref<number | null>(null);
const imagePreviewOpen = ref(false);
const imagePreviewSrc = ref('');
const imagePreviewName = ref('');

const DATA_ACCURACY_IMAGE_SLOTS = 4;
const applicationFailureSlotLabels = [
  'Implant site photo (required)',
  'Sensor application photo (required)',
  'Additional site angle (optional)',
  'Additional packaging/applicator photo (optional)',
];

function uploadSlotLimit() {
  return meta.value.category === 'Data accuracy'
    ? DATA_ACCURACY_IMAGE_SLOTS
    : APPLICATION_FAILURE_TOTAL_PHOTO_SLOTS;
}

function requiredUploadCount() {
  if (meta.value.category === 'Application failure') return APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT;
  return 0;
}

function validateSelectedUploads() {
  const required = requiredUploadCount();
  if (!required) return true;

  const missing = selectedDevices.value.filter(device => {
    const files = deviceImageFiles.value[device.sn] ?? [];
    return files.filter(Boolean).length < required;
  });
  if (!missing.length) return true;

  const label = meta.value.category === 'Data accuracy'
    ? `${DATA_ACCURACY_IMAGE_SLOTS} CGM/BGM comparison images`
    : `${APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT} required site photos`;
  pendingLines.value = missing.map(device => ({
    line: device.sn,
    message: `${device.sn}: upload ${label} before running ${meta.value.category} detect.`,
  }));
  openUploadModal(missing[0].sn);
  return false;
}

function openUploadModal(sn: string) {
  uploadModalSn.value = sn;
  const limit = uploadSlotLimit();
  if (!deviceImageFiles.value[sn]) {
    deviceImageFiles.value[sn] = Array(limit).fill(null);
  }
  if (!deviceImagePreviews.value[sn]) {
    deviceImagePreviews.value[sn] = Array(limit).fill(null);
  }
  uploadError.value = '';
  showUploadModal.value = true;
}

function triggerFileInput(index: number) {
  const sn = uploadModalSn.value;
  if (sn && deviceImagePreviews.value[sn]?.[index]) return;
  currentUploadingIndex.value = index;
  if (fileInputRef.value) {
    fileInputRef.value.value = ''; // Reset selection
    fileInputRef.value.click();
  }
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

async function uploadFileForIndex(file: File, index: number) {
  const sn = uploadModalSn.value;
  if (!sn || index === null) return;

  const limit = uploadSlotLimit();
  if (!deviceImageFiles.value[sn]) {
    deviceImageFiles.value[sn] = Array(limit).fill(null);
  }
  if (!deviceImagePreviews.value[sn]) {
    deviceImagePreviews.value[sn] = Array(limit).fill(null);
  }

  uploadError.value = '';
  try {
    const dataUrl = await readFileAsDataUrl(file);
    deviceImagePreviews.value[sn][index] = dataUrl;
    const uploadFile = store.backendOnline.value
      ? await compressImage(file)
      : file;
    deviceImageFiles.value[sn][index] = store.backendOnline.value
      ? (await backendApi.uploadFile(uploadFile)).id
      : dataUrl;
    deviceImages.value[sn] = deviceImageFiles.value[sn].filter(Boolean).length;
  } catch (err) {
    uploadError.value = err instanceof Error ? err.message : 'Failed to upload image.';
  }
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  if (!input.files || input.files.length === 0) return;
  const file = input.files[0];
  const index = currentUploadingIndex.value;
  if (index === null) return;
  await uploadFileForIndex(file, index);
}

async function handleDrop(event: DragEvent, index: number) {
  const files = event.dataTransfer?.files;
  if (!files || files.length === 0) return;
  const file = files[0];
  if (!file.type.startsWith('image/')) {
    uploadError.value = 'Only image files are allowed.';
    return;
  }
  await uploadFileForIndex(file, index);
}

function removeSlotImage(index: number) {
  const sn = uploadModalSn.value;
  if (sn && deviceImageFiles.value[sn]) {
    deviceImageFiles.value[sn][index] = null;
    if (deviceImagePreviews.value[sn]) {
      deviceImagePreviews.value[sn][index] = null;
    }
    deviceImages.value[sn] = deviceImageFiles.value[sn].filter(Boolean).length;
  }
  closeImagePreview();
}

function closeUploadModal() {
  showUploadModal.value = false;
  uploadModalSn.value = '';
}

function openImagePreview(index: number) {
  const sn = uploadModalSn.value;
  const preview = sn ? deviceImagePreviews.value[sn]?.[index] : '';
  if (!preview) return;
  imagePreviewSrc.value = preview;
  imagePreviewName.value = sn
    ? `${sn} · ${meta.value.category === 'Data accuracy' ? `CGM/BGM image ${index + 1}` : applicationFailureSlotLabels[index]}`
    : `Uploaded image ${index + 1}`;
  imagePreviewOpen.value = true;
}

function closeImagePreview() {
  imagePreviewOpen.value = false;
  imagePreviewSrc.value = '';
  imagePreviewName.value = '';
}

function handleUploadSlotClick(index: number) {
  const sn = uploadModalSn.value;
  if (sn && deviceImagePreviews.value[sn]?.[index]) {
    openImagePreview(index);
    return;
  }
  triggerFileInput(index);
}

function goBackToPreviousPage() {
  if (route.query.fromBatch === '1' || route.query.fromDetect === '1') {
    router.replace({ name: 'chat' });
    return;
  }
  if (typeof window !== 'undefined' && window.history.state?.back) {
    router.back();
    return;
  }
  router.push({ name: 'chat' });
}

const meta = computed(() => faultMetaForKey(props.categoryKey));
const runButtonLabel = computed(() => {
  if (selectedDevices.value.length <= 1) return 'Run detect';
  return `Run detect for ${selectedDevices.value.length} devices`;
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
  delete deviceImages.value[sn];
  delete deviceImageFiles.value[sn];
  delete deviceImagePreviews.value[sn];
}

function parseLines() {
  return snInput.value
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean);
}

function normalizeLookupValue(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9]/g, '');
}

function deviceMatchesLookup(device: Device, line: string) {
  const needle = normalizeLookupValue(line);
  if (!needle) return false;
  const sn = normalizeLookupValue(device.sn);
  const type = normalizeLookupValue(device.type);
  return sn.includes(needle) || type.includes(needle);
}

function deviceExactlyMatchesLookup(device: Device, line: string) {
  const needle = normalizeLookupValue(line);
  if (!needle) return false;
  return normalizeLookupValue(device.sn) === needle || normalizeLookupValue(device.type) === needle;
}

function addCandidate(sn: string) {
  const device = candidates.value.find(item => item.sn === sn);
  if (!device) return;
  addSelectedDevice(device);
  candidates.value = candidates.value.filter(item => item.sn !== device.sn);
}

function resolveLine(line: string, index: number, autoAddUniqueFuzzy: boolean, devices: Device[]) {
  const matches = devices.filter(device => deviceMatchesLookup(device, line));
  if (!matches.length) {
    pendingLines.value.push({ line, message: `Line ${index + 1}: ${line} was not found.` });
    return;
  }

  const exact = matches.find(device => deviceExactlyMatchesLookup(device, line));
  if (exact) {
    addSelectedDevice(exact);
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

async function search() {
  const lines = parseLines();
  candidates.value = [];
  pendingLines.value = [];
  if (!lines.length) return;

  const entrySource = (route.query.entry_source as string) || 'shortcut';
  trackBackendEvent('device.query', 'fault_query', {
    entry_source: entrySource,
    fault_category: meta.value.category,
    query_type: lines.length > 1 ? 'batch' : 'single',
    query_count: lines.length,
    serial_nos: lines,
  });

  // 植入失败：设备通常未激活，接口查不到（返回为空）。直接信任用户输入的 SN / deviceName，
  // 不调用查询接口，为每个输入构造占位设备并加入选中列表，随后走图片上传流程。
  if (meta.value.category === 'Application failure') {
    lines.forEach(line => addSelectedDevice(store.buildUnactivatedDevice(line)));
    snInput.value = '';
    return;
  }

  const isMultiLine = lines.length > 1;
  const matches = await store.searchBySnLinesRemote(lines);
  lines.forEach((line, index) => resolveLine(line, index, isMultiLine, matches));
  snInput.value = '';
}

async function runSelected() {
  if (!selectedDevices.value.length) return;
  if (!validateSelectedUploads()) return;

  clearTimers();

  const deviceFiles: Record<string, string[]> = {};
  selectedDevices.value.forEach(device => {
    const files = deviceImageFiles.value[device.sn];
    if (files) {
      deviceFiles[device.sn] = files.filter((f): f is string => f !== null);
    }
  });

  if (selectedDevices.value.length === 1) {
    const sn = selectedDevices.value[0].sn;
    const files = deviceFiles[sn] || [];
    router.push({
      name: 'detect-new',
      params: { sn },
      query: {
        category: meta.value.category,
        from: 'fault-query',
        ...(files.length ? { files: files.join(',') } : {}),
      },
    });
    return;
  }

  const remoteBatch = await store.runMultiDeviceDetectRemote(
    selectedDevices.value.map(device => device.sn),
    meta.value.category,
    deviceFiles,
  );
  const batchId = remoteBatch?.batchId ?? `MULTI-${Date.now()}`;
  activeBatchId.value = batchId;
  if (!remoteBatch) selectedDevices.value.forEach(device => {
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
    const timer = window.setInterval(() => void advanceRow(row.sessionId), 900);
    timers.push(timer);
  }
}

async function advanceRow(sessionId: string) {
  const index = resultRows.value.findIndex(row => row.sessionId === sessionId);
  const row = resultRows.value[index];
  if (!row || row.status === 'complete') return;

  const currentStepIndex = Math.max(0, batchSteps.indexOf(row.stepLabel));
  const nextStepIndex = currentStepIndex + 1;
  if (nextStepIndex >= batchSteps.length) {
    const record = await store.runDetectRemote(row.sn, meta.value.category);
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
  store.restoreDetectRecord(row.record);
  router.push({
    name: 'detect-record',
    params: { sn: row.sn, recordId: row.record.id },
    query: {
      category: meta.value.category,
      from: 'multi-detect',
      ...(activeBatchId.value ? { batch: activeBatchId.value } : {}),
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
    .map(session => store.findCachedDeviceBySn(session.sn))
    .filter((device): device is Device => !!device);
  selectedDevices.value = devices;
  resultRows.value = sessions.map(session => {
    const record = session.recordId
      ? store.records.value.find(item => String(item.id) === String(session.recordId))
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
          <button class="fault-query-back" type="button" @click="goBackToPreviousPage">
            <span aria-hidden="true">&larr;</span> Device Detection
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
              <h2>Add devices by SN or device name</h2>
            </div>
            <div v-if="selectedDevices.length" class="fault-query-stats" aria-label="Selected device summary">
              <span class="fault-query-stat">{{ selectedDevices.length }} selected</span>
            </div>
          </header>

          <form class="fault-query-command fault-query-shell" @submit.prevent="search">
            <label class="fault-query-command-label" for="fault-sn-input">
              <span>SN or device name</span>
              <span>Paste a full SN, an SN fragment, a device name, or multiple lines. Unique device matches are added to the selected devices list.</span>
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
                ADD to list
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
                <div class="selected-device-main">
                  <strong class="mono">{{ device.sn }}</strong>
                  <span class="selected-device-activation">
                    <span class="selected-device-activated">Activated</span>
                    <span class="selected-device-activated-time">{{ formatDeviceTime(device.activatedAt) }}</span>
                  </span>
                </div>
                <span class="selected-device-meta">{{ device.type }} · Worn {{ formatWearTime(device) }}</span>
                
                <!-- Conditionally render simulated upload zone based on category -->
                <div v-if="meta.category === 'Data accuracy'" class="row-upload-zone" data-test="row-upload-zone">
                  <button
                    class="btn btn-sm"
                    :class="(deviceImages[device.sn] || 0) >= 4 ? 'btn-success' : ''"
                    type="button"
                    @click="openUploadModal(device.sn)"
                  >
                    <span>Upload CGM/BGM pair</span>
                    <span class="badge ml-2" :class="(deviceImages[device.sn] || 0) >= 4 ? 'badge-green' : 'badge-gray'">
                      {{ deviceImages[device.sn] || 0 }}/4
                    </span>
                  </button>
                </div>
                <div v-else-if="meta.category === 'Application failure'" class="row-upload-zone" data-test="row-upload-zone">
                  <button
                    class="btn btn-sm"
                    :class="(deviceImages[device.sn] || 0) >= APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT ? 'btn-success' : ''"
                    type="button"
                    @click="openUploadModal(device.sn)"
                  >
                    <span>Upload site photos</span>
                    <span class="badge ml-2" :class="(deviceImages[device.sn] || 0) >= APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT ? 'badge-green' : 'badge-gray'">
                      {{ deviceImages[device.sn] || 0 }}/{{ APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT }}
                    </span>
                  </button>
                </div>

                <button class="btn btn-danger btn-sm" type="button" data-test="remove-selected-device" @click="removeSelectedDevice(device.sn)">remove from the list</button>
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
              <button class="btn btn-secondary btn-sm" type="button" :disabled="!batchComplete" @click="openRecords">Open Detection History</button>
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

    <!-- Image Upload Modal -->
    <div v-if="showUploadModal" class="modal-overlay" data-test="upload-modal" @click.self="closeUploadModal">
      <div class="modal-container">
        <header class="modal-header">
          <h3>Upload visual evidence</h3>
          <button class="modal-close-btn" type="button" @click="closeUploadModal">&times;</button>
        </header>

        <main class="modal-body">
          <p style="margin-top:0; margin-bottom:16px; color:var(--text-secondary)">
            Device: <strong class="mono">{{ uploadModalSn }}</strong>
          </p>
          <p v-if="uploadError" class="form-error">{{ uploadError }}</p>

          <div v-if="meta.category === 'Data accuracy'" class="modal-guidance">
            <h4>Required CGM/BGM evidence</h4>
            <ul>
              <li>Unless specified otherwise, please wait for 48 hours and perform data comparison under fasting conditions or 2 hours postprandial.</li>
              <li>4 comparison images (2 groups of paired CGM & BGM readings) are required.</li>
              <li>Ensure the timestamps and glucose values are legible.</li>
            </ul>
          </div>
          <div v-else class="modal-guidance">
            <h4>Required Site Photos</h4>
            <ul>
              <li>Upload 2 required photos before review.</li>
              <li>2 additional photos are optional and can add more site or applicator detail.</li>
            </ul>
          </div>

          <!-- Hidden file input for real uploads -->
          <input
            ref="fileInputRef"
            type="file"
            accept="image/*"
            style="display: none"
            @change="handleFileChange"
          />

          <div class="upload-grid-container">
            <template v-if="meta.category === 'Data accuracy'">
              <button
                v-for="(label, index) in ['Group 1 CGM image', 'Group 1 BGM image', 'Group 2 CGM image', 'Group 2 BGM image']"
                :key="`modal-data-${index}`"
                class="modal-upload-zone"
                :class="{ 'is-done': !!deviceImageFiles[uploadModalSn]?.[index] }"
                type="button"
                @click="handleUploadSlotClick(index)"
                @dragover.prevent
                @drop.prevent="handleDrop($event, index)"
              >
                <div v-if="deviceImagePreviews[uploadModalSn]?.[index]" class="modal-upload-preview-container">
                  <img :src="deviceImagePreviews[uploadModalSn][index]!" class="modal-upload-preview-img" alt="Preview" />
                  <button class="remove-image-btn" type="button" aria-label="Remove image" @click.stop="removeSlotImage(index)">&times;</button>
                </div>
                <template v-else>
                  <div class="modal-upload-icon">+</div>
                  <p>{{ label }}</p>
                  <small>Click to upload</small>
                </template>
              </button>
            </template>
            <template v-else>
              <button
                v-for="(label, index) in applicationFailureSlotLabels"
                :key="`modal-app-${index}`"
                class="modal-upload-zone"
                :class="{ 'is-done': !!deviceImageFiles[uploadModalSn]?.[index] }"
                type="button"
                @click="handleUploadSlotClick(index)"
                @dragover.prevent
                @drop.prevent="handleDrop($event, index)"
              >
                <div v-if="deviceImagePreviews[uploadModalSn]?.[index]" class="modal-upload-preview-container">
                  <img :src="deviceImagePreviews[uploadModalSn][index]!" class="modal-upload-preview-img" alt="Preview" />
                  <button class="remove-image-btn" type="button" aria-label="Remove image" @click.stop="removeSlotImage(index)">&times;</button>
                </div>
                <template v-else>
                  <div class="modal-upload-icon">+</div>
                  <p>{{ label }}</p>
                  <small>Click to upload</small>
                </template>
              </button>
            </template>
          </div>

          <p style="margin: 0; font-size: var(--text-sm); color: var(--text-secondary)">
            Uploaded: <strong>{{ deviceImages[uploadModalSn] || 0 }}</strong> / {{ meta.category === 'Data accuracy' ? DATA_ACCURACY_IMAGE_SLOTS : APPLICATION_FAILURE_TOTAL_PHOTO_SLOTS }} images
          </p>
        </main>

        <footer class="modal-actions">
          <button class="btn btn-primary" type="button" @click="closeUploadModal">Done</button>
        </footer>
      </div>
    </div>

    <div v-if="imagePreviewOpen" class="image-preview-overlay" data-test="fault-image-preview-modal" @click.self="closeImagePreview">
      <section class="image-preview-modal" role="dialog" aria-modal="true" aria-labelledby="fault-image-preview-title">
        <header class="image-preview-header">
          <h3 id="fault-image-preview-title">{{ imagePreviewName }}</h3>
          <button class="modal-close-btn image-preview-close" type="button" aria-label="Close image preview" @click="closeImagePreview">&times;</button>
        </header>
        <div class="image-preview-body">
          <img :src="imagePreviewSrc" alt="Uploaded evidence full preview" />
        </div>
      </section>
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
  font-size: var(--text-xs);
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
  gap: var(--space-sm);
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
  gap: var(--space-sm);
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
  border-radius: var(--radius-sm);
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
  border-radius: var(--radius-sm);
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
  gap: var(--space-md);
  align-items: stretch;
}

.fault-query-sn-input {
  min-height: 86px;
  padding: var(--card-padding);
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
  gap: var(--space-md);
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
  gap: var(--space-sm);
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
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: start;
  column-gap: 12px;
  row-gap: 10px;
}

.selected-device-row button[data-test="remove-selected-device"] {
  grid-column: 3;
  justify-self: end;
  white-space: nowrap;
}

.row-upload-zone {
  grid-column: 2;
  min-width: 0;
  justify-self: end;
}

.row-upload-zone .btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  background-color: rgba(15, 23, 42, 0.04);
  border: 1px solid rgba(15, 23, 42, 0.1);
  color: var(--text-primary);
  transition: all 0.2s ease;
  font-weight: 500;
  white-space: nowrap;
}

.row-upload-zone .btn > span:first-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.row-upload-zone .btn:hover {
  background-color: rgba(15, 23, 42, 0.08);
}

.row-upload-zone .btn-success {
  background-color: rgba(34, 197, 94, 0.1) !important;
  border-color: rgba(34, 197, 94, 0.2) !important;
  color: #15803d !important;
}

.row-upload-zone .btn-success:hover {
  background-color: rgba(34, 197, 94, 0.15) !important;
}

.badge-green {
  background: rgba(34, 197, 94, 0.15) !important;
  color: #15803d !important;
}

.badge-gray {
  background: rgba(15, 23, 42, 0.08) !important;
  color: var(--text-secondary) !important;
}

.ml-2 {
  margin-left: 8px;
}

.selected-device-main,
.multi-result-head {
  min-width: 0;
}

.selected-device-main {
  display: grid;
  grid-column: 1 / -1;
  gap: 8px;
  align-content: center;
}

.selected-device-main .mono {
  min-width: 0;
  overflow-wrap: anywhere;
}

.multi-result-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.selected-device-activated {
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
  font-size: 0.82rem;
  font-weight: 800;
  overflow-wrap: anywhere;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.62),
    0 8px 20px rgba(0, 168, 132, 0.08);
  white-space: nowrap;
}

.selected-device-activation {
  display: inline-flex;
  align-items: center;
  justify-self: start;
  gap: 8px;
  min-width: 0;
  max-width: 100%;
  flex-wrap: wrap;
}

.selected-device-activated::before {
  content: "";
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--accent);
  box-shadow: 0 0 0 3px rgba(0, 168, 132, 0.12);
}

.selected-device-activated-time {
  min-width: 0;
  overflow-wrap: anywhere;
}

.selected-device-meta,
.multi-result-row p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.86rem;
  min-width: 0;
  overflow-wrap: anywhere;
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

  .selected-device-row button[data-test="remove-selected-device"],
  .row-upload-zone {
    grid-column: auto;
    justify-self: stretch;
  }

  .row-upload-zone .btn,
  .selected-device-row button[data-test="remove-selected-device"] {
    width: 100%;
    justify-content: center;
  }
}

/* Modal overlay styling */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(15, 23, 42, 0.4);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease-out;
}

/* Modal box */
.modal-container {
  background: var(--bg-surface, #ffffff);
  border-radius: 24px;
  width: 90%;
  max-width: 580px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(15, 23, 42, 0.08);
  overflow: hidden;
  animation: scaleUp 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

.modal-header {
  padding: var(--card-padding);
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  margin: 0;
  font-family: 'Sora', sans-serif;
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-primary);
}

.modal-close-btn {
  background: transparent;
  border: 0;
  font-size: 1.5rem;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  line-height: 1;
}

.modal-close-btn:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: var(--card-padding);
}

.modal-guidance {
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.15);
  border-radius: 16px;
  padding: 12px 16px;
  margin-bottom: 20px;
}

.modal-guidance h4 {
  margin: 0 0 6px;
  font-size: var(--text-sm);
  font-weight: 700;
  color: #b45309;
}

.modal-guidance ul {
  margin: 0;
  padding-left: 20px;
  font-size: var(--text-xs);
  color: #78350f;
}

.modal-guidance li {
  margin-bottom: 4px;
}

.upload-grid-container {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

/* Upload zone button styling matching DetectFlowView */
.modal-upload-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px 16px;
  border: 2px dashed rgba(15, 23, 42, 0.15);
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.02);
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: center;
  font-family: inherit;
  width: 100%;
}

.modal-upload-zone:hover {
  background: rgba(15, 23, 42, 0.04);
  border-color: var(--accent);
}

.modal-upload-zone.is-done {
  border-color: #22c55e;
  background: rgba(34, 197, 94, 0.03);
  padding: 8px;
  border-style: solid;
}

.modal-upload-preview-container {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 90px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: visible;
}

.modal-upload-preview-img {
  max-width: 100%;
  max-height: 90px;
  border-radius: 8px;
  object-fit: contain;
}

.remove-image-btn {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #ef4444;
  color: #ffffff;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 14px;
  font-weight: bold;
  line-height: 1;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: transform 0.2s ease, background-color 0.2s ease;
  z-index: 10;
}

.remove-image-btn:hover {
  transform: scale(1.1);
  background: #dc2626;
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

.image-preview-close {
  color: var(--text-muted);
}

.image-preview-close:hover {
  color: var(--text-primary);
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

.modal-upload-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: rgba(15, 23, 42, 0.06);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--text-secondary);
  margin-bottom: 8px;
  transition: all 0.2s ease;
}

.modal-upload-zone:hover .modal-upload-icon {
  background: rgba(15, 23, 42, 0.1);
  color: var(--accent);
}

.modal-upload-zone.is-done .modal-upload-icon {
  background: #22c55e;
  color: #ffffff;
}

.modal-upload-zone p {
  margin: 0 0 4px;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.modal-upload-zone small {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-md);
  border-top: 1px solid rgba(15, 23, 42, 0.06);
  padding: var(--card-padding);
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes scaleUp {
  from { transform: scale(0.95); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

@media (max-width: 768px) {
  .bulk-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .bulk-grid {
    grid-template-columns: 1fr;
  }

  .fault-query-search-bar {
    flex-direction: column;
    gap: var(--space-sm);
  }

  .fault-query-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-md);
  }

  .device-upload-modal {
    inset: 0 !important;
    border-radius: 0 !important;
    width: 100% !important;
  }
}
</style>
