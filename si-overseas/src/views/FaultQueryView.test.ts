import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { backendApi } from '@/api/backend';
import { useDemoStore } from '@/composables/useDemoStore';
import FaultQueryView from './FaultQueryView.vue';

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/chat', name: 'chat', component: { template: '<div>Chat</div>' } },
      { path: '/fault-query/:categoryKey', name: 'fault-query', component: FaultQueryView, props: true },
      { path: '/multi-detect/:batchId', name: 'multi-detect', component: { template: '<div>Multi</div>' } },
      { path: '/detect/:sn/new', name: 'detect-new', component: { template: '<div>Detect New</div>' } },
      { path: '/detect/:sn/records/:recordId', name: 'detect-record', component: { template: '<div>Detect Record</div>' } },
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
    vi.restoreAllMocks();
    const store = useDemoStore();
    store.backendOnline.value = false;
    store.resetDemoState();
  });

  it('shows the selected fault context and an empty selected-devices workspace', async () => {
    const { wrapper } = await mountFaultQuery('sensor-falling-off');

    expect(wrapper.find('.fault-query-rail-title').text()).toBe('Sensor falling off');
    expect(wrapper.text()).toContain('The sensor detached unexpectedly while being worn.');
    expect(wrapper.find('textarea[aria-label="Fault SN lookup input"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('Add devices by SN or device name');
    expect(wrapper.text()).toContain('Paste a full SN, an SN fragment, a device name, or multiple lines.');
    expect(wrapper.find('[data-test="selected-devices"]').text()).toContain('No devices selected yet');
    expect(wrapper.text()).not.toContain('Batch Query');
  });

  it('returns from a batch-restored query page with one click instead of landing on the same query page', async () => {
    const router = makeRouter();
    await router.push({ name: 'chat' });
    await router.push({ name: 'fault-query', params: { categoryKey: 'sensor-falling-off' } });
    await router.push({
      name: 'multi-detect',
      params: { batchId: 'MULTI-TEST' },
      query: { category: 'Sensor falling off' },
    });
    await router.replace({
      name: 'fault-query',
      params: { categoryKey: 'sensor-falling-off' },
      query: { fromBatch: '1' },
    });
    await router.isReady();

    const wrapper = mount(FaultQueryView, {
      props: { categoryKey: 'sensor-falling-off' },
      global: { plugins: [router] },
    });

    await wrapper.find('.fault-query-back').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('chat');
  });

  it('returns from a single-detect-restored query page with one click instead of landing on the same query page', async () => {
    const router = makeRouter();
    await router.push({ name: 'chat' });
    await router.push({ name: 'fault-query', params: { categoryKey: 'sensor-falling-off' } });
    await router.push({
      name: 'detect',
      params: { sn: 'P2251212806JND44' },
      query: { category: 'Sensor falling off', from: 'fault-query' },
    });
    await router.replace({
      name: 'fault-query',
      params: { categoryKey: 'sensor-falling-off' },
      query: { fromDetect: '1' },
    });
    await router.isReady();

    const wrapper = mount(FaultQueryView, {
      props: { categoryKey: 'sensor-falling-off' },
      global: { plugins: [router] },
    });

    await wrapper.find('.fault-query-back').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('chat');
  });

  it('adds a full SN to selected devices before running detect workspace', async () => {
    const { router, wrapper } = await mountFaultQuery('sensor-falling-off');

    await wrapper.find('textarea[aria-label="Fault SN lookup input"]').setValue('P2251212806JND44');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('fault-query');
    expect(wrapper.find('[data-test="selected-devices"]').text()).toContain('P2251212806JND44');
    expect(wrapper.find('[data-test="run-selected"]').text()).toBe('Run detect');

    await wrapper.find('[data-test="run-selected"]').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('detect-new');
    expect(router.currentRoute.value.params.sn).toBe('P2251212806JND44');
    expect(router.currentRoute.value.query.category).toBe('Sensor falling off');
  });

  it('runs Data accuracy detect without forcing image upload first', async () => {
    const { router, wrapper } = await mountFaultQuery('data-accuracy');

    await wrapper.find('textarea[aria-label="Fault SN lookup input"]').setValue('P2251212806JND44');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    expect(wrapper.find('[data-test="row-upload-zone"]').text()).toContain('0/4');

    await wrapper.find('[data-test="run-selected"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-test="upload-modal"]').exists()).toBe(false);
    expect(router.currentRoute.value.name).toBe('detect-new');
    expect(router.currentRoute.value.params.sn).toBe('P2251212806JND44');
    expect(router.currentRoute.value.query).toMatchObject({
      category: 'Data accuracy',
      from: 'fault-query',
    });
    expect(router.currentRoute.value.query.files).toBeUndefined();
  });

  it('shows fuzzy candidates and adds the chosen candidate without navigating', async () => {
    const { router, wrapper } = await mountFaultQuery('data-accuracy');

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
    const { wrapper } = await mountFaultQuery('data-accuracy');

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

  it('uses one remote search request for multiline lookup instead of per-line getDevice calls', async () => {
    const store = useDemoStore();
    store.backendOnline.value = true;
    const searchSpy = vi.spyOn(backendApi, 'searchDevices').mockResolvedValue([
      {
        sn: 'P2251212806JND44',
        type: 'AA250862SE',
        status: 'wearing',
        activatedAt: '2026-01-01T00:00:00Z',
        wearDays: 1,
        wearHours: 0,
        lastDataAt: '2026-01-02T00:00:00Z',
        hasServiceCard: true,
        fault: null,
      },
      {
        sn: 'P2251212813RVK19',
        type: 'AA260901AB',
        status: 'wearing',
        activatedAt: '2026-01-01T00:00:00Z',
        wearDays: 1,
        wearHours: 0,
        lastDataAt: '2026-01-02T00:00:00Z',
        hasServiceCard: true,
        fault: null,
      },
    ]);
    const getDeviceSpy = vi.spyOn(backendApi, 'getDevice');
    const { wrapper } = await mountFaultQuery('data-accuracy');

    await wrapper.find('textarea[aria-label="Fault SN lookup input"]').setValue([
      'P2251212806JND44',
      'RVK19',
    ].join('\n'));
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    expect(searchSpy).toHaveBeenCalledTimes(1);
    expect(searchSpy).toHaveBeenCalledWith('P2251212806JND44\nRVK19');
    expect(getDeviceSpy).not.toHaveBeenCalled();
    const selected = wrapper.find('[data-test="selected-devices"]').text();
    expect(selected).toContain('P2251212806JND44');
    expect(selected).toContain('P2251212813RVK19');
  });

  it('removes selected devices and disables running when none remain', async () => {
    const { wrapper } = await mountFaultQuery('data-accuracy');

    await wrapper.find('textarea[aria-label="Fault SN lookup input"]').setValue('P2251212806JND44');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    expect(wrapper.find('[data-test="remove-selected-device"]').classes()).toContain('btn-danger');

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

    expect(wrapper.find('[data-test="run-selected"]').text()).toBe('Run detect for 2 devices');
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

  it('renders upload zone buttons for Data accuracy, opens the upload modal, and increments simulated count on slot click', async () => {
    const { wrapper } = await mountFaultQuery('data-accuracy');

    await wrapper.find('textarea[aria-label="Fault SN lookup input"]').setValue('P2251212806JND44');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    // Verify row upload zone is present
    const uploadZone = wrapper.find('[data-test="row-upload-zone"]');
    expect(uploadZone.exists()).toBe(true);
    expect(uploadZone.text()).toContain('Upload CGM/BGM pair');
    expect(uploadZone.text()).toContain('0/4');

    // Click upload button to open modal
    await uploadZone.find('button').trigger('click');
    await flushPromises();

    // Verify modal is visible
    const modal = wrapper.find('[data-test="upload-modal"]');
    expect(modal.exists()).toBe(true);
    expect(modal.text()).toContain('Upload visual evidence');

    // Mock FileReader to trigger onload synchronously
    const mockDataUrl = 'data:image/png;base64,mockbase64';
    const readAsDataURLSpy = vi.spyOn(FileReader.prototype, 'readAsDataURL').mockImplementation(function (this: FileReader) {
      this.onload?.({
        target: { result: mockDataUrl }
      } as ProgressEvent<FileReader>);
    });

    const modalUploadZones = modal.findAll('.modal-upload-zone');
    expect(modalUploadZones).toHaveLength(4);

    // Click first zone to trigger file input click
    await modalUploadZones[0].trigger('click');

    // Simulate change event on file input
    const fileInput = wrapper.find('input[type="file"]');
    const file = new File([''], 'test.png', { type: 'image/png' });
    Object.defineProperty(fileInput.element, 'files', {
      value: [file],
      writable: true
    });
    await fileInput.trigger('change');
    await flushPromises();

    expect(uploadZone.text()).toContain('1/4');

    await modalUploadZones[0].trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-test="fault-image-preview-modal"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="fault-image-preview-modal"] img').attributes('src')).toBe(mockDataUrl);

    await wrapper.find('[aria-label="Close image preview"]').trigger('click');
    await modalUploadZones[0].find('.remove-image-btn').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-test="fault-image-preview-modal"]').exists()).toBe(false);
    expect(uploadZone.text()).toContain('0/4');

    // Simulate for other three slots
    for (let i = 0; i <= 3; i++) {
      await modalUploadZones[i].trigger('click');
      await fileInput.trigger('change');
      await flushPromises();
    }

    expect(uploadZone.text()).toContain('4/4');
    expect(uploadZone.find('button').classes()).toContain('btn-success');

    // Click close/done button to close the modal
    await modal.find('.modal-actions button').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-test="upload-modal"]').exists()).toBe(false);

    readAsDataURLSpy.mockRestore();
  });

  it('trusts entered SN/deviceName for Application failure without calling the device API', async () => {
    const store = useDemoStore();
    store.backendOnline.value = true;
    const searchSpy = vi.spyOn(backendApi, 'searchDevices');
    const getDeviceSpy = vi.spyOn(backendApi, 'getDevice');
    const { router, wrapper } = await mountFaultQuery('application-failure');

    // 未激活设备用蓝牙名 (deviceName) 输入
    await wrapper.find('textarea[aria-label="Fault SN lookup input"]').setValue('AA250862SE');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    // 植入失败不查询设备接口，直接信任用户输入
    expect(searchSpy).not.toHaveBeenCalled();
    expect(getDeviceSpy).not.toHaveBeenCalled();
    expect(router.currentRoute.value.name).toBe('fault-query');
    expect(wrapper.find('[data-test="selected-devices"]').text()).toContain('AA250862SE');
  });

  it('renders four application-failure slots with two required photos', async () => {
    const { wrapper } = await mountFaultQuery('application-failure');

    await wrapper.find('textarea[aria-label="Fault SN lookup input"]').setValue('P2251212806JND44');
    await wrapper.find('form').trigger('submit');
    await flushPromises();

    const uploadZone = wrapper.find('[data-test="row-upload-zone"]');
    expect(uploadZone.exists()).toBe(true);
    expect(uploadZone.text()).toContain('Upload site photos');
    expect(uploadZone.text()).toContain('0/2');

    await uploadZone.find('button').trigger('click');
    await flushPromises();

    const modal = wrapper.find('[data-test="upload-modal"]');
    expect(modal.exists()).toBe(true);
    expect(modal.text()).toContain('Upload 2 required photos before review.');
    expect(modal.text()).toContain('2 additional photos are optional');

    const modalUploadZones = modal.findAll('.modal-upload-zone');
    expect(modalUploadZones).toHaveLength(4);
    expect(modal.text()).toContain('Implant site photo (required)');
    expect(modal.text()).toContain('Additional site angle (optional)');
    expect(modal.text()).toContain('0');
    expect(modal.text()).toContain('/ 4 images');
  });
});
