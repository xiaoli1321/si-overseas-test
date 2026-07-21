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

// ─── Create account ───
const showCreate = ref(false);
const createForm = ref({ email: '', password: '', distributorName: '', role: 'dealer' as 'dealer' | 'manager' });
const creating = ref(false);
const createError = ref('');

function openCreate() {
  createForm.value = { email: '', password: '', distributorName: '', role: 'dealer' };
  createError.value = '';
  showCreate.value = true;
}

function closeCreate() {
  showCreate.value = false;
}

async function submitCreate() {
  const { email, password, distributorName, role } = createForm.value;
  if (!email.trim() || !distributorName.trim()) {
    createError.value = 'Email and dealer name are required.';
    return;
  }
  if (password.trim().length < 8) {
    createError.value = 'Password must be at least 8 characters.';
    return;
  }
  creating.value = true;
  createError.value = '';
  try {
    await store.createUserRemote(email.trim(), password, distributorName.trim(), role);
    showCreate.value = false;
    await loadAccounts();
  } catch (err) {
    createError.value = (err as Error).message || 'Failed to create account.';
  } finally {
    creating.value = false;
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
            Accounts you have created. Passwords are stored one-way (hashed) and cannot be shown &mdash;
            use <strong>Reset password</strong> to set a new one, which is displayed once so you can pass it on.
          </p>
        </div>
        <button class="btn btn-primary" type="button" data-test="account-create-open" @click="openCreate">&#43; New account</button>
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
                  No accounts yet. Click <strong>New account</strong> to create your first dealer login.
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

    <!-- Create account modal -->
    <div v-if="showCreate" class="modal-overlay accounts-modal-overlay" role="presentation" @click.self="closeCreate" data-test="account-create-modal">
      <section class="modal accounts-modal" role="dialog" aria-modal="true" aria-labelledby="account-create-title">
        <h2 id="account-create-title">New account</h2>
        <label class="accounts-field">
          <span>Email</span>
          <input v-model="createForm.email" class="form-input" type="email" autocomplete="off" placeholder="dealer@example.com" />
        </label>
        <label class="accounts-field">
          <span>Dealer / Organization name</span>
          <input v-model="createForm.distributorName" class="form-input" type="text" placeholder="e.g. Germany Dealer" />
        </label>
        <label class="accounts-field">
          <span>Password (min 8 chars)</span>
          <input v-model="createForm.password" class="form-input" type="text" autocomplete="off" placeholder="Set an initial password" />
        </label>
        <label class="accounts-field">
          <span>Role</span>
          <select v-model="createForm.role" class="form-input">
            <option value="dealer">dealer</option>
            <option value="manager">manager</option>
          </select>
        </label>
        <p v-if="createError" class="accounts-modal-error" data-test="account-create-error">{{ createError }}</p>
        <div class="modal-actions accounts-modal-actions">
          <button class="btn btn-secondary btn-sm" type="button" @click="closeCreate">Cancel</button>
          <button class="btn btn-primary btn-sm" type="button" data-test="account-create-submit" :disabled="creating" @click="submitCreate">
            {{ creating ? 'Creating…' : 'Create account' }}
          </button>
        </div>
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
</style>
