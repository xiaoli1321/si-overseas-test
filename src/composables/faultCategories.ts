import type { FaultCategory } from '@/types/device';

export type FaultPathTagKind = 'check' | 'material' | 'outcome';

export interface FaultPathTag {
  label: string;
  kind: FaultPathTagKind;
}

export interface FaultCategoryMeta {
  category: FaultCategory;
  key: string;
  title: string;
  shortCopy: string;
  queryCopy: string;
  tags: FaultPathTag[];
}

export const FAULT_CATEGORY_META: FaultCategoryMeta[] = [
  {
    category: 'Data accuracy',
    key: 'data-accuracy',
    title: 'Data accuracy',
    shortCopy: 'Glucose readings differ from BGM, stay flat or low, or show sudden jumps.',
    queryCopy: 'The user reports glucose readings that differ from BGM — including flat-line traces, persistent lows, or sudden jumps.',
    tags: [
      { label: 'Differences from BGM', kind: 'check' },
      { label: 'Jump and down data.', kind: 'check' },
      { label: 'Glucose data in a straight line', kind: 'check' },
    ],
  },
  {
    category: 'Sensor falling off',
    key: 'sensor-falling-off',
    title: 'Sensor falling off',
    shortCopy: 'The sensor unexpectedly fell out while the user was wearing it.',
    queryCopy: 'The sensor unexpectedly fell out while the user was wearing it.',
    tags: [
      { label: 'Sudden fall off', kind: 'check' },
      { label: 'Scratches or exercise', kind: 'check' },
    ],
  },
  {
    category: 'Sensor Malfunction',
    key: 'abnormal-after-warm-up',
    title: 'Sensor Malfunction',
    shortCopy: "The sensor is worn correctly, but the app's home page shows an error message.",
    queryCopy: "The sensor is worn correctly, but the app's home page shows an error message.",
    tags: [
      { label: 'Device error', kind: 'check' },
      { label: 'Not functional', kind: 'check' },
      { label: 'Abnormal during warm-up', kind: 'check' },
    ],
  },
  {
    category: 'Application failure',
    key: 'application-failure',
    title: 'Application failure',
    shortCopy: 'Device malfunction may result from assembly failure or failure to wear the equipment correctly.',
    queryCopy: 'Device malfunction may result from assembly failure or failure to wear the equipment correctly.',
    tags: [
      { label: 'Assembly failed', kind: 'check' },
      { label: 'Guiding needle retention', kind: 'check' },
      { label: 'Early launch', kind: 'check' },
    ],
  },
];

export function faultMetaForCategory(category: FaultCategory) {
  return FAULT_CATEGORY_META.find(item => item.category === category) ?? FAULT_CATEGORY_META[0];
}

export function faultMetaForKey(key: string) {
  return FAULT_CATEGORY_META.find(item => item.key === key) ?? FAULT_CATEGORY_META[0];
}

export function keyForFaultCategory(category: FaultCategory) {
  return faultMetaForCategory(category).key;
}
