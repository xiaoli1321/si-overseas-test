<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';
import { backendApi, type DashboardData } from '@/api/backend';

const router = useRouter();
const store = useDemoStore();

const data = ref<DashboardData | null>(null);
const loading = ref(false);
const loadError = ref('');

async function loadDashboard() {
  if (!store.backendOnline.value) {
    loadError.value = 'Dashboard requires the backend to be online.';
    return;
  }
  loading.value = true;
  loadError.value = '';
  try {
    data.value = await backendApi.getDashboard();
  } catch (err) {
    loadError.value = (err as Error).message || 'Failed to load dashboard.';
    data.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await store.loadRemoteBootstrap();
  if (!store.isManager.value) {
    router.replace({ name: 'chat' });
    return;
  }
  void loadDashboard();
});

const kpis = computed(() => {
  const t = data.value?.totals;
  return [
    { key: 'logins', label: 'Logins', value: t?.logins ?? 0 },
    { key: 'deviceQueries', label: 'Device queries', value: t?.deviceQueries ?? 0 },
    { key: 'batchQueries', label: 'Batch queries', value: t?.batchQueries ?? 0, sub: `${t?.batchDevices ?? 0} devices` },
    { key: 'diagnoses', label: 'Diagnoses', value: t?.diagnoses ?? 0 },
    { key: 'records', label: 'Records', value: t?.records ?? 0 },
  ];
});

const adoptionRate = computed(() => {
  const a = data.value?.adoption;
  if (!a) return 0;
  const denom = a.adopted + a.rejected;
  return denom > 0 ? Math.round((a.adopted / denom) * 1000) / 10 : 0;
});

const verdictBars = computed(() => {
  const v = data.value?.verdicts;
  if (!v) return [];
  const max = Math.max(v.eligible, v.notEligible, v.underReview, 1);
  return [
    { label: 'Replacement eligible', value: v.eligible, cls: 'bar-green', pct: (v.eligible / max) * 100 },
    { label: 'Not eligible', value: v.notEligible, cls: 'bar-gray', pct: (v.notEligible / max) * 100 },
    { label: 'Under review', value: v.underReview, cls: 'bar-amber', pct: (v.underReview / max) * 100 },
  ];
});

const queryUsageBars = computed(() => {
  const q = data.value?.queryUsage;
  if (!q) return [];
  const max = Math.max(q.single, q.batch, q.search, 1);
  return [
    { label: 'Single', value: q.single, pct: (q.single / max) * 100 },
    { label: 'Batch', value: q.batch, pct: (q.batch / max) * 100 },
    { label: 'Search', value: q.search, pct: (q.search / max) * 100 },
  ];
});

const faultMax = computed(() => Math.max(1, ...(data.value?.byFaultCategory ?? []).map(f => f.count)));

function accountAdoptionRate(row: DashboardData['byAccount'][number]) {
  const denom = row.adopted + row.rejected;
  return denom > 0 ? `${Math.round((row.adopted / denom) * 100)}%` : '—';
}
</script>

<template>
  <div class="page active" id="page-dashboard">
    <div class="page-body dashboard-page-body">
      <div class="logs-header slide-up stagger-1">
        <div>
          <h1>Operations Dashboard</h1>
          <p style="color: var(--text-secondary); font-size: var(--text-sm); margin-top: 6px; max-width: 620px">
            Live, org-wide metrics generated directly from telemetry &amp; detection records across every account.
          </p>
        </div>
        <button class="btn btn-secondary" type="button" data-test="dashboard-refresh" :disabled="loading" @click="loadDashboard">
          {{ loading ? 'Loading…' : '↻ Refresh' }}
        </button>
      </div>

      <div v-if="loadError" class="dashboard-error" data-test="dashboard-error">{{ loadError }}</div>

      <template v-if="data">
        <!-- KPI cards -->
        <div class="kpi-grid slide-up stagger-2">
          <div v-for="kpi in kpis" :key="kpi.key" class="kpi-card" :data-test="`kpi-${kpi.key}`">
            <div class="kpi-value">{{ kpi.value.toLocaleString() }}</div>
            <div class="kpi-label">{{ kpi.label }}</div>
            <div v-if="kpi.sub" class="kpi-sub">{{ kpi.sub }}</div>
          </div>
        </div>

        <!-- Verdict + adoption + query usage -->
        <div class="dashboard-cards-3 slide-up stagger-3">
          <section class="dashboard-panel">
            <h2>Verdict outcome</h2>
            <div v-for="bar in verdictBars" :key="bar.label" class="bar-row">
              <span class="bar-label">{{ bar.label }}</span>
              <span class="bar-track"><span class="bar-fill" :class="bar.cls" :style="{ width: `${bar.pct}%` }"></span></span>
              <span class="bar-value">{{ bar.value }}</span>
            </div>
          </section>

          <section class="dashboard-panel">
            <h2>Adoption</h2>
            <div class="adoption-rate" data-test="dashboard-adoption-rate">
              <span class="adoption-rate-value">{{ adoptionRate }}%</span>
              <span class="adoption-rate-label">adoption rate</span>
            </div>
            <div class="adoption-split">
              <span class="badge badge-green">Adopted {{ data.adoption.adopted }}</span>
              <span class="badge badge-amber">Rejected {{ data.adoption.rejected }}</span>
            </div>
          </section>

          <section class="dashboard-panel">
            <h2>Query usage</h2>
            <div v-for="bar in queryUsageBars" :key="bar.label" class="bar-row">
              <span class="bar-label">{{ bar.label }}</span>
              <span class="bar-track"><span class="bar-fill bar-teal" :style="{ width: `${bar.pct}%` }"></span></span>
              <span class="bar-value">{{ bar.value }}</span>
            </div>
          </section>
        </div>

        <!-- Fault category -->
        <section class="dashboard-panel slide-up stagger-4" style="margin-top: 18px">
          <h2>Records by fault category</h2>
          <div v-if="!data.byFaultCategory.length" class="empty-state" style="padding: 20px">No records yet.</div>
          <div v-for="fc in data.byFaultCategory" :key="fc.category" class="bar-row">
            <span class="bar-label bar-label-wide">{{ fc.category }}</span>
            <span class="bar-track"><span class="bar-fill bar-teal" :style="{ width: `${(fc.count / faultMax) * 100}%` }"></span></span>
            <span class="bar-value">{{ fc.count }}</span>
          </div>
        </section>

        <!-- Per-account activity -->
        <section class="dashboard-panel slide-up stagger-5" style="margin-top: 18px">
          <h2>Account activity (top {{ data.byAccount.length }})</h2>
          <div class="table-wrap">
            <table class="records-table dashboard-table">
              <thead>
                <tr>
                  <th style="text-align:left">Account</th>
                  <th>Dealer</th>
                  <th>Logins</th>
                  <th>Queries</th>
                  <th>Batch devices</th>
                  <th>Diagnoses</th>
                  <th>Adoption</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!data.byAccount.length">
                  <td colspan="7"><div class="empty-state" style="padding: 20px">No account activity yet.</div></td>
                </tr>
                <tr v-for="row in data.byAccount" :key="row.accountId" :data-test="`dashboard-account-${row.accountId}`">
                  <td class="mono" style="text-align:left">{{ row.email }}</td>
                  <td>{{ row.dealerName }}</td>
                  <td>{{ row.logins }}</td>
                  <td>{{ row.queries }}</td>
                  <td>{{ row.batchDevices }}</td>
                  <td>{{ row.diagnoses }}</td>
                  <td>{{ accountAdoptionRate(row) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.dashboard-page-body {
  max-width: min(1280px, calc(100vw - 48px));
  padding-left: 24px;
  padding-right: 24px;
}

.dashboard-error {
  margin: 12px 0;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(234, 67, 53, 0.08);
  color: #c5221f;
  font-size: 0.85rem;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 14px;
  margin-top: 12px;
}

.kpi-card {
  padding: 18px;
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.9));
}

.kpi-value {
  font-size: 1.7rem;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.1;
}

.kpi-label {
  margin-top: 6px;
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.kpi-sub {
  margin-top: 2px;
  font-size: 0.72rem;
  color: var(--text-muted, #94a3b8);
}

.dashboard-cards-3 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
  margin-top: 18px;
}

.dashboard-panel {
  padding: 18px;
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.9);
}

.dashboard-panel h2 {
  margin: 0 0 14px;
  font-size: 0.95rem;
  color: var(--text-primary);
}

.bar-row {
  display: grid;
  grid-template-columns: 120px 1fr 44px;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.bar-label {
  font-size: 0.78rem;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-label-wide {
  white-space: normal;
}

.bar-track {
  height: 10px;
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.06);
  overflow: hidden;
}

.bar-fill {
  display: block;
  height: 100%;
  border-radius: 6px;
  background: var(--accent, #00a884);
  min-width: 2px;
  transition: width 0.3s ease;
}

.bar-teal { background: #00a884; }
.bar-green { background: #00b894; }
.bar-amber { background: #f6a623; }
.bar-gray { background: #94a3b8; }

.bar-value {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-primary);
  text-align: right;
}

.adoption-rate {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 14px;
}

.adoption-rate-value {
  font-size: 2rem;
  font-weight: 700;
  color: #00a884;
}

.adoption-rate-label {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.adoption-split {
  display: flex;
  gap: 10px;
}

.dashboard-table th,
.dashboard-table td {
  text-align: center;
  padding: 12px 10px;
}
</style>
