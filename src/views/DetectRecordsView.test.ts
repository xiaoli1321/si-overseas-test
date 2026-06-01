import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { useDemoStore } from '@/composables/useDemoStore';
import DetectRecordsView from './DetectRecordsView.vue';

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/records', name: 'records', component: DetectRecordsView },
      { path: '/detect/:sn', name: 'detect', component: { template: '<div>Detect</div>' } },
    ],
  });
}

async function mountRecords() {
  const router = makeRouter();
  await router.push('/records');
  await router.isReady();

  const wrapper = mount(DetectRecordsView, {
    global: {
      plugins: [router],
    },
  });

  return { router, wrapper };
}

describe('DetectRecordsView', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    useDemoStore().resetDemoState();
  });

  it('renders detect records with the reference table badges and no Rules column', async () => {
    const store = useDemoStore();
    store.runDetect('P2251212806JND44', 'Sensor falling off');

    const { wrapper } = await mountRecords();
    const headers = wrapper.findAll('thead th').map(th => th.text());

    expect(headers).toEqual([
      'Device SN',
      'Type',
      'Scenario',
      'Subtype',
      'Conclusion',
      'After-sales',
      'Adopted',
      'Reject reason',
      'Timestamp',
    ]);
    expect(wrapper.find('.logs-summary').exists()).toBe(true);
    expect(wrapper.find('thead').text()).not.toContain('Job ID');
    expect(wrapper.find('thead').text()).not.toContain('Region');
    expect(wrapper.find('thead').text()).not.toContain('Initiator');
    expect(wrapper.find('thead').text()).not.toContain('Organization');
    expect(wrapper.find('tbody').text()).not.toContain(store.records.value[0].id);
    expect(wrapper.find('tbody').text()).not.toContain(store.records.value[0].initiatorEmail);
    expect(wrapper.find('[data-test="records-page-body"]').classes()).toContain('records-page-body');
    expect(wrapper.find('table').classes()).toContain('records-table');
    expect(wrapper.find('tbody td').classes()).toContain('records-cell-wrap');
    expect(wrapper.find('tbody td').classes()).toContain('records-cell-sn');
    expect(wrapper.findAll('.log-sum-card')).toHaveLength(4);
    expect(wrapper.find('tbody .badge-red, tbody .badge-green').exists()).toBe(true);
    expect(wrapper.find('tbody .badge-teal, tbody .badge-gray').exists()).toBe(true);
    expect(wrapper.find('[data-test="organization-filter-group"]').exists()).toBe(false);
  });

  it('shows verdict adoption status and rejection reason in the table', async () => {
    const store = useDemoStore();
    const acceptedRecord = store.runDetect('P2251212809MRF71', 'Sensor falling off');
    store.updateDetectRecordVerdict(acceptedRecord.id, {
      verdictAdoption: 'Yes',
      verdictRejectionReason: '',
    });
    const rejectedRecord = store.runDetect('P2251212813RVK19', 'Application failure');
    store.updateDetectRecordVerdict(rejectedRecord.id, {
      verdictAdoption: 'No',
      verdictRejectionReason: 'Photos are blurry',
    });

    const { wrapper } = await mountRecords();
    const headers = wrapper.findAll('thead th').map(th => th.text());

    expect(headers).toContain('Adopted');
    expect(headers).toContain('Reject reason');
    expect(wrapper.find('tbody').text()).toContain('Yes');
    expect(wrapper.find('tbody').text()).toContain('No');
    expect(wrapper.find('tbody').text()).toContain('Photos are blurry');
  });

  it('exports detect records without initiator or organization columns', async () => {
    const store = useDemoStore();
    store.runDetect('P2251212806JND44', 'Sensor falling off');
    const createObjectURL = vi.fn((blob: Blob) => {
      void blob;
      return 'blob:detect-records';
    });
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    const { wrapper } = await mountRecords();

    await wrapper.find('[data-test="records-export-csv"]').trigger('click');
    const blob = createObjectURL.mock.calls[0][0] as Blob;
    const csv = await blob.text();

    expect(csv.split('\n')[0]).toBe('Device SN,Type,Scenario,Subtype,Conclusion,After-sales,Adopted,Reject Reason,Timestamp,Reason');
    expect(csv).not.toContain(store.records.value[0].id);
    expect(csv).not.toContain('Initiator Email');
    expect(csv).not.toContain('Organization');
    expect(csv).toContain('"P2251212806JND44"');
  });

  it('opens the verdict using the recorded scenario', async () => {
    const store = useDemoStore();
    store.runDetect('P2251212806JND44', 'Sensor falling off');
    const { router, wrapper } = await mountRecords();

    await wrapper.find('tbody tr.log-row-open').trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.name).toBe('detect');
    expect(router.currentRoute.value.params.sn).toBe('P2251212806JND44');
    expect(router.currentRoute.value.query.category).toBe('Sensor falling off');
    expect(router.currentRoute.value.query.record).toBe(store.records.value[0].id);
    expect(router.currentRoute.value.query.from).toBe('records');
  });

  it('filters records by usable date inputs and can clear filters', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-05-15T12:00:00.000Z'));
    const store = useDemoStore();
    const first = store.runDetect('P2251212806JND44', 'Sensor falling off');
    const second = store.runDetect('P2251212813RVK19', 'Application failure');
    first.timestamp = '2026-05-01T10:00:00.000Z';
    second.timestamp = '2026-05-13T10:00:00.000Z';

    const { wrapper } = await mountRecords();

    expect(wrapper.find('.filter-bar').text()).toContain('Date From');
    expect(wrapper.find('.filter-bar').text()).toContain('Date To');
    expect(wrapper.find('.filter-bar').attributes('lang')).toBe('en-US');
    expect(wrapper.find('[data-test="date-from-input"]').exists()).toBe(false);
    expect(wrapper.find('[data-test="date-from-trigger"]').classes()).toContain('english-date-trigger');
    expect(wrapper.find('[data-test="date-from-trigger"]').classes()).toContain('no-click-outline');
    expect(wrapper.find('[data-test="date-to-trigger"]').classes()).toContain('english-date-trigger');
    expect(wrapper.find('[data-test="scenario-filter-trigger"]').classes()).toContain('ios-select-trigger');
    expect(wrapper.find('[data-test="scenario-filter-trigger"]').classes()).toContain('no-click-outline');
    expect(wrapper.find('[data-test="date-from-trigger"]').text()).not.toContain('v');
    expect(wrapper.find('[data-test="scenario-filter-trigger"]').text()).not.toContain('v');

    await wrapper.find('[data-test="date-from-trigger"]').trigger('click');
    expect(wrapper.find('[data-test="date-picker-panel"]').attributes('lang')).toBe('en-US');
    expect(wrapper.find('[data-test="date-picker-panel"]').text()).toContain('May 2026');
    expect(wrapper.find('[data-test="date-picker-panel"]').element.parentElement?.getAttribute('data-test')).toBe('date-from-group');
    await wrapper.find('[data-test="date-day-2026-05-13"]').trigger('click');

    await wrapper.find('[data-test="date-to-trigger"]').trigger('click');
    await wrapper.find('[data-test="date-day-2026-05-13"]').trigger('click');

    expect(wrapper.find('tbody').text()).toContain('P2251212813RVK19');
    expect(wrapper.find('tbody').text()).not.toContain('P2251212806JND44');

    await wrapper.find('[data-test="scenario-filter-trigger"]').trigger('click');
    expect(wrapper.find('[data-test="ios-select-panel"]').classes()).toContain('ios-select-panel');
    expect(wrapper.find('[data-test="ios-select-panel"]').element.parentElement?.getAttribute('data-test')).toBe('scenario-filter-group');
    await wrapper.find('[data-test="scenario-option-Application failure"]').trigger('click');
    expect(wrapper.find('tbody').text()).toContain('P2251212813RVK19');

    await wrapper.find('[data-test="clear-filters"]').trigger('click');

    expect(wrapper.find('tbody').text()).toContain('P2251212813RVK19');
    expect(wrapper.find('tbody').text()).toContain('P2251212806JND44');
  });
});
