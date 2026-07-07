import type {
  ApplicationFailureThresholdRules,
  DetachmentThresholdRules,
  DeviceAbnormalThresholdRules,
  ThresholdProfile,
  ThresholdRules,
  ThresholdValidationIssue,
} from '@/types/threshold';

export type CompleteThresholdRules = ThresholdRules & {
  deviceAbnormal: DeviceAbnormalThresholdRules;
  detachment: DetachmentThresholdRules;
  applicationFailure: ApplicationFailureThresholdRules;
};

export const THRESHOLD_PROFILE_STORAGE_KEY = 'si-overseas-threshold-profile';
export const DATA_DEVIATION_REQUIRED_PAIR_COUNT = 2;
export const APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT = 2;
export const APPLICATION_FAILURE_TOTAL_PHOTO_SLOTS = 4;

export const defaultThresholdProfile: ThresholdProfile = {
  version: 1,
  savedAt: null,
  display: {
    glucoseUnit: 'mmol/L',
  },
  rules: {
    inaccuracy: {
      lowPersist: {
        belowMmol: 2.8,
        minHours: 4,
        max24hMmol: 7.8,
      },
      noFluctuation: {
        floorMmol: 4.5,
        minHours: 8,
        maxSwingMmol: 1.0,
      },
      jump: {
        deltaMmol: 3.0,
        consecutive: 3,
      },
      deviation: {
        within48hDeviationMmol: 7.0,
        within48hPairCount: DATA_DEVIATION_REQUIRED_PAIR_COUNT,
        within48hQualifiedPairCount: DATA_DEVIATION_REQUIRED_PAIR_COUNT,
        after48hDeviationRangePct: 20,
        after48hPairCount: DATA_DEVIATION_REQUIRED_PAIR_COUNT,
        after48hQualifiedPairCount: DATA_DEVIATION_REQUIRED_PAIR_COUNT,
        after48hWearDays: 2,
      },
    },
    deviceAbnormal: {
      wearDays: 0,
      temporaryAbnormalHours: 3,
    },
    detachment: {
      detachedStatusValue: 1,
      wearDays: 0,
    },
    applicationFailure: {
      photoCount: APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT,
      afterSalesScore: 8,
      manualReviewScore: 5,
    },
  },
};

const fieldRanges: Record<string, { min: number; max: number; integer?: boolean }> = {
  'lowPersist.belowMmol': { min: 2, max: 10 },
  'lowPersist.minHours': { min: 1, max: 24 },
  'lowPersist.max24hMmol': { min: 2, max: 20 },
  'noFluctuation.floorMmol': { min: 1, max: 20 },
  'noFluctuation.minHours': { min: 1, max: 24 },
  'noFluctuation.maxSwingMmol': { min: 0.1, max: 10 },
  'jump.deltaMmol': { min: 0.1, max: 20 },
  'jump.consecutive': { min: 1, max: 10, integer: true },
  'deviation.within48hDeviationMmol': { min: 0.1, max: 20 },
  'deviation.within48hPairCount': { min: 1, max: 10, integer: true },
  'deviation.within48hQualifiedPairCount': { min: 1, max: 10, integer: true },
  'deviation.after48hDeviationRangePct': { min: 1, max: 100 },
  'deviation.after48hPairCount': { min: 1, max: 10, integer: true },
  'deviation.after48hQualifiedPairCount': { min: 1, max: 10, integer: true },
  'deviation.after48hWearDays': { min: 0, max: 30, integer: true },
  'deviceAbnormal.wearDays': { min: 0, max: 30, integer: true },
  'deviceAbnormal.temporaryAbnormalHours': { min: 1, max: 24, integer: true },
  'detachment.detachedStatusValue': { min: 0, max: 1, integer: true },
  'detachment.wearDays': { min: 0, max: 30, integer: true },
  'applicationFailure.photoCount': { min: 2, max: 10, integer: true },
  'applicationFailure.afterSalesScore': { min: 1, max: 10, integer: true },
  'applicationFailure.manualReviewScore': { min: 1, max: 10, integer: true },
};

export function completeThresholdRules(rules: ThresholdRules): CompleteThresholdRules {
  const defaults = defaultThresholdProfile.rules as CompleteThresholdRules;
  return {
    ...cloneThresholdRules(defaults),
    ...rules,
    inaccuracy: {
      ...cloneThresholdRules(defaults).inaccuracy,
      ...rules.inaccuracy,
      lowPersist: {
        ...defaults.inaccuracy.lowPersist,
        ...rules.inaccuracy.lowPersist,
      },
      noFluctuation: {
        ...defaults.inaccuracy.noFluctuation,
        ...rules.inaccuracy.noFluctuation,
      },
      jump: {
        ...defaults.inaccuracy.jump,
        ...rules.inaccuracy.jump,
      },
      deviation: {
        ...defaults.inaccuracy.deviation,
        ...rules.inaccuracy.deviation,
        within48hPairCount: DATA_DEVIATION_REQUIRED_PAIR_COUNT,
        within48hQualifiedPairCount: DATA_DEVIATION_REQUIRED_PAIR_COUNT,
        after48hPairCount: DATA_DEVIATION_REQUIRED_PAIR_COUNT,
        after48hQualifiedPairCount: DATA_DEVIATION_REQUIRED_PAIR_COUNT,
      },
    },
    deviceAbnormal: {
      wearDays: rules.deviceAbnormal?.wearDays ?? defaults.deviceAbnormal.wearDays,
      temporaryAbnormalHours: rules.deviceAbnormal?.temporaryAbnormalHours ?? defaults.deviceAbnormal.temporaryAbnormalHours,
    },
    detachment: {
      detachedStatusValue: rules.detachment?.detachedStatusValue ?? defaults.detachment.detachedStatusValue,
      wearDays: rules.detachment?.wearDays ?? defaults.detachment.wearDays,
    },
    applicationFailure: {
      photoCount: APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT,
      afterSalesScore: rules.applicationFailure?.afterSalesScore ?? defaults.applicationFailure.afterSalesScore,
      manualReviewScore: rules.applicationFailure?.manualReviewScore ?? defaults.applicationFailure.manualReviewScore,
    },
  };
}

export function cloneThresholdProfile(profile: ThresholdProfile): ThresholdProfile {
  const cloned = JSON.parse(JSON.stringify(profile)) as ThresholdProfile;
  cloned.rules = completeThresholdRules(cloned.rules);
  cloned.display = {
    glucoseUnit: cloned.display?.glucoseUnit === 'mg/dL' ? 'mg/dL' : 'mmol/L',
  };
  return cloned;
}

export function cloneThresholdRules(rules: ThresholdRules): ThresholdRules {
  return JSON.parse(JSON.stringify(rules)) as ThresholdRules;
}

function getRuleValue(rules: ThresholdRules, path: string): number {
  const completeRules = completeThresholdRules(rules);
  const [root, groupOrField, maybeField] = path.split('.');
  const inaccuracyGroup = completeRules.inaccuracy[root as keyof ThresholdRules['inaccuracy']];
  const bucket = maybeField
    ? (completeRules[root as keyof ThresholdRules] as unknown as Record<string, Record<string, number>>)[groupOrField]
    : inaccuracyGroup
      ? inaccuracyGroup as unknown as Record<string, number>
      : completeRules[root as keyof ThresholdRules] as unknown as Record<string, number>;
  const field = maybeField ?? groupOrField;
  return bucket[field];
}

export function validateThresholdRules(rules: ThresholdRules): ThresholdValidationIssue[] {
  const issues: ThresholdValidationIssue[] = [];
  const completeRules = completeThresholdRules(rules);

  for (const [field, range] of Object.entries(fieldRanges)) {
    const value = getRuleValue(completeRules, field);
    if (!Number.isFinite(value)) {
      issues.push({ field, message: `${field} must be a valid number.` });
      continue;
    }
    if (range.integer && !Number.isInteger(value)) {
      issues.push({ field, message: `${field} must be a whole number.` });
    }
    if (value < range.min || value > range.max) {
      issues.push({
        field,
        message: `${field} must be between ${range.min} and ${range.max}.`,
      });
    }
  }

  const { within48hPairCount, within48hQualifiedPairCount, after48hPairCount, after48hQualifiedPairCount } = completeRules.inaccuracy.deviation;
  if (within48hPairCount !== DATA_DEVIATION_REQUIRED_PAIR_COUNT) {
    issues.push({
      field: 'deviation.within48hPairCount',
      message: 'within-48h comparison pair count is fixed at 2.',
    });
  }
  if (within48hQualifiedPairCount !== DATA_DEVIATION_REQUIRED_PAIR_COUNT) {
    issues.push({
      field: 'deviation.within48hQualifiedPairCount',
      message: 'within-48h qualified pair count is fixed at 2.',
    });
  }
  if (after48hPairCount !== DATA_DEVIATION_REQUIRED_PAIR_COUNT) {
    issues.push({
      field: 'deviation.after48hPairCount',
      message: 'after-48h comparison pair count is fixed at 2.',
    });
  }
  if (after48hQualifiedPairCount !== DATA_DEVIATION_REQUIRED_PAIR_COUNT) {
    issues.push({
      field: 'deviation.after48hQualifiedPairCount',
      message: 'after-48h qualified pair count is fixed at 2.',
    });
  }
  if (completeRules.applicationFailure!.photoCount !== APPLICATION_FAILURE_REQUIRED_PHOTO_COUNT) {
    issues.push({
      field: 'applicationFailure.photoCount',
      message: 'application-failure required photo count is fixed at 2.',
    });
  }
  if (within48hQualifiedPairCount > within48hPairCount) {
    issues.push({
      field: 'deviation.within48hQualifiedPairCount',
      message: 'within-48h qualified pair count cannot exceed comparison pair count.',
    });
  }
  if (after48hQualifiedPairCount > after48hPairCount) {
    issues.push({
      field: 'deviation.after48hQualifiedPairCount',
      message: 'after-48h qualified pair count cannot exceed comparison pair count.',
    });
  }
  if (completeRules.applicationFailure!.manualReviewScore > completeRules.applicationFailure!.afterSalesScore) {
    issues.push({
      field: 'applicationFailure.manualReviewScore',
      message: 'manual review score cannot be above the after-sales score.',
    });
  }

  return issues;
}

export function assertValidThresholdRules(rules: ThresholdRules) {
  const issues = validateThresholdRules(rules);
  if (issues.length) {
    throw new Error(issues.map(issue => issue.message).join(' '));
  }
}

export function loadStoredThresholdProfile(): ThresholdProfile {
  if (typeof window === 'undefined') return cloneThresholdProfile(defaultThresholdProfile);

  const raw = window.localStorage.getItem(THRESHOLD_PROFILE_STORAGE_KEY);
  if (!raw) return cloneThresholdProfile(defaultThresholdProfile);

  try {
    const parsed = JSON.parse(raw) as ThresholdProfile;
    assertValidThresholdRules(parsed.rules);
    return cloneThresholdProfile(parsed);
  } catch {
    window.localStorage.removeItem(THRESHOLD_PROFILE_STORAGE_KEY);
    return cloneThresholdProfile(defaultThresholdProfile);
  }
}

export function persistThresholdProfile(profile: ThresholdProfile) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(THRESHOLD_PROFILE_STORAGE_KEY, JSON.stringify(profile));
}

export function clearStoredThresholdProfile() {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(THRESHOLD_PROFILE_STORAGE_KEY);
}
