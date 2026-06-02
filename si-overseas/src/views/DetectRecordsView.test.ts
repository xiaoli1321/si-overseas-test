import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { backendApi } from '@/api/backend';
import { useDemoStore } from '@/composables/useDemoStore';
import DetectRecordsView from './DetectRecordsView.vue';

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/records', name: 'records', component: DetectRecordsView },
      { path: '/detect/:sn/records/:recordId', name: 'detect-record', component: { template: '<div>Detect Record</div>' } },
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
    store.runDetect('P2251212806JND44', 'Data accuracy');

    const { wrapper } = await mountRecords();
    const headers = wrapper.findAll('thead th').map(th => th.text());

    expect(headers).toEqual([
      '',
      'Device Identifier',
      'Type',
      'Scenario',
      'Subtype',
      'Conclusion',
      'After-sales',
      'Adopted',
      'Reject reason',
      'Timestamp',
      'Actions',
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
    expect(wrapper.find('tbody td.records-cell-sn').classes()).toContain('records-cell-sn');
    expect(wrapper.findAll('.log-sum-card')).toHaveLength(4);
    expect(wrapper.find('tbody .badge-red, tbody .badge-green').exists()).toBe(true);
    expect(wrapper.find('tbody .badge-teal, tbody .badge-gray').exists()).toBe(true);
    expect(wrapper.find('[data-test="organization-filter-group"]').exists()).toBe(false);
  });

  it('loads remote stats only once on records page mount in backend mode', async () => {
    const store = useDemoStore();
    store.backendOnline.value = true;
    vi.spyOn(backendApi, 'getRecordsStats').mockResolvedValue({
      total: 0,
      allowed: 0,
      notAllowed: 0,
      pending: 0,
    });
    vi.spyOn(backendApi, 'me').mockResolvedValue(store.currentAccount.value);
    vi.spyOn(backendApi, 'getThreshold').mockResolvedValue(store.activeThresholdProfile.value);
    vi.spyOn(backendApi, 'getRecordsPage').mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 10,
    });

    await mountRecords();
    await flushPromises();

    expect(backendApi.getRecordsStats).toHaveBeenCalledTimes(1);
    expect(backendApi.getRecordsPage).toHaveBeenCalledTimes(1);
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

    expect(csv.split('\n')[0]).toBe('Device Identifier,Type,Scenario,Subtype,Conclusion,After-sales,Adopted,Reject Reason,Timestamp,Reason');
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

    expect(router.currentRoute.value.name).toBe('detect-record');
    expect(router.currentRoute.value.params.sn).toBe('P2251212806JND44');
    expect(router.currentRoute.value.params.recordId).toBe(store.records.value[0].id);
    expect(router.currentRoute.value.query.category).toBe('Sensor falling off');
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

  it('supports pagination controls, changing page size, page clicks, and jump input navigation', async () => {
    const store = useDemoStore();
    // Clear default records and generate 25 records to test pagination (3 pages under page size 10)
    store.clearRecords();
    const account = store.currentAccount.value;
    for (let i = 1; i <= 25; i++) {
      const sn = `P2251212809MRF${String(i).padStart(2, '0')}`;
      store.records.value.push({
        id: `REC-${i}`,
        sn,
        email: 'user@example.com',
        initiatorEmail: account.email,
        initiatorName: account.displayName,
        dealerId: account.dealerId,
        dealerName: account.dealerName,
        organizationName: account.organizationName,
        organizationType: account.organizationType,
        region: account.region,
        deviceType: 'GS1',
        faultCategory: 'Sensor falling off',
        faultSubtype: 'Detachment Detected',
        conclusion: 'Issue Detected',
        afterSales: 'Replacement Eligible',
        timestamp: new Date().toISOString(),
        thresholdProfileVersion: 1,
        thresholdSnapshot: {},
        reasonSummary: 'Test reason',
        verdictAdoption: 'Not recorded',
        verdictRejectionReason: '',
      });
    }

    const { wrapper } = await mountRecords();

    // Verify initial pagination state
    expect(wrapper.find('.pagination').text()).toContain('Showing 1-10 of 25 results');
    
    // Check page buttons
    const prevBtn = wrapper.find('[data-test="page-prev"]');
    const nextBtn = wrapper.find('[data-test="page-next"]');
    expect(prevBtn.attributes('disabled')).toBeDefined();
    expect(nextBtn.attributes('disabled')).toBeUndefined();

    // Verify page numbers are rendered
    expect(wrapper.find('[data-test="page-num-1"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="page-num-2"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="page-num-3"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="page-num-1"]').classes()).toContain('active');

    // Click Page 2
    await wrapper.find('[data-test="page-num-2"]').trigger('click');
    expect(wrapper.find('.pagination').text()).toContain('Showing 11-20 of 25 results');
    expect(wrapper.find('[data-test="page-num-2"]').classes()).toContain('active');

    // Test quick jump navigation
    const jumpInput = wrapper.find('[data-test="page-jump-input"]');
    const jumpBtn = wrapper.find('[data-test="page-jump-btn"]');
    
    await jumpInput.setValue('3');
    await jumpBtn.trigger('click');
    expect(wrapper.find('.pagination').text()).toContain('Showing 21-25 of 25 results');
    expect(wrapper.find('[data-test="page-num-3"]').classes()).toContain('active');

    // Test page size changing
    const select = wrapper.find('.page-size-select');
    await select.setValue(5);
    // Since page size changes, we reset to page 1
    expect(wrapper.find('.pagination').text()).toContain('Showing 1-5 of 25 results');
    expect(wrapper.find('[data-test="page-num-1"]').classes()).toContain('active');
  });

  it('allows deleting a record via confirmation modal', async () => {
    const store = useDemoStore();
    store.runDetect('P2251212806JND44', 'Sensor falling off');
    expect(store.records.value).toHaveLength(1);

    const { wrapper } = await mountRecords();
    
    // Initial state: delete confirmation modal does not exist
    expect(wrapper.find('[data-test="delete-confirm-modal"]').exists()).toBe(false);

    // Click trash button
    const deleteBtn = wrapper.find('.btn-delete');
    expect(deleteBtn.exists()).toBe(true);
    await deleteBtn.trigger('click');

    // Modal should now be open
    const modal = wrapper.find('[data-test="delete-confirm-modal"]');
    expect(modal.exists()).toBe(true);
    expect(modal.text()).toContain('Are you sure you want to delete');

    // Click cancel first
    await wrapper.find('[data-test="delete-confirm-cancel"]').trigger('click');
    expect(wrapper.find('[data-test="delete-confirm-modal"]').exists()).toBe(false);
    expect(store.records.value).toHaveLength(1); // not deleted

    // Click delete again, then click confirm
    await deleteBtn.trigger('click');
    expect(wrapper.find('[data-test="delete-confirm-modal"]').exists()).toBe(true);
    await wrapper.find('[data-test="delete-confirm-ok"]').trigger('click');

    // Modal closes and record is deleted
    expect(wrapper.find('[data-test="delete-confirm-modal"]').exists()).toBe(false);
    expect(store.records.value).toHaveLength(0);
    expect(wrapper.find('tbody').text()).toContain('No detection history yet');
  });

  it('allows batch deleting records via batch confirmation modal', async () => {
    const store = useDemoStore();
    store.runDetect('P2251212806JND44', 'Sensor falling off');
    store.runDetect('P2251212814SWL27', 'Data accuracy');
    expect(store.records.value).toHaveLength(2);

    const { wrapper } = await mountRecords();

    // Checkbox columns are rendered
    const checkboxes = wrapper.findAll('.records-checkbox');
    // Header checkbox + 2 row checkboxes = 3
    expect(checkboxes).toHaveLength(3);

    // Selected count starts at 0, no toolbar visible
    expect(wrapper.find('[data-test="batch-action-bar"]').exists()).toBe(false);

    // Select all using header checkbox
    const headerCheckbox = checkboxes[0];
    await headerCheckbox.setChecked(true);

    // Toolbar should now show up
    expect(wrapper.find('[data-test="batch-action-bar"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="batch-action-bar"]').text()).toContain('Selected 2 records');

    // Click Batch Delete button -> opens batch delete modal
    expect(wrapper.find('[data-test="batch-delete-confirm-modal"]').exists()).toBe(false);
    await wrapper.find('[data-test="batch-delete-btn"]').trigger('click');
    expect(wrapper.find('[data-test="batch-delete-confirm-modal"]').exists()).toBe(true);

    // Click Cancel -> closes modal, records still there
    await wrapper.find('[data-test="batch-delete-confirm-cancel"]').trigger('click');
    expect(wrapper.find('[data-test="batch-delete-confirm-modal"]').exists()).toBe(false);
    expect(store.records.value).toHaveLength(2);

    // Click Batch Delete again -> click Confirm
    await wrapper.find('[data-test="batch-delete-btn"]').trigger('click');
    await wrapper.find('[data-test="batch-delete-confirm-ok"]').trigger('click');

    // Modal closes, records deleted, toolbar disappears
    expect(wrapper.find('[data-test="batch-delete-confirm-modal"]').exists()).toBe(false);
    expect(wrapper.find('[data-test="batch-action-bar"]').exists()).toBe(false);
    expect(store.records.value).toHaveLength(0);
    expect(wrapper.find('tbody').text()).toContain('No detection history yet');
  });
});
