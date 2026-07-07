import { flushPromises, mount as baseMount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';
import { backendApi } from '@/api/backend';
import DetectFlowView from './DetectFlowView.vue';

let activeWrappers: any[] = [];
function mount(component: any, options?: any) {
  const wrapper = baseMount(component, options);
  activeWrappers.push(wrapper);
  return wrapper;
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/chat', name: 'chat', component: { template: '<div>Chat</div>' } },
      { path: '/detect', redirect: '/chat' },
      { path: '/fault-query/:categoryKey', name: 'fault-query', component: { template: '<div>Fault Query</div>' } },
      { path: '/records', name: 'records', component: { template: '<div>Records</div>' } },
      { path: '/multi-detect/:batchId', name: 'multi-detect', component: { template: '<div>Multi Detect</div>' } },
      { path: '/detect-devices', name: 'detect-devices', component: { template: '<div>Detect Devices</div>' } },
      { path: '/detect/:sn/new', name: 'detect-new', component: DetectFlowView, props: route => ({ sn: String(route.params.sn) }) },
      { path: '/detect/:sn/records/:recordId', name: 'detect-record', component: DetectFlowView, props: route => ({ sn: String(route.params.sn) }) },
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

async function advanceProcessingToResult(ms = 4200) {
  await vi.advanceTimersByTimeAsync(ms);
  await flushPromises();
}

describe('DetectFlowView', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    const store = useDemoStore();
    store.resetDemoState();
    store.backendOnline.value = false;
    activeWrappers.forEach(w => {
      try {
        w.unmount();
      } catch {}
    });
    activeWrappers = [];
  });

  it('starts on the reference detect form shell after a fault is selected', async () => {
    const { wrapper } = await mountDetect();

    expect(wrapper.find('#page-detect-form').exists()).toBe(true);
    expect(wrapper.find('#diag-form-shell').exists()).toBe(true);
    expect(wrapper.find('.diag-form-header h1').text()).toBe('Data accuracy');
    expect(wrapper.find('.guidance-box').exists()).toBe(true);
    expect(wrapper.find('.card .card-body').text()).toContain('Run automated curve screening');
  });

  it('shows a determinate progress ring before non-implant verdicts', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountDetect();
    const store = useDemoStore();

    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    await flushPromises();

    expect(store.sessions.value).toHaveLength(1);
    expect(wrapper.find('#page-processing').exists()).toBe(true);
    expect(wrapper.find('.processing-progress-ring').exists()).toBe(true);
    expect(wrapper.find('.proc-eta').text()).toBe('Analyzing 1%');

    await vi.advanceTimersByTimeAsync(640);
    await flushPromises();

    expect(wrapper.find('#page-processing').exists()).toBe(true);
    expect(wrapper.find('.proc-eta').text()).toMatch(/^Analyzing (?!1%)\d+%$/);

    await advanceProcessingToResult();

    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(wrapper.find('.verdict-page').exists()).toBe(true);
    expect(store.sessions.value[0]).toMatchObject({
      sn: 'P2251212806JND44',
      faultCategory: 'Data accuracy',
      status: 'complete',
      recordId: store.records.value[0].id,
    });
  });

  it('runs first-pass data accuracy screening without forcing image upload first', async () => {
    vi.useFakeTimers();
    const store = useDemoStore();
    const router = makeRouter();
    const sn = 'P2251212823BFV10';
    await router.push({ name: 'detect', params: { sn }, query: { category: 'Data accuracy' } });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn },
      global: { plugins: [router] },
    });

    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('#page-inaccuracy-upload').exists()).toBe(false);
    expect(wrapper.find('#page-processing').exists()).toBe(true);
    expect(store.sessions.value).toHaveLength(1);

    await advanceProcessingToResult();

    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(store.records.value[0].faultSubtype).toBe('Data Deviation Review Required');
    expect(wrapper.find('[data-test="go-to-upload"]').exists()).toBe(true);
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
    await flushPromises();
    await advanceProcessingToResult();

    expect(wrapper.find('.verdict-page').exists()).toBe(true);
    expect(wrapper.find('.verdict-page .processing-complete-check').exists()).toBe(false);
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

  it('shows the completion check only for the application-failure processing handoff', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountDetect('Application failure');

    await wrapper.findAll('.implant-photo-slot')[0].trigger('click');
    await wrapper.findAll('.implant-photo-slot')[1].trigger('click');
    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('#page-processing').exists()).toBe(true);
    expect(wrapper.find('.processing-progress-ring').exists()).toBe(true);
    expect(wrapper.find('.proc-eta').text()).toMatch(/^Analyzing \d+%$/);
    expect(wrapper.find('.processing-complete-check').exists()).toBe(false);

    await vi.advanceTimersByTimeAsync(3500);
    await flushPromises();

    expect(wrapper.find('#page-processing').exists()).toBe(true);
    expect(wrapper.find('.processing-progress-ring').exists()).toBe(true);
    expect(wrapper.find('.processing-complete-check').exists()).toBe(false);

    await vi.advanceTimersByTimeAsync(2500);
    await flushPromises();

    expect(wrapper.find('.processing-complete-check').exists()).toBe(true);
    expect(wrapper.find('.proc-eta').text()).toBe('Complete');

    await vi.advanceTimersByTimeAsync(900);
    await flushPromises();

    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(wrapper.find('.verdict-page .processing-complete-check').exists()).toBe(false);
  });

  it('starts application-failure progress immediately for fault-query auto detection', async () => {
    vi.useFakeTimers();
    const router = makeRouter();
    const sn = 'P2251212813RVK19';
    await router.push({
      name: 'detect',
      params: { sn },
      query: {
        category: 'Application failure',
        from: 'fault-query',
        files: 'file-implant-1,file-implant-2',
      },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn },
      global: { plugins: [router] },
    });
    await flushPromises();

    expect(wrapper.find('#page-processing').exists()).toBe(true);
    expect(wrapper.find('.processing-progress-ring').exists()).toBe(true);
    expect(wrapper.find('.proc-eta').text()).toBe('Analyzing 1%');

    await vi.advanceTimersByTimeAsync(640);
    await flushPromises();

    expect(wrapper.find('#page-processing').exists()).toBe(true);
    expect(wrapper.find('.proc-eta').text()).toMatch(/^Analyzing (?!1%)\d+%$/);
    expect(wrapper.find('.processing-complete-check').exists()).toBe(false);
  });

  it('uses a red badge treatment when the verdict detects a fault', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountDetect();

    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    await flushPromises();
    await advanceProcessingToResult();

    expect(wrapper.find('.verdict-hero').classes()).toContain('fault');
    expect(wrapper.find('.verdict-hero-badge').classes()).toContain('verdict-hero-badge--fault');
    expect(wrapper.find('.verdict-hero-badge').classes()).not.toContain('badge-blue');
  });

  it('supports adopt and reject feedback on the verdict page', async () => {
    vi.useFakeTimers();
    const { wrapper } = await mountDetect();
    const store = useDemoStore();

    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    await flushPromises();
    await advanceProcessingToResult();

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

  it('renders records-page verdicts for backend-only devices without a blank screen', async () => {
    const store = useDemoStore();
    const record = store.restoreDetectRecord({
      id: 'REC-BACKEND-ONLY',
      sn: 'BACKENDONLY123',
      email: 'user@example.com',
      initiatorEmail: 'agent@example.com',
      initiatorName: 'Agent',
      dealerId: 'dealer-1',
      dealerName: 'Dealer',
      organizationName: 'Org',
      organizationType: 'distributor',
      region: 'US',
      deviceType: 'GS1',
      faultCategory: 'Sensor falling off',
      faultSubtype: 'Detachment Detected',
      conclusion: 'Issue Detected',
      afterSales: 'Replacement Eligible',
      timestamp: '2026-06-30T00:00:00.000Z',
      thresholdProfileVersion: 1,
      thresholdSnapshot: store.activeThresholdProfile.value,
      reasonSummary: 'Fallback abnormal duration 11100 minutes.',
      verdictAdoption: 'Not recorded',
      verdictRejectionReason: '',
      status: 'complete',
      evidence: {
        device: {
          sn: 'BACKENDONLY123',
          device_type: 'GS1',
          status: 'wearing',
          activatedAt: '2024-08-16T18:52:44+08:00',
          lastDataAt: '2024-08-16T19:14:40+08:00',
          timeZone: 'Asia/Shanghai',
          wear_days: 1,
          device_status: 1,
          fall_off_status: 'fallen_off',
        },
      },
    });
    const router = makeRouter();
    await router.push({
      name: 'detect',
      params: { sn: record.sn },
      query: { category: record.faultCategory, record: record.id, from: 'records' },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: record.sn },
      global: { plugins: [router] },
    });

    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(wrapper.find('.verdict-page').exists()).toBe(true);
    expect(wrapper.find('.processing-shell').exists()).toBe(false);
    expect(wrapper.text()).toContain('BACKENDONLY123');
    expect(wrapper.find('.verdict-cards').text()).toContain('Activated');
    expect(wrapper.find('.verdict-cards').text()).toContain('2024-08-16');
  });

  it('formats long duration values in verdict presentation copy', async () => {
    const store = useDemoStore();
    const record = store.restoreDetectRecord({
      id: 'REC-DURATION-COPY',
      sn: 'DURATION123',
      email: 'user@example.com',
      initiatorEmail: 'agent@example.com',
      initiatorName: 'Agent',
      dealerId: 'dealer-1',
      dealerName: 'Dealer',
      organizationName: 'Org',
      organizationType: 'distributor',
      region: 'US',
      deviceType: 'GS1',
      faultCategory: 'Sensor Abnormal',
      faultSubtype: 'Probe Abnormality',
      conclusion: 'Issue Detected',
      afterSales: 'Replacement Eligible',
      timestamp: '2026-06-30T00:00:00.000Z',
      thresholdProfileVersion: 1,
      thresholdSnapshot: store.activeThresholdProfile.value,
      reasonSummary: 'Loaded from server records page.',
      verdictAdoption: 'Not recorded',
      verdictRejectionReason: '',
      status: 'complete',
      evidence: {
        device: {
          sn: 'DURATION123',
          device_type: 'GS1',
          status: 'wearing',
          activatedAt: '2024-08-16T18:52:44+08:00',
          lastDataAt: '2024-08-16T19:14:40+08:00',
          timeZone: 'Asia/Shanghai',
          wear_days: 1.5,
          device_status: 4,
        },
      },
      presentation: {
        templateVersion: 'test',
        scenarioKey: 'sensor_abnormal.probe',
        badge: 'WARRANTY ELIGIBLE',
        title: 'Probe Abnormality',
        summary: 'Issue detected with abnormal duration 11100 minutes.',
        whatWeFound: 'Abnormality lasted 1520.555555 minutes and short observation lasted 45.55 minutes.',
        whyThisResult: 'Waiting window reached 90.25 minutes.',
        possibleCauses: 'The prior condition lasted 48 hours.',
        supportingMaterials: [],
        guidance: {
          why: 'Keep monitoring for 59.94 minutes if the state changes.',
          nextAction: 'Escalate after 1500.25 minutes of abnormality.',
        },
      },
    });
    const router = makeRouter();
    await router.push({
      name: 'detect',
      params: { sn: record.sn },
      query: { category: record.faultCategory, record: record.id, from: 'records' },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: record.sn },
      global: { plugins: [router] },
    });

    const text = wrapper.find('.verdict-cards').text();
    expect(wrapper.find('.verdict-hero-detail').text()).toContain('abnormal duration 7.7 d');
    expect(wrapper.find('.verdict-hero-detail').text()).not.toContain('11100 minutes');
    expect(text).toContain('Abnormality lasted 1.1 d');
    expect(text).toContain('short observation lasted 45.6 min');
    expect(text).toContain('Waiting window reached 1.5 h');
    expect(text).toContain('prior condition lasted 2 d');
    expect(text).toContain('Keep monitoring for 59.9 min');
    expect(text).toContain('Escalate after 1 d');
    expect(text).not.toContain('1520.555555 minutes');
    expect(text).not.toContain('1500.25 minutes');
  });

  it('formats duration values from fallback verdict fields', async () => {
    const store = useDemoStore();
    const record = store.restoreDetectRecord({
      id: 'REC-DURATION-FALLBACK',
      sn: 'FALLBACKDURATION123',
      email: 'user@example.com',
      initiatorEmail: 'agent@example.com',
      initiatorName: 'Agent',
      dealerId: 'dealer-1',
      dealerName: 'Dealer',
      organizationName: 'Org',
      organizationType: 'distributor',
      region: 'US',
      deviceType: 'GS1',
      faultCategory: 'Sensor Abnormal',
      faultSubtype: 'Probe abnormal duration 11100 minutes; Device is fallen off and wear days 10.184166666666666 is below 14',
      conclusion: 'Issue Detected',
      afterSales: 'Replacement Eligible',
      timestamp: '2026-06-30T00:00:00.000Z',
      thresholdProfileVersion: 1,
      thresholdSnapshot: store.activeThresholdProfile.value,
      reasonSummary: 'Device is fallen off and wear days 10.184166666666666 is below 14.',
      verdictAdoption: 'Not recorded',
      verdictRejectionReason: '',
      status: 'complete',
      evidence: {
        device: {
          sn: 'FALLBACKDURATION123',
          device_type: 'GS1',
          status: 'wearing',
          activatedAt: '2024-08-16T18:52:44+08:00',
          lastDataAt: '2024-08-16T19:14:40+08:00',
          timeZone: 'Asia/Shanghai',
          wear_days: 7.7,
          device_status: 4,
        },
      },
    });
    const router = makeRouter();
    await router.push({
      name: 'detect',
      params: { sn: record.sn },
      query: { category: record.faultCategory, record: record.id, from: 'records' },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: record.sn },
      global: { plugins: [router] },
    });

    expect(wrapper.find('.verdict-hero-title').text()).toContain('Probe abnormal duration 7.7 d');
    expect(wrapper.find('.verdict-hero-title').text()).toContain('wear time 10.2 d is below 14 d');
    expect(wrapper.find('.verdict-hero-title').text()).not.toContain('11100 minutes');
    expect(wrapper.text()).not.toContain('10.184166666666666');
  });

  it('shows Back to Device Detection and hides footer actions when opened from chat', async () => {
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

    expect(wrapper.find('[data-test="detect-back"]').text()).toContain('Back to Device Detection');
    expect(wrapper.find('.verdict-footer-actions').exists()).toBe(false);

    await wrapper.find('[data-test="detect-back"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('chat');
    expect(router.currentRoute.value.query.session).toBe('CHAT-test');
  });

  it('returns to detection history and hides footer actions when opened from records list', async () => {
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

    expect(wrapper.find('[data-test="detect-back"]').text()).toContain('Back to Detection History');
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

  it('handles image deviation upload mock flow correctly', async () => {
    vi.useFakeTimers();
    const store = useDemoStore();
    const router = makeRouter();
    const sn = 'P2251212823BFV10';
    await router.push({ name: 'detect', params: { sn }, query: { category: 'Data accuracy' } });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn },
      global: { plugins: [router] },
    });

    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    await flushPromises();
    await advanceProcessingToResult();

    await wrapper.find('[data-test="go-to-upload"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-test="detect-upload-modal"]').exists()).toBe(true);

    for (let i = 0; i < 4; i++) {
      await wrapper.findAll('.detect-upload-zone')[i].trigger('click');
    }
    expect(wrapper.find('.detect-upload-count').text()).toContain('Uploaded: 4 / 4 images');

    await wrapper.find('.detect-upload-modal-actions button.btn-primary').trigger('click');
    await flushPromises();
    await advanceProcessingToResult();

    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(wrapper.find('.verdict-hero-badge').text()).toBe('WARRANTY ELIGIBLE');
    expect(wrapper.find('.verdict-cards').text()).toContain('OCR completed screenshot pair extraction.');
  });

  it('previews uploaded deviation images and only reopens upload after removal', async () => {
    const store = useDemoStore();
    store.backendOnline.value = true;
    vi.stubGlobal('FileReader', class {
      public result = 'data:image/png;base64,cHJldmlldw==';
      public onload: ((event: ProgressEvent<FileReader>) => void) | null = null;
      public onerror: (() => void) | null = null;

      readAsDataURL() {
        this.onload?.({ target: { result: this.result } } as ProgressEvent<FileReader>);
      }
    });
    vi.spyOn(backendApi, 'uploadFile').mockResolvedValue({
      id: 'file-preview-1',
      filename: 'pair-one.png',
      public_url: '/api/v1/files/file-preview-1',
    });

    const router = makeRouter();
    const record = store.runDetect('P2251212823BFV10', 'Data accuracy', []);
    record.faultSubtype = 'Data Deviation Review Required';
    record.conclusion = 'No Issue';
    record.afterSales = 'Under Review';

    const getDetectionSpy = vi.spyOn(backendApi, 'getDetection').mockResolvedValue(record as any);

    await router.push({
      name: 'detect',
      params: { sn: 'P2251212823BFV10' },
      query: { category: 'Data accuracy', record: record.id },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212823BFV10' },
      global: { plugins: [router] },
    });

    await wrapper.find('[data-test="go-to-upload"]').trigger('click');
    await flushPromises();

    const input = wrapper.find<HTMLInputElement>('#result-deviation-file-input-0');
    const file = new File(['preview'], 'pair-one.png', { type: 'image/png' });
    Object.defineProperty(input.element, 'files', {
      value: [file],
      configurable: true,
    });

    await input.trigger('change');
    await flushPromises();

    const firstZone = wrapper.findAll('.detect-upload-zone')[0];
    expect(firstZone.find('.detect-upload-preview img').exists()).toBe(true);

    await firstZone.trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-test="image-preview-modal"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="image-preview-modal"] img').attributes('src')).toContain('data:image/png');

    await wrapper.find('[aria-label="Close image preview"]').trigger('click');
    await firstZone.find('.detect-upload-remove').trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-test="image-preview-modal"]').exists()).toBe(false);
    expect(wrapper.findAll('.detect-upload-zone')[0].find('.detect-upload-preview').exists()).toBe(false);
    expect(wrapper.find('.detect-upload-count').text()).toContain('Uploaded: 0 / 4 images');

    getDetectionSpy.mockRestore();
  });

  it('navigates to chat when New lookup is clicked', async () => {
    vi.useFakeTimers();
    const { router, wrapper } = await mountDetect();

    await wrapper.find('button[data-test="run-detect"]').trigger('click');
    await flushPromises();
    await advanceProcessingToResult();

    await wrapper.find('[data-test="new-lookup"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('chat');
  });

  it('replaces the result route when Detect another is clicked so browser back does not restore old progress', async () => {
    const store = useDemoStore();
    const router = makeRouter();
    const record = store.runDetect('P2251212806JND44', 'Data accuracy');

    await router.push({ name: 'fault-query', params: { categoryKey: 'data-accuracy' } });
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

    expect(wrapper.find('#page-result').exists()).toBe(true);

    await wrapper.find('[data-test="detect-another"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('fault-query');
    expect(router.currentRoute.value.query.fromDetect).toBe('1');

    router.back();
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('fault-query');
  });

  it('returns single-device results from fault query with a one-click return marker', async () => {
    const store = useDemoStore();
    const router = makeRouter();
    const record = store.runDetect('P2251212806JND44', 'Sensor falling off');

    await router.push({ name: 'chat' });
    await router.push({ name: 'fault-query', params: { categoryKey: 'sensor-falling-off' } });
    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: {
        category: 'Sensor falling off',
        record: record.id,
        from: 'fault-query',
      },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212806JND44' },
      global: { plugins: [router] },
    });

    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(wrapper.find('#page-processing').exists()).toBe(false);

    await wrapper.find('[data-test="detect-back"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('fault-query');
    expect(router.currentRoute.value.query.fromDetect).toBe('1');
  });

  it('restores the latest completed fault-query result on refresh instead of starting detection again', async () => {
    const store = useDemoStore();
    const record = store.runDetect('P2251212806JND44', 'Data accuracy');
    const startSessionSpy = vi.spyOn(store, 'startDetectSession');
    const runRemoteSpy = vi.spyOn(store, 'runDetectRemote');
    const router = makeRouter();

    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: {
        category: 'Data accuracy',
        from: 'fault-query',
      },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212806JND44' },
      global: { plugins: [router] },
    });

    await flushPromises();

    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(wrapper.find('#page-processing').exists()).toBe(false);
    expect(wrapper.find('#diag-form-shell').exists()).toBe(false);
    expect(wrapper.find('.verdict-page').exists()).toBe(true);
    expect(startSessionSpy).not.toHaveBeenCalled();
    expect(runRemoteSpy).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain(record.sn);
  });

  it('starts a fresh fault-query run when the route carries an explicit run marker', async () => {
    vi.useFakeTimers();
    const store = useDemoStore();
    const previousRecord = store.runDetect('P2251212806JND44', 'Data accuracy');
    const router = makeRouter();

    await router.push({
      name: 'detect-new',
      params: { sn: 'P2251212806JND44' },
      query: {
        category: 'Data accuracy',
        from: 'fault-query',
      },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212806JND44' },
      global: { plugins: [router] },
    });

    await flushPromises();

    expect(wrapper.find('#page-processing').exists()).toBe(true);
    expect(store.sessions.value).toHaveLength(1);

    await advanceProcessingToResult();

    const latest = store.records.value[0];
    expect(latest.id).not.toBe(previousRecord.id);
    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(router.currentRoute.value.name).toBe('detect-record');
    expect(router.currentRoute.value.params.recordId).toBe(latest.id);
    expect(router.currentRoute.value.query.record).toBeUndefined();
    expect(router.currentRoute.value.query.run).toBeUndefined();
    expect(router.currentRoute.value.query.files).toBeUndefined();
  });

  it('does not leave the bare detect URL on the standalone detect form', async () => {
    const router = makeRouter();

    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212806JND44' },
      global: { plugins: [router] },
    });

    await flushPromises();

    expect(wrapper.find('#diag-form-shell').exists()).toBe(false);
    expect(router.currentRoute.value.name).toBe('fault-query');
    expect(router.currentRoute.value.query.fromDetect).toBe('1');
  });

  it('returns single-device results from matched devices with a one-click return marker', async () => {
    const store = useDemoStore();
    const router = makeRouter();
    const record = store.runDetect('P2251212806JND44', 'Data accuracy');

    await router.push({ name: 'chat' });
    await router.push({ name: 'detect-devices', query: { q: 'JND44' } });
    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: {
        category: 'Data accuracy',
        record: record.id,
        from: 'device-detect',
        q: 'JND44',
      },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212806JND44' },
      global: { plugins: [router] },
    });

    await wrapper.find('[data-test="detect-back"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('detect-devices');
    expect(router.currentRoute.value.query).toMatchObject({ q: 'JND44', fromDetect: '1' });
  });

  it('returns batch result details to the matching multi-device page instead of detection history', async () => {
    const store = useDemoStore();
    const router = makeRouter();
    const record = store.runDetect('P2251212806JND44', 'Sensor falling off');

    await router.push({
      name: 'multi-detect',
      params: { batchId: 'MULTI-TEST' },
      query: { category: 'Sensor falling off' },
    });
    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: {
        category: 'Sensor falling off',
        record: record.id,
        from: 'multi-detect',
        batch: 'MULTI-TEST',
      },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212806JND44' },
      global: { plugins: [router] },
    });

    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(wrapper.find('#page-processing').exists()).toBe(false);
    expect(wrapper.find('[data-test="detect-back"]').text()).toContain('Back to batch results');

    await wrapper.find('[data-test="detect-back"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('multi-detect');
    expect(router.currentRoute.value.params.batchId).toBe('MULTI-TEST');
  });

  it('displays go-to-upload button on first-pass result and opens an in-page upload modal when clicked', async () => {
    const store = useDemoStore();
    const router = makeRouter();
    const record = store.runDetect('P2251212823BFV10', 'Data accuracy', []);
    record.faultSubtype = 'Data Deviation Review Required';
    record.conclusion = 'No Issue';
    record.afterSales = 'Under Review';

    await router.push({
      name: 'detect',
      params: { sn: 'P2251212823BFV10' },
      query: { category: 'Data accuracy', record: record.id, from: 'records' },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212823BFV10' },
      global: { plugins: [router] },
    });

    expect(wrapper.find('#page-result').exists()).toBe(true);
    const uploadBtn = wrapper.find('[data-test="go-to-upload"]');
    expect(uploadBtn.exists()).toBe(true);
    expect(uploadBtn.text()).toContain('Upload comparison images');

    await uploadBtn.trigger('click');
    await flushPromises();

    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(wrapper.find('#page-inaccuracy-upload').exists()).toBe(false);
    expect(wrapper.find('[data-test="detect-upload-modal"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="detect-upload-modal"]').text()).toContain('Upload visual evidence');
    expect(wrapper.findAll('.detect-upload-zone')).toHaveLength(4);
  });

  it('shows blurry/invalid message instead of first-round curve message when hasUploadedFiles is true on result page', async () => {
    const store = useDemoStore();
    const router = makeRouter();
    const record = store.runDetect('P2251212823BFV10', 'Data accuracy', ['file1', 'file2', 'file3', 'file4']);
    record.faultSubtype = 'Data Deviation Review Required';
    record.conclusion = 'No Issue';
    record.afterSales = 'Under Review';
    record.reasonSummary = 'Image 1 is blurry or unreadable.';

    await router.push({
      name: 'detect',
      params: { sn: 'P2251212823BFV10' },
      query: { category: 'Data accuracy', record: record.id },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212823BFV10' },
      global: { plugins: [router] },
    });

    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(wrapper.find('.verdict-cards').text()).toContain('Evidence verification failed');
    expect(wrapper.find('.verdict-cards').text()).toContain('Image 1 is blurry or unreadable.');
  });

  it('fetches record from backend if routeRecordId is provided but not in store and backend is online', async () => {
    const store = useDemoStore();
    store.backendOnline.value = true;
    store.selectedDevice.value = {
      sn: 'P2251212806JND44',
      type: 'GS1',
      status: 'active',
      wearDays: 5,
      wearHours: 12,
      lastDataAt: '2026-06-24T10:00:00Z',
      fault: {
        faultCategory: 'Data accuracy',
        faultSubtype: '',
      },
    } as any;

    const mockRecord = {
      id: '26',
      sn: 'P2251212806JND44',
      faultCategory: 'Data accuracy',
      status: 'complete',
      timestamp: new Date().toISOString(),
      afterSales: 'Under Review',
      verdictAdoption: 'Not recorded',
      verdictRejectionReason: '',
      faultSubtype: '',
    };

    const getDetectionSpy = vi.spyOn(backendApi, 'getDetection').mockResolvedValue(mockRecord as any);

    const router = makeRouter();
    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: { category: 'Data accuracy', record: '26' },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212806JND44' },
      global: { plugins: [router] },
    });

    expect(wrapper.find('#page-processing').exists()).toBe(false);

    await flushPromises();

    expect(getDetectionSpy).toHaveBeenCalledWith('26');
    expect(store.records.value.find((r: any) => r.id === '26')).toBeDefined();
    expect(wrapper.find('#page-result').exists()).toBe(true);

    getDetectionSpy.mockRestore();
  });

  it('restores a backend record detail on refresh without an existing selected device', async () => {
    const store = useDemoStore();
    store.backendOnline.value = true;
    store.selectedDevice.value = null;

    const mockRecord = {
      id: 'REC-REFRESH-ONLY',
      sn: 'BACKENDREFRESH123',
      email: 'user@example.com',
      initiatorEmail: 'agent@example.com',
      initiatorName: 'Agent',
      dealerId: 'dealer-1',
      dealerName: 'Dealer',
      organizationName: 'Org',
      organizationType: 'distributor',
      region: 'US',
      deviceType: 'GS1',
      faultCategory: 'Sensor falling off',
      faultSubtype: 'Detachment Detected',
      conclusion: 'Issue Detected',
      afterSales: 'Replacement Eligible',
      timestamp: '2026-06-30T00:00:00.000Z',
      thresholdProfileVersion: 1,
      thresholdSnapshot: store.activeThresholdProfile.value,
      reasonSummary: 'Loaded after refresh.',
      verdictAdoption: 'Not recorded',
      verdictRejectionReason: '',
      status: 'complete',
      evidence: {
        device: {
          sn: 'BACKENDREFRESH123',
          device_type: 'GS1',
          status: 'wearing',
          activatedAt: '2024-08-16T18:52:44+08:00',
          lastDataAt: '2024-08-16T19:14:40+08:00',
          wear_days: 1,
        },
      },
    };

    const getDetectionSpy = vi.spyOn(backendApi, 'getDetection').mockResolvedValue(mockRecord as any);
    const getDeviceSpy = vi.spyOn(backendApi, 'getDevice').mockRejectedValue(new Error('not found'));

    const router = makeRouter();
    await router.push({
      name: 'detect',
      params: { sn: 'BACKENDREFRESH123' },
      query: { category: 'Sensor falling off', record: 'REC-REFRESH-ONLY', from: 'records' },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'BACKENDREFRESH123' },
      global: { plugins: [router] },
    });

    expect(wrapper.find('#page-detect-restore').exists()).toBe(true);

    await flushPromises();

    expect(getDetectionSpy).toHaveBeenCalledWith('REC-REFRESH-ONLY');
    expect(wrapper.find('#page-result').exists()).toBe(true);
    expect(wrapper.find('.verdict-page').exists()).toBe(true);
    expect(wrapper.text()).toContain('BACKENDREFRESH123');
    expect(wrapper.find('.processing-shell').exists()).toBe(false);

    getDetectionSpy.mockRestore();
    getDeviceSpy.mockRestore();
  });

  it('shows device not found error card when device lookup fails', async () => {
    const store = useDemoStore();
    store.selectedDevice.value = null;

    const getDeviceSpy = vi.spyOn(backendApi, 'getDevice').mockRejectedValue(new Error('Device with SN NOT_FOUND_SN was not found.'));

    const router = makeRouter();
    await router.push({
      name: 'detect',
      params: { sn: 'NOT_FOUND_SN' },
      query: { category: 'Sensor falling off' },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'NOT_FOUND_SN' },
      global: { plugins: [router] },
    });

    await flushPromises();

    expect(wrapper.find('#page-detect-restore').exists()).toBe(true);
    expect(wrapper.find('.error-card').exists()).toBe(true);
    expect(wrapper.find('.error-warning-icon').exists()).toBe(true);
    expect(wrapper.text()).toContain('Device Not Found');
    expect(wrapper.text()).toContain('Unknown SN: NOT_FOUND_SN');
    expect(wrapper.find('[data-test="error-back-lookup"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="error-back"]').exists()).toBe(true);

    getDeviceSpy.mockRestore();
  });

  it('shows record not found error card when record lookup fails', async () => {
    const store = useDemoStore();
    store.backendOnline.value = true;
    store.selectedDevice.value = {
      sn: 'P2251212806JND44',
      type: 'GS1',
      status: 'active',
      wearDays: 5,
      wearHours: 12,
      lastDataAt: '2026-06-24T10:00:00Z',
      fault: {
        faultCategory: 'Data accuracy',
        faultSubtype: '',
      },
    } as any;

    const getDetectionSpy = vi.spyOn(backendApi, 'getDetection').mockRejectedValue(new Error('Record with ID REC-MISSING was not found.'));

    const router = makeRouter();
    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: { category: 'Data accuracy', record: 'REC-MISSING' },
    });
    await router.isReady();

    const wrapper = mount(DetectFlowView, {
      props: { sn: 'P2251212806JND44' },
      global: { plugins: [router] },
    });

    await flushPromises();

    expect(wrapper.find('#page-detect-restore').exists()).toBe(true);
    expect(wrapper.find('.error-card').exists()).toBe(true);
    expect(wrapper.text()).toContain('Record Not Found');
    expect(wrapper.text()).toContain('Record with ID REC-MISSING was not found.');

    getDetectionSpy.mockRestore();
  });
});

