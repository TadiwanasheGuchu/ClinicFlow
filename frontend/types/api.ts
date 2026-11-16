export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export type MembershipSummary = {
  organisation_id: string;
  organisation_name: string;
  organisation_status: string;
  membership_id: string;
  status: "invited" | "active" | "suspended";
};

export type Me = {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  is_platform_admin: boolean;
  last_login_at: string | null;
  memberships: MembershipSummary[];
};

export type Access = {
  organisation_id: string;
  membership_id: string;
  is_owner: boolean;
  permissions: string[];
  grants: { permission: string; branch_id: string | null }[];
};

export type OrganisationSettings = {
  patient_number_prefix: string;
  invoice_number_prefix: string;
  default_appointment_minutes: number;
  booking_buffer_minutes: number;
};

export type Organisation = {
  id: string;
  name: string;
  legal_name: string | null;
  registration_number: string | null;
  email: string | null;
  phone: string | null;
  currency: string;
  timezone: string;
  status: string;
  settings: OrganisationSettings;
  created_at: string;
};

export type TimeInterval = { open: string; close: string };
export type Weekday = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

export type Branch = {
  id: string;
  name: string;
  branch_code: string;
  address: string | null;
  phone: string | null;
  email: string | null;
  operating_hours: Partial<Record<Weekday, TimeInterval[]>>;
  is_active: boolean;
  created_at: string;
};

export type Permission = { code: string; description: string; privileged: boolean };

export type Role = {
  id: string;
  name: string;
  description: string | null;
  template_key: string | null;
  is_system: boolean;
  permissions: string[];
  assignment_count: number;
  created_at: string;
};

export type Assignment = {
  role_id: string;
  role_name: string;
  branch_id: string | null;
  branch_name: string | null;
};

export type Member = {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  phone: string | null;
  status: "invited" | "active" | "suspended";
  roles: Assignment[];
  last_login_at: string | null;
  created_at: string;
};

export type AuditEntry = {
  id: string;
  timestamp: string;
  actor_user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  branch_id: string | null;
  request_id: string | null;
  source_ip: string | null;
  details: Record<string, unknown>;
};

export type Tenant = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  status: string;
  created_at: string;
};
