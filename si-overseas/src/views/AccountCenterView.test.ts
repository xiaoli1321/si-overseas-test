import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { backendApi } from '@/api/backend';
import { useDemoStore } from '@/composables/useDemoStore';
import AccountCenterView from './AccountCenterView.vue';

const MANAGER = {
  email: 'manager@sibionics.com',
  displayName: 'Manager User',
  role: 'manager' as const,
  dealerId: 'manager-id',
  dealerName: 'Manager Name',
  organizationName: 'Manager Name',
  organizationType: 'Distributor' as const,
  region: 'A Region',
};

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/chat', name: 'chat', component: { template: '<div>chat</div>' } },
      { path: '/accounts', name: 'accounts', component: AccountCenterView },
    ],
  });
}

async function mountAsManager() {
  const store = useDemoStore();
  store.currentAccountProfile.value = { ...MANAGER };
  // Keep backend offline during mount so loadRemoteBootstrap()/loadAccounts()
  // no-op (no network); the role guard still passes via currentAccountProfile.
  store.backendOnline.value = false;
  const router = makeRouter();
  await router.push('/accounts');
  await router.isReady();
  const wrapper = mount(AccountCenterView, { global: { plugins: [router] } });
  await flushPromises();
  return { wrapper, router, store };
}

describe('AccountCenterView', () => {
  afterEach(() => {
    useDemoStore().resetDemoState();
    vi.restoreAllMocks();
  });

  it('creates an account (no role field) and closes the modal', async () => {
    const { wrapper, store } = await mountAsManager();
    expect(store.isManager.value).toBe(true);

    store.backendOnline.value = true;
    vi.spyOn(backendApi, 'getUsers').mockResolvedValue([]);
    const createSpy = vi.spyOn(backendApi, 'createUser').mockResolvedValue({
      ...MANAGER,
      email: 'newdealer@sibionics.com',
      role: 'dealer',
    });

    await wrapper.find('[data-test="account-create-open"]').trigger('click');
    expect(wrapper.find('[data-test="create-user-form"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="create-user-role"]').exists()).toBe(false);

    await wrapper.find('[data-test="create-user-email"]').setValue('newdealer@sibionics.com');
    await wrapper.find('[data-test="create-user-distributor"]').setValue('New Distributor');
    await wrapper.find('[data-test="create-user-password"]').setValue('password123');
    await wrapper.find('[data-test="create-user-confirm-password"]').setValue('password123');
    await wrapper.find('[data-test="create-user-form"]').trigger('submit');
    await flushPromises();

    expect(createSpy).toHaveBeenCalledWith({
      email: 'newdealer@sibionics.com',
      password: 'password123',
      distributorName: 'New Distributor',
    });
    expect(wrapper.find('[data-test="create-user-form"]').exists()).toBe(false);
  });

  it('blocks submit when passwords do not match', async () => {
    const { wrapper, store } = await mountAsManager();
    store.backendOnline.value = true;
    const createSpy = vi.spyOn(backendApi, 'createUser');

    await wrapper.find('[data-test="account-create-open"]').trigger('click');
    await wrapper.find('[data-test="create-user-email"]').setValue('x@sibionics.com');
    await wrapper.find('[data-test="create-user-distributor"]').setValue('Org');
    await wrapper.find('[data-test="create-user-password"]').setValue('password123');
    await wrapper.find('[data-test="create-user-confirm-password"]').setValue('different1');
    await wrapper.find('[data-test="create-user-form"]').trigger('submit');
    await flushPromises();

    expect(createSpy).not.toHaveBeenCalled();
    expect(wrapper.find('[data-test="create-user-error"]').text()).toContain('Passwords do not match');
  });

  it('toggles password visibility with the icon buttons', async () => {
    const { wrapper } = await mountAsManager();
    await wrapper.find('[data-test="account-create-open"]').trigger('click');

    const passwordInput = () => wrapper.find('[data-test="create-user-password"]').element as HTMLInputElement;
    const confirmInput = () => wrapper.find('[data-test="create-user-confirm-password"]').element as HTMLInputElement;

    expect(passwordInput().type).toBe('password');
    expect(confirmInput().type).toBe('password');

    await wrapper.find('[data-test="create-user-password-toggle"]').trigger('click');
    await wrapper.find('[data-test="create-user-confirm-password-toggle"]').trigger('click');

    expect(passwordInput().type).toBe('text');
    expect(confirmInput().type).toBe('text');
  });
});
