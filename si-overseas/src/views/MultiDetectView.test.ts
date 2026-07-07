import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';
import MultiDetectView from './MultiDetectView.vue';

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/fault-query/:categoryKey', name: 'fault-query', component: { template: '<div>Fault Query</div>' } },
      { path: '/records', name: 'records', component: { template: '<div>Records</div>' } },
      { path: '/detect/:sn/records/:recordId', name: 'detect-record', component: { template: '<div>Detect Record</div>' } },
      { path: '/detect/:sn', name: 'detect', component: { template: '<div>Detect</div>' } },
      { path: '/multi-detect/:batchId', name: 'multi-detect', component: MultiDetectView, props: true },
    ],
  });
}

async function mountMulti(batchId = 'MULTI-TEST') {
  const router = makeRouter();
  await router.push({
    name: 'multi-detect',
    params: { batchId },
    query: { category: 'Sensor falling off' },
  });
  await router.isReady();
  const wrapper = mount(MultiDetectView, {
    props: { batchId },
    global: { plugins: [router] },
  });
  return { router, wrapper };
}

describe('MultiDetectView', () => {
  afterEach(() => {
    vi.useRealTimers();
    useDemoStore().resetDemoState();
  });

  it('shows a richer multi-device detect workspace and completes same-fault records', async () => {
    vi.useFakeTimers();
    const store = useDemoStore();
    store.startDetectSession('P2251212806JND44', 'Sensor falling off', {
      source: 'multi',
      batchId: 'MULTI-TEST',
      stepLabel: 'Retrieving device information',
      progress: 10,
    });
    store.startDetectSession('P2251212813RVK19', 'Sensor falling off', {
      source: 'multi',
      batchId: 'MULTI-TEST',
      stepLabel: 'Retrieving device information',
      progress: 10,
    });

    const { wrapper } = await mountMulti();

    expect(wrapper.find('[data-test="multi-detect-page"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="multi-summary"]').text()).toContain('2');
    expect(wrapper.find('[data-test="multi-summary"]').text()).toContain('0/2 complete');
    expect(wrapper.findAll('[data-test="multi-device-row"]')).toHaveLength(2);
    expect(wrapper.find('[data-test="multi-device-row"]').text()).toContain('Mapped scenario');
    expect(wrapper.find('[data-test="multi-device-row"]').text()).toContain('Last upload');
    expect(wrapper.find('[data-test="multi-device-row"]').text()).not.toContain('Service card');

    await vi.advanceTimersByTimeAsync(5000);
    await flushPromises();

    expect(wrapper.find('[data-test="multi-summary"]').text()).toContain('2/2 complete');
    expect(wrapper.findAll('[data-test="multi-device-row"]').every(row => row.text().includes('Complete'))).toBe(true);
    expect(store.records.value).toHaveLength(2);
    expect(store.records.value.every(record => record.faultCategory === 'Sensor falling off')).toBe(true);
    expect(wrapper.text()).toContain('Open result');
  });

  it('opens completed device results from the multi-device page', async () => {
    const store = useDemoStore();
    const session = store.startDetectSession('P2251212806JND44', 'Sensor falling off', {
      source: 'multi',
      batchId: 'MULTI-TEST',
      stepLabel: 'Complete',
      progress: 100,
    });
    const record = store.runDetect('P2251212806JND44', 'Sensor falling off');
    store.completeDetectSession(session.id, record);
    const { router, wrapper } = await mountMulti();

    await wrapper.find('[data-test="open-multi-result"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('detect-record');
    expect(router.currentRoute.value.params.sn).toBe('P2251212806JND44');
    expect(router.currentRoute.value.params.recordId).toBe(record.id);
    expect(router.currentRoute.value.query.from).toBe('multi-detect');
    expect(router.currentRoute.value.query.batch).toBe('MULTI-TEST');
    expect(store.selectedDevice.value?.sn).toBe('P2251212806JND44');
    expect(store.selectedDevice.value?.fault?.faultCategory).toBe('Sensor falling off');
  });

  it('replaces the batch page when returning to selected devices so browser back does not reopen batch results', async () => {
    const store = useDemoStore();
    store.startDetectSession('P2251212806JND44', 'Sensor falling off', {
      source: 'multi',
      batchId: 'MULTI-TEST',
      stepLabel: 'Complete',
      progress: 100,
    });
    const { router, wrapper } = await mountMulti();

    await wrapper.find('.fault-query-back').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('fault-query');
    expect(router.currentRoute.value.query.fromBatch).toBe('1');

    router.back();
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('fault-query');
  });

  it('does not let remote processing progress move backward during local animation', async () => {
    vi.useFakeTimers();
    const store = useDemoStore();
    store.startDetectSession('P2251212806JND44', 'Sensor falling off', {
      source: 'multi',
      batchId: 'MULTI-TEST',
      stepLabel: 'Processing',
      progress: 50,
    });

    const { wrapper } = await mountMulti();

    expect(wrapper.text()).toContain('50%');

    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    expect(wrapper.text()).not.toContain('40%');
    expect(wrapper.text()).toContain('60%');
  });
});
