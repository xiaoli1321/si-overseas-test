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
    shortCopy: 'Glucose readings differ from BGM, remain flat, stay unusually low, or change suddenly.',
    queryCopy: 'User feedback glucose data showed discrepancies compared to BGM, also included instances of flat glucose readings, persistent low glucose, or sudden glucose fluctuations.',
    tags: [
      { label: 'Differences from BGM', kind: 'check' },
      { label: 'Sudden Glucose Fluctuations.', kind: 'check' },
      { label: 'Flat Glucose Readings', kind: 'check' },
    ],
  },
  {
    category: 'Sensor falling off',
    key: 'sensor-falling-off',
    title: 'Sensor falling off',
    shortCopy: 'The sensor detached unexpectedly while being worn.',
    queryCopy: 'The sensor detached unexpectedly while being worn.',
    tags: [
      { label: 'Sudden fall off', kind: 'check' },
      { label: 'Scratches or exercise', kind: 'check' },
    ],
  },
  {
    category: 'Sensor Abnormal',
    key: 'abnormal-after-warm-up',
    title: 'Sensor Malfunction',
    shortCopy: "The sensor is being worn correctly, but the app displays an error message.",
    queryCopy: "The sensor is being worn correctly, but the app displays an error message.",
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
    shortCopy: 'The device may not function properly due to an assembly issue or incorrect application.',
    queryCopy: 'The device may not function properly due to an assembly issue or incorrect application.',
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
