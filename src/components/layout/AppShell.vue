<script setup lang="ts">
import { computed, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { keyForFaultCategory } from '@/composables/faultCategories';
import { useDemoStore } from '@/composables/useDemoStore';
import type { DetectSession } from '@/types/record';

const route = useRoute();
const router = useRouter();
const store = useDemoStore();
const helpOpen = ref(false);
const sessionsOpen = ref(false);
const accountOpen = ref(false);

const isLogin = computed(() => route.name === 'login');
const isPlainWhitePage = computed(() => false);

const isDetectRecordNavActive = computed(() => {
  if (route.name === 'records') return true;
  if (route.name !== 'detect') return false;
  if (route.query.from === 'records') return true;
  const from = route.query.from;
  if (route.query.record && from !== 'chat' && from !== 'fault-query' && from !== 'device-detect') return true;
  return false;
});

const isDeviceDetectNavActive = computed(() => {
  if (isDetectRecordNavActive.value) return false;
  const n = route.name;
  if (n === 'chat' || n === 'fault-query' || n === 'multi-detect' || n === 'detect-devices') return true;
  if (n === 'detect') {
    const from = route.query.from;
    return from === 'chat' || from === 'fault-query' || from === 'device-detect';
  }
  return false;
});

interface SessionGroup {
  id: string;
  faultCategory: DetectSession['faultCategory'];
  status: DetectSession['status'];
  sessions: DetectSession[];
  updatedAt: string;
  batchId?: string;
  sn?: string;
  recordId?: string;
  stepLabel?: string;
  progress?: number;
}

const initials = computed(() => store.currentUser.value.slice(0, 2).toUpperCase());
const sessionGroups = computed<SessionGroup[]>(() => {
  const grouped = new Map<string, DetectSession[]>();
  for (const session of store.sessions.value) {
    const key = session.source === 'multi' && session.batchId
      ? `multi:${session.batchId}:${session.faultCategory}`
      : `single:${session.id}`;
    grouped.set(key, [...(grouped.get(key) ?? []), session]);
  }

  return [...grouped.entries()]
    .map(([id, sessions]) => {
      const sorted = [...sessions].sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
      const latest = sorted[0];
      const processing = sorted.find(session => session.status === 'processing');
      return {
        id,
        faultCategory: latest.faultCategory,
        status: processing ? 'processing' : 'complete',
        sessions: sorted,
        updatedAt: latest.updatedAt,
        batchId: latest.source === 'multi' ? latest.batchId : undefined,
        sn: latest.source === 'multi' ? undefined : latest.sn,
        recordId: latest.source === 'multi' ? undefined : latest.recordId,
        stepLabel: processing?.stepLabel ?? latest.stepLabel,
        progress: processing?.progress ?? latest.progress,
      } satisfies SessionGroup;
    })
    .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
});
const processingSessions = computed(() => sessionGroups.value.filter(session => session.status === 'processing'));
const completedSessions = computed(() => sessionGroups.value.filter(session => session.status === 'complete'));
const sessionGroupCount = computed(() => sessionGroups.value.length);

function signOut() {
  accountOpen.value = false;
  router.push('/');
}

function openSession(session: SessionGroup) {
  sessionsOpen.value = false;
  if (session.batchId) {
    router.push({
      name: 'multi-detect',
      params: { batchId: session.batchId },
      query: { category: session.faultCategory },
    });
    return;
  }

  const query: Record<string, string> = {
    category: session.faultCategory,
    session: session.id.replace(/^single:/, ''),
  };
  if (session.recordId) {
    query.record = session.recordId;
    query.from = 'records';
  }
  router.push({
    name: 'detect',
    params: { sn: session.sn },
    query,
  });
}

function openRecords() {
  sessionsOpen.value = false;
  router.push({ name: 'records' });
}

function clearSessions() {
  store.clearSessions();
}

function sessionDeviceCount(session: SessionGroup) {
  return session.sessions.length;
}

function sessionCompletedCount(session: SessionGroup) {
  return session.sessions.filter(item => item.status === 'complete').length;
}

function sessionRecordCount(session: SessionGroup) {
  return session.sessions.filter(item => item.recordId).length;
}

function formatSessionTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(date);
}
</script>

<template>
  <div v-if="!isPlainWhitePage" class="app-bg-ambient" aria-hidden="true">
    <div class="aurora-mesh"></div>
    <div class="bg-grid-fine"></div>
    <div class="wave-layer wave-layer--top wave-layer--a">
      <svg viewBox="0 0 2400 320" preserveAspectRatio="none">
        <path d="M0,160 C300,60 500,260 800,160 C1100,60 1300,260 1600,160 C1900,60 2100,260 2400,160" fill="none" stroke="rgba(124,255,103,0.3)" stroke-width="2.5" />
        <path d="M0,200 C400,100 600,300 1000,200 C1400,100 1800,300 2400,200" fill="none" stroke="rgba(180,151,207,0.24)" stroke-width="1.5" />
      </svg>
    </div>
    <div class="wave-layer wave-layer--a">
      <svg viewBox="0 0 2400 420" preserveAspectRatio="none">
        <path d="M0,220 C200,120 400,320 600,220 C800,120 1000,320 1200,220 C1400,120 1600,320 1800,220 C2000,120 2200,320 2400,220" fill="none" stroke="rgba(124,255,103,0.42)" stroke-width="2.5" />
        <path d="M0,260 C250,160 450,360 700,260 C950,160 1150,360 1400,260 C1650,160 1850,360 2100,260 C2250,180 2350,280 2400,240" fill="none" stroke="rgba(180,151,207,0.3)" stroke-width="2" />
        <path d="M0,300 C300,200 500,400 800,300 C1100,200 1300,400 1600,300 C1900,200 2100,400 2400,300" fill="none" stroke="rgba(82,39,255,0.24)" stroke-width="1.5" />
      </svg>
    </div>
    <div class="wave-layer wave-layer--b">
      <svg viewBox="0 0 2400 420" preserveAspectRatio="none">
        <path d="M0,280 C350,180 550,380 900,280 C1250,180 1450,380 1800,280 C2050,200 2250,360 2400,300" fill="none" stroke="rgba(124,255,103,0.2)" stroke-width="1.8" />
        <path d="M0,320 C400,220 600,420 1000,320 C1400,220 1600,420 2000,320 C2200,280 2300,340 2400,310" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="1" />
      </svg>
    </div>
  </div>

  <header v-if="!isLogin" class="topbar" :class="{ 'topbar--plain-white': isPlainWhitePage }">
    <div class="topbar-left">
      <div>
        <div class="logo">
          <div class="logo-mark">SI</div>
          SIBIONICS
        </div>
        <div class="topbar-tagline">CGM AI Service Desk</div>
      </div>
      <nav class="nav theme-adaptive-nav">
        <RouterLink
          class="top-nav-pill"
          to="/chat"
          active-class=""
          exact-active-class=""
          :class="{ active: isDeviceDetectNavActive }"
        >
          Device detection
        </RouterLink>
        <RouterLink class="top-nav-pill" active-class="active" to="/thresholds">Thresholds</RouterLink>
        <RouterLink
          class="top-nav-pill"
          to="/records"
          active-class=""
          exact-active-class=""
          :class="{ active: isDetectRecordNavActive }"
        >
          Detection records
        </RouterLink>
      </nav>
    </div>
    <div class="topbar-right">
      <button class="toolbar-icon-btn" type="button" title="Help center" aria-label="Help center" @click="helpOpen = true">?</button>
      <button class="toolbar-icon-btn" type="button" title="Session manager" aria-label="Session manager" @click="sessionsOpen = true">
        &#9776; <span class="toolbar-count">{{ sessionGroupCount }}</span>
      </button>
      <div class="account-menu-wrap">
        <button class="user-pill" type="button" aria-haspopup="menu" :aria-expanded="accountOpen" @click.stop="accountOpen = !accountOpen">
          <div class="user-avatar">{{ initials }}</div>
          <span class="user-name">{{ store.currentUser.value }}</span>
        </button>
        <div v-if="accountOpen" class="account-menu theme-surface" data-test="account-menu" role="menu">
          <div class="account-menu-meta">
            <strong>{{ store.currentUser.value }}</strong>
            <span>{{ store.currentAccount.value.dealerName }}</span>
          </div>
          <button class="account-menu-item" type="button" data-test="account-sign-out" role="menuitem" @click="signOut">Sign out</button>
        </div>
      </div>
    </div>
  </header>

  <slot />

  <div class="drawer-overlay" :class="{ show: helpOpen }" @click.self="helpOpen = false">
    <section class="side-drawer theme-surface" role="dialog" aria-modal="true" aria-labelledby="help-drawer-title">
      <div class="drawer-header">
        <div>
          <h3 id="help-drawer-title">Help Center</h3>
          <p>Search workflow guidance, technical terms, quick videos, and support actions without leaving your current detection.</p>
        </div>
        <button class="toolbar-icon-btn" type="button" aria-label="Close help drawer" @click="helpOpen = false">&times;</button>
      </div>
      <div class="drawer-body">
        <p>Please search by SN first. Results, dashboard cards, and detection records are only generated after a detection is run.</p>
      </div>
    </section>
  </div>

  <div class="drawer-overlay" :class="{ show: sessionsOpen }" @click.self="sessionsOpen = false">
    <section class="side-drawer theme-surface" role="dialog" aria-modal="true" aria-labelledby="sessions-drawer-title">
      <div class="drawer-header">
        <div>
          <h3 id="sessions-drawer-title">Session Manager</h3>
          <p>Each completed session retains a snapshot of its threshold settings. Any subsequent changes to the rules will not modify historical records.</p>
        </div>
        <button class="toolbar-icon-btn" type="button" aria-label="Close session drawer" @click="sessionsOpen = false">&times;</button>
      </div>
      <div class="drawer-body">
        <p v-if="!sessionGroupCount">No active or completed detect sessions yet.</p>
        <template v-else>
          <section v-if="processingSessions.length" class="drawer-card session-section">
            <h4>Processing</h4>
            <p>Detection runs that are currently analyzing sensor data or evidence.</p>
            <ul class="session-list">
              <li v-for="session in processingSessions" :key="session.id" class="session-item">
                <div class="session-item-title">
                  <strong :class="{ mono: !session.batchId }">{{ session.batchId ? session.faultCategory : session.sn }}</strong>
                  <span class="badge badge-blue">Processing</span>
                </div>
                <span v-if="session.batchId">{{ sessionDeviceCount(session) }} devices · {{ sessionCompletedCount(session) }}/{{ sessionDeviceCount(session) }} complete · updated {{ formatSessionTime(session.updatedAt) }}</span>
                <span v-else>Single · {{ session.faultCategory }} · updated {{ formatSessionTime(session.updatedAt) }}</span>
                <p v-if="session.stepLabel" class="session-progress-copy">{{ session.stepLabel }} · {{ session.progress ?? 0 }}%</p>
                <div class="session-actions">
                  <button class="btn btn-primary btn-sm" type="button" data-test="session-view-progress" @click="openSession(session)">View progress</button>
                  <button class="btn btn-secondary btn-sm" type="button" @click="router.push({ name: 'fault-query', params: { categoryKey: keyForFaultCategory(session.faultCategory) } })">New detection</button>
                </div>
              </li>
            </ul>
          </section>
          <section v-if="completedSessions.length" class="drawer-card session-section">
            <h4>Completed</h4>
            <p>Completed sessions can reopen the verdict page without changing the record.</p>
            <ul class="session-list">
              <li v-for="session in completedSessions" :key="session.id" class="session-item">
                <div class="session-item-title">
                  <strong :class="{ mono: !session.batchId }">{{ session.batchId ? session.faultCategory : session.sn }}</strong>
                  <span class="badge badge-green">Complete</span>
                </div>
                <span v-if="session.batchId">{{ sessionRecordCount(session) }} records · updated {{ formatSessionTime(session.updatedAt) }}</span>
                <span v-else>{{ session.faultCategory }} · {{ session.recordId }} · updated {{ formatSessionTime(session.updatedAt) }}</span>
                <div class="session-actions">
                  <button class="btn btn-primary btn-sm" type="button" data-test="session-view-result" @click="openSession(session)">View result</button>
                  <button class="btn btn-secondary btn-sm" type="button" @click="router.push({ name: 'fault-query', params: { categoryKey: keyForFaultCategory(session.faultCategory) } })">New detection</button>
                </div>
              </li>
            </ul>
          </section>
          <div class="drawer-actions session-manager-actions">
            <button class="btn btn-secondary btn-sm" type="button" data-test="session-open-records" @click="openRecords">Open detection record</button>
            <button class="btn btn-ghost btn-sm" type="button" data-test="session-clear" @click="clearSessions">Clear sessions</button>
          </div>
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped>
.session-actions,
.session-manager-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.theme-adaptive-nav {
  padding: 5px;
}

.top-nav-pill {
  border: 1px solid transparent;
  background: transparent;
  box-shadow: none;
}

.top-nav-pill.active {
  color: var(--accent);
  background: rgba(0, 168, 132, 0.12);
  border-color: rgba(0, 168, 132, 0.24);
}

.topbar-right {
  gap: 8px;
  justify-content: flex-end;
}

.user-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  width: auto;
  min-width: 0;
  max-width: 260px;
  padding: 4px 12px 4px 4px;
}

.user-avatar {
  flex: 0 0 auto;
}

.user-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topbar--plain-white {
  background: #ffffff !important;
  border-bottom: 1px solid #e5e7eb !important;
  box-shadow: none !important;
  -webkit-backdrop-filter: none !important;
  backdrop-filter: none !important;
}

.topbar--plain-white .theme-adaptive-nav,
.topbar--plain-white .toolbar-icon-btn,
.topbar--plain-white .user-pill {
  background: #ffffff !important;
  border-color: #e5e7eb !important;
  box-shadow: none !important;
  -webkit-backdrop-filter: none !important;
  backdrop-filter: none !important;
}

.topbar--plain-white .top-nav-pill.active {
  background: #ecfdf5 !important;
  border-color: rgba(0, 168, 132, 0.25) !important;
  box-shadow: none !important;
}

.session-manager-actions {
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.session-section {
  margin-bottom: 14px;
}

.session-list {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.theme-surface {
  color: var(--text-primary);
}

.session-item-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.session-progress-copy {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 0.82rem;
}

.account-menu-wrap {
  position: relative;
}

.account-menu {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  z-index: 30;
  min-width: 240px;
  max-width: min(320px, calc(100vw - 24px));
  padding: 10px;
}

.account-menu-meta {
  display: grid;
  gap: 4px;
  padding: 8px 10px 10px;
  border-bottom: 1px solid var(--border);
}

.account-menu-meta span {
  color: var(--text-secondary);
  font-size: 0.8rem;
}

.account-menu-item {
  width: 100%;
  margin-top: 8px;
  padding: 10px 14px;
  border: 0;
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
}

.account-menu-item:hover {
  background: var(--bg-elevated);
}
</style>
