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
  portal_enabled: boolean;
  online_auto_confirm: boolean;
  online_min_notice_hours: number;
  online_max_days_ahead: number;
  online_cancel_cutoff_hours: number;
  online_max_upcoming: number;
  reminder_hours_before: number;
  reminders_enabled: boolean;
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
  slug: string | null;
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

export type PatientSummary = {
  id: string;
  patient_number: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  phone: string | null;
  status: string;
};

export type EmergencyContact = { name: string; phone: string; relationship: string | null };

export type Patient = PatientSummary & {
  sex: string | null;
  nationality: string | null;
  id_number: string | null;
  email: string | null;
  address: string | null;
  emergency_contact: EmergencyContact | null;
  preferred_channel: string;
  created_at: string;
};

export type StaffProfile = {
  id: string;
  membership_id: string;
  profession: string;
  specialty: string | null;
  registration_body: string | null;
  professional_number: string | null;
  licence_expiry_date: string | null;
  registration_status: "unverified" | "verified" | "rejected";
  verified_by: string | null;
  verified_at: string | null;
  verification_note: string | null;
  licence_current: boolean;
};

export type Provider = {
  id: string;
  membership_id: string;
  display_name: string;
  profession: string;
  specialty: string | null;
  booking_enabled: boolean;
  online_booking_enabled: boolean;
  credentials_current: boolean;
  branch_ids: string[];
};

export type AvailabilityWindow = {
  id?: string;
  branch_id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  effective_from: string | null;
  effective_until: string | null;
};

export type Unavailability = { id: string; start_at: string; end_at: string; reason: string | null };

export type AppointmentType = {
  id: string;
  name: string;
  description: string | null;
  duration_minutes: number;
  fee: string;
  booking_buffer_minutes: number;
  is_active: boolean;
  online_bookable: boolean;
};

export type Slot = { start_at: string; end_at: string };

export type AppointmentStatus =
  | "requested"
  | "pending_confirmation"
  | "confirmed"
  | "checked_in"
  | "waiting"
  | "in_consultation"
  | "completed"
  | "cancelled"
  | "no_show";

export type Appointment = {
  id: string;
  reference: string;
  status: AppointmentStatus;
  start_at: string;
  end_at: string;
  booking_source: string;
  booking_note: string | null;
  cancellation_reason: string | null;
  is_override: boolean;
  patient: { id: string; name: string; patient_number: string; date_of_birth: string };
  provider: { id: string; name: string };
  branch: { id: string; name: string };
  appointment_type: { id: string; name: string; duration_minutes: number };
  created_at: string;
  updated_at: string;
};

export type AppointmentEvent = {
  id: string;
  event_type: string;
  previous_status: string | null;
  new_status: string | null;
  actor_user_id: string | null;
  reason: string | null;
  details: Record<string, unknown>;
  created_at: string;
};

export type AppointmentDetail = Appointment & { events: AppointmentEvent[] };

export type NotificationStatus = "pending" | "sent" | "failed" | "cancelled" | "skipped";

export type Notification = {
  id: string;
  patient_id: string | null;
  appointment_id: string | null;
  event_type: string;
  channel: string;
  recipient: string | null;
  body: string;
  delivery_status: NotificationStatus;
  scheduled_for: string;
  attempts: number;
  next_attempt_at: string | null;
  last_error: string | null;
  sent_at: string | null;
  created_at: string;
};

export type PortalAccountStatus = { linked: boolean; linked_via: string | null; linked_at: string | null; email: string | null };
