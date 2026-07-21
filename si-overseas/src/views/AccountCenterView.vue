<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';
import { backendApi, type ManagedUser } from '@/api/backend';

const router = useRouter();
const store = useDemoStore();

const accounts = ref<ManagedUser[]>([]);
const loading = ref(false);
const loadError = ref('');

async function loadAccounts() {
  if (!store.backendOnline.value) return;
  loading.value = true;
  loadError.value = '';
  try {
    accounts.value = await backendApi.getUsers();
  } catch (err) {
    loadError.value = (err as Error).message || 'Failed to load accounts.';
    accounts.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await store.loadRemoteBootstrap();
  // Defense in depth: the nav entry is manager-only, but guard the route too.
  if (!store.isManager.value) {
    router.replace({ name: 'chat' });
    return;
  }
  void loadAccounts();
});

function formatTs(iso: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(d);
}

// ─── Create account (same UX/style as the former top-bar "Create user") ───
const createUserOpen = ref(false);
const createUserEmail = ref('');
const createUserPassword = ref('');
const createUserConfirmPassword = ref('');
const createUserDistributorName = ref('');
const createUserError = ref('');
const createUserSubmitting = ref(false);
const showCreateUserPassword = ref(false);
const showCreateUserConfirmPassword = ref(false);

function openCreateUser() {
  createUserOpen.value = true;
  createUserError.value = '';
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
    await store.createUserRemote(email, password, distributorName);
    createUserOpen.value = false;
    await loadAccounts();
  } catch (err: any) {
    createUserError.value = err?.message || 'Failed to create account.';
  } finally {
    createUserSubmitting.value = false;
  }
}

// ─── Reset password ───
const resetTarget = ref<ManagedUser | null>(null);
const resetPasswordInput = ref('');
const resetting = ref(false);
const resetError = ref('');
const resetResult = ref<{ email: string; password: string } | null>(null);
const copied = ref(false);

function openReset(account: ManagedUser) {
  resetTarget.value = account;
  resetPasswordInput.value = '';
  resetError.value = '';
  resetResult.value = null;
  copied.value = false;
}

function closeReset() {
  resetTarget.value = null;
  resetResult.value = null;
}

async function submitReset() {
  const target = resetTarget.value;
  if (!target) return;
  const custom = resetPasswordInput.value.trim();
  if (custom && custom.length < 8) {
    resetError.value = 'Password must be at least 8 characters.';
    return;
  }
  resetting.value = true;
  resetError.value = '';
  try {
    const result = await backendApi.resetUserPassword(target.id, custom || undefined);
    resetResult.value = { email: result.email, password: result.password };
  } catch (err) {
    resetError.value = (err as Error).message || 'Failed to reset password.';
  } finally {
    resetting.value = false;
  }
}

async function copyPassword() {
  if (!resetResult.value) return;
  try {
    await navigator.clipboard.writeText(resetResult.value.password);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 1600);
  } catch {
    copied.value = false;
  }
}
</script>

<template>
  <div class="page active" id="page-accounts">
    <div class="page-body accounts-page-body">
      <div class="logs-header slide-up stagger-1">
        <div>
          <h1>Account Center</h1>
          <p style="color: var(--text-secondary); font-size: var(--text-sm); margin-top: 6px; max-width: 620px">
            Accounts you manage. Passwords are stored one-way (hashed) and cannot be shown &mdash;
            use <strong>Reset password</strong> to set a new one, which is displayed once so you can pass it on.
          </p>
        </div>
        <button class="btn btn-primary" type="button" data-test="account-create-open" @click="openCreateUser">&#43; Create account</button>
      </div>

      <div class="table-wrap slide-up stagger-2">
        <div v-if="loadError" class="accounts-error" data-test="accounts-error">{{ loadError }}</div>
        <table class="records-table accounts-table">
          <thead>
            <tr>
              <th>Account (email)</th>
              <th>Role</th>
              <th>Dealer / Organization</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="5"><div class="empty-state" style="padding: 28px">Loading accounts&hellip;</div></td>
            </tr>
            <tr v-else-if="!accounts.length">
              <td colspan="5">
                <div class="empty-state" style="padding: 28px">
                  No accounts yet. Click <strong>Create account</strong> to create your first dealer login.
                </div>
              </td>
            </tr>
            <tr v-for="account in accounts" :key="account.id" :data-test="`account-row-${account.id}`">
              <td class="mono records-cell-wrap">{{ account.email }}</td>
              <td class="records-cell-wrap">
                <span class="badge" :class="account.role === 'manager' ? 'badge-teal' : 'badge-gray'">{{ account.role }}</span>
              </td>
              <td class="records-cell-wrap">{{ account.dealerName }}</td>
              <td class="records-cell-wrap" style="font-size:0.82rem">{{ formatTs(account.createdAt) }}</td>
              <td class="records-cell-wrap">
                <button class="btn btn-secondary btn-sm" type="button" :data-test="`account-reset-${account.id}`" @click="openReset(account)">
                  Reset password
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Create account modal (ported from the former top-bar Create user, same style) -->
    <div v-if="createUserOpen" class="modal-overlay accounts-modal-overlay" role="presentation" @click.self="closeCreateUser" data-test="account-create-modal">
      <section class="modal create-user-modal" role="dialog" aria-modal="true" aria-labelledby="create-user-title">
        <div class="create-user-head">
          <div>
            <h2 id="create-user-title">Create account</h2>
            <p>New users can sign in after the account is created.</p>
          </div>
          <button class="toolbar-icon-btn" type="button" aria-label="Close create account dialog" @click="closeCreateUser">&times;</button>
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
          <div class="modal-actions accounts-modal-actions">
            <button class="btn btn-secondary" type="button" :disabled="createUserSubmitting" @click="closeCreateUser">Cancel</button>
            <button class="btn btn-primary" type="submit" :disabled="createUserSubmitting" data-test="create-user-submit">
              {{ createUserSubmitting ? 'Creating...' : 'Create account' }}
            </button>
          </div>
        </form>
      </section>
    </div>

    <!-- Reset password modal -->
    <div v-if="resetTarget" class="modal-overlay accounts-modal-overlay" role="presentation" @click.self="closeReset" data-test="account-reset-modal">
      <section class="modal accounts-modal" role="dialog" aria-modal="true" aria-labelledby="account-reset-title">
        <h2 id="account-reset-title">Reset password</h2>
        <template v-if="!resetResult">
          <p class="accounts-reset-hint">
            Set a new password for <strong>{{ resetTarget.email }}</strong>, or leave blank to generate one automatically.
          </p>
          <label class="accounts-field">
            <span>New password (optional)</span>
            <input v-model="resetPasswordInput" class="form-input" type="text" autocomplete="off" placeholder="Leave blank to auto-generate" />
          </label>
          <p v-if="resetError" class="accounts-modal-error" data-test="account-reset-error">{{ resetError }}</p>
          <div class="modal-actions accounts-modal-actions">
            <button class="btn btn-secondary btn-sm" type="button" @click="closeReset">Cancel</button>
            <button class="btn btn-primary btn-sm" type="button" data-test="account-reset-submit" :disabled="resetting" @click="submitReset">
              {{ resetting ? 'Resetting…' : 'Reset password' }}
            </button>
          </div>
        </template>
        <template v-else>
          <p class="accounts-reset-hint">
            New password for <strong>{{ resetResult.email }}</strong>. This is shown <strong>once</strong> &mdash; copy it now.
          </p>
          <div class="accounts-password-reveal" data-test="account-reset-result">
            <code>{{ resetResult.password }}</code>
            <button class="btn btn-secondary btn-sm" type="button" @click="copyPassword">{{ copied ? 'Copied' : 'Copy' }}</button>
          </div>
          <div class="modal-actions accounts-modal-actions">
            <button class="btn btn-primary btn-sm" type="button" data-test="account-reset-done" @click="closeReset">Done</button>
          </div>
        </template>
      </section>
    </div>
  </div>
</template>

<style scoped>
.accounts-page-body {
  max-width: min(1100px, calc(100vw - 48px));
  padding-left: 24px;
  padding-right: 24px;
}

.accounts-table {
  width: 100%;
}

.accounts-error {
  margin-bottom: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(234, 67, 53, 0.08);
  color: #c5221f;
  font-size: 0.85rem;
}

.accounts-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.18);
}

.accounts-modal {
  width: min(460px, 100%);
  padding: 24px;
}

.accounts-modal h2 {
  margin: 0 0 16px;
  color: var(--text-primary);
  font-size: 1.1rem;
}

.accounts-field {
  display: block;
  margin-bottom: 14px;
}

.accounts-field > span {
  display: block;
  margin-bottom: 6px;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.accounts-modal-error {
  margin: 4px 0 0;
  color: #c5221f;
  font-size: 0.82rem;
}

.accounts-reset-hint {
  margin: 0 0 14px;
  color: var(--text-secondary);
  line-height: 1.5;
  font-size: 0.88rem;
}

.accounts-password-reveal {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid rgba(0, 168, 132, 0.4);
  background: rgba(0, 168, 132, 0.08);
  margin-bottom: 16px;
}

.accounts-password-reveal code {
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.accounts-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
}

/* ── Create-account modal (ported from the former top-bar Create user) ── */
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
</style>
