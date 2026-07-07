import { describe, expect, it } from 'vitest';
import originalHtml from '../../index_aligned_to_doc (1)_pdf-ch5-8-en.html?raw';
import {
  extractBodyMarkup,
  extractInlineScript,
  extractStyleBlock,
  normalizeLightOnlyStyleBlock,
} from './originalHtml';

describe('original HTML extraction', () => {
  it('extracts the body markup without executable script tags', () => {
    const body = extractBodyMarkup(originalHtml);

    expect(body).toContain('id="page-login"');
    expect(body).toContain('id="page-diagnosis-search"');
    expect(body).not.toMatch(/<script[\s>]/i);
  });

  it('extracts the original inline script used by the demo interactions', () => {
    const script = extractInlineScript(originalHtml);

    expect(script).toContain('function handleLogin');
    expect(script).toContain('function searchBySn');
    expect(script).not.toContain('function searchDevices');
    expect(script).toContain('function navigateTo');
    expect(() => new Function(script)).not.toThrow();
  });

  it('extracts the visual stylesheet from the original document', () => {
    const style = extractStyleBlock(originalHtml);

    expect(style).toContain('DESIGN TOKENS');
    expect(style).toContain('.page.active');
    expect(style).toContain('.login-shell');
  });

  it('uses GS1-only demo devices with standard SN codes', () => {
    const script = extractInlineScript(originalHtml);
    const mockDeviceSection = script.match(/const MOCK_DEVICES = \{([\s\S]*?)\n\};/)?.[1] ?? '';
    const serials = [...mockDeviceSection.matchAll(/sn: '([^']+)'/g)].map(match => match[1]);
    const types = [...mockDeviceSection.matchAll(/\btype: '([^']+)'/g)].map(match => match[1]);

    expect(mockDeviceSection).toContain("'christest@sibionics.com'");
    expect(mockDeviceSection).not.toContain("'user@example.com'");
    expect(mockDeviceSection).not.toContain("'dealer@sibionics.com'");
    expect(serials.length).toBeGreaterThanOrEqual(4);
    expect(serials.every(sn => /^P\d{10}[A-Z0-9]{5}$/.test(sn))).toBe(true);
    expect(new Set(types)).toEqual(new Set(['GS1']));
    expect(mockDeviceSection).not.toContain('GS3');
    expect(mockDeviceSection).not.toContain('GS1 ECO');
  });

  it('promotes original light-theme styles to the only runtime theme', () => {
    const style = normalizeLightOnlyStyleBlock(extractStyleBlock(originalHtml));

    expect(style).toContain(':root {');
    expect(style).not.toContain('[data-theme="light"]');
    expect(style).not.toContain('[data-theme="dark"]');
    expect(style).not.toContain('.theme-toggle');
    expect(style).toContain('--brand-green');
    expect(style).toContain('LIGHT-ONLY RUNTIME OVERRIDES');
    expect(style).not.toContain('--bg-deep: #040810');
    expect(style).toContain('--bg-deep: #eef1f7');
  });

  it('keeps recommended and not recommended after-sales mocks for every fault subtype', () => {
    const script = extractInlineScript(originalHtml);
    const mockDeviceSection = script.match(/const MOCK_DEVICES = \{([\s\S]*?)\n\};/)?.[1] ?? '';
    const rows = [...mockDeviceSection.matchAll(/mappedFaultSubtype: '([^']+)'[\s\S]*?expectedAfterSales: '([^']+)'/g)];
    const resultsBySubtype = new Map<string, Set<string>>();

    for (const [, subtype, afterSales] of rows) {
      const current = resultsBySubtype.get(subtype) ?? new Set<string>();
      current.add(afterSales);
      resultsBySubtype.set(subtype, current);
    }

    expect(resultsBySubtype.size).toBeGreaterThanOrEqual(4);
    expect(resultsBySubtype.get('Data deviation detected')).toEqual(new Set([
      'Replacement Eligible',
      'Not Eligible',
    ]));
    expect([...resultsBySubtype.values()].every(results => (
      results.has('Replacement Eligible') && results.has('Not Eligible')
    ))).toBe(true);
  });

  it('routes a single SN match directly to fault-category selection', () => {
    const script = extractInlineScript(originalHtml);

    expect(script).toContain('if (matched.length === 1)');
    expect(script).toContain('selectDevice(matched[0].__idx, matched[0].__email)');
    expect(script).not.toContain('validateFields([\'search-email\'])');
  });

  it('allows batch devices to choose non-mapped fault categories but marks them not eligible', () => {
    const script = extractInlineScript(originalHtml);
    const bulkSelectionBody = script.match(/function setBulkDeviceSelection\(sn, scenario\) \{([\s\S]*?)\n\}/)?.[1] ?? '';

    expect(script).toContain('function isDeviceMappedScenario');
    expect(bulkSelectionBody).not.toContain('assertDeviceScenario');
    expect(script).toContain('if (!isDeviceMappedScenario(device, category))');
    expect(script).toContain("isMappedScenario && device?.expectedAfterSales");
    expect(script).toContain("isMappedScenario && isFault && device?.hasServiceCard");
  });

  it('routes data accuracy through curve screening before paired deviation upload', () => {
    const script = extractInlineScript(originalHtml);
    const inferPatternBody = script.match(/function inferInaccuracyPatternDemo\(d\) \{([\s\S]*?)\n\}/)?.[1] ?? '';

    expect(script).toContain('function getExplicitInaccuracyPattern');
    expect(inferPatternBody).toContain("return getExplicitInaccuracyPattern(d) || 'none';");
    expect(inferPatternBody).not.toContain("return ['low', 'nofluc', 'jump'][h % 3]");
    expect(script).toContain("if (category === 'inaccuracy' && !options.inaccuracyDeviationMode)");
    expect(script).toContain('const autoScreenHit = !!getExplicitInaccuracyPattern(device);');
    expect(script).toContain("navigateTo('inaccuracy-upload')");
  });

  it('requires paired evidence in batch when data accuracy curve screening has no hit', () => {
    const script = extractInlineScript(originalHtml);

    expect(script).toContain('function getBulkInaccuracyFirstPassPattern');
    expect(script).toContain("scenario === 'inaccuracy' && !getBulkInaccuracyFirstPassPattern(device)");
    expect(script).toContain("reason: 'inaccuracy_requires_two_pairs'");
    expect(script).toContain('getScenarioReadiness(scenario, evidence, device)');
    expect(script).toContain('const inaccuracyRequiresEvidence = scenario === \'inaccuracy\' && !getExplicitInaccuracyPattern(device);');
  });

  it('keeps completed batch sessions visible with result navigation and management actions', () => {
    const script = extractInlineScript(originalHtml);
    const renderBody = script.match(/function renderSessionManager\(\) \{([\s\S]*?)\n\}\n\nfunction getScenarioLabel/)?.[1] ?? '';

    expect(script).toContain('function getTrackableSessions');
    expect(script).toContain('function renderSessionListSection');
    expect(renderBody).toContain('const sessions = getTrackableSessions();');
    expect(renderBody).not.toContain('const openSessions = getOpenSessions();');
    expect(renderBody).toContain('renderSessionListSection');
    expect(script).toContain("item.status === 'complete'");
    expect(script).toContain("'View result'");
    expect(script).toContain("onclick=\"restoreSession('${item.id}')\"");
    expect(script).toContain('onclick="exportBatchSummaryAsPrintView()"');
    expect(script).toContain('onclick="clearCompletedSessions()"');
    expect(script).toContain('localStorage.setItem(STORAGE_KEYS.sessions');
  });

  it('starts detect records empty and appends them through detect interactions', () => {
    const script = extractInlineScript(originalHtml);

    expect(script).toContain('const MOCK_LOGS = [];');
    expect(script).toContain('function appendDetectRecordFromResult');
    expect(script).toContain('renderLogsSummary();');
    expect(script).toContain('renderDiagPulseStrip();');
  });

  it('keeps one mapped fault scenario per mock SN', () => {
    const script = extractInlineScript(originalHtml);

    expect(script).toContain('function getDeviceExpectedScenario');
    expect(script).toContain('function assertDeviceScenario');
    expect(script).toContain('function isDeviceMappedScenario');
    expect(script).toContain('mappedScenario');
    expect(script).toContain('mappedFaultSubtype');
  });
});
