<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';
import { faultCategoryLabel } from '@/composables/faultCategories';
import EnglishDatePicker from '@/components/common/EnglishDatePicker.vue';
import type { FaultCategory } from '@/types/device';
import {
  backendApi,
  type DashboardOverview,
  type DashboardDetailRow,
  type DashboardFilters,
  type ManagedUser,
} from '@/api/backend';

const router = useRouter();
const store = useDemoStore();

const activeTab = ref<'overview' | 'detail'>('overview');

const dateFrom = ref('');
const dateTo = ref('');
const country = ref('');
const accountId = ref('');
const accounts = ref<ManagedUser[]>([]);

const overview = ref<DashboardOverview | null>(null);
const overviewLoading = ref(false);
const overviewError = ref('');

const detailRows = ref<DashboardDetailRow[]>([]);
const detailTotal = ref(0);
const detailPage = ref(1);
const detailPageSize = ref(20);
const detailLoading = ref(false);
const detailError = ref('');
const detailLoaded = ref(false);

function currentFilters(): DashboardFilters {
  return {
    dateFrom: dateFrom.value || undefined,
    dateTo: dateTo.value || undefined,
    country: country.value || undefined,
    accountId: accountId.value || undefined,
  };
}

async function loadOverview() {
  if (!store.backendOnline.value) {
    overviewError.value = 'The dashboard requires the backend to be online.';
    return;
  }
  overviewLoading.value = true;
  overviewError.value = '';
  try {
    overview.value = await backendApi.getDashboardOverview(currentFilters());
  } catch (err) {
    overviewError.value = (err as Error).message || 'Failed to load the overview.';
    overview.value = null;
  } finally {
    overviewLoading.value = false;
  }
}

async function loadDetail() {
  if (!store.backendOnline.value) {
    detailError.value = 'The dashboard requires the backend to be online.';
    return;
  }
  detailLoading.value = true;
  detailError.value = '';
  try {
    const data = await backendApi.getDashboardDetail(currentFilters(), detailPage.value, detailPageSize.value);
    detailRows.value = data.items;
    detailTotal.value = data.total;
    detailLoaded.value = true;
  } catch (err) {
    detailError.value = (err as Error).message || 'Failed to load the records.';
    detailRows.value = [];
    detailTotal.value = 0;
  } finally {
    detailLoading.value = false;
  }
}

function switchTab(tab: 'overview' | 'detail') {
  activeTab.value = tab;
  if (tab === 'detail' && !detailLoaded.value) void loadDetail();
}

function refresh() {
  if (activeTab.value === 'overview') void loadOverview();
  else void loadDetail();
}

function clearFilters() {
  dateFrom.value = '';
  dateTo.value = '';
  country.value = '';
  accountId.value = '';
}

const hasActiveFilters = computed(
  () => !!(dateFrom.value || dateTo.value || country.value || accountId.value),
);

// Auto-apply: any filter change reloads the active tab and invalidates the other.
watch([dateFrom, dateTo, country, accountId], () => {
  detailPage.value = 1;
  if (activeTab.value === 'overview') {
    void loadOverview();
    detailLoaded.value = false;
  } else {
    void loadDetail();
    void loadOverview(); // keep the country option list fresh
  }
});

function changeDetailPage(delta: number) {
  const next = detailPage.value + delta;
  if (next < 1 || next > detailPageCount.value) return;
  detailPage.value = next;
  void loadDetail();
}

const detailPageCount = computed(() => Math.max(1, Math.ceil(detailTotal.value / detailPageSize.value)));
const detailRangeStart = computed(() => (detailTotal.value ? (detailPage.value - 1) * detailPageSize.value + 1 : 0));
const detailRangeEnd = computed(() => Math.min(detailPage.value * detailPageSize.value, detailTotal.value));

onMounted(async () => {
  await store.loadRemoteBootstrap();
  if (!store.isManager.value) {
    router.replace({ name: 'chat' });
    return;
  }
  try {
    accounts.value = await backendApi.getUsers();
  } catch {
    accounts.value = [];
  }
  void loadOverview();
});

// ── labels & helpers ──
function scenarioLabel(value: string) {
  return faultCategoryLabel(value as FaultCategory);
}

const kpis = computed(() => {
  const c = overview.value?.core;
  return [
    { key: 'problemEntries', label: 'Device Queries', value: (c?.problemEntries ?? 0).toLocaleString(), tone: 'neutral' as const },
    { key: 'deviceDetections', label: 'Detections', value: (c?.deviceDetections ?? 0).toLocaleString(), tone: 'neutral' as const },
    { key: 'eligible', label: 'Replacement Eligible', value: (c?.eligible ?? 0).toLocaleString(), tone: 'green' as const },
    { key: 'notEligible', label: 'Not Eligible', value: (c?.notEligible ?? 0).toLocaleString(), tone: 'gray' as const },
    { key: 'underReview', label: 'Under Review', value: (c?.detecting ?? 0).toLocaleString(), tone: 'amber' as const },
    { key: 'adopted', label: 'Adopted', value: (c?.adopted ?? 0).toLocaleString(), tone: 'green' as const },
    { key: 'rejected', label: 'Rejected', value: (c?.rejected ?? 0).toLocaleString(), tone: 'red' as const },
  ];
});

const adoptionRate = computed(() => overview.value?.core.adoptionRate ?? 0);

const CONCLUSION_TONE: Record<string, string> = {
  'Issue Detected': 'tone-teal',
  'No Issue': 'tone-gray',
  'Under Review': 'tone-amber',
};
const AFTERSALES_TONE: Record<string, string> = {
  'Replacement Eligible': 'tone-green',
  'Not Eligible': 'tone-gray',
  'Under Review': 'tone-amber',
};

function afterSalesBadge(value: string) {
  if (value === 'Replacement Eligible') return 'badge-green';
  if (value === 'Not Eligible') return 'badge-gray';
  return 'badge-amber';
}
function conclusionBadge(value: string) {
  if (value === 'Issue Detected') return 'badge-teal';
  if (value === 'No Issue') return 'badge-gray';
  return 'badge-amber';
}
function adoptionBadge(value: string) {
  if (value === 'Yes') return 'badge-green';
  if (value === 'No') return 'badge-red';
  return 'badge-gray';
}

// ── daily chart ──
const dailyMax = computed(() => Math.max(1, ...(overview.value?.daily ?? []).map(d => d.deviceDetections)));
const hoveredDay = ref<DashboardOverview['daily'][number] | null>(null);
function formatDay(iso: string) {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(d);
}
</script>

<template>
  <div class="page active" id="page-dashboard">
    <div class="page-body dashboard-page-body">
      <div class="dash-header slide-up stagger-1">
        <div>
          <h1>Operations Dashboard</h1>
          <p class="dash-subtitle">
            Org-wide detection activity across every account, generated live from telemetry &amp; detection records.
            Metrics count system detections only; country is derived from each account's distributor.
          </p>
        </div>
        <button class="dash-refresh" type="button" data-test="dash-refresh" :disabled="overviewLoading || detailLoading" @click="refresh" title="Refresh">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v6h-6" /></svg>
          <span>Refresh</span>
        </button>
      </div>

      <!-- Filter bar -->
      <div class="dash-filters slide-up stagger-2">
        <div class="dash-filter">
          <span>From</span>
          <EnglishDatePicker v-model="dateFrom" placeholder="Start date" data-test="dash-date-from" />
        </div>
        <div class="dash-filter">
          <span>To</span>
          <EnglishDatePicker v-model="dateTo" placeholder="End date" data-test="dash-date-to" />
        </div>
        <label class="dash-filter">
          <span>Country</span>
          <select v-model="country" class="dash-control" data-test="dash-country">
            <option value="">All countries</option>
            <option v-for="c in overview?.countries ?? []" :key="c" :value="c">{{ c }}</option>
          </select>
        </label>
        <label class="dash-filter">
          <span>Account</span>
          <select v-model="accountId" class="dash-control" data-test="dash-account">
            <option value="">All accounts</option>
            <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.email }}</option>
          </select>
        </label>
        <button
          v-if="hasActiveFilters"
          class="dash-clear"
          type="button"
          data-test="dash-clear"
          @click="clearFilters"
        >
          Clear filters
        </button>
      </div>

      <!-- Segmented tabs -->
      <div class="dash-segment slide-up stagger-3" role="tablist">
        <button class="dash-seg-btn" :class="{ active: activeTab === 'overview' }" role="tab" type="button" data-test="dash-tab-overview" @click="switchTab('overview')">Overview</button>
        <button class="dash-seg-btn" :class="{ active: activeTab === 'detail' }" role="tab" type="button" data-test="dash-tab-detail" @click="switchTab('detail')">Records</button>
      </div>

      <!-- ═══════════ OVERVIEW ═══════════ -->
      <template v-if="activeTab === 'overview'">
        <div v-if="overviewError" class="dash-banner dash-banner--error" data-test="dashboard-error">{{ overviewError }}</div>
        <div v-else-if="overviewLoading && !overview" class="dash-skeleton">Loading overview…</div>

        <template v-else-if="overview">
          <!-- KPI cards -->
          <div class="kpi-grid slide-up stagger-4">
            <div v-for="k in kpis" :key="k.key" class="kpi-card" :class="`kpi-${k.tone}`" :data-test="`kpi-${k.key}`">
              <div class="kpi-label">{{ k.label }}</div>
              <div class="kpi-value">{{ k.value }}</div>
            </div>
            <div class="kpi-card kpi-hero" data-test="kpi-adoptionRate">
              <div class="kpi-label">Adoption Rate</div>
              <div class="kpi-value">{{ adoptionRate }}<span class="kpi-unit">%</span></div>
              <div class="kpi-hero-meter"><span :style="{ width: `${Math.min(adoptionRate, 100)}%` }"></span></div>
            </div>
          </div>

          <!-- Fault category breakdown -->
          <section class="dash-panel slide-up stagger-5">
            <div class="dash-panel-head"><h2>Fault Category Breakdown</h2></div>
            <div class="dash-table-wrap">
              <table class="dash-table">
                <thead>
                  <tr>
                    <th class="col-left">Fault Category</th>
                    <th>Queries</th>
                    <th>Detections</th>
                    <th>Eligible</th>
                    <th>Not Eligible</th>
                    <th>Under Review</th>
                    <th>Adopted</th>
                    <th>Rejected</th>
                    <th class="col-rate">Adoption Rate</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in overview.byScenario" :key="row.scenario" :data-test="`scenario-${row.scenario}`">
                    <td class="col-left"><strong>{{ scenarioLabel(row.scenario) }}</strong></td>
                    <td>{{ row.problemEntries }}</td>
                    <td>{{ row.deviceDetections }}</td>
                    <td class="num-green">{{ row.eligible }}</td>
                    <td>{{ row.notEligible }}</td>
                    <td class="num-amber">{{ row.detecting }}</td>
                    <td>{{ row.adopted }}</td>
                    <td>{{ row.rejected }}</td>
                    <td class="col-rate">
                      <div class="rate-cell">
                        <span class="rate-track"><span class="rate-fill" :style="{ width: `${Math.min(row.adoptionRate, 100)}%` }"></span></span>
                        <span class="rate-num">{{ row.adoptionRate }}%</span>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <!-- Distributions -->
          <div class="dash-two-col slide-up stagger-5">
            <section class="dash-panel">
              <div class="dash-panel-head"><h2>Detection Conclusion</h2></div>
              <div class="dist-list">
                <div v-for="row in overview.conclusionDist" :key="row.label" class="dist-row">
                  <span class="dist-label"><i class="dist-dot" :class="CONCLUSION_TONE[row.label]"></i>{{ row.label }}</span>
                  <span class="dist-track"><span class="dist-fill" :class="CONCLUSION_TONE[row.label]" :style="{ width: `${row.ratio}%` }"></span></span>
                  <span class="dist-meta">{{ row.count }} · {{ row.ratio }}%</span>
                </div>
              </div>
            </section>
            <section class="dash-panel">
              <div class="dash-panel-head"><h2>After-sales Verdict</h2></div>
              <div class="dist-list">
                <div v-for="row in overview.afterSalesDist" :key="row.label" class="dist-row">
                  <span class="dist-label"><i class="dist-dot" :class="AFTERSALES_TONE[row.label]"></i>{{ row.label }}</span>
                  <span class="dist-track"><span class="dist-fill" :class="AFTERSALES_TONE[row.label]" :style="{ width: `${row.ratio}%` }"></span></span>
                  <span class="dist-meta">{{ row.count }} · {{ row.ratio }}%</span>
                </div>
              </div>
            </section>
          </div>

          <!-- Daily activity -->
          <section class="dash-panel slide-up stagger-6">
            <div class="dash-panel-head">
              <h2>Daily Activity</h2>
              <span class="dash-panel-caption">
                <template v-if="hoveredDay">{{ formatDay(hoveredDay.date) }} — {{ hoveredDay.deviceDetections }} detections · {{ hoveredDay.problemEntries }} queries · {{ hoveredDay.eligible }} eligible</template>
                <template v-else>Detections per day · hover a column for the breakdown</template>
              </span>
            </div>
            <div v-if="!overview.daily.length" class="dash-empty">No activity in this range.</div>
            <div v-else class="chart" @mouseleave="hoveredDay = null">
              <div
                v-for="d in overview.daily"
                :key="d.date"
                class="chart-col"
                :class="{ active: hoveredDay?.date === d.date }"
                @mouseenter="hoveredDay = d"
              >
                <span class="chart-bar" :style="{ height: `${Math.max((d.deviceDetections / dailyMax) * 100, 3)}%` }"></span>
                <span class="chart-x">{{ formatDay(d.date) }}</span>
              </div>
            </div>
          </section>
        </template>
      </template>

      <!-- ═══════════ RECORDS (DETAIL) ═══════════ -->
      <template v-else>
        <div v-if="detailError" class="dash-banner dash-banner--error" data-test="dashboard-detail-error">{{ detailError }}</div>
        <section class="dash-panel slide-up stagger-4">
          <div class="dash-table-wrap">
            <table class="dash-table dash-detail-table">
              <thead>
                <tr>
                  <th class="col-left">Record Type</th>
                  <th>Date</th>
                  <th>Country</th>
                  <th class="col-left">Account</th>
                  <th class="col-left">Device SN</th>
                  <th>Type</th>
                  <th class="col-left">Fault Category</th>
                  <th>Conclusion</th>
                  <th>After-sales</th>
                  <th>Adoption</th>
                  <th class="col-left">Reject Reason</th>
                  <th>Rule Profile</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="detailLoading">
                  <td colspan="13"><div class="dash-empty">Loading records…</div></td>
                </tr>
                <tr v-else-if="!detailRows.length">
                  <td colspan="13"><div class="dash-empty">No records match the current filters.</div></td>
                </tr>
                <tr v-for="(row, idx) in detailRows" :key="`${row.sn}-${idx}`">
                  <td class="col-left dim">{{ row.recordType }}</td>
                  <td>{{ row.date }}</td>
                  <td>{{ row.country }}</td>
                  <td class="col-left mono">{{ row.account }}</td>
                  <td class="col-left mono">{{ row.sn }}</td>
                  <td>{{ row.deviceType }}</td>
                  <td class="col-left">{{ scenarioLabel(row.scenario) }}</td>
                  <td><span class="badge" :class="conclusionBadge(row.conclusion)">{{ row.conclusion }}</span></td>
                  <td><span class="badge" :class="afterSalesBadge(row.afterSales)">{{ row.afterSales }}</span></td>
                  <td><span class="badge" :class="adoptionBadge(row.adopted)">{{ row.adopted }}</span></td>
                  <td class="col-left dim">{{ row.rejectReason || '—' }}</td>
                  <td class="dim">{{ row.ruleVersion || '—' }}</td>
                  <td>{{ row.detectTime }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="detailTotal" class="dash-pagination">
            <span class="dash-pg-info">Showing <strong>{{ detailRangeStart }}–{{ detailRangeEnd }}</strong> of {{ detailTotal }}</span>
            <div class="dash-pg-btns">
              <button class="dash-pg-btn" type="button" :disabled="detailPage <= 1" data-test="dash-detail-prev" @click="changeDetailPage(-1)">‹ Prev</button>
              <span class="dash-pg-page">{{ detailPage }} / {{ detailPageCount }}</span>
              <button class="dash-pg-btn" type="button" :disabled="detailPage >= detailPageCount" data-test="dash-detail-next" @click="changeDetailPage(1)">Next ›</button>
            </div>
          </div>
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.dashboard-page-body {
  max-width: min(1480px, calc(100vw - 48px));
  padding: 8px 24px 40px;
}

/* Header */
.dash-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
}
.dash-header h1 {
  margin: 0;
  font-size: 1.6rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}
.dash-subtitle {
  margin: 8px 0 0;
  max-width: 680px;
  font-size: 0.86rem;
  line-height: 1.5;
  color: var(--text-secondary);
}
.dash-refresh {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 14px;
  border-radius: var(--radius-full, 9999px);
  border: 1px solid rgba(0, 168, 132, 0.4);
  background: rgba(0, 168, 132, 0.08);
  color: #00806a;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}
.dash-refresh:hover:not(:disabled) { background: rgba(0, 168, 132, 0.16); transform: translateY(-1px); }
.dash-refresh:disabled { opacity: 0.5; cursor: default; }
.dash-refresh svg { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

/* Filters */
.dash-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 14px;
  padding: 16px 18px;
  border-radius: 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(12px);
  margin-bottom: 18px;
}
.dash-filter {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--text-muted, #94a3b8);
}
.dash-control {
  min-width: 168px;
  height: 38px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid rgba(15, 23, 42, 0.14);
  background: #fff;
  color: var(--text-primary);
  font-size: 0.86rem;
  font-weight: 500;
  text-transform: none;
  letter-spacing: normal;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
.dash-control:focus { outline: none; border-color: #00a884; box-shadow: 0 0 0 3px rgba(0, 168, 132, 0.16); }
.dash-clear {
  height: 38px;
  padding: 0 14px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}
.dash-clear:hover { color: #c5221f; }

/* Segmented control */
.dash-segment {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border-radius: var(--radius-full, 9999px);
  background: rgba(15, 23, 42, 0.05);
  margin-bottom: 20px;
}
.dash-seg-btn {
  padding: 8px 22px;
  border: none;
  border-radius: var(--radius-full, 9999px);
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.86rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}
.dash-seg-btn.active {
  background: #fff;
  color: #00806a;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.12);
}

/* Banners / states */
.dash-banner { margin-bottom: 16px; padding: 12px 16px; border-radius: 12px; font-size: 0.85rem; }
.dash-banner--error { background: rgba(234, 67, 53, 0.08); color: #c5221f; }
.dash-skeleton, .dash-empty {
  padding: 40px;
  text-align: center;
  color: var(--text-muted, #94a3b8);
  font-size: 0.9rem;
}

/* KPI cards */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}
.kpi-card {
  position: relative;
  padding: 16px 18px;
  border-radius: 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.92);
  overflow: hidden;
}
.kpi-card::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: transparent;
}
.kpi-green::before { background: #00b894; }
.kpi-amber::before { background: #f6a623; }
.kpi-red::before { background: #ea4335; }
.kpi-gray::before { background: #cbd5e1; }
.kpi-label {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--text-muted, #94a3b8);
}
.kpi-value {
  margin-top: 8px;
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1.05;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.kpi-hero {
  color: #fff;
  border-color: transparent;
  background: linear-gradient(140deg, #00b894 0%, #00a884 55%, #009e7e 100%);
}
.kpi-hero .kpi-label { color: rgba(255, 255, 255, 0.85); }
.kpi-hero .kpi-value { color: #fff; }
.kpi-unit { font-size: 1.05rem; font-weight: 600; margin-left: 2px; }
.kpi-hero-meter { margin-top: 10px; height: 5px; border-radius: 3px; background: rgba(255, 255, 255, 0.28); overflow: hidden; }
.kpi-hero-meter span { display: block; height: 100%; border-radius: 3px; background: #fff; transition: width 0.4s ease; }

/* Panels */
.dash-panel {
  padding: 20px;
  border-radius: 18px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.9);
  margin-bottom: 18px;
}
.dash-panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
.dash-panel-head h2 { margin: 0; font-size: 1rem; font-weight: 700; color: var(--text-primary); }
.dash-panel-caption { font-size: 0.78rem; color: var(--text-muted, #94a3b8); }
.dash-two-col { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 18px; }
.dash-two-col > .dash-panel { margin-bottom: 0; }

/* Tables */
.dash-table-wrap { overflow-x: auto; }
.dash-table { width: 100%; border-collapse: collapse; }
.dash-table th, .dash-table td {
  padding: 12px 12px;
  text-align: center;
  font-size: 0.84rem;
  white-space: nowrap;
  color: var(--text-primary);
}
.dash-table th {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--text-muted, #94a3b8);
  border-bottom: 1px solid rgba(15, 23, 42, 0.1);
  position: sticky;
  top: 0;
  background: rgba(255, 255, 255, 0.96);
}
.dash-table td { border-bottom: 1px solid rgba(15, 23, 42, 0.05); }
.dash-table tbody tr { transition: background 0.14s ease; }
.dash-table tbody tr:hover { background: rgba(0, 168, 132, 0.04); }
.dash-table .col-left { text-align: left; }
.dash-table .col-rate { min-width: 150px; }
.num-green { color: #00806a; font-weight: 600; }
.num-amber { color: #b7791f; font-weight: 600; }
.dim { color: var(--text-muted, #94a3b8); }
.dash-detail-table td, .dash-detail-table th { font-size: 0.8rem; padding: 10px 12px; }

/* Adoption-rate mini bar in table */
.rate-cell { display: flex; align-items: center; gap: 8px; }
.rate-track { flex: 1; height: 6px; border-radius: 3px; background: rgba(15, 23, 42, 0.08); overflow: hidden; min-width: 60px; }
.rate-fill { display: block; height: 100%; border-radius: 3px; background: #00a884; }
.rate-num { font-variant-numeric: tabular-nums; font-weight: 600; min-width: 42px; text-align: right; }

/* Distribution bars */
.dist-list { display: flex; flex-direction: column; gap: 14px; }
.dist-row { display: grid; grid-template-columns: 150px 1fr auto; align-items: center; gap: 12px; }
.dist-label { display: inline-flex; align-items: center; gap: 8px; font-size: 0.84rem; color: var(--text-primary); }
.dist-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.dist-track { height: 8px; border-radius: 4px; background: rgba(15, 23, 42, 0.06); overflow: hidden; }
.dist-fill { display: block; height: 100%; border-radius: 4px; transition: width 0.4s ease; }
.dist-meta { font-size: 0.8rem; color: var(--text-secondary); font-variant-numeric: tabular-nums; white-space: nowrap; }
.tone-green { background: #00b894; } .dist-dot.tone-green { background: #00b894; }
.tone-amber { background: #f6a623; } .dist-dot.tone-amber { background: #f6a623; }
.tone-gray { background: #cbd5e1; } .dist-dot.tone-gray { background: #94a3b8; }
.tone-teal { background: #14b8a6; } .dist-dot.tone-teal { background: #14b8a6; }

/* Daily chart */
.chart { display: flex; align-items: flex-end; gap: 8px; height: 200px; padding-top: 10px; overflow-x: auto; }
.chart-col {
  flex: 1 0 34px;
  min-width: 34px;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  cursor: default;
  border-radius: 8px 8px 0 0;
  transition: background 0.14s ease;
}
.chart-col.active { background: rgba(0, 168, 132, 0.06); }
.chart-bar {
  width: 60%;
  min-height: 3px;
  border-radius: 5px 5px 0 0;
  background: linear-gradient(180deg, #00c9a3 0%, #00a884 100%);
  transition: height 0.4s ease, filter 0.14s ease;
}
.chart-col.active .chart-bar { filter: brightness(1.08); }
.chart-x { font-size: 0.68rem; color: var(--text-muted, #94a3b8); white-space: nowrap; }

/* Badges (fallbacks if global variants are absent) */
.badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: var(--radius-full, 9999px);
  font-size: 0.74rem;
  font-weight: 600;
  line-height: 1.5;
}
.badge-green { background: rgba(0, 184, 148, 0.14); color: #00806a; }
.badge-amber { background: rgba(246, 166, 35, 0.16); color: #b7791f; }
.badge-red { background: rgba(234, 67, 53, 0.12); color: #c5221f; }
.badge-gray { background: rgba(100, 116, 139, 0.14); color: #475569; }
.badge-teal { background: rgba(20, 184, 166, 0.14); color: #0f766e; }

/* Pagination */
.dash-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 16px;
  padding-top: 4px;
  font-size: 0.84rem;
  color: var(--text-secondary);
}
.dash-pg-btns { display: flex; align-items: center; gap: 12px; }
.dash-pg-page { font-variant-numeric: tabular-nums; color: var(--text-muted, #94a3b8); }
.dash-pg-btn {
  height: 34px;
  padding: 0 14px;
  border-radius: 9px;
  border: 1px solid rgba(15, 23, 42, 0.14);
  background: #fff;
  color: var(--text-primary);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.16s ease;
}
.dash-pg-btn:hover:not(:disabled) { border-color: #00a884; color: #00806a; }
.dash-pg-btn:disabled { opacity: 0.4; cursor: default; }

@media (max-width: 640px) {
  .dash-header { flex-direction: column; }
  .dist-row { grid-template-columns: 120px 1fr auto; }
}
</style>
