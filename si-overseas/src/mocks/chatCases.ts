import type { FaultCategory } from '@/types/device';

/**
 * Chat input matrix derived from mock-sn-fault-list.xlsx (GS1 SN Fault List).
 * Covers SN-only, SN + natural-language description, description-only,
 * follow-up SN, and image combinations.
 */
export type ChatMockInputKind =
  | 'sn_only'
  | 'sn_and_description'
  | 'description_only'
  | 'description_then_sn'
  | 'sn_description_and_images'
  | 'images_only';

export interface ChatMockTurn {
  text: string;
  imageCount?: number;
}

export interface ChatMockCase {
  id: string;
  kind: ChatMockInputKind;
  sn: string;
  /** When omitted, expected fault category is not asserted. */
  expectedCategory?: FaultCategory;
  turns: ChatMockTurn[];
  expectsResult: boolean;
  expectsNeedSn?: boolean;
  expectsNeedImages?: boolean;
}

const NL_BY_CATEGORY: Record<FaultCategory, string[]> = {
  'Data accuracy': [
    'The glucose curve looks inaccurate with persistent lows.',
    'Readings are flat with no fluctuation on the CGM curve.',
    'We see repeated jump points in the glucose trace.',
  ],
  'Sensor falling off': [
    'The sensor fell off during wear and will not stay attached.',
  ],
  'Sensor Abnormal': [
    'Abnormal sensor status after warm-up during initialization.',
    'Probe failure detected right after sensor start-up.',
    'Temporary sensor error that did not recover after 3 hours.',
  ],
  'Application failure': [
    'Application site failure with bleeding and poor adhesive at the implant site.',
  ],
};

const XLSX_SN_MATRIX: Array<{ sn: string; category: FaultCategory }> = [
  { sn: 'P2251212806JND44', category: 'Data accuracy' },
  { sn: 'P2251212809MRF71', category: 'Sensor falling off' },
  { sn: 'P2251212810NSG88', category: 'Sensor Abnormal' },
  { sn: 'P2251212813RVK19', category: 'Application failure' },
];

export const CHAT_FAULT_CATEGORY_BY_SN = new Map(
  XLSX_SN_MATRIX.map(row => [row.sn, row.category] as const),
);

function pickDescription(category: FaultCategory, index = 0) {
  const options = NL_BY_CATEGORY[category];
  return options[index % options.length];
}

export const CHAT_MOCK_CASES: ChatMockCase[] = [
  ...XLSX_SN_MATRIX.map((row) => ({
    id: `sn-only-${row.sn}`,
    kind: 'sn_only' as const,
    sn: row.sn,
    expectedCategory: row.category,
    turns: [{ text: row.sn }],
    expectsResult: row.category !== 'Application failure',
    expectsNeedImages: row.category === 'Application failure',
  })),
  ...XLSX_SN_MATRIX.map((row, index) => ({
    id: `sn-desc-${row.sn}`,
    kind: 'sn_and_description' as const,
    sn: row.sn,
    expectedCategory: row.category,
    turns: [{ text: `SN ${row.sn}: ${pickDescription(row.category, index)}` }],
    expectsResult: row.category !== 'Application failure',
    expectsNeedImages: row.category === 'Application failure',
  })),
  ...XLSX_SN_MATRIX.filter(row => row.category === 'Application failure').map(row => ({
    id: `sn-desc-img-${row.sn}`,
    kind: 'sn_description_and_images' as const,
    sn: row.sn,
    expectedCategory: row.category,
    turns: [{ text: `SN ${row.sn} ${pickDescription(row.category)}`, imageCount: 2 }],
    expectsResult: true,
  })),
  {
    id: 'description-only-data-accuracy',
    kind: 'description_only',
    sn: 'P2251212806JND44',
    expectedCategory: 'Data accuracy',
    turns: [{ text: pickDescription('Data accuracy') }],
    expectsResult: false,
    expectsNeedSn: true,
  },
  {
    id: 'description-then-sn-data-accuracy',
    kind: 'description_then_sn',
    sn: 'P2251212806JND44',
    expectedCategory: 'Data accuracy',
    turns: [
      { text: pickDescription('Data accuracy') },
      { text: 'P2251212806JND44' },
    ],
    expectsResult: true,
  },
  {
    id: 'description-then-sn-falloff',
    kind: 'description_then_sn',
    sn: 'P2251212809MRF71',
    expectedCategory: 'Sensor falling off',
    turns: [
      { text: pickDescription('Sensor falling off') },
      { text: 'P2251212809MRF71' },
    ],
    expectsResult: true,
  },
  {
    id: 'images-only-app-failure',
    kind: 'images_only',
    sn: 'P2251212813RVK19',
    expectedCategory: 'Application failure',
    turns: [{ text: 'Application site photos are available for review.', imageCount: 2 }],
    expectsResult: false,
    expectsNeedSn: true,
  },
];

export const CHAT_AGENT_SCRIPTS = {
  major: (bracketLabel: string) =>
    `Based on our AI agent's assessment, the current device fault is likely **${bracketLabel}**. Click to open the after-sales tool.`,
  offFour:
    "Our AI agent could not determine the fault type for now. Please assess it manually.",
  unrelated:
    'Sorry, the issue you described doesn't appear to be CGM-related. Please rephrase it, or ask about a CGM-related problem.',
} as const;

export const CHAT_SCRIPT_BRACKET: Record<FaultCategory, string> = {
  'Data accuracy': '[data accuracy]',
  'Application failure': '[implantation failure]',
  'Sensor Abnormal': '[Sensor Malfunction]',
  'Sensor falling off': '[detachment]',
};

export const CHAT_MAJOR_SCENARIO_KEYWORDS: Record<FaultCategory, readonly string[]> = {
  'Data accuracy': [
    'data accuracy',
    'inaccurate glucose',
    'wrong glucose readings',
    'glucose readings look wrong',
  ],
  'Application failure': [
    'implant failure',
    'implantation failure',
    'insertion failed',
    'application site failure',
  ],
  'Sensor Abnormal': [
    'sensor abnormal',
    'abnormal after warm-up',
    'abnormal after warmup',
    'probe failure after startup',
  ],
  'Sensor falling off': [
    'detachment',
    'sensor fell off',
    'fell off during wear',
    'came loose',
  ],
} as const;

export const CHAT_UNRELATED_PHRASES: readonly string[] = [
  'not related to cgm',
  'nothing to do with cgm',
  'not related to glucose monitoring',
  'unrelated to my cgm',
];

export const CHAT_OFF_FOUR_PHRASES: readonly string[] = [
  'manual judgment',
  'manual triage needed',
  'cannot auto-classify',
  'cannot classify the fault type',
];

export function textMatchesPhraseList(text: string, phrases: readonly string[]): boolean {
  const lower = text.trim().toLowerCase();
  if (!lower) return false;
  return phrases.some(phrase => lower.includes(phrase.trim().toLowerCase()));
}

export const CHAT_SCRIPT_REPLY_MOCK_CASES: ChatMockCase[] = [
  {
    id: 'script-major-alt-data-accuracy',
    kind: 'description_only',
    sn: 'P2251212806JND44',
    expectedCategory: 'Data accuracy',
    turns: [{ text: 'wrong glucose readings' }],
    expectsResult: false,
    expectsNeedSn: true,
  },
  {
    id: 'script-major-en-data-accuracy',
    kind: 'description_only',
    sn: 'P2251212806JND44',
    expectedCategory: 'Data accuracy',
    turns: [{ text: 'data accuracy on the trace' }],
    expectsResult: false,
    expectsNeedSn: true,
  },
  {
    id: 'script-major-alt-implant',
    kind: 'description_only',
    sn: 'P2251212813RVK19',
    expectedCategory: 'Application failure',
    turns: [{ text: 'insertion failed' }],
    expectsResult: false,
    expectsNeedSn: true,
  },
  {
    id: 'script-major-en-implant',
    kind: 'description_only',
    sn: 'P2251212813RVK19',
    expectedCategory: 'Application failure',
    turns: [{ text: 'implant failure at the site' }],
    expectsResult: false,
    expectsNeedSn: true,
  },
  {
    id: 'script-major-alt-sensor-abnormal',
    kind: 'description_only',
    sn: 'P2251212810NSG88',
    expectedCategory: 'Sensor Abnormal',
    turns: [{ text: 'abnormal sensor status' }],
    expectsResult: false,
    expectsNeedSn: true,
  },
  {
    id: 'script-major-en-sensor-abnormal',
    kind: 'description_only',
    sn: 'P2251212810NSG88',
    expectedCategory: 'Sensor Abnormal',
    turns: [{ text: 'sensor abnormal after startup' }],
    expectsResult: false,
    expectsNeedSn: true,
  },
  {
    id: 'script-major-alt-detach',
    kind: 'description_only',
    sn: 'P2251212809MRF71',
    expectedCategory: 'Sensor falling off',
    turns: [{ text: 'detachment during wear' }],
    expectsResult: false,
    expectsNeedSn: true,
  },
  {
    id: 'script-major-en-detach',
    kind: 'description_only',
    sn: 'P2251212809MRF71',
    expectedCategory: 'Sensor falling off',
    turns: [{ text: 'sensor fell off yesterday' }],
    expectsResult: false,
    expectsNeedSn: true,
  },
  {
    id: 'script-off-four-alt',
    kind: 'description_only',
    sn: 'P2251212806JND44',
    turns: [{ text: 'cannot auto-classify this case' }],
    expectsResult: false,
  },
  {
    id: 'script-off-four-en',
    kind: 'description_only',
    sn: 'P2251212806JND44',
    turns: [{ text: 'manual triage needed for this ticket' }],
    expectsResult: false,
  },
  {
    id: 'script-unrelated-alt',
    kind: 'description_only',
    sn: '-',
    turns: [{ text: 'nothing to do with cgm' }],
    expectsResult: false,
  },
  {
    id: 'script-unrelated-en',
    kind: 'description_only',
    sn: '-',
    turns: [{ text: 'This is not related to cgm at all.' }],
    expectsResult: false,
  },
];

export const CHAT_MOCK_CASES_ALL: ChatMockCase[] = [...CHAT_MOCK_CASES, ...CHAT_SCRIPT_REPLY_MOCK_CASES];
