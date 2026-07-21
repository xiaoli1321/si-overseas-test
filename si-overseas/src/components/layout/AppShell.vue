<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { keyForFaultCategory, faultCategoryLabel } from '@/composables/faultCategories';
import { useDemoStore } from '@/composables/useDemoStore';
import { useAgentChat } from '@/composables/useAgentChat';
import type { DetectSession } from '@/types/record';

import logoImage from '@/assets/logo.png';

const route = useRoute();
const router = useRouter();
const store = useDemoStore();
const chat = useAgentChat();
const navOpen = ref(false);
const sessionsOpen = ref(false);
const accountOpen = ref(false);
const clearSessionsConfirmOpen = ref(false);

const createUserOpen = ref(false);
const createUserEmail = ref('');
const createUserPassword = ref('');
const createUserConfirmPassword = ref('');
const createUserDistributorName = ref('');
const createUserError = ref('');
const createUserSuccess = ref('');
const createUserSubmitting = ref(false);
const showCreateUserPassword = ref(false);
const showCreateUserConfirmPassword = ref(false);

const createAlertOpen = ref(false);
const createAlertTitle = ref('');
const createAlertMessage = ref('');
const createAlertType = ref<'success' | 'error'>('success');

function showCreateAlert(type: 'success' | 'error', title: string, message: string) {
  createAlertType.value = type;
  createAlertTitle.value = title;
  createAlertMessage.value = message;
  createAlertOpen.value = true;
}

const isLogin = computed(() => route.name === 'login');
const isPlainWhitePage = computed(() => false);


const isDetectRecordNavActive = computed(() => {
  if (route.name === 'records') return true;
  if (route.name === 'detect-record') {
    const from = route.query.from;
    return from !== 'chat' && from !== 'fault-query' && from !== 'device-detect';
  }
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
  if (n === 'detect-new') return true;
  if (n === 'detect' || n === 'detect-record') {
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

const onDocumentClick = (event: MouseEvent) => {
  const target = event.target as HTMLElement;
  if (!target.closest('.account-menu-wrap')) {
    accountOpen.value = false;
  }
};

watch(accountOpen, (isOpen) => {
  if (isOpen) {
    document.addEventListener('click', onDocumentClick);
  } else {
    document.removeEventListener('click', onDocumentClick);
  }
});

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick);
  window.removeEventListener('auth-unauthorized', onAuthUnauthorized);
});

function signOut() {
  accountOpen.value = false;
  store.logout();
  router.push('/');
}

function goAccountCenter() {
  accountOpen.value = false;
  router.push({ name: 'accounts' });
}

function goDashboard() {
  accountOpen.value = false;
  router.push({ name: 'dashboard' });
}

function openCreateUser() {
  accountOpen.value = false;
  createUserOpen.value = true;
  createUserError.value = '';
  createUserSuccess.value = '';
  createUserEmail.value = '';
  createUserPassword.value = '';
  createUserConfirmPassword.value = '';
  showCreateUserPassword.value = false;
  showCreateUserConfirmPassword.value = false;
  createUserDistributorName.value = '';
}

function closeCreateUser() {
  if (createUserSubmitting.value) return;
  createUserOpen.value = false;
}

async function submitCreateUser() {
  const email = createUserEmail.value.trim();
  const password = createUserPassword.value;
  const distributorName = createUserDistributorName.value.trim();
  createUserError.value = '';
  createUserSuccess.value = '';

  if (!email) {
    createUserError.value = 'Email is required.';
    return;
  }
  if (!distributorName) {
    createUserError.value = 'Distributor name is required.';
    return;
  }
  if (password.length < 8) {
    createUserError.value = 'Temporary password must be at least 8 characters.';
    return;
  }
  if (password !== createUserConfirmPassword.value) {
    createUserError.value = 'Passwords do not match.';
    return;
  }

  createUserSubmitting.value = true;
  try {
    const created = await store.createUserRemote(email, password, distributorName);
    createUserEmail.value = '';
    createUserPassword.value = '';
    createUserConfirmPassword.value = '';
    showCreateUserPassword.value = false;
    showCreateUserConfirmPassword.value = false;
    createUserDistributorName.value = '';
    createUserOpen.value = false;
    showCreateAlert('success', 'Success', `User ${created.email} has been created successfully.`);
  } catch (err: any) {
    const errMsg = err?.message || 'Failed to create user.';
    showCreateAlert('error', 'Error', errMsg);
  } finally {
    createUserSubmitting.value = false;
  }
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
    query.from = 'records';
    router.push({
      name: 'detect-record',
      params: { sn: session.sn, recordId: session.recordId },
      query,
    });
    return;
  }
  router.push({
    name: 'detect',
    params: { sn: session.sn },
    query,
  });
}

function requestClearSessions() {
  clearSessionsConfirmOpen.value = true;
}

function clearSessions() {
  store.clearSessions();
  clearSessionsConfirmOpen.value = false;
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

const isUnauthorizedOpen = ref(false);

function handleRedirectToLogin() {
  isUnauthorizedOpen.value = false;
  store.logout();
  router.push('/');
}

function onAuthUnauthorized() {
  isUnauthorizedOpen.value = true;
}

onMounted(() => {
  window.addEventListener('auth-unauthorized', onAuthUnauthorized);
});
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
          <img :src="logoImage" alt="SIBIONICS" class="logo-img" />
        </div>
        <div class="topbar-tagline">CGM AI SERVICE DESK</div>
      </div>
      <button
        class="hamburger-btn"
        :class="{ active: navOpen }"
        type="button"
        aria-label="Toggle navigation"
        @click="navOpen = !navOpen"
      >
        <span></span><span></span><span></span>
      </button>
      <nav class="nav theme-adaptive-nav">
        <RouterLink
          class="top-nav-pill"
          :to="chat.currentSessionId.value ? { name: 'chat', query: { session: chat.currentSessionId.value } } : '/chat'"
          active-class=""
          exact-active-class=""
          :class="{ active: isDeviceDetectNavActive }"
        >
          Device Detection
        </RouterLink>
        <RouterLink class="top-nav-pill" active-class="active" to="/thresholds">Thresholds</RouterLink>
        <RouterLink
          class="top-nav-pill"
          to="/records"
          active-class=""
          exact-active-class=""
          :class="{ active: isDetectRecordNavActive }"
        >
          Detection History
        </RouterLink>
      </nav>
    </div>
    <div class="topbar-right">
      <button class="toolbar-icon-btn" type="button" title="Session manager" aria-label="Session manager" @click="sessionsOpen = true">
        &#9776; <span class="toolbar-count">{{ sessionGroupCount }}</span>
      </button>
      <div class="account-menu-wrap">
        <button class="user-pill" type="button" aria-haspopup="menu" :aria-expanded="accountOpen" @click.stop="accountOpen = !accountOpen">
          <span class="user-name">{{ store.currentUser.value }}</span>
        </button>
        <div v-if="accountOpen" class="account-menu theme-surface" data-test="account-menu" role="menu">
          <div class="account-menu-meta">
            <strong>{{ store.currentUser.value }}</strong>
            <span>{{ store.currentAccount.value.dealerName }}</span>
          </div>
          <button
            v-if="store.canCreateUsers.value"
            class="account-menu-item"
            type="button"
            data-test="account-create-user"
            role="menuitem"
            @click="openCreateUser"
          >
            Create user
          </button>
          <button
            v-if="store.isManager.value"
            class="account-menu-item"
            type="button"
            data-test="dashboard-link"
            role="menuitem"
            @click="goDashboard"
          >
            Dashboard
          </button>
          <button
            v-if="store.isManager.value"
            class="account-menu-item"
            type="button"
            data-test="account-center-link"
            role="menuitem"
            @click="goAccountCenter"
          >
            Account center
          </button>
          <button class="account-menu-item" type="button" data-test="account-sign-out" role="menuitem" @click="signOut">Sign out</button>
        </div>
      </div>
    </div>
  </header>

  <div v-if="navOpen" class="nav-overlay" @click.self="navOpen = false">
    <nav class="nav-drawer">
      <div class="nav-drawer-head">
        <img :src="logoImage" alt="SIBIONICS" class="logo-img" />
        <button class="nav-drawer-close" type="button" aria-label="Close navigation" @click="navOpen = false">&times;</button>
      </div>
      <RouterLink
        class="nav-drawer-item"
        :to="chat.currentSessionId.value ? { name: 'chat', query: { session: chat.currentSessionId.value } } : '/chat'"
        :class="{ active: isDeviceDetectNavActive }"
        @click="navOpen = false"
      >Device Detection</RouterLink>
      <RouterLink class="nav-drawer-item" active-class="active" to="/thresholds" @click="navOpen = false">Thresholds</RouterLink>
      <RouterLink
        class="nav-drawer-item"
        to="/records"
        :class="{ active: isDetectRecordNavActive }"
        @click="navOpen = false"
      >Detection History</RouterLink>
    </nav>
  </div>

  <slot />

  <div class="drawer-overlay" :class="{ show: sessionsOpen }" @click.self="sessionsOpen = false">
    <section class="side-drawer theme-surface session-manager-drawer" role="dialog" aria-modal="true" aria-labelledby="sessions-drawer-title">
      <div class="drawer-header">
        <div>
          <h3 id="sessions-drawer-title">Session Manager</h3>
          <p>Each completed session retains a snapshot of its threshold settings. Any subsequent changes to the rules will not modify historical records.</p>
        </div>
        <button class="toolbar-icon-btn" type="button" aria-label="Close session drawer" @click="sessionsOpen = false">&times;</button>
      </div>
      <div class="drawer-body">
        <p v-if="!sessionGroupCount">No active or completed detection sessions yet.</p>
        <template v-else>
          <section v-if="processingSessions.length" class="drawer-card session-section">
            <h4>Processing</h4>
            <p>Detection runs that are currently analyzing sensor data or evidence.</p>
            <ul class="session-list">
              <li v-for="session in processingSessions" :key="session.id" class="session-item">
                <div class="session-item-title">
                  <strong :class="{ mono: !session.batchId }">{{ session.batchId ? faultCategoryLabel(session.faultCategory) : session.sn }}</strong>
                  <span class="badge badge-blue">Processing</span>
                </div>
                <span v-if="session.batchId">{{ sessionDeviceCount(session) }} devices · {{ sessionCompletedCount(session) }}/{{ sessionDeviceCount(session) }} complete · updated {{ formatSessionTime(session.updatedAt) }}</span>
                <span v-else>Single · {{ faultCategoryLabel(session.faultCategory) }} · updated {{ formatSessionTime(session.updatedAt) }}</span>
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
                  <strong :class="{ mono: !session.batchId }">{{ session.batchId ? faultCategoryLabel(session.faultCategory) : session.sn }}</strong>
                  <span class="badge badge-green">Complete</span>
                </div>
                <span v-if="session.batchId">{{ sessionRecordCount(session) }} records · updated {{ formatSessionTime(session.updatedAt) }}</span>
                <span v-else>{{ faultCategoryLabel(session.faultCategory) }} · updated {{ formatSessionTime(session.updatedAt) }}</span>
                <div class="session-actions">
                  <button class="btn btn-primary btn-sm" type="button" data-test="session-view-result" @click="openSession(session)">View result</button>
                  <button class="btn btn-secondary btn-sm" type="button" @click="router.push({ name: 'fault-query', params: { categoryKey: keyForFaultCategory(session.faultCategory) } })">New detection</button>
                </div>
              </li>
            </ul>
          </section>
          <div class="drawer-actions session-manager-actions">
            <button class="btn btn-danger btn-sm" type="button" data-test="session-clear" @click="requestClearSessions">Clear sessions</button>
          </div>
        </template>
      </div>
    </section>
  </div>

  <div v-if="clearSessionsConfirmOpen" class="modal-overlay session-confirm-overlay" role="presentation" @click.self="clearSessionsConfirmOpen = false">
    <section
      class="modal session-confirm-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="session-clear-confirm-title"
      aria-describedby="session-clear-confirm-description"
    >
      <h2 id="session-clear-confirm-title">Clear all sessions?</h2>
      <p id="session-clear-confirm-description">
        This will remove every active and completed detect session from the session manager.
      </p>
      <div class="modal-actions session-confirm-actions">
        <button class="btn btn-secondary" type="button" @click="clearSessionsConfirmOpen = false">Cancel</button>
        <button class="btn btn-danger" type="button" data-test="session-clear-confirm" @click="clearSessions">Clear sessions</button>
      </div>
    </section>
  </div>

  <div v-if="isUnauthorizedOpen" class="modal-overlay session-confirm-overlay" role="presentation">
    <section
      class="modal session-confirm-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="session-expired-title"
      aria-describedby="session-expired-description"
    >
      <h2 id="session-expired-title">Session Expired</h2>
      <p id="session-expired-description">
        Your login session has expired. Please sign in again to continue using the platform.
      </p>
      <div class="modal-actions session-confirm-actions">
        <button class="btn btn-primary" type="button" @click="handleRedirectToLogin">Log In</button>
      </div>
    </section>
  </div>

  <div v-if="createUserOpen" class="modal-overlay session-confirm-overlay" role="presentation">
    <section
      class="modal create-user-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-user-title"
    >
      <div class="create-user-head">
        <div>
          <h2 id="create-user-title">Create user</h2>
          <p>New users can sign in after the account is created.</p>
        </div>
        <button class="toolbar-icon-btn" type="button" aria-label="Close create user dialog" @click="closeCreateUser">&times;</button>
      </div>
      <form class="create-user-form" data-test="create-user-form" @submit.prevent="submitCreateUser">
        <label class="create-user-field">
          <span>Email</span>
          <input v-model="createUserEmail" class="form-input" type="email" autocomplete="off" data-test="create-user-email" required />
        </label>
        <label class="create-user-field">
          <span>Distributor name</span>
          <input v-model="createUserDistributorName" class="form-input" type="text" autocomplete="organization" data-test="create-user-distributor" required />
        </label>
        <label class="create-user-field">
          <span>Temporary password</span>
          <span class="create-user-password-wrap">
            <input
              v-model="createUserPassword"
              class="form-input create-user-password-input"
              :type="showCreateUserPassword ? 'text' : 'password'"
              autocomplete="new-password"
              data-test="create-user-password"
              required
            />
            <button
              class="create-user-password-toggle"
              type="button"
              data-test="create-user-password-toggle"
              :aria-label="showCreateUserPassword ? 'Hide temporary password' : 'Show temporary password'"
              @click="showCreateUserPassword = !showCreateUserPassword"
            >
              <svg v-if="showCreateUserPassword" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M3 3l18 18" />
                <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8" />
                <path d="M9.5 5.3A10.6 10.6 0 0 1 12 5c5.2 0 8.6 4.7 9.6 6.4a1.1 1.1 0 0 1 0 1.2 18.2 18.2 0 0 1-2.7 3.3" />
                <path d="M6.7 6.8a17.5 17.5 0 0 0-4.3 4.6 1.1 1.1 0 0 0 0 1.2C3.4 14.3 6.8 19 12 19a10.7 10.7 0 0 0 4.1-.8" />
              </svg>
              <svg v-else viewBox="0 0 24 24" aria-hidden="true">
                <path d="M2.4 11.4C3.4 9.7 6.8 5 12 5s8.6 4.7 9.6 6.4a1.1 1.1 0 0 1 0 1.2C20.6 14.3 17.2 19 12 19s-8.6-4.7-9.6-6.4a1.1 1.1 0 0 1 0-1.2Z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            </button>
          </span>
        </label>
        <label class="create-user-field">
          <span>Confirm password</span>
          <span class="create-user-password-wrap">
            <input
              v-model="createUserConfirmPassword"
              class="form-input create-user-password-input"
              :type="showCreateUserConfirmPassword ? 'text' : 'password'"
              autocomplete="new-password"
              data-test="create-user-confirm-password"
              required
            />
            <button
              class="create-user-password-toggle"
              type="button"
              data-test="create-user-confirm-password-toggle"
              :aria-label="showCreateUserConfirmPassword ? 'Hide confirmed password' : 'Show confirmed password'"
              @click="showCreateUserConfirmPassword = !showCreateUserConfirmPassword"
            >
              <svg v-if="showCreateUserConfirmPassword" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M3 3l18 18" />
                <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8" />
                <path d="M9.5 5.3A10.6 10.6 0 0 1 12 5c5.2 0 8.6 4.7 9.6 6.4a1.1 1.1 0 0 1 0 1.2 18.2 18.2 0 0 1-2.7 3.3" />
                <path d="M6.7 6.8a17.5 17.5 0 0 0-4.3 4.6 1.1 1.1 0 0 0 0 1.2C3.4 14.3 6.8 19 12 19a10.7 10.7 0 0 0 4.1-.8" />
              </svg>
              <svg v-else viewBox="0 0 24 24" aria-hidden="true">
                <path d="M2.4 11.4C3.4 9.7 6.8 5 12 5s8.6 4.7 9.6 6.4a1.1 1.1 0 0 1 0 1.2C20.6 14.3 17.2 19 12 19s-8.6-4.7-9.6-6.4a1.1 1.1 0 0 1 0-1.2Z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            </button>
          </span>
        </label>
        <p v-if="createUserError" class="create-user-error" data-test="create-user-error">{{ createUserError }}</p>
        <p v-if="createUserSuccess" class="create-user-success" data-test="create-user-success">{{ createUserSuccess }}</p>
        <div class="modal-actions session-confirm-actions">
          <button class="btn btn-secondary" type="button" :disabled="createUserSubmitting" @click="closeCreateUser">Cancel</button>
          <button class="btn btn-primary" type="submit" :disabled="createUserSubmitting" data-test="create-user-submit">
            {{ createUserSubmitting ? 'Creating...' : 'Create user' }}
          </button>
        </div>
      </form>
    </section>
  </div>

  <div v-if="createAlertOpen" class="modal-overlay session-confirm-overlay" role="presentation">
    <section
      class="modal session-confirm-modal"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="createAlertType === 'success' ? 'create-alert-success-title' : 'create-alert-error-title'"
    >
      <h2 :id="createAlertType === 'success' ? 'create-alert-success-title' : 'create-alert-error-title'">
        {{ createAlertTitle }}
      </h2>
      <p>{{ createAlertMessage }}</p>
      <div class="modal-actions session-confirm-actions">
        <button class="btn btn-primary" type="button" data-test="create-alert-ok" @click="createAlertOpen = false">OK</button>
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
  justify-content: center;
  width: auto;
  min-width: 0;
  max-width: 260px;
  padding: 6px 16px;
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

.session-manager-drawer {
  background: #ffffff !important;
  border-color: rgba(15, 23, 42, 0.12) !important;
  -webkit-backdrop-filter: none !important;
  backdrop-filter: none !important;
}

.session-manager-drawer .drawer-card {
  background: #ffffff !important;
  border-color: rgba(15, 23, 42, 0.1) !important;
  -webkit-backdrop-filter: none !important;
  backdrop-filter: none !important;
  box-shadow: none !important;
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
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
}

.account-menu-item:hover {
  background: var(--bg-elevated);
}

.session-confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.18);
}

.session-confirm-modal {
  width: min(420px, 100%);
  padding: 24px;
}

.session-confirm-modal h2 {
  margin: 0 0 8px;
  color: var(--text-primary);
  font-size: 1.1rem;
}

.session-confirm-modal p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.5;
}

.session-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

.logo-img {
  height: 32px;
  width: auto;
  display: block;
}

/* Tablet: nav pills wrap */
@media (max-width: 1023px) {
  .topbar {
    padding: 0 var(--page-padding);
  }

  .topbar-left {
    gap: var(--space-md);
    min-width: 0;
  }

  .topbar-left > div:first-child {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: var(--space-sm);
  }

  .theme-adaptive-nav {
    flex-wrap: wrap;
    gap: 4px;
  }

  .top-nav-pill {
    font-size: var(--text-xs);
    padding: 4px 10px;
  }
}

/* Mobile: hamburger nav */
@media (max-width: 480px) {
  .theme-adaptive-nav {
    display: none;
  }

  .hamburger-btn {
    display: inline-flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 4px;
    width: 36px;
    height: 36px;
    padding: 6px;
    border: 1px solid var(--glass-border-soft);
    border-radius: var(--radius-md);
    background: linear-gradient(180deg, rgba(255,255,255,0.32), rgba(255,255,255,0.16));
    cursor: pointer;
  }

  .hamburger-btn span {
    display: block;
    width: 18px;
    height: 2px;
    border-radius: 2px;
    background: var(--text-primary);
    transition: transform 0.2s ease, opacity 0.2s ease;
  }

  .hamburger-btn.active span:nth-child(1) {
    transform: translateY(6px) rotate(45deg);
  }

  .hamburger-btn.active span:nth-child(2) {
    opacity: 0;
  }

  .hamburger-btn.active span:nth-child(3) {
    transform: translateY(-6px) rotate(-45deg);
  }

  .topbar-tagline {
    display: none;
  }

  .nav-overlay {
    position: fixed;
    inset: 0;
    z-index: 100;
    background: rgba(15, 23, 42, 0.18);
  }

  .nav-drawer {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 101;
    width: min(280px, 85vw);
    padding: var(--space-lg);
    background: #ffffff;
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
    box-shadow: 0 0 40px rgba(15, 23, 42, 0.12);
  }

  .nav-drawer-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--space-lg);
    padding-bottom: var(--space-md);
    border-bottom: 1px solid var(--glass-border-soft);
  }

  .nav-drawer-close {
    width: 32px;
    height: 32px;
    border: 1px solid var(--glass-border-soft);
    border-radius: var(--radius-md);
    background: transparent;
    font-size: 1.2rem;
    cursor: pointer;
  }

  .nav-drawer-item {
    display: block;
    padding: var(--space-md) var(--space-lg);
    border-radius: var(--radius-md);
    color: var(--text-primary);
    font-size: var(--text-base);
    font-weight: 600;
    text-decoration: none;
  }

  .nav-drawer-item.active {
    background: rgba(0, 168, 132, 0.1);
    color: var(--accent);
  }

  .topbar-right {
    gap: var(--space-sm);
  }

  .user-pill {
    padding: 4px 10px;
    max-width: 120px;
    font-size: var(--text-xs);
  }

  .toolbar-count {
    font-size: var(--text-xs);
  }

  .session-manager-drawer {
    inset: 0 !important;
    border-radius: 0 !important;
    width: 100% !important;
    max-width: 100% !important;
  }
}

/* Ensure hamburger is hidden on desktop */
@media (min-width: 481px) {
  .hamburger-btn {
    display: none;
  }
}

.create-user-modal {
  width: 440px;
  max-width: 90%;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.create-user-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.create-user-head h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
}

.create-user-head p {
  margin: 4px 0 0;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.create-user-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.create-user-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
}

.create-user-password-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.create-user-password-input {
  width: 100%;
  padding-right: 40px !important;
}

.create-user-password-toggle {
  position: absolute;
  right: 12px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.create-user-password-toggle svg {
  width: 20px;
  height: 20px;
  stroke: currentColor;
  stroke-width: 2;
  fill: none;
}

.create-user-password-input::-ms-reveal,
.create-user-password-input::-ms-clear {
  display: none !important;
}

.create-user-error {
  margin: 0;
  color: #b42318;
  font-size: 0.875rem;
  font-weight: 500;
}

.create-user-success {
  margin: 0;
  color: #027a48;
  font-size: 0.875rem;
  font-weight: 500;
}
</style>
