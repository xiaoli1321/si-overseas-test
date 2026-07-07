import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';
import DetectFlowView from './DetectFlowView.vue';

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/chat', name: 'chat', component: { template: '<div>Chat</div>' } },
      { path: '/detect', redirect: '/chat' },
      { path: '/fault-query/:categoryKey', name: 'fault-query', component: { template: '<div>Fault Query</div>' } },
      { path: '/records', name: 'records', component: { template: '<div>Records</div>' } },
      { path: '/detect/:sn', name: 'detect', component: DetectFlowView, props: true },
    ],
  });
}

async function mountDetect(category = 'Data accuracy') {
  const router = makeRouter();
  const sn = 'P2251212806JND44';
  await router.push({ name: 'detect', params: { sn }, query: { category } });
  await router.isReady();

  const wrapper = mount(DetectFlowView, {
    props: { sn },
    global: {
      plugins: [router],
    },
  });

  return { router, wrapper };
}

describe('DetectFlowView', () => {
  afterEach(() => {
    vi.useRealTimers();
    useDemoStore().resetDemoState();
  });

  it('starts on the reference detect form shell after a fault is selected', async () => {
    const { wrapper } = await mountDetect();

    expect(wrapper.find('#page-detect-form').exists()).toBe(true);
    expect(wrapper.find('#diag-form-shell').exists()).toBe(true);
    expect(wrapper.find('.diag-form-header h1').text()).toBe('Data accuracy');
    expect(wrapper.find('.guidance-box').exists()).toBe(true);
    expect(wrapper.find('.card .card-body').text()).toContain('Run automated curve screening');
  });

  it('uses the reference processing UI before showing the verdict', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountDetect();
    const store = useDemoStore();

    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    await flushPromises();

    expect(store.sessions.value).toHaveLength(1);
    expect(store.sessions.value[0]).toMatchObject({
      sn: 'P2251212806JND44',
      faultCategory: 'Data accuracy',
      status: 'processing',
    });
    expect(store.records.value).toEqual([]);
    expect(wrapper.find('#page-processing').exists()).toBe(true);
    expect(wrapper.find('.processing-shell').exists()).toBe(true);
    expect(wrapper.find('.processing-spinner').exists()).toBe(true);
    expect(wrapper.find('.processing-progress-bar').exists()).toBe(true);

    await vi.advanceTimersByTimeAsync(8500);
    await flushPromises();

    expect(wrapper.find('.processing-complete-check').exists()).toBe(true);
    expect(store.records.value).toEqual([]);

    await vi.advanceTimersByTimeAsync(1000);
    await flushPromises();

    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(wrapper.find('.verdict-page').exists()).toBe(true);
    expect(store.sessions.value[0]).toMatchObject({
      status: 'complete',
      recordId: store.records.value[0].id,
    });
  });

  it('routes first-pass data accuracy misses to CGM/BGM deviation upload instead of a not-eligible verdict', async () => {
    const store = useDemoStore();
    store.saveThresholdProfile({
      rules: {
        inaccuracy: {
          ...store.activeThresholdProfile.value.rules.inaccuracy,
          lowPersist: {
            ...store.activeThresholdProfile.value.rules.inaccuracy.lowPersist,
            minHours: 6,
          },
        },
      },
    });
    const { wrapper } = await mountDetect();

    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('#page-inaccuracy-upload').exists()).toBe(true);
    expect(wrapper.find('.diag-form-header').text()).toContain('Blood sugar deviation judgment');
    expect(wrapper.find('.implant-upload-status').text()).toContain('0 / 4 images uploaded');
    expect(store.sessions.value).toEqual([]);
    expect(store.records.value).toEqual([]);
  });

  it('uses the reference application-failure photo upload interaction', async () => {
    const { wrapper } = await mountDetect('Application failure');

    expect(wrapper.find('#page-detect-form').exists()).toBe(true);
    expect(wrapper.find('.implant-hero-bar').text()).toContain('VLM');
    expect(wrapper.findAll('.implant-photo-slot')).toHaveLength(3);
    expect(wrapper.find('.implant-upload-status').text()).toContain('0 / 2 minimum');

    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    expect(wrapper.find('.implant-upload-status').text()).toContain('add at least 2 more photo');

    await wrapper.findAll('.implant-photo-slot')[0].trigger('click');
    await wrapper.findAll('.implant-photo-slot')[1].trigger('click');

    expect(wrapper.find('.implant-upload-status').text()).toContain('2 photo(s) uploaded');
  });

  it('renders a full telemetry review form for non-upload fault types', async () => {
    const { wrapper } = await mountDetect('Sensor falling off');

    expect(wrapper.find('#page-detect-form').exists()).toBe(true);
    expect(wrapper.find('.detect-review-pack').exists()).toBe(true);
    expect(wrapper.find('.detect-review-pack').text()).toContain('Telemetry review pack');
    expect(wrapper.find('.detect-review-grid').text()).toContain('Device state');
    expect(wrapper.find('.detect-review-grid').text()).not.toContain('After-sales service card');
  });

  it('uses light themed surfaces on the judgment form', async () => {
    const { wrapper } = await mountDetect('Sensor Abnormal');

    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
    expect(wrapper.find('.detect-form-card').exists()).toBe(true);
    expect(wrapper.find('.detect-review-pack').classes()).toContain('detect-light-surface');
  });

  it('uses the reference-style verdict layout after running detection', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountDetect();

    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();

    expect(wrapper.find('.verdict-page').exists()).toBe(true);
    expect(wrapper.find('.verdict-bc').text()).toContain('Devices');
    expect(wrapper.find('.verdict-hero').exists()).toBe(true);
    expect(wrapper.find('.verdict-hero-badge').exists()).toBe(true);
    expect(['WARRANTY ELIGIBLE', 'NOT WARRANTY ELIGIBLE']).toContain(wrapper.find('.verdict-hero-badge').text());
    expect(wrapper.findAll('.verdict-card-head').map(node => node.text())).toEqual(expect.arrayContaining([
      'Basis for the verdict',
      'Device overview',
      'Guidance',
    ]));
    expect(wrapper.find('.verdict-spec-row').text()).toContain('What we found');
    expect(wrapper.find('.verdict-card-list').text()).toContain('After-sales status:');
    expect(wrapper.find('.verdict-review-rail').exists()).toBe(true);
    expect(wrapper.find('.verdict-footer-actions').exists()).toBe(true);
    expect(wrapper.find('[data-test="new-lookup"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="detect-another"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="verdict-feedback"]').exists()).toBe(true);
  });

  it('uses a red badge treatment when the verdict detects a fault', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountDetect();

    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();

    expect(wrapper.find('.verdict-hero').classes()).toContain('fault');
    expect(wrapper.find('.verdict-hero-badge').classes()).toContain('verdict-hero-badge--fault');
    expect(wrapper.find('.verdict-hero-badge').classes()).not.toContain('badge-blue');
  });

  it('supports adopt and reject feedback on the verdict page', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountDetect();
    const store = useDemoStore();

    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();

    await wrapper.find('[data-test="verdict-adopt"]').trigger('click');
    expect(wrapper.find('.verdict-feedback--adopted').exists()).toBe(true);
    expect(wrapper.find('[data-test="verdict-adopt-note"]').text()).toContain('Adopted');
    expect(store.records.value[0].verdictAdoption).toBe('Yes');
    expect(store.records.value[0].verdictRejectionReason).toBe('');

    await wrapper.find('[data-test="verdict-reject"]').trigger('click');
    expect(wrapper.find('[data-test="verdict-reject-comment"]').exists()).toBe(true);

    await wrapper.find('[data-test="verdict-reject-submit"]').trigger('click');
    expect(wrapper.find('.verdict-feedback--rejected').exists()).toBe(true);
    expect(wrapper.find('[data-test="verdict-reject-submitted"]').text()).toContain('Submitted');
    expect(wrapper.find('[data-test="verdict-reject-comment"]').exists()).toBe(false);
    expect(store.records.value[0].verdictAdoption).toBe('No');
    expect(store.records.value[0].verdictRejectionReason).toBe('');

    await wrapper.find('[data-test="verdict-reject"]').trigger('click');
    await wrapper.find('[data-test="verdict-reject-comment"]').setValue('Need manual curve review');
    await wrapper.find('[data-test="verdict-reject-submit"]').trigger('click');
    expect(wrapper.find('[data-test="verdict-reject-comment"]').exists()).toBe(false);
    expect(wrapper.find('[data-test="verdict-reject-note"]').text()).toContain('Need manual curve review');
    expect(store.records.value[0].verdictAdoption).toBe('No');
    expect(store.records.value[0].verdictRejectionReason).toBe('Need manual curve review');
  });

  it('opens the verdict for the explicit record id when multiple records share a device and category', async () => {
    const store = useDemoStore();
    const first = store.runDetect('P2251212806JND44', 'Sensor falling off');
    const second = store.runDetect('P2251212806JND44', 'Sensor falling off');
    first.reasonSummary = 'first explicit record reason';
    second.reasonSummary = 'second latest record reason';
    const router = makeRouter();
    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: { category: 'Sensor falling off', record: first.id },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212806JND44' },
      global: { plugins: [router] },
    });

    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(wrapper.find('.verdict-hero-title').exists()).toBe(true);
  });

  it('shows Back to Device detect and hides footer actions when opened from chat', async () => {
    const store = useDemoStore();
    const record = store.runDetect('P2251212806JND44', 'Data accuracy');
    const router = makeRouter();
    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: {
        category: 'Data accuracy',
        record: record.id,
        from: 'chat',
        session: 'CHAT-test',
      },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212806JND44' },
      global: { plugins: [router] },
    });

    expect(wrapper.find('[data-test="detect-back"]').text()).toContain('Back to Device detect');
    expect(wrapper.find('.verdict-footer-actions').exists()).toBe(false);

    await wrapper.find('[data-test="detect-back"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('chat');
    expect(router.currentRoute.value.query.session).toBe('CHAT-test');
  });

  it('returns to detect records and hides footer actions when opened from records list', async () => {
    const store = useDemoStore();
    const record = store.runDetect('P2251212806JND44', 'Data accuracy');
    const router = makeRouter();
    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: {
        category: 'Data accuracy',
        record: record.id,
        from: 'records',
      },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212806JND44' },
      global: { plugins: [router] },
    });

    expect(wrapper.find('[data-test="detect-back"]').text()).toContain('Back to Detect records');
    expect(wrapper.find('.verdict-footer-actions').exists()).toBe(false);

    await wrapper.find('[data-test="detect-back"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('records');
  });

  it('keeps a fault-query back path when not opened from chat', async () => {
    const store = useDemoStore();
    const record = store.runDetect('P2251212806JND44', 'Data accuracy');
    const router = makeRouter();
    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: { category: 'Data accuracy', record: record.id },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212806JND44' },
      global: { plugins: [router] },
    });

    expect(wrapper.find('[data-test="detect-back"]').text()).toContain('Back to Fault Query');
    expect(wrapper.find('.verdict-footer-actions').exists()).toBe(true);
  });

  it('navigates to chat when New lookup is clicked', async () => {
    vi.useFakeTimers();
    const { router, wrapper } = await mountDetect();

    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();

    await wrapper.find('[data-test="new-lookup"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('chat');
  });
});
