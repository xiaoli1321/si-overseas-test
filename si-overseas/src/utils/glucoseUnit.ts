import type { GlucoseUnitPreference } from '@/types/threshold';

const MGDL_PER_MMOL = 18;

export function toDisplayGlucose(valueMmol: number, unit: GlucoseUnitPreference): number {
  if (!Number.isFinite(valueMmol)) return valueMmol;
  return unit === 'mg/dL' ? Number((valueMmol * MGDL_PER_MMOL).toFixed(1)) : valueMmol;
}

export function toMmol(value: number, unit: GlucoseUnitPreference): number {
  if (!Number.isFinite(value)) return value;
  const mmol = unit === 'mg/dL' ? value / MGDL_PER_MMOL : value;
  return Number(mmol.toFixed(2));
}

export function formatGlucose(valueMmol: number, unit: GlucoseUnitPreference): string {
  if (!Number.isFinite(valueMmol)) return `N/A ${unit}`;
  const display = toDisplayGlucose(valueMmol, unit);
  const formatted = unit === 'mg/dL' ? String(Math.round(display)) : display.toFixed(1);
  return `${formatted} ${unit}`;
}

export function formatGlucoseDelta(valueMmol: number, unit: GlucoseUnitPreference): string {
  return formatGlucose(valueMmol, unit);
}

export function convertGlucoseText(value: string, unit: GlucoseUnitPreference): string {
  if (unit === 'mmol/L') return value;
  return value.replace(/(\d+(?:\.\d+)?)\s*mmol\/L/g, (_, raw: string) => {
    const mmol = Number(raw);
    if (!Number.isFinite(mmol)) return `${raw} mmol/L`;
    return formatGlucose(mmol, unit);
  });
}
