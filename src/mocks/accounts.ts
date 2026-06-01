import type { AccountProfile } from '@/types/account';

export const MOCK_ACCOUNT_PROFILES: AccountProfile[] = [
  {
    email: 'christest@sibionics.com',
    password: 'password123',
    displayName: 'Chris Test',
    role: 'manager',
    dealerId: 'chris-overseas-dealer',
    dealerName: 'Chris Overseas Dealer',
    organizationName: 'Chris Overseas Dealer',
    organizationType: 'Distributor',
    region: 'A Region',
  },
];

export function cloneAccountProfile(profile: AccountProfile): AccountProfile {
  return { ...profile };
}

export function resolveAccountProfile(email: string, profiles = MOCK_ACCOUNT_PROFILES): AccountProfile {
  const normalizedEmail = email.trim().toLowerCase();
  const accountProfileByEmail = new Map(
    profiles.map(profile => [profile.email.toLowerCase(), profile]),
  );
  const matched = accountProfileByEmail.get(normalizedEmail);
  if (matched) return { ...matched };

  const displayEmail = email.trim() || 'unknown.operator@example.com';
  return {
    email: displayEmail,
    password: '',
    displayName: displayEmail,
    role: 'manager',
    dealerId: 'unassigned-dealer',
    dealerName: 'Unassigned dealer',
    organizationName: 'Unassigned organization',
    organizationType: 'Unassigned',
    region: 'Unassigned region',
  };
}
