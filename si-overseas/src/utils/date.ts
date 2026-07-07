/**
 * Formats a device-side local ISO string (e.g. "2026-06-21T13:53:00.302000+02:00")
 * into a clean, human-readable date-time representation showing the device's local time
 * and offset, e.g. "2026-06-21 13:53:00 (UTC+02:00)".
 */
export function formatDeviceTime(isoString: string | null | undefined): string {
  if (!isoString) return 'Unknown';
  if (!isoString.includes('T')) return isoString;

  try {
    const parts = isoString.split('T');
    const datePart = parts[0];
    const rest = parts[1];

    let timePart = '';
    let offsetPart = '';

    if (rest.includes('+')) {
      const idx = rest.indexOf('+');
      timePart = rest.substring(0, idx);
      offsetPart = 'UTC' + rest.substring(idx);
    } else if (rest.includes('-')) {
      const idx = rest.indexOf('-');
      timePart = rest.substring(0, idx);
      offsetPart = 'UTC' + rest.substring(idx);
    } else if (rest.endsWith('Z')) {
      timePart = rest.substring(0, rest.length - 1);
      offsetPart = 'UTC';
    } else {
      timePart = rest;
    }

    if (timePart.includes('.')) {
      timePart = timePart.split('.')[0];
    }

    return offsetPart ? `${datePart} ${timePart} (${offsetPart})` : `${datePart} ${timePart}`;
  } catch {
    return isoString;
  }
}

function formatDurationNumber(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

export function formatDurationMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || !Number.isFinite(minutes)) return 'Unknown';
  const normalizedMinutes = Math.max(0, minutes);
  if (normalizedMinutes < 60) {
    return `${formatDurationNumber(normalizedMinutes)} min`;
  }

  const hours = normalizedMinutes / 60;
  if (hours < 24) {
    return `${formatDurationNumber(hours)} h`;
  }

  return `${formatDurationNumber(hours / 24)} d`;
}

export function formatDurationHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || !Number.isFinite(hours)) return 'Unknown';
  return formatDurationMinutes(hours * 60);
}

export function formatDurationDays(days: number | null | undefined): string {
  if (days === null || days === undefined || !Number.isFinite(days)) return 'Unknown';
  return formatDurationMinutes(days * 24 * 60);
}

export function formatDurationText(value: string): string {
  if (!value) return value;
  const normalizedWearDays = value.replace(
    /\bwear days?\s+(\d+(?:\.\d+)?)(?=\b)/gi,
    (match, rawValue: string) => {
      const numericValue = Number(rawValue);
      if (!Number.isFinite(numericValue)) return match;
      return `wear time ${formatDurationDays(numericValue)}`;
    },
  );
  const normalizedWearThreshold = normalizedWearDays.replace(
    /\bis below\s+(\d+(?:\.\d+)?)(?=\.?\b)/gi,
    (match, rawValue: string) => {
      const numericValue = Number(rawValue);
      if (!Number.isFinite(numericValue)) return match;
      return `is below ${formatDurationDays(numericValue)}`;
    },
  );
  return normalizedWearThreshold.replace(
    /(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?|days?)\b/gi,
    (match, rawValue: string, rawUnit: string) => {
      const numericValue = Number(rawValue);
      if (!Number.isFinite(numericValue)) return match;
      const unit = rawUnit.toLowerCase();
      if (unit.startsWith('min')) return formatDurationMinutes(numericValue);
      if (unit.startsWith('h')) return formatDurationHours(numericValue);
      if (unit.startsWith('d')) return formatDurationDays(numericValue);
      return match;
    },
  );
}
