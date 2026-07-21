<script setup lang="ts">
import { faultCategoryLabel } from '@/composables/faultCategories';
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import DashboardCards from '@/components/records/DashboardCards.vue';
import { useDemoStore } from '@/composables/useDemoStore';
import { backendApi, type ManagedUser } from '@/api/backend';
import { formatDurationText } from '@/utils/date';
import type { DetectRecord } from '@/types/record';

const router = useRouter();
const store = useDemoStore();

// ─── Manager-only: per-account attribution & filtering ───
const managedAccounts = ref<ManagedUser[]>([]);
const accountFilter = ref<string>('all');

async function loadManagedAccounts() {
  if (!store.isManager.value || !store.backendOnline.value) return;
  try {
    managedAccounts.value = await backendApi.getUsers();
  } catch {
    managedAccounts.value = [];
  }
}

function selectedAccountLabel() {
  if (accountFilter.value === 'all') return 'All accounts';
  return managedAccounts.value.find(a => a.id === accountFilter.value)?.email ?? 'All accounts';
}

function debounce<T extends (...args: any[]) => any>(fn: T, delay = 300): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout> | null = null;
  return (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      fn(...args);
    }, delay);
  };
}

onMounted(() => {
  void store.loadRemoteBootstrap().then(() => {
    void loadManagedAccounts();
  });
  if (store.backendOnline.value) {
    void fetchPage();
  }
});

const dateFrom = ref('');
const dateTo = ref('');
const scenario = ref<'all' | DetectRecord['faultCategory']>('all');
const conclusion = ref<'all' | DetectRecord['conclusion']>('all');
const snFilter = ref('');
const openDatePicker = ref<'from' | 'to' | null>(null);
const openSelect = ref<'scenario' | 'conclusion' | 'account' | null>(null);

const page = ref(1);
const pageSize = ref(10);
const selectedRecordIds = ref<string[]>([]);
const jumpPageInput = ref('');
const calendarCursor = ref(new Date());
const monthFormatter = new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric' });
const weekdayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const scenarioOptions: Array<{ value: 'all' | DetectRecord['faultCategory']; label: string }> = [
  { value: 'all', label: 'All Scenarios' },
  { value: 'Data accuracy', label: 'Data accuracy' },
  { value: 'Sensor falling off', label: 'Sensor falling off' },
  { value: 'Sensor Abnormal', label: 'Sensor Malfunction' },
  { value: 'Application failure', label: 'Application failure' },
];
const conclusionOptions: Array<{ value: 'all' | DetectRecord['conclusion']; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'Issue Detected', label: 'Issue Detected' },
  { value: 'No Issue', label: 'No Issue' },
];

// ─── Server-driven state (online mode) ───
const serverRecords = ref<DetectRecord[]>([]);
const serverTotal = ref(0);
const loading = ref(false);

async function fetchPage() {
  if (!store.backendOnline.value) return;
  loading.value = true;
  try {
    const result = await backendApi.getRecordsPage({
      page: page.value,
      pageSize: pageSize.value,
      faultCategory: scenario.value !== 'all' ? scenario.value : undefined,
      conclusion: conclusion.value !== 'all' ? conclusion.value : undefined,
      serialNo: snFilter.value.trim() || undefined,
      dateFrom: dateFrom.value || undefined,
      dateTo: dateTo.value || undefined,
      accountId: accountFilter.value !== 'all' ? accountFilter.value : undefined,
    });
    serverRecords.value = result.items;
    serverTotal.value = result.total;
  } catch {
    serverRecords.value = [];
    serverTotal.value = 0;
  } finally {
    loading.value = false;
  }
}

// ─── Offline/demo mode: local filtering (unchanged) ───
function parseDayStart(isoDate: string) {
  const d = new Date(`${isoDate}T00:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function parseDayEnd(isoDate: string) {
  const d = new Date(`${isoDate}T23:59:59.999`);
  return Number.isNaN(d.getTime()) ? null : d;
}

const localFilteredRecords = computed(() => {
  if (store.backendOnline.value) return [];
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

// ─── Unified computed values ───
const isOnline = computed(() => store.backendOnline.value);
const totalFiltered = computed(() => isOnline.value ? serverTotal.value : localFilteredRecords.value.length);
const pageCount = computed(() => Math.max(1, Math.ceil(totalFiltered.value / pageSize.value)));

// Watch for filter/page changes
watch(pageSize, () => {
  page.value = 1;
  selectedRecordIds.value = [];
  if (isOnline.value) void fetchPage();
});

const debouncedFetchPage = debounce(() => {
  if (isOnline.value) void fetchPage();
}, 300);

watch([dateFrom, dateTo, scenario, conclusion, accountFilter], () => {
  page.value = 1;
  selectedRecordIds.value = [];
  if (isOnline.value) void fetchPage();
});

watch(snFilter, () => {
  page.value = 1;
  selectedRecordIds.value = [];
  debouncedFetchPage();
});

watch(page, () => {
  selectedRecordIds.value = [];
  if (isOnline.value) void fetchPage();
});

// Offline mode: clamp page if data shrinks
watch(totalFiltered, count => {
  if (isOnline.value) return;
  const max = Math.max(1, Math.ceil(count / pageSize.value));
  if (page.value > max) page.value = max;
});

const pageSlice = computed(() => {
  if (isOnline.value) return serverRecords.value;
  const start = (page.value - 1) * pageSize.value;
  return localFilteredRecords.value.slice(start, start + pageSize.value);
});

const hasAnyRecords = computed(() => {
  if (isOnline.value) return serverTotal.value > 0 || loading.value;
  return store.visibleRecords.value.length > 0;
});

const paginationLabel = computed(() => {
  if (!totalFiltered.value) return 'No results';
  const start = (page.value - 1) * pageSize.value + 1;
  const end = Math.min(page.value * pageSize.value, totalFiltered.value);
  return `Showing ${start}-${end} of ${totalFiltered.value} results`;
});

const visiblePages = computed(() => {
  const total = pageCount.value;
  const current = page.value;
  
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  
  if (current <= 4) {
    return [1, 2, 3, 4, 5, '...', total];
  }
  
  if (current >= total - 3) {
    return [1, '...', total - 4, total - 3, total - 2, total - 1, total];
  }
  
  return [1, '...', current - 1, current, current + 1, '...', total];
});

function jumpToPage() {
  const val = parseInt(jumpPageInput.value.trim(), 10);
  if (!isNaN(val) && val >= 1 && val <= pageCount.value) {
    page.value = val;
  }
  jumpPageInput.value = '';
}
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
  if (isOnline.value) void fetchPage();
}

function clearFilters() {
  dateFrom.value = '';
  dateTo.value = '';
  scenario.value = 'all';
  conclusion.value = 'all';
  snFilter.value = '';
  accountFilter.value = 'all';
  page.value = 1;
  if (isOnline.value) void fetchPage();
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

function toggleSelect(target: 'scenario' | 'conclusion' | 'account') {
  openDatePicker.value = null;
  openSelect.value = openSelect.value === target ? null : target;
}

function chooseAccount(value: string) {
  accountFilter.value = value;
  openSelect.value = null;
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

function getRecordSubtypeTitle(record: DetectRecord): string {
  const title = record.presentation?.title;
  if (title && title !== '/') {
    return formatDurationText(title.replace(/\*\*/g, ''));
  }
  return formatDurationText(record.faultSubtype || '');
}

function verdictAdoptionClass(record: DetectRecord) {
  const adoption = verdictAdoptionLabel(record);
  if (adoption === 'Yes') return 'badge-green';
  if (adoption === 'No') return 'badge-amber';
  return 'badge-gray';
}

function verdictRejectionReason(record: DetectRecord) {
  return verdictAdoptionLabel(record) === 'No' ? formatDurationText(record.verdictRejectionReason ?? '') : '';
}

function formatRecordReason(record: DetectRecord) {
  return formatDurationText(record.reasonSummary);
}

function openRow(record: DetectRecord) {
  store.restoreDetectRecord(record);
  router.push({
    name: 'detect-record',
    params: { sn: record.sn, recordId: record.id },
    query: { category: record.faultCategory, from: 'records' },
  });
}

const pendingDeleteRecord = ref<DetectRecord | null>(null);

function confirmDelete(record: DetectRecord) {
  pendingDeleteRecord.value = record;
}

function cancelDelete() {
  pendingDeleteRecord.value = null;
}

async function executeDelete() {
  const record = pendingDeleteRecord.value;
  if (!record) return;
  pendingDeleteRecord.value = null;
  try {
    if (store.backendOnline.value) {
      await backendApi.deleteRecord(record.id);
      await fetchPage();
      void store.refreshRemoteStats();
    } else {
      store.records.value = store.records.value.filter(r => r.id !== record.id);
    }
  } catch (err) {
    alert('Failed to delete record: ' + (err as Error).message);
  }
}

const pendingBatchDelete = ref(false);

const isAllSelected = computed(() => {
  const slice = pageSlice.value;
  if (!slice.length) return false;
  return slice.every(record => selectedRecordIds.value.includes(record.id));
});

function toggleSelectAll() {
  const slice = pageSlice.value;
  if (isAllSelected.value) {
    selectedRecordIds.value = selectedRecordIds.value.filter(id => !slice.some(r => r.id === id));
  } else {
    const idsToAdd = slice.map(r => r.id).filter(id => !selectedRecordIds.value.includes(id));
    selectedRecordIds.value.push(...idsToAdd);
  }
}

function confirmBatchDelete() {
  pendingBatchDelete.value = true;
}

function cancelBatchDelete() {
  pendingBatchDelete.value = false;
}

async function executeBatchDelete() {
  const ids = selectedRecordIds.value;
  if (!ids.length) return;
  pendingBatchDelete.value = false;
  selectedRecordIds.value = [];
  try {
    if (store.backendOnline.value) {
      await backendApi.batchDeleteRecords(ids);
      await fetchPage();
      void store.refreshRemoteStats();
    } else {
      store.records.value = store.records.value.filter(r => !ids.includes(r.id));
    }
  } catch (err) {
    alert('Failed to delete records: ' + (err as Error).message);
  }
}

function exportCsv() {
  // Online mode: download from backend with current filters
  if (store.backendOnline.value) {
    const url = backendApi.exportRecordsCsvUrl({
      faultCategory: scenario.value !== 'all' ? scenario.value : undefined,
      conclusion: conclusion.value !== 'all' ? conclusion.value : undefined,
      serialNo: snFilter.value.trim() || undefined,
      dateFrom: dateFrom.value || undefined,
      dateTo: dateTo.value || undefined,
      accountId: accountFilter.value !== 'all' ? accountFilter.value : undefined,
    });
    window.open(url, '_blank');
    return;
  }

  // Offline mode: local CSV export (unchanged)
  const rows = localFilteredRecords.value;
  const header = ['Device Identifier', 'Type', 'Scenario', 'Subtype', 'Conclusion', 'After-sales', 'Accepted', 'Reject Reason', 'Timestamp', 'Reason'];
  const lines = [
    header.join(','),
    ...rows.map(record =>
      [
        record.sn,
        record.deviceType,
        record.faultCategory,
        getRecordSubtypeTitle(record),
        record.conclusion,
        record.afterSales,
        verdictAdoptionLabel(record),
        verdictRejectionReason(record),
        record.timestamp,
        formatRecordReason(record),
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
          <h1>Detection History</h1>
          <p style="color: var(--text-secondary); font-size: var(--text-sm); margin-top: 6px; max-width: 560px">
            Immutable detection-record history: <strong>click any row</strong> to open the same verdict screen with result summary, reason card, device overview, optional supporting materials, and guidance. Filter, paginate, or export for QA.
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
              <span v-if="option.value === scenario" class="selected-checkmark" aria-hidden="true">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </span>
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
              <span v-if="option.value === conclusion" class="selected-checkmark" aria-hidden="true">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </span>
            </button>
          </div>
        </div>
        <div v-if="store.isManager.value" class="filter-group filter-popover-anchor" data-test="account-filter-group">
          <label>Account</label>
          <button class="ios-select-trigger no-click-outline" type="button" data-test="account-filter-trigger" @click="toggleSelect('account')">
            <span>{{ selectedAccountLabel() }}</span>
          </button>
          <div v-if="openSelect === 'account'" class="ios-select-panel" data-test="ios-select-panel">
            <button
              class="ios-select-option no-click-outline"
              type="button"
              :class="{ 'is-selected': accountFilter === 'all' }"
              data-test="account-option-all"
              @click="chooseAccount('all')"
            >
              <span>All accounts</span>
              <span v-if="accountFilter === 'all'" class="selected-checkmark" aria-hidden="true">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </span>
            </button>
            <button
              v-for="acct in managedAccounts"
              :key="acct.id"
              class="ios-select-option no-click-outline"
              type="button"
              :class="{ 'is-selected': acct.id === accountFilter }"
              :data-test="`account-option-${acct.id}`"
              @click="chooseAccount(acct.id)"
            >
              <span>{{ acct.email }}</span>
              <span v-if="acct.id === accountFilter" class="selected-checkmark" aria-hidden="true">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </span>
            </button>
          </div>
        </div>
        <div class="filter-group">
          <label>Device Identifier</label>
          <input v-model="snFilter" class="form-input macos-control" type="text" placeholder="Filter by Device Identifier..." lang="en-US" />
        </div>
        <button class="btn btn-primary btn-sm no-click-outline" type="button" @click="applyFilter">Filter</button>
        <button class="btn btn-secondary btn-sm no-click-outline" type="button" data-test="clear-filters" @click="clearFilters">Clear filters</button>
      </div>

      <div class="table-wrap slide-up stagger-4">
        <!-- Batch Delete Toolbar -->
        <div v-if="selectedRecordIds.length > 0" class="batch-action-bar" data-test="batch-action-bar">
          <span class="batch-action-text">Selected <strong>{{ selectedRecordIds.length }}</strong> records</span>
          <button class="btn btn-danger btn-sm" type="button" data-test="batch-delete-btn" @click="confirmBatchDelete">
            Delete Selected
          </button>
        </div>

        <table class="records-table">
          <thead>
            <tr>
              <th style="width: 44px; text-align: center;">
                <input
                  type="checkbox"
                  :checked="isAllSelected"
                  @change="toggleSelectAll"
                  aria-label="Select all records on page"
                  class="records-checkbox"
                />
              </th>
              <th>Device Identifier</th>
              <th>Type</th>
              <th>Scenario</th>
              <th>Subtype</th>
              <th>Conclusion</th>
              <th>After-sales</th>
              <th>Accepted</th>
              <th>Reject reason</th>
              <th>Timestamp</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!hasAnyRecords">
              <td colspan="11">
                <div class="empty-state" style="padding: 28px">No detection history yet. Run a detection from Device Detection to populate this log.</div>
              </td>
            </tr>
            <tr v-else-if="!pageSlice.length">
              <td colspan="11">
                <div class="empty-state" style="padding: 28px">No rows match the current filters.</div>
              </td>
            </tr>
            <tr
              v-for="record in pageSlice"
              :key="record.id"
              class="log-row-open"
              :class="{ 'is-selected-row': selectedRecordIds.includes(record.id) }"
              tabindex="0"
              role="button"
              :aria-label="`Open verdict for device ${record.sn}`"
              @click="openRow(record)"
              @keydown.enter.prevent="openRow(record)"
              @keydown.space.prevent="openRow(record)"
            >
              <td class="records-cell-wrap" style="text-align: center;" @click.stop>
                <input
                  v-model="selectedRecordIds"
                  :value="record.id"
                  type="checkbox"
                  aria-label="Select record"
                  class="records-checkbox"
                />
              </td>
              <td class="mono records-cell-wrap records-cell-sn">
                {{ record.sn }}
                <div v-if="store.isManager.value" class="record-account" :title="record.dealerName && record.dealerName !== '—' ? record.dealerName : ''">
                  {{ record.initiatorEmail }}
                </div>
              </td>
              <td class="records-cell-wrap"><span class="badge badge-teal">{{ record.deviceType }}</span></td>
              <td class="records-cell-wrap">{{ faultCategoryLabel(record.faultCategory) }}</td>
              <td class="records-cell-wrap">{{ getRecordSubtypeTitle(record) }}</td>
              <td class="records-cell-wrap">
                <span v-if="record.conclusion === 'Issue Detected'" class="badge badge-red">
                  {{ record.conclusion }}
                </span>
                <span v-else class="conclusion-no-issue">
                  {{ record.conclusion }}
                </span>
              </td>
              <td class="records-cell-wrap">
                <span class="badge" :class="record.afterSales === 'Replacement Eligible' ? 'badge-teal' : 'badge-gray'">
                  {{ record.afterSales === 'Replacement Eligible' ? 'Allowed' : 'Not allowed' }}
                </span>
              </td>
              <td class="records-cell-wrap">
                <span class="badge" :class="verdictAdoptionClass(record)">
                  {{ verdictAdoptionLabel(record) }}
                </span>
              </td>
              <td class="records-cell-wrap">{{ verdictRejectionReason(record) }}</td>
              <td class="records-cell-wrap" style="font-size:0.82rem">{{ formatTs(record.timestamp) }}</td>
              <td class="records-cell-wrap" @click.stop>
                <button
                  class="btn-delete"
                  title="Delete Record"
                  type="button"
                  @click="confirmDelete(record)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-trash-2">
                    <polyline points="3 6 5 6 21 6"></polyline>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    <line x1="10" y1="11" x2="10" y2="17"></line>
                    <line x1="14" y1="11" x2="14" y2="17"></line>
                  </svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="hasAnyRecords && totalFiltered" class="pagination">
          <span>{{ paginationLabel }}</span>
          <div class="page-controls">
            <!-- Page Size Selector -->
            <label class="page-size-control">
              <span>Per page</span>
              <select v-model.number="pageSize" class="page-size-select" aria-label="Records per page">
                <option :value="5">5</option>
                <option :value="10">10</option>
                <option :value="20">20</option>
                <option :value="50">50</option>
                <option :value="100">100</option>
              </select>
            </label>

            <!-- Page Number Buttons -->
            <div class="page-btns">
              <button class="page-btn-arrow" type="button" :disabled="page <= 1" @click="logsPage(-1)" data-test="page-prev">&lt;</button>
              
              <template v-for="(p, idx) in visiblePages" :key="idx">
                <span v-if="p === '...'" class="pagination-ellipsis">...</span>
                <button
                  v-else
                  class="page-num-btn"
                  :class="{ active: p === page }"
                  type="button"
                  :data-test="`page-num-${p}`"
                  @click="page = (p as number)"
                >
                  {{ p }}
                </button>
              </template>

              <button class="page-btn-arrow" type="button" :disabled="page >= pageCount" @click="logsPage(1)" data-test="page-next">&gt;</button>
            </div>

            <!-- Quick Jump Input -->
            <div class="page-jump">
              <span>Go to page</span>
              <input
                v-model="jumpPageInput"
                type="text"
                class="page-jump-input"
                placeholder="Page"
                data-test="page-jump-input"
                @keydown.enter="jumpToPage"
              />
              <button class="page-jump-btn" type="button" data-test="page-jump-btn" @click="jumpToPage">Go</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation Modal -->
    <div v-if="pendingDeleteRecord" class="modal-overlay delete-confirm-overlay" role="presentation" @click.self="cancelDelete" data-test="delete-confirm-modal">
      <section
        class="modal delete-confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-confirm-title"
      >
        <h2 id="delete-confirm-title">Delete record?</h2>
        <p>Are you sure you want to delete the detection record for device <strong>{{ pendingDeleteRecord.sn }}</strong>?</p>
        <div class="modal-actions delete-confirm-actions">
          <button class="btn btn-secondary btn-sm" type="button" data-test="delete-confirm-cancel" @click="cancelDelete">Cancel</button>
          <button class="btn btn-danger btn-sm" type="button" data-test="delete-confirm-ok" @click="executeDelete">Delete</button>
        </div>
      </section>
    </div>

    <!-- Batch Delete Confirmation Modal -->
    <div v-if="pendingBatchDelete" class="modal-overlay delete-confirm-overlay" role="presentation" @click.self="cancelBatchDelete" data-test="batch-delete-confirm-modal">
      <section
        class="modal delete-confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="batch-delete-confirm-title"
      >
        <h2 id="batch-delete-confirm-title">Delete selected records?</h2>
        <p>Are you sure you want to delete the <strong>{{ selectedRecordIds.length }}</strong> selected detection records?</p>
        <div class="modal-actions delete-confirm-actions">
          <button class="btn btn-secondary btn-sm" type="button" data-test="batch-delete-confirm-cancel" @click="cancelBatchDelete">Cancel</button>
          <button class="btn btn-danger btn-sm" type="button" data-test="batch-delete-confirm-ok" @click="executeBatchDelete">Delete</button>
        </div>
      </section>
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
  vertical-align: middle;
  text-align: center;
}

.records-table th {
  line-height: 1.25;
  padding: 14px 10px;
}

.records-table td {
  padding: 16px 10px;
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

.record-account {
  margin-top: 4px;
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--text-muted, #94a3b8);
  white-space: normal;
  overflow-wrap: anywhere;
}

.records-table th:nth-child(1) {
  width: 44px;
}

.records-table th:nth-child(2) {
  width: 15%;
}

.records-table th:nth-child(3) {
  width: 5%;
}

.records-table th:nth-child(4) {
  width: 12%;
}

.records-table th:nth-child(5) {
  width: 13%;
}

.records-table th:nth-child(6) {
  width: 10%;
}

.records-table th:nth-child(7) {
  width: 9%;
}

.records-table th:nth-child(8) {
  width: 9%;
}

.records-table th:nth-child(9) {
  width: 11%;
}

.records-table th:nth-child(10) {
  width: 11%;
}

.records-table th:nth-child(11) {
  width: 5%;
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
  gap: var(--space-md);
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
  gap: var(--space-md);
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

/* Tablet: filters stack */
@media (max-width: 768px) {
  .records-filters {
    flex-wrap: wrap;
  }

  .records-filters > * {
    flex: 1 1 45%;
    min-width: 0;
  }
}

/* Mobile */
@media (max-width: 480px) {
  .records-filters {
    flex-direction: column;
  }

  .records-filters > * {
    width: 100%;
  }

  .logs-table-wrap {
    margin: 0 calc(-1 * var(--page-padding));
    overflow-x: auto;
  }

  .pagination {
    flex-direction: column;
    align-items: stretch;
    gap: var(--space-sm);
  }

  .page-btns {
    justify-content: center;
  }
}

.page-controls {
  display: flex;
  align-items: center;
  gap: 24px;
}

.page-size-control {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 0.82rem;
}

.page-size-select {
  appearance: none;
  -webkit-appearance: none;
  height: 32px;
  padding: 0 28px 0 12px;
  border-radius: 8px;
  border: 1px solid rgba(15, 23, 42, 0.12);
  background: 
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%23475569' stroke-width='2'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E") no-repeat right 10px center/10px,
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.94)),
    #ffffff;
  color: var(--text-primary);
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  transition: all 0.2s ease;
}

.page-size-select:hover {
  border-color: rgba(15, 23, 42, 0.2);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}

.page-size-select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--glow);
}

.page-btns {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(15, 23, 42, 0.03);
  padding: 4px;
  border-radius: 10px;
  border: 1px solid rgba(15, 23, 42, 0.05);
}

.page-btn-arrow,
.page-num-btn {
  background: transparent;
  border: 0;
  outline: none;
  min-width: 32px;
  height: 32px;
  padding: 0 8px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}

.page-btn-arrow:hover:not(:disabled),
.page-num-btn:hover:not(:disabled) {
  background: rgba(15, 23, 42, 0.06);
  color: var(--text-primary);
}

.page-num-btn.active {
  background: var(--accent);
  color: #ffffff !important;
  font-weight: 600;
  box-shadow: 0 2px 8px var(--glow);
}

.page-btn-arrow:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.pagination-ellipsis {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  height: 32px;
  color: var(--text-muted);
  font-size: 0.88rem;
  user-select: none;
}

.page-jump {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 0.82rem;
}

.page-jump-input {
  width: 48px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid rgba(15, 23, 42, 0.12);
  background: #ffffff;
  color: var(--text-primary);
  font-size: 0.82rem;
  text-align: center;
  padding: 0;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  transition: all 0.2s ease;
  outline: none;
}

.page-jump-input:hover {
  border-color: rgba(15, 23, 42, 0.25);
}

.page-jump-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--glow);
}

.page-jump-btn {
  height: 32px;
  border-radius: 8px;
  border: 1px solid rgba(15, 23, 42, 0.12);
  background: 
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.94)),
    #ffffff;
  color: var(--text-primary);
  font-size: 0.82rem;
  font-weight: 500;
  padding: 0 12px;
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  transition: all 0.2s ease;
}

.page-jump-btn:hover {
  background: rgba(15, 23, 42, 0.03);
  border-color: rgba(15, 23, 42, 0.2);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}

.page-jump-btn:active {
  background: rgba(15, 23, 42, 0.06);
}

.selected-checkmark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #00b894;
}

.selected-checkmark svg {
  width: 18px;
  height: 18px;
}

.btn-delete {
  background: none;
  border: none;
  color: #ea4335;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  vertical-align: middle;
}

.btn-delete:hover {
  background-color: rgba(234, 67, 53, 0.1);
  color: #c5221f;
}

.delete-confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.18);
}

.delete-confirm-modal {
  width: min(420px, 100%);
  padding: 24px;
}

.delete-confirm-modal h2 {
  margin: 0 0 8px;
  color: var(--text-primary);
  font-size: 1.1rem;
}

.delete-confirm-modal p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.5;
}

.delete-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}

.batch-action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  background: rgba(15, 23, 42, 0.03);
  border-radius: 12px;
  margin-bottom: 16px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(10px);
  animation: slideDown 0.2s ease-out;
}

.batch-action-text {
  font-size: 0.9rem;
  color: var(--text-primary);
}

.records-checkbox {
  cursor: pointer;
  width: 15px;
  height: 15px;
  accent-color: var(--color-danger, #ea4335);
}

.is-selected-row {
  background-color: rgba(234, 67, 53, 0.02) !important;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
