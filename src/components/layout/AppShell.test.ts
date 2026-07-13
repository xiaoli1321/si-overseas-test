import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';
import AppShell from './AppShell.vue';

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'login', component: { template: '<div>Login</div>' } },
      { path: '/chat', name: 'chat', component: { template: '<div>Chat</div>' } },
      { path: '/detect', redirect: '/chat' },
      { path: '/thresholds', name: 'thresholds', component: { template: '<div>Thresholds</div>' } },
      { path: '/records', name: 'records', component: { template: '<div>Records</div>' } },
      { path: '/detect/:sn', name: 'detect', component: { template: '<div>Detect</div>' } },
      { path: '/fault-query/:categoryKey', name: 'fault-query', component: { template: '<div>Fault Query</div>' } },
      { path: '/multi-detect/:batchId', name: 'multi-detect', component: { template: '<div>Multi</div>' } },
    ],
  });
}

async function mountShell() {
  const router = makeRouter();
  await router.push('/chat');
  await router.isReady();

  const wrapper = mount(AppShell, {
    global: {
      plugins: [router],
    },
    slots: {
      default: '<main>Content</main>',
    },
  });

  return wrapper;
}

describe('AppShell', () => {
  afterEach(() => {
    useDemoStore().resetDemoState();
  });

  it('removes network and theme controls from the light-only shell', async () => {
    const wrapper = await mountShell();

    expect(wrapper.find('.topbar-status').exists()).toBe(false);
    expect(wrapper.find('.theme-toggle').exists()).toBe(false);
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });

  it('shows device-detect-first navigation without a separate device query tab', async () => {
    const wrapper = await mountShell();

    expect(wrapper.find('[data-test="brand-logo"]').exists()).toBe(false);
    expect(wrapper.find('.logo-mark').text()).toBe('SI');
    expect(wrapper.find('.topbar-tagline').text()).toBe('CGM AI Service Desk');
    const navLinks = wrapper.findAll('.nav a');
    expect(navLinks.map(link => link.text())).toEqual(['Device detection', 'Thresholds', 'Detection records']);
    expect(navLinks.every(link => link.classes().includes('top-nav-pill'))).toBe(true);
    expect(wrapper.find('.nav').classes()).toContain('theme-adaptive-nav');
    expect(navLinks[0].classes()).toContain('active');
    expect(wrapper.find('select[aria-label="Language"]').exists()).toBe(false);
  });

  it('keeps session and account overlays on light surfaces', async () => {
    const wrapper = await mountShell();
    const store = useDemoStore();
    store.startDetectSession('P2251212806JND44', 'Sensor falling off', {
      source: 'multi',
      batchId: 'MULTI-0001',
      stepLabel: 'Retrieving device information',
      progress: 20,
    });

    await wrapper.find('button[aria-label="Session manager"]').trigger('click');
    await wrapper.find('.user-pill').trigger('click');

    expect(wrapper.find('.side-drawer').classes()).toContain('theme-surface');
    expect(wrapper.find('[data-test="account-menu"]').classes()).toContain('theme-surface');
  });

  it('shows processing sessions before detection records are submitted', async () => {
    const wrapper = await mountShell();
    const store = useDemoStore();

    const session = store.startDetectSession('P2251212806JND44', 'Sensor falling off');
    await wrapper.find('button[aria-label="Session manager"]').trigger('click');
    const sessionsBody = () => wrapper.findAll('.drawer-body')[1];

    expect(wrapper.find('.toolbar-count').text()).toBe('1');
    expect(sessionsBody().text()).toContain('Processing');
    expect(sessionsBody().text()).toContain('P2251212806JND44');
    expect(sessionsBody().text()).toContain('View progress');
    expect(store.records.value).toEqual([]);

    store.runDetect('P2251212806JND44');
    store.completeDetectSession(session.id, store.records.value[0]);
    await wrapper.vm.$nextTick();

    expect(wrapper.find('.toolbar-count').text()).toBe('1');
    expect(sessionsBody().text()).toContain('Completed');
    expect(wrapper.find('.session-list').text()).toContain('P2251212806JND44');
  });

  it('groups multi-device progress details in the session manager', async () => {
    const wrapper = await mountShell();
    const store = useDemoStore();

    store.startDetectSession('P2251212806JND44', 'Sensor falling off', {
      source: 'multi',
      batchId: 'MULTI-0001',
      stepLabel: 'Running batch rule checks',
      progress: 60,
    });
    const completeSession = store.startDetectSession('P2251212813RVK19', 'Sensor falling off', {
      source: 'multi',
      batchId: 'MULTI-0001',
      stepLabel: 'Complete',
      progress: 100,
    });
    const record = store.runDetect('P2251212813RVK19', 'Sensor falling off');
    store.completeDetectSession(completeSession.id, record);
    await wrapper.find('button[aria-label="Session manager"]').trigger('click');

    const sessionsBody = wrapper.findAll('.drawer-body')[1];
    expect(wrapper.find('.toolbar-count').text()).toBe('1');
    expect(sessionsBody.text()).toContain('Sensor falling off');
    expect(sessionsBody.text()).toContain('2 devices');
    expect(sessionsBody.text()).toContain('1/2 complete');
    expect(sessionsBody.text()).toContain('Running batch rule checks');
  });

  it('opens grouped multi-device progress on the multi-device detect page', async () => {
    const router = makeRouter();
    await router.push('/chat');
    await router.isReady();
    const wrapper = mount(AppShell, {
      global: { plugins: [router] },
      slots: { default: '<main>Content</main>' },
    });
    const store = useDemoStore();

    store.startDetectSession('P2251212806JND44', 'Sensor falling off', {
      source: 'multi',
      batchId: 'MULTI-0001',
      stepLabel: 'Running batch rule checks',
      progress: 60,
    });
    store.startDetectSession('P2251212813RVK19', 'Sensor falling off', {
      source: 'multi',
      batchId: 'MULTI-0001',
      stepLabel: 'Retrieving device information',
      progress: 20,
    });

    await wrapper.find('button[aria-label="Session manager"]').trigger('click');
    await wrapper.find('button[data-test="session-view-progress"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('multi-detect');
    expect(router.currentRoute.value.params.batchId).toBe('MULTI-0001');
    expect(router.currentRoute.value.query.category).toBe('Sensor falling off');
    expect(store.records.value).toEqual([]);
  });

  it('lets session manager open a verdict, open records, and clear sessions', async () => {
    const router = makeRouter();
    await router.push('/chat');
    await router.isReady();
    const wrapper = mount(AppShell, {
      global: { plugins: [router] },
      slots: { default: '<main>Content</main>' },
    });
    const store = useDemoStore();
    const session = store.startDetectSession('P2251212806JND44', 'Sensor falling off');
    const record = store.runDetect('P2251212806JND44', 'Sensor falling off');
    store.completeDetectSession(session.id, record);
    await wrapper.vm.$nextTick();

    await wrapper.find('button[aria-label="Session manager"]').trigger('click');
    await wrapper.find('button[data-test="session-view-result"]').trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.name).toBe('detect');
    expect(router.currentRoute.value.params.sn).toBe('P2251212806JND44');
    expect(router.currentRoute.value.query.category).toBe('Sensor falling off');
    expect(router.currentRoute.value.query.record).toBe(record.id);
    expect(router.currentRoute.value.query.from).toBe('records');

    await wrapper.find('button[aria-label="Session manager"]').trigger('click');
    await wrapper.find('button[data-test="session-open-records"]').trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.name).toBe('records');

    await wrapper.find('button[aria-label="Session manager"]').trigger('click');
    await wrapper.find('button[data-test="session-clear"]').trigger('click');
    expect(store.sessions.value).toHaveLength(0);
    expect(wrapper.find('.toolbar-count').text()).toBe('0');
  });

  it('highlights detect record while viewing a verdict opened from records', async () => {
    const router = makeRouter();
    await router.push('/chat');
    await router.isReady();
    const wrapper = mount(AppShell, {
      global: { plugins: [router] },
      slots: { default: '<main>Content</main>' },
    });
    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: { category: 'Sensor falling off', record: 'REC-1', from: 'records' },
    });
    await flushPromises();

    const navLinks = wrapper.findAll('.nav a');
    expect(navLinks[2].classes()).toContain('active');
    expect(navLinks[0].classes()).not.toContain('active');
  });

  it('highlights device detect while viewing a verdict opened from fault query', async () => {
    const router = makeRouter();
    await router.push('/chat');
    await router.isReady();
    const wrapper = mount(AppShell, {
      global: { plugins: [router] },
      slots: { default: '<main>Content</main>' },
    });
    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: { category: 'Sensor falling off', from: 'fault-query' },
    });
    await flushPromises();

    const navLinks = wrapper.findAll('.nav a');
    expect(navLinks[0].classes()).toContain('active');
    expect(navLinks[2].classes()).not.toContain('active');
  });

  it('highlights device detect while viewing a multi-device detect run', async () => {
    const router = makeRouter();
    await router.push('/chat');
    await router.isReady();
    const wrapper = mount(AppShell, {
      global: { plugins: [router] },
      slots: { default: '<main>Content</main>' },
    });
    await router.push({
      name: 'multi-detect',
      params: { batchId: 'MULTI-0001' },
      query: { category: 'Sensor falling off' },
    });
    await flushPromises();

    const navLinks = wrapper.findAll('.nav a');
    expect(navLinks[0].classes()).toContain('active');
    expect(navLinks[2].classes()).not.toContain('active');
  });

  it('opens an account dropdown with sign out only', async () => {
    const router = makeRouter();
    await router.push('/chat');
    await router.isReady();
    const wrapper = mount(AppShell, {
      global: { plugins: [router] },
      slots: { default: '<main>Content</main>' },
    });

    await wrapper.find('.user-pill').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('chat');
    expect(wrapper.find('[data-test="account-menu"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="account-manage"]').exists()).toBe(false);
    expect(wrapper.find('[data-test="account-menu"]').text()).toContain('Chris Overseas Dealer');

    await wrapper.find('[data-test="account-sign-out"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('login');
  });
});
