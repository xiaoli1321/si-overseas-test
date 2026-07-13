import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';
import FaultQueryView from './FaultQueryView.vue';

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/chat', name: 'chat', component: { template: '<div>Chat</div>' } },
      { path: '/fault-query/:categoryKey', name: 'fault-query', component: FaultQueryView, props: true },
      { path: '/multi-detect/:batchId', name: 'multi-detect', component: { template: '<div>Multi</div>' } },
      { path: '/detect/:sn', name: 'detect', component: { template: '<div>Detect</div>' } },
    ],
  });
}

async function mountFaultQuery(categoryKey = 'data-accuracy', query: Record<string, string> = {}) {
  const router = makeRouter();
  await router.push({ name: 'fault-query', params: { categoryKey }, query });
  await router.isReady();
  const wrapper = mount(FaultQueryView, {
    props: { categoryKey },
    global: {
      plugins: [router],
    },
  });
  return { router, wrapper };
}

describe('FaultQueryView', () => {
  afterEach(() => {
    vi.useRealTimers();
    useDemoStore().resetDemoState();
  });

  it('shows the selected fault context and an empty selected-devices workspace', async () => {
    const { wrapper } = await mountFaultQuery('sensor-falling-off');

    expect(wrapper.find('.fault-query-rail-title').text()).toBe('Sensor falling off');
    expect(wrapper.text()).toContain('The sensor unexpectedly fell out while the user was wearing it.');
    expect(wrapper.find('textarea[aria-label="Fault SN lookup input"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="selected-devices"]').text()).toContain('No devices selected yet');
    expect(wrapper.text()).not.toContain('Batch Query');
  });

  it('adds a full SN to selected devices before opening single-device detect', async () => {
    const { router, wrapper } = await mountFaultQuery('data-accuracy');

    await wrapper.find('textarea[aria-label="Fault SN lookup input"]').setValue('P2251212806JND44');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('fault-query');
    expect(wrapper.find('[data-test="selected-devices"]').text()).toContain('P2251212806JND44');
    expect(wrapper.find('[data-test="run-selected"]').text()).toBe('Run detection');

    await wrapper.find('[data-test="run-selected"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('detect');
    expect(router.currentRoute.value.params.sn).toBe('P2251212806JND44');
    expect(router.currentRoute.value.query.category).toBe('Data accuracy');
    expect(router.currentRoute.value.query.from).toBe('fault-query');
  });

  it('shows fuzzy candidates and adds the chosen candidate without navigating', async () => {
    const { router, wrapper } = await mountFaultQuery('application-failure');

    await wrapper.find('textarea[aria-label="Fault SN lookup input"]').setValue('P22512128');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('fault-query');
    expect(wrapper.findAll('[data-test="candidate-device"]').length).toBeGreaterThan(1);

    await wrapper.find('[data-test="candidate-device"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-test="selected-devices"]').text()).toContain('P2251212806JND44');
    expect(router.currentRoute.value.name).toBe('fault-query');
  });

  it('keeps selected devices under the search command and matching candidates at the bottom', async () => {
    const { wrapper } = await mountFaultQuery('application-failure');

    await wrapper.find('textarea[aria-label="Fault SN lookup input"]').setValue('P22512128');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    const form = wrapper.find('.fault-query-command').element;
    const selected = wrapper.find('[data-test="selected-devices"]').element;
    const candidates = wrapper.find('.fault-query-results').element;

    expect(Boolean(form.compareDocumentPosition(selected) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
    expect(Boolean(selected.compareDocumentPosition(candidates) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
  });

  it('parses pasted SN lines, adds unique matches, and keeps ambiguous or missing lines pending', async () => {
    const { wrapper } = await mountFaultQuery('data-accuracy');

    await wrapper.find('textarea[aria-label="Fault SN lookup input"]').setValue([
      'P2251212806JND44',
      'P2251212806JND44',
      'RVK19',
      'P22512128',
      'NO-SUCH-SN',
    ].join('\n'));
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    const selected = wrapper.find('[data-test="selected-devices"]').text();
    expect(selected).toContain('P2251212806JND44');
    expect(selected).toContain('P2251212813RVK19');
    expect(wrapper.findAll('[data-test="selected-device-row"]')).toHaveLength(2);
    expect(wrapper.find('[data-test="pending-lines"]').text()).toContain('P22512128 matches');
    expect(wrapper.find('[data-test="pending-lines"]').text()).toContain('NO-SUCH-SN was not found');
  });

  it('removes selected devices and disables running when none remain', async () => {
    const { wrapper } = await mountFaultQuery('data-accuracy');

    await wrapper.find('textarea[aria-label="Fault SN lookup input"]').setValue('P2251212806JND44');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    await wrapper.find('[data-test="remove-selected-device"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-test="selected-devices"]').text()).toContain('No devices selected yet');
    expect(wrapper.find('[data-test="run-selected"]').attributes('disabled')).toBeDefined();
  });

  it('starts multiple selected devices and navigates to the multi-device detect page', async () => {
    const { router, wrapper } = await mountFaultQuery('sensor-falling-off');
    const store = useDemoStore();

    await wrapper.find('textarea[aria-label="Fault SN lookup input"]').setValue('P2251212806JND44\nP2251212813RVK19');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    expect(wrapper.find('[data-test="run-selected"]').text()).toBe('Run detection for 2 devices');
    await wrapper.find('[data-test="run-selected"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('multi-detect');
    expect(router.currentRoute.value.query.category).toBe('Sensor falling off');
    expect(router.currentRoute.value.params.batchId).toEqual(expect.stringMatching(/^MULTI-/));
    expect(store.sessions.value).toHaveLength(2);
    expect(new Set(store.sessions.value.map(session => session.batchId)).size).toBe(1);
    expect(store.sessions.value.every(session => (
      session.source === 'multi' && session.faultCategory === 'Sensor falling off'
    ))).toBe(true);
  });
});
