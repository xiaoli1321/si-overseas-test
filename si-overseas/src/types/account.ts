export type OrganizationType = 'Pharmacy' | 'Hospital' | 'Distributor' | 'Unassigned';
export type AccountRole = 'manager' | 'staff';

export interface AccountProfile {
  email: string;
  password: string;
  displayName: string;
  role: AccountRole;
  dealerId: string;
  dealerName: string;
  organizationName: string;
  organizationType: OrganizationType;
  region: string;
}
