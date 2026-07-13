<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import DashboardCards from '@/components/records/DashboardCards.vue';
import { useDemoStore } from '@/composables/useDemoStore';
import type { DetectRecord } from '@/types/record';

const router = useRouter();
const store = useDemoStore();

const dateFrom = ref('');
const dateTo = ref('');
const scenario = ref<'all' | DetectRecord['faultCategory']>('all');
const conclusion = ref<'all' | DetectRecord['conclusion']>('all');
const snFilter = ref('');
const openDatePicker = ref<'from' | 'to' | null>(null);
const openSelect = ref<'scenario' | 'conclusion' | null>(null);

const page = ref(1);
const pageSize = 10;
const calendarCursor = ref(new Date());
const monthFormatter = new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric' });
const weekdayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const scenarioOptions: Array<{ value: 'all' | DetectRecord['faultCategory']; label: string }> = [
  { value: 'all', label: 'All Scenarios' },
  { value: 'Data accuracy', label: 'Data accuracy' },
  { value: 'Sensor falling off', label: 'Sensor falling off' },
  { value: 'Sensor Malfunction', label: 'Sensor Malfunction' },
  { value: 'Application failure', label: 'Application failure' },
];
const conclusionOptions: Array<{ value: 'all' | DetectRecord['conclusion']; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'Issue Detected', label: 'Issue Detected' },
  { value: 'No Issue', label: 'No Issue' },
];
function parseDayStart(isoDate: string) {
  const d = new Date(`${isoDate}T00:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function parseDayEnd(isoDate: string) {
  const d = new Date(`${isoDate}T23:59:59.999`);
  return Number.isNaN(d.getTime()) ? null : d;
}

const filteredRecords = computed(() => {
  const from = dateFrom.value ? parseDayStart(dateFrom.value) : null;
  const to = dateTo.value ? parseDayEnd(dateTo.value) : null;
  const q = snFilter.value.trim().toLowerCase();

  return store.visibleRecords.value.filter(record => {
    if (scenario.value !== 'all' && record.faultCategory !== scenario.value) return false;
    if (conclusion.value !== 'all' && record.conclusion !== conclusion.value) return false;
    if (q && !record.sn.toLowerCase().includes(q)) return false;

    const t = new Date(record.timestamp).getTime();
    if (from && t < from.getTime()) return false;
    if (to && t > to.getTime()) return false;

    return true;
  });
});

const totalFiltered = computed(() => filteredRecords.value.length);
const pageCount = computed(() => Math.max(1, Math.ceil(totalFiltered.value / pageSize)));

watch(totalFiltered, count => {
  const max = Math.max(1, Math.ceil(count / pageSize));
  if (page.value > max) page.value = max;
});

watch([dateFrom, dateTo, scenario, conclusion, snFilter], () => {
  page.value = 1;
});

const pageSlice = computed(() => {
  const start = (page.value - 1) * pageSize;
  return filteredRecords.value.slice(start, start + pageSize);
});

const paginationLabel = computed(() => {
  if (!totalFiltered.value) return 'No results';
  const start = (page.value - 1) * pageSize + 1;
  const end = Math.min(page.value * pageSize, totalFiltered.value);
  return `Showing ${start}-${end} of ${totalFiltered.value} results`;
});
const calendarMonthLabel = computed(() => monthFormatter.format(calendarCursor.value));
const calendarDays = computed(() => {
  const year = calendarCursor.value.getFullYear();
  const month = calendarCursor.value.getMonth();
  const first = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const blanks = Array.from({ length: first.getDay() }, (_, index) => ({
    key: `blank-${index}`,
    label: '',
    value: '',
    blank: true,
  }));
  const days = Array.from({ length: daysInMonth }, (_, index) => {
    const day = index + 1;
    const value = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    return {
      key: value,
      label: String(day),
      value,
      blank: false,
    };
  });
  return [...blanks, ...days];
});

function applyFilter() {
  page.value = 1;
}

function clearFilters() {
  dateFrom.value = '';
  dateTo.value = '';
  scenario.value = 'all';
  conclusion.value = 'all';
  snFilter.value = '';
  page.value = 1;
}

function selectedScenarioLabel() {
  return scenarioOptions.find(option => option.value === scenario.value)?.label ?? 'All Scenarios';
}

function selectedConclusionLabel() {
  return conclusionOptions.find(option => option.value === conclusion.value)?.label ?? 'All';
}

function openCalendar(target: 'from' | 'to') {
  openSelect.value = null;
  openDatePicker.value = openDatePicker.value === target ? null : target;
  const selected = target === 'from' ? dateFrom.value : dateTo.value;
  if (selected) {
    const parsed = parseDayStart(selected);
    if (parsed) calendarCursor.value = parsed;
  }
}

function selectDate(value: string) {
  if (openDatePicker.value === 'from') dateFrom.value = value;
  if (openDatePicker.value === 'to') dateTo.value = value;
  openDatePicker.value = null;
}

function shiftCalendarMonth(delta: number) {
  calendarCursor.value = new Date(
    calendarCursor.value.getFullYear(),
    calendarCursor.value.getMonth() + delta,
    1,
  );
}

function toggleSelect(target: 'scenario' | 'conclusion') {
  openDatePicker.value = null;
  openSelect.value = openSelect.value === target ? null : target;
}

function chooseScenario(value: 'all' | DetectRecord['faultCategory']) {
  scenario.value = value;
  openSelect.value = null;
}

function chooseConclusion(value: 'all' | DetectRecord['conclusion']) {
  conclusion.value = value;
  openSelect.value = null;
}

function logsPage(delta: number) {
  const next = page.value + delta;
  if (next < 1 || next > pageCount.value) return;
  page.value = next;
}

function formatTs(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(d);
}

function verdictAdoptionLabel(record: DetectRecord) {
  return record.verdictAdoption ?? 'Not recorded';
}

function verdictAdoptionClass(record: DetectRecord) {
  const adoption = verdictAdoptionLabel(record);
  if (adoption === 'Yes') return 'badge-green';
  if (adoption === 'No') return 'badge-amber';
  return 'badge-gray';
}

function verdictRejectionReason(record: DetectRecord) {
  return verdictAdoptionLabel(record) === 'No' ? (record.verdictRejectionReason ?? '') : '';
}

function openRow(record: DetectRecord) {
  router.push({
    name: 'detect',
    params: { sn: record.sn },
    query: { category: record.faultCategory, record: record.id, from: 'records' },
  });
}

function exportCsv() {
  const rows = filteredRecords.value;
  const header = ['Device SN', 'Type', 'Scenario', 'Subtype', 'Conclusion', 'After-sales', 'Accepted', 'Reject Reason', 'Timestamp', 'Reason'];
  const lines = [
    header.join(','),
    ...rows.map(record =>
      [
        record.sn,
        record.deviceType,
        record.faultCategory,
        record.faultSubtype,
        record.conclusion,
        record.afterSales,
        verdictAdoptionLabel(record),
        verdictRejectionReason(record),
        record.timestamp,
        record.reasonSummary,
      ]
        .map(cell => `"${String(cell).replace(/"/g, '""')}"`)
        .join(','),
    ),
  ];
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `detect-records-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <div class="page active" id="page-logs">
    <div class="page-body records-page-body" data-test="records-page-body">
      <div class="logs-header slide-up stagger-1">
        <div>
          <h1>Detection records</h1>
          <p style="color: var(--text-secondary); font-size: 0.88rem; margin-top: 6px; max-width: 560px">
            Immutable detection-record history: <strong>click any row</strong> to open the same verdict screen, including the result summary, reason cards, device overview, optional supporting materials, and guidance. Records can be filtered, paginated, or exported for QA.
          </p>
        </div>
        <button class="btn btn-primary" type="button" data-test="records-export-csv" @click="exportCsv">&#8681; Export CSV</button>
      </div>

      <div class="slide-up stagger-2">
        <DashboardCards />
      </div>

      <div class="filter-bar records-filter-bar slide-up stagger-3" lang="en-US">
        <div class="filter-group filter-popover-anchor" data-test="date-from-group">
          <label>Date From</label>
          <button
            class="english-date-trigger no-click-outline"
            type="button"
            lang="en-US"
            data-test="date-from-trigger"
            @click="openCalendar('from')"
          >
            <span>{{ dateFrom || 'Select date' }}</span>
          </button>
          <div v-if="openDatePicker === 'from'" class="english-date-panel" lang="en-US" data-test="date-picker-panel">
            <div class="english-date-head">
              <button class="date-nav-btn no-click-outline" type="button" aria-label="Previous month" @click="shiftCalendarMonth(-1)">&lt;</button>
              <strong>{{ calendarMonthLabel }}</strong>
              <button class="date-nav-btn no-click-outline" type="button" aria-label="Next month" @click="shiftCalendarMonth(1)">&gt;</button>
            </div>
            <div class="english-weekdays">
              <span v-for="weekday in weekdayLabels" :key="weekday">{{ weekday }}</span>
            </div>
            <div class="english-date-grid">
              <button
                v-for="day in calendarDays"
                :key="day.key"
                class="english-date-day no-click-outline"
                :class="{ 'is-placeholder': day.blank, 'is-selected': day.value && (day.value === dateFrom || day.value === dateTo) }"
                type="button"
                :disabled="day.blank"
                :data-test="day.value ? `date-day-${day.value}` : undefined"
                @click="!day.blank && selectDate(day.value)"
              >
                {{ day.label }}
              </button>
            </div>
          </div>
        </div>
        <div class="filter-group filter-popover-anchor" data-test="date-to-group">
          <label>Date To</label>
          <button
            class="english-date-trigger no-click-outline"
            type="button"
            lang="en-US"
            data-test="date-to-trigger"
            @click="openCalendar('to')"
          >
            <span>{{ dateTo || 'Select date' }}</span>
          </button>
          <div v-if="openDatePicker === 'to'" class="english-date-panel" lang="en-US" data-test="date-picker-panel">
            <div class="english-date-head">
              <button class="date-nav-btn no-click-outline" type="button" aria-label="Previous month" @click="shiftCalendarMonth(-1)">&lt;</button>
              <strong>{{ calendarMonthLabel }}</strong>
              <button class="date-nav-btn no-click-outline" type="button" aria-label="Next month" @click="shiftCalendarMonth(1)">&gt;</button>
            </div>
            <div class="english-weekdays">
              <span v-for="weekday in weekdayLabels" :key="weekday">{{ weekday }}</span>
            </div>
            <div class="english-date-grid">
              <button
                v-for="day in calendarDays"
                :key="day.key"
                class="english-date-day no-click-outline"
                :class="{ 'is-placeholder': day.blank, 'is-selected': day.value && (day.value === dateFrom || day.value === dateTo) }"
                type="button"
                :disabled="day.blank"
                :data-test="day.value ? `date-day-${day.value}` : undefined"
                @click="!day.blank && selectDate(day.value)"
              >
                {{ day.label }}
              </button>
            </div>
          </div>
        </div>
        <div class="filter-group filter-popover-anchor" data-test="scenario-filter-group">
          <label>Scenario</label>
          <button class="ios-select-trigger no-click-outline" type="button" data-test="scenario-filter-trigger" @click="toggleSelect('scenario')">
            <span>{{ selectedScenarioLabel() }}</span>
          </button>
          <div v-if="openSelect === 'scenario'" class="ios-select-panel" data-test="ios-select-panel">
            <button
              v-for="option in scenarioOptions"
              :key="option.value"
              class="ios-select-option no-click-outline"
              type="button"
              :class="{ 'is-selected': option.value === scenario }"
              :data-test="`scenario-option-${option.value}`"
              @click="chooseScenario(option.value)"
            >
              <span>{{ option.label }}</span>
              <span v-if="option.value === scenario" aria-hidden="true">Selected</span>
            </button>
          </div>
        </div>
        <div class="filter-group filter-popover-anchor">
          <label>Conclusion</label>
          <button class="ios-select-trigger no-click-outline" type="button" data-test="conclusion-filter-trigger" @click="toggleSelect('conclusion')">
            <span>{{ selectedConclusionLabel() }}</span>
          </button>
          <div v-if="openSelect === 'conclusion'" class="ios-select-panel" data-test="ios-select-panel">
            <button
              v-for="option in conclusionOptions"
              :key="option.value"
              class="ios-select-option no-click-outline"
              type="button"
              :class="{ 'is-selected': option.value === conclusion }"
              @click="chooseConclusion(option.value)"
            >
              <span>{{ option.label }}</span>
              <span v-if="option.value === conclusion" aria-hidden="true">Selected</span>
            </button>
          </div>
        </div>
        <div class="filter-group">
          <label>Device SN</label>
          <input v-model="snFilter" class="form-input macos-control" type="text" placeholder="Filter by SN..." lang="en-US" />
        </div>
        <button class="btn btn-primary btn-sm no-click-outline" type="button" @click="applyFilter">Filter</button>
        <button class="btn btn-secondary btn-sm no-click-outline" type="button" data-test="clear-filters" @click="clearFilters">Clear filters</button>
      </div>

      <div class="table-wrap slide-up stagger-4">
        <table class="records-table">
          <thead>
            <tr>
              <th>Device SN</th>
              <th>Type</th>
              <th>Scenario</th>
              <th>Subtype</th>
              <th>Conclusion</th>
              <th>After-sales</th>
              <th>Accepted</th>
              <th>Reject reason</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!store.visibleRecords.value.length">
              <td colspan="9">
                <div class="empty-state" style="padding: 28px">No detection records available. Please run a detection from the Device detection page to populate this log.</div>
              </td>
            </tr>
            <tr v-else-if="!pageSlice.length">
              <td colspan="9">
                <div class="empty-state" style="padding: 28px">No rows match the current filters.</div>
              </td>
            </tr>
            <tr
              v-for="record in pageSlice"
              :key="record.id"
              class="log-row-open"
              tabindex="0"
              role="button"
              :aria-label="`Open verdict for device ${record.sn}`"
              @click="openRow(record)"
              @keydown.enter.prevent="openRow(record)"
              @keydown.space.prevent="openRow(record)"
            >
              <td class="mono records-cell-wrap records-cell-sn">{{ record.sn }}</td>
              <td class="records-cell-wrap"><span class="badge badge-teal">{{ record.deviceType }}</span></td>
              <td class="records-cell-wrap">{{ record.faultCategory }}</td>
              <td class="records-cell-wrap">{{ record.faultSubtype }}</td>
              <td class="records-cell-wrap">
                <span class="badge badge-dot" :class="record.conclusion === 'Issue Detected' ? 'badge-red' : 'badge-green'">
                  {{ record.conclusion }}
                </span>
              </td>
              <td class="records-cell-wrap">
                <span class="badge" :class="record.afterSales === 'Warranty Eligible' ? 'badge-teal' : 'badge-gray'">
                  {{ record.afterSales === 'Warranty Eligible' ? 'Allowed' : 'Not allowed' }}
                </span>
              </td>
              <td class="records-cell-wrap">
                <span class="badge" :class="verdictAdoptionClass(record)">
                  {{ verdictAdoptionLabel(record) }}
                </span>
              </td>
              <td class="records-cell-wrap">{{ verdictRejectionReason(record) }}</td>
              <td class="records-cell-wrap" style="font-size:0.82rem">{{ formatTs(record.timestamp) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="store.visibleRecords.value.length && totalFiltered" class="pagination">
          <span>{{ paginationLabel }}</span>
          <div class="page-btns">
            <button class="btn btn-secondary btn-sm" type="button" :disabled="page <= 1" @click="logsPage(-1)">Previous</button>
            <button class="btn btn-secondary btn-sm" type="button" :disabled="page >= pageCount" @click="logsPage(1)">Next</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.records-filter-bar {
  position: relative;
  overflow: visible;
  z-index: 30;
  gap: 14px;
  align-items: flex-end;
}

.records-page-body {
  max-width: min(1600px, calc(100vw - 48px));
  padding-left: 24px;
  padding-right: 24px;
}

.records-table {
  width: 100%;
  table-layout: fixed;
}

.records-table th,
.records-table td {
  white-space: normal;
  vertical-align: top;
}

.records-table th {
  line-height: 1.25;
}

.records-cell-wrap {
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: normal;
  line-height: 1.38;
}

.records-cell-sn {
  white-space: nowrap;
  overflow-wrap: normal;
  word-break: keep-all;
}

.records-table th:nth-child(1) {
  width: 12%;
}

.records-table th:nth-child(2) {
  width: 7%;
}

.records-table th:nth-child(3) {
  width: 12%;
}

.records-table th:nth-child(4) {
  width: 12%;
}

.records-table th:nth-child(5) {
  width: 11%;
}

.records-table th:nth-child(6),
.records-table th:nth-child(7) {
  width: 9%;
}

.records-table th:nth-child(8) {
  width: 12%;
}

.records-table th:nth-child(9) {
  width: 16%;
}

.filter-popover-anchor {
  position: relative;
  overflow: visible;
}

.no-click-outline {
  outline: none;
  -webkit-tap-highlight-color: transparent;
}

.no-click-outline:focus:not(:focus-visible) {
  outline: none;
  box-shadow: none;
}

.no-click-outline:focus-visible {
  outline: none;
  border-color: color-mix(in srgb, var(--accent) 56%, var(--border));
  box-shadow: 0 0 0 3px var(--glow);
}

.english-date-trigger,
.ios-select-trigger,
.macos-control {
  min-height: 38px;
  min-width: 150px;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--border) 88%, transparent);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.02)),
    var(--bg-deep);
  color: var(--text-primary);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.08),
    0 1px 2px rgba(0, 0, 0, 0.08);
  cursor: pointer;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.english-date-trigger:hover,
.ios-select-trigger:hover,
.macos-control:hover {
  transform: translateY(-1px);
}

.english-date-trigger:focus,
.ios-select-trigger:focus,
.macos-control:focus {
  border-color: color-mix(in srgb, var(--accent) 56%, var(--border));
  box-shadow: 0 0 0 3px var(--glow);
}

.english-date-panel,
.ios-select-panel {
  position: absolute;
  z-index: 80;
  top: calc(100% + 10px);
  left: 0;
  width: min(340px, calc(100vw - 48px));
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 22px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--bg-card) 94%, transparent), color-mix(in srgb, var(--bg-elevated) 90%, transparent));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.26);
  backdrop-filter: blur(20px);
}

.english-date-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.date-nav-btn {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 50%;
  background: color-mix(in srgb, var(--bg-elevated) 78%, transparent);
  color: var(--text-primary);
  cursor: pointer;
}

.english-weekdays,
.english-date-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
}

.english-weekdays {
  margin-bottom: 6px;
  color: var(--text-muted);
  font-size: 0.68rem;
  text-align: center;
}

.english-date-day {
  aspect-ratio: 1;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
}

.english-date-day:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
}

.english-date-day.is-selected {
  background: var(--accent);
  color: var(--text-inverse);
  font-weight: 800;
}

.english-date-day.is-placeholder {
  cursor: default;
}

.ios-select-panel {
  left: 0;
  right: auto;
  width: 280px;
  display: grid;
  gap: 6px;
  animation: ios-select-rise 0.18s ease;
}

.ios-select-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: 0;
  border-radius: 16px;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
}

.ios-select-option:hover,
.ios-select-option.is-selected {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}

@keyframes ios-select-rise {
  from {
    opacity: 0;
    transform: translateY(6px) scale(0.98);
  }

  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.macos-select {
  appearance: none;
  -webkit-appearance: none;
  padding-right: 34px;
  background-image:
    linear-gradient(45deg, transparent 50%, var(--text-secondary) 50%),
    linear-gradient(135deg, var(--text-secondary) 50%, transparent 50%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.02));
  background-position:
    calc(100% - 16px) 50%,
    calc(100% - 11px) 50%,
    0 0;
  background-size:
    5px 5px,
    5px 5px,
    100% 100%;
  background-repeat: no-repeat;
}

.english-date-trigger,
.ios-select-trigger,
.macos-control {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.92)),
    #ffffff;
  border-color: rgba(15, 23, 42, 0.12);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.85),
    0 1px 2px rgba(15, 23, 42, 0.06);
}

.english-date-panel,
.ios-select-panel {
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.14);
}
</style>
