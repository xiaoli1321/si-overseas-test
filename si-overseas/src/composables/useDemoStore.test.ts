import { beforeEach, describe, expect, it } from 'vitest';
import { useDemoStore } from './useDemoStore';
import { MOCK_DEVICES } from '@/mocks/devices';
import { resolveAccountProfile } from '@/mocks/accounts';

describe('useDemoStore', () => {
  beforeEach(() => {
    const store = useDemoStore();
    store.resetDemoState();
  });

  it('starts with no detect records and an empty dashboard', () => {
    const store = useDemoStore();

    expect(store.records.value).toEqual([]);
    expect(store.dashboard.value).toEqual({
      total: 0,
      allowed: 0,
      notAllowed: 0,
      pending: 0,
    });
  });

  it('starts with the default threshold profile active', () => {
    const store = useDemoStore();

    expect(store.activeThresholdProfile.value.version).toBe(1);
    expect(store.activeThresholdProfile.value.savedAt).toBeNull();
    expect(store.activeThresholdProfile.value.rules.inaccuracy.lowPersist.belowMmol).toBe(2.8);
    expect(store.activeThresholdProfile.value.rules.inaccuracy.noFluctuation.minHours).toBe(8);
    expect(store.activeThresholdProfile.value.rules.inaccuracy.jump.consecutive).toBe(3);
    expect(store.activeThresholdProfile.value.rules.deviceAbnormal).not.toHaveProperty('appScreenshotRequired');
    expect(store.activeThresholdProfile.value.rules.detachment).not.toHaveProperty('appScreenshotRequired');
    expect(store.activeThresholdProfile.value.rules.applicationFailure).not.toHaveProperty('appScreenshotRequired');
  });

  it('saves and resets threshold profiles with versioned snapshots', () => {
    const store = useDemoStore();

    const saved = store.saveThresholdProfile({
      rules: {
        inaccuracy: {
          ...store.activeThresholdProfile.value.rules.inaccuracy,
          lowPersist: {
            ...store.activeThresholdProfile.value.rules.inaccuracy.lowPersist,
            belowMmol: 3.1,
          },
        },
      },
    });

    expect(saved.version).toBe(2);
    expect(saved.savedAt).toEqual(expect.any(String));
    expect(store.activeThresholdProfile.value.rules.inaccuracy.lowPersist.belowMmol).toBe(3.1);

    store.resetThresholdProfile();

    expect(store.activeThresholdProfile.value.version).toBe(3);
    expect(store.activeThresholdProfile.value.rules.inaccuracy.lowPersist.belowMmol).toBe(2.8);
  });

  it('rejects invalid threshold profile values before saving', () => {
    const store = useDemoStore();

    expect(() => store.saveThresholdProfile({
      rules: {
        inaccuracy: {
          ...store.activeThresholdProfile.value.rules.inaccuracy,
          jump: {
            ...store.activeThresholdProfile.value.rules.inaccuracy.jump,
            consecutive: 0,
          },
        },
      },
    })).toThrow(/consecutive/i);
    expect(store.activeThresholdProfile.value.version).toBe(1);
  });

  it('does not expose email-based device lookup', () => {
    const store = useDemoStore();

    expect(store.searchResults.value).toEqual([]);
    expect('searchByEmail' in store).toBe(false);
  });

  it('matches devices by standard SN or partial SN', () => {
    const store = useDemoStore();

    const exact = store.searchBySn('P2251212806JND44');
    const partial = store.searchBySn('JND44');
    const copiedFragment = store.searchBySn('1212-806');

    expect(exact).toHaveLength(1);
    expect(partial).toHaveLength(1);
    expect(copiedFragment.map(device => device.sn)).toEqual(['P2251212806JND44']);
    expect(exact[0].sn).toBe('P2251212806JND44');
  });

  it('distinguishes exact SN matches from fuzzy SN searches', () => {
    const store = useDemoStore();

    const exact = store.findExactDeviceBySn(' p2251212806jnd44 ');
    const fuzzyOnly = store.findExactDeviceBySn('JND44');

    expect(exact?.sn).toBe('P2251212806JND44');
    expect(fuzzyOnly).toBeUndefined();
    expect(store.searchBySn('JND44').map(device => device.sn)).toEqual(['P2251212806JND44']);
  });

  it('keeps a single fault mapping per SN', () => {
    const store = useDemoStore();
    const faults = MOCK_DEVICES.map(device => store.getFaultForSn(device.sn));
    const afterSalesBySubtype = new Map<string, Set<string>>();

    for (const device of MOCK_DEVICES) {
      const current = afterSalesBySubtype.get(device.fault!.faultSubtype) ?? new Set<string>();
      current.add(device.fault!.expectedAfterSales);
      afterSalesBySubtype.set(device.fault!.faultSubtype, current);
    }

    expect(faults.every(Boolean)).toBe(true);
    expect(new Set(MOCK_DEVICES.map(device => device.sn)).size).toBe(MOCK_DEVICES.length);
    expect(MOCK_DEVICES.every(device => device.fault!.faultCategory.length > 0)).toBe(true);
    expect(MOCK_DEVICES.every(device => device.type === 'GS1')).toBe(true);
    expect([...afterSalesBySubtype.values()].every(results => (
      results.has('Replacement Eligible') && results.has('Not Eligible')
    ))).toBe(true);
  });

  it('appends one detect record per completed run and updates dashboard', () => {
    const store = useDemoStore();
    const first = MOCK_DEVICES[0];
    const second = MOCK_DEVICES[1];

    const firstRecord = store.runDetect(first.sn);
    const secondRecord = store.runDetect(second.sn);

    expect(store.records.value).toHaveLength(2);
    expect(store.records.value.map(record => record.sn)).toEqual([second.sn, first.sn]);
    expect(firstRecord.faultSubtype).toBe(first.fault!.faultSubtype);
    expect(secondRecord.faultSubtype).toBe(second.fault!.faultSubtype);
    expect(store.dashboard.value.total).toBe(2);
    expect(store.dashboard.value.allowed + store.dashboard.value.notAllowed + store.dashboard.value.pending).toBe(2);
  });

  it('keeps repeated detect runs for the same SN as separate records', () => {
    const store = useDemoStore();
    const sn = MOCK_DEVICES[0].sn;

    const firstRecord = store.runDetect(sn, 'Data accuracy');
    const secondRecord = store.runDetect(sn, 'Data accuracy');

    expect(store.records.value).toHaveLength(2);
    expect(secondRecord.id).not.toBe(firstRecord.id);
    expect(new Set(store.records.value.map(record => record.id)).size).toBe(2);
    expect(store.records.value.map(record => record.sn)).toEqual([sn, sn]);
  });

  it('snapshots the signed-in account as the detect record initiator and organization', () => {
    const store = useDemoStore();
    const account = resolveAccountProfile(store.currentUser.value);

    const record = store.runDetect(MOCK_DEVICES[0].sn);

    expect(record.initiatorEmail).toBe(account.email);
    expect(record.initiatorName).toBe(account.displayName);
    expect(record.organizationName).toBe(account.organizationName);
    expect(record.organizationType).toBe(account.organizationType);
    expect(record.region).toBe(account.region);
  });

  it('keeps initiator organization as a historical snapshot on each detect run', () => {
    const store = useDemoStore();

    const firstRecord = store.runDetect(MOCK_DEVICES[0].sn);
    const secondRecord = store.runDetect(MOCK_DEVICES[1].sn);

    expect(firstRecord.organizationName).toBe('Chris Overseas Dealer');
    expect(secondRecord.organizationName).toBe('Chris Overseas Dealer');
    expect(store.records.value.find(record => record.id === firstRecord.id)?.organizationName).toBe('Chris Overseas Dealer');
  });

  it('uses an unassigned organization fallback for unknown signed-in emails', () => {
    const store = useDemoStore();
    store.currentUser.value = 'unknown.operator@example.com';

    const record = store.runDetect(MOCK_DEVICES[0].sn);

    expect(record.initiatorEmail).toBe('unknown.operator@example.com');
    expect(record.initiatorName).toBe('unknown.operator@example.com');
    expect(record.organizationName).toBe('Unassigned organization');
    expect(record.organizationType).toBe('Unassigned');
    expect(record.region).toBe('Unassigned region');
  });

  it('scopes visible detect records to the signed-in dealer', () => {
    const store = useDemoStore();

    const firstRecord = store.runDetect(MOCK_DEVICES[0].sn, 'Sensor falling off');
    const secondRecord = store.runDetect(MOCK_DEVICES[1].sn, 'Data accuracy');

    expect(store.visibleRecords.value.map(record => record.id)).toEqual([secondRecord.id, firstRecord.id]);
    expect(store.visibleRecords.value.every(record => record.dealerId === store.currentAccount.value.dealerId)).toBe(true);
  });

  it('seeds default dealer detect records on first load', () => {
    const store = useDemoStore();

    store.ensureDefaultDetectRecords();

    expect(store.records.value.length).toBeGreaterThanOrEqual(4);
    expect(store.visibleRecords.value.every(record => record.dealerId === store.currentAccount.value.dealerId)).toBe(true);
    expect(store.visibleRecords.value.every(record => record.organizationName === 'Chris Overseas Dealer')).toBe(true);
  });

  it('adds missing default detect records without duplicating existing seed rows', () => {
    const store = useDemoStore();
    const manualRecord = store.runDetect(MOCK_DEVICES[0].sn, 'Data accuracy');

    store.ensureDefaultDetectRecords();
    store.ensureDefaultDetectRecords();

    expect(store.records.value.filter(record => record.id.startsWith('FD-DEMO-'))).toHaveLength(4);
    expect(store.records.value.filter(record => record.id === manualRecord.id)).toHaveLength(1);
  });

  it('allows the dealer account to manage threshold settings', () => {
    const store = useDemoStore();

    expect(store.currentAccount.value.email).toBe('christest@sibionics.com');
    expect(store.canManageThresholds.value).toBe(true);
  });

  it('tracks processing sessions separately from completed detect records', () => {
    const store = useDemoStore();

    const session = store.startDetectSession('P2251212806JND44', 'Sensor falling off');

    expect(store.sessions.value).toHaveLength(1);
    expect(store.sessions.value[0]).toMatchObject({
      id: session.id,
      sn: 'P2251212806JND44',
      faultCategory: 'Sensor falling off',
      status: 'processing',
    });
    expect(store.records.value).toEqual([]);

    const record = store.runDetect('P2251212806JND44', 'Sensor falling off');
    store.completeDetectSession(session.id, record);

    expect(store.sessions.value[0]).toMatchObject({
      id: session.id,
      status: 'complete',
      recordId: record.id,
    });
    expect(store.records.value).toHaveLength(1);
  });

  it('tracks multi-device session metadata and progress updates', () => {
    const store = useDemoStore();

    const session = store.startDetectSession('P2251212806JND44', 'Sensor falling off', {
      source: 'multi',
      batchId: 'MULTI-0001',
      stepLabel: 'Retrieving device information',
      progress: 10,
    });

    store.updateDetectSession(session.id, {
      stepLabel: 'Running batch rule checks',
      progress: 55,
    });

    expect(store.sessions.value[0]).toMatchObject({
      id: session.id,
      source: 'multi',
      batchId: 'MULTI-0001',
      status: 'processing',
      stepLabel: 'Running batch rule checks',
      progress: 55,
    });
  });

  it('stores the active threshold snapshot on each data accuracy detect record', () => {
    const store = useDemoStore();

    store.saveThresholdProfile({
      rules: {
        inaccuracy: {
          ...store.activeThresholdProfile.value.rules.inaccuracy,
          lowPersist: {
            ...store.activeThresholdProfile.value.rules.inaccuracy.lowPersist,
            minHours: 5,
          },
        },
      },
    });

    const record = store.runDetect(MOCK_DEVICES[0].sn);

    expect(record.thresholdProfileVersion).toBe(2);
    expect(record.thresholdSnapshot?.rules.inaccuracy.lowPersist.minHours).toBe(5);
    expect(record.reasonSummary).toContain('5h');
  });

  it('uses saved thresholds to change the next data accuracy decision', () => {
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

    const record = store.runDetect(MOCK_DEVICES[0].sn);

    expect(record.conclusion).toBe('No Issue');
    expect(record.afterSales).toBe('Not Eligible');
    expect(record.reasonSummary).toContain('does not meet');
  });

  it('runs multi-device detect by adding one same-category record for each SN', () => {
    const store = useDemoStore();
    const sns = MOCK_DEVICES.slice(0, 3).map(device => device.sn);

    const records = store.runMultiDeviceDetect(sns, 'Sensor falling off');

    expect(records).toHaveLength(3);
    expect(store.records.value).toHaveLength(3);
    expect(records.every(record => record.faultCategory === 'Sensor falling off')).toBe(true);
    expect(store.dashboard.value.total).toBe(3);
  });

  it('marks a user-selected non-mapped fault category as not eligible', () => {
    const store = useDemoStore();

    const record = store.runDetect('P2251212806JND44', 'Sensor falling off');

    expect(record.faultCategory).toBe('Sensor falling off');
    expect(record.conclusion).toBe('No Issue');
    expect(record.afterSales).toBe('Not Eligible');
    expect(record.reasonSummary).toContain('not supported by this mock device');
  });

  it('selects a device and exposes its mapped fault before running detect', () => {
    const store = useDemoStore();
    const device = MOCK_DEVICES[3];

    store.selectDevice(device.sn);

    expect(store.selectedDevice.value?.sn).toBe(device.sn);
    expect(store.currentFault.value?.faultCategory).toBe(device.fault!.faultCategory);
    expect(store.records.value).toEqual([]);
  });

  it('supports version remarks, restoration tracking, and soft-hiding history', async () => {
    window.localStorage.clear();
    const store = useDemoStore();
    store.activeThresholdProfile.value = {
      version: 1,
      savedAt: null,
      rules: JSON.parse(JSON.stringify(store.defaultThresholdProfile.rules)),
    };

    // 1. Save with custom remark
    const rules = store.activeThresholdProfile.value.rules;
    const saved = store.saveThresholdProfile({ rules }, 'Custom remark v2');
    expect(saved.version).toBe(2);
    expect(saved.remark).toBe('Custom remark v2');

    // 2. Rollback to version 1 with remark
    const rolled = await store.rollbackThresholdRemote(1, 'Rollback remark');
    expect(rolled.version).toBe(3);
    expect(rolled.remark).toBe('Rollback remark');
    expect(rolled.restoredFrom).toBe(1);

    // 3. Verify history has both versions
    let history = await store.getThresholdHistoryRemote();
    expect(history.map(p => p.version)).toContain(3);
    expect(history.map(p => p.version)).toContain(2);

    // 4. Update remark for version 2
    const updated = await store.updateThresholdRemarkRemote(2, 'Newly updated remark');
    expect(updated.remark).toBe('Newly updated remark');
    
    history = await store.getThresholdHistoryRemote();
    const v2 = history.find(p => p.version === 2);
    expect(v2?.remark).toBe('Newly updated remark');

    // 5. Hide version 2
    await store.hideThresholdRemote(2);
    history = await store.getThresholdHistoryRemote();
    expect(history.map(p => p.version)).not.toContain(2);
  });
});
