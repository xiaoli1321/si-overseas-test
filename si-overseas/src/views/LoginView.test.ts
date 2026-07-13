import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';
import LoginView from './LoginView.vue';

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'login', component: LoginView },
      { path: '/chat', name: 'chat', component: { template: '<div>Agent Chat</div>' } },
      { path: '/detect', name: 'detect', component: { template: '<div>Fault Detect</div>' } },
    ],
  });
}

describe('LoginView', () => {
  afterEach(() => {
    vi.useRealTimers();
    useDemoStore().resetDemoState();
  });

  it('types the login hero copy progressively', async () => {
    vi.useFakeTimers();
    const router = makeRouter();
    await router.push('/');
    await router.isReady();

    const wrapper = mount(LoginView, {
      global: {
        plugins: [router],
      },
    });

    expect(wrapper.find('.text-type__content').text()).toBe('');

    await vi.advanceTimersByTimeAsync(120 + 75 * 'Device'.length);

    expect(wrapper.find('.text-type__content').text()).toBe('Device');
    wrapper.unmount();
  });

  it('navigates to agent chat after sign in', async () => {
    const router = makeRouter();
    await router.push('/');
    await router.isReady();

    const wrapper = mount(LoginView, {
      global: {
        plugins: [router],
      },
    });

    await wrapper.find('#login-email').setValue('christest@sibionics.com');
    await wrapper.find('input[type="password"]').setValue('password123');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe('/chat');
  });

  it('uses a standard email and password form without demo account chips', async () => {
    const router = makeRouter();
    await router.push('/');
    await router.isReady();

    const wrapper = mount(LoginView, {
      global: {
        plugins: [router],
      },
    });

    expect(wrapper.find('[data-test^="demo-account-"]').exists()).toBe(false);
    await wrapper.find('#login-email').setValue('christest@sibionics.com');
    await wrapper.find('input[type="password"]').setValue('password123');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    expect(useDemoStore().currentUser.value).toBe('christest@sibionics.com');
    expect(router.currentRoute.value.fullPath).toBe('/chat');
  });

  it('loads default dealer detection records after sign in', async () => {
    const router = makeRouter();
    await router.push('/');
    await router.isReady();

    const wrapper = mount(LoginView, {
      global: {
        plugins: [router],
      },
    });

    await wrapper.find('#login-email').setValue('christest@sibionics.com');
    await wrapper.find('input[type="password"]').setValue('password123');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    const store = useDemoStore();
    expect(store.records.value.length).toBeGreaterThanOrEqual(4);
    expect(store.records.value.every(record => record.dealerId === store.currentAccount.value.dealerId)).toBe(true);
  });
});
