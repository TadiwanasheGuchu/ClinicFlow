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
  vat_registered: boolean;
  vat_rate: string;
  vat_number: string | null;
  invoice_due_days: number;
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

// --- Clinical (Phase 4) ---
export type Allergy = { id: string; substance: string; reaction: string | null; severity: string; status: string; status_reason: string | null; created_at: string };
export type AllergySummary = { state: "has_allergies" | "no_known_allergies" | "not_recorded"; allergies: Allergy[]; assessed_at: string | null };

export type ClinicalNote = {
  id: string;
  encounter_id: string;
  note_group_id: string;
  version_number: number;
  status: "draft" | "signed" | "amended";
  note_type: string;
  content: Record<string, string>;
  author_user_id: string;
  author_name: string | null;
  signed_at: string | null;
  content_sha256: string | null;
  amends_note_id: string | null;
  amendment_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type Observation = { id: string; encounter_id: string; observation_type: string; value: string; unit: string; measured_at: string; status: string; status_reason: string | null };
export type Diagnosis = { id: string; encounter_id: string; code_system: string; code: string | null; description: string; clinical_status: string; status_reason: string | null; onset_date: string | null; created_at: string };
export type Referral = { id: string; encounter_id: string; receiving_provider: string; receiving_specialty: string | null; urgency: string; reason: string; status: string; status_reason: string | null; referring_user_id: string; created_at: string };
export type PrescriptionItem = { position: number; medication: string; strength: string | null; dosage_form: string | null; dose: string; frequency: string; route: string | null; duration: string | null; quantity: string | null; instructions: string | null };
export type Prescription = {
  id: string;
  encounter_id: string;
  patient_id: string;
  prescription_number: string;
  prescriber_name: string;
  prescriber_registration: string;
  status: "issued" | "cancelled";
  issued_at: string;
  cancelled_at: string | null;
  cancel_reason: string | null;
  allergy_warning: { matches: { medication: string; allergy: string }[]; reason: string } | null;
  items: PrescriptionItem[];
};
export type Encounter = {
  id: string;
  patient_id: string;
  branch_id: string;
  branch_name: string;
  appointment_id: string | null;
  encounter_type: string;
  status: "open" | "closed";
  clinician_user_id: string;
  clinician_name: string;
  started_at: string;
  ended_at: string | null;
};
export type EncounterDetail = Encounter & { notes: ClinicalNote[]; observations: Observation[]; diagnoses: Diagnosis[]; prescriptions: Prescription[]; referrals: Referral[] };
export type ClinicalSummary = {
  patient_id: string;
  allergies: AllergySummary;
  active_diagnoses: Diagnosis[];
  latest_observations: { observation_type: string; value: string; unit: string; measured_at: string }[];
  recent_prescriptions: Prescription[];
  encounters: Encounter[];
};

// --- Billing and medical aid (Phase 5) ---
export type Service = { id: string; code: string; tariff_code: string | null; name: string; description: string | null; unit_price: string; tax_category: "standard" | "zero" | "exempt"; is_active: boolean };
export type InvoiceItem = { position: number; service_id: string | null; code: string | null; tariff_code: string | null; description: string; quantity: string; unit_price: string; tax_rate: string; line_subtotal: string; tax_amount: string; line_total: string };
export type BillingPayment = { id: string; invoice_id: string; receipt_number: string; amount: string; method: string; reference: string | null; status: "completed" | "reversed"; received_at: string; received_by: string; claim_id: string | null; reversed_at: string | null; reversal_reason: string | null };
export type CreditNote = { id: string; credit_note_number: string; amount: string; reason: string; issued_at: string; issued_by: string };
export type Refund = { id: string; refund_number: string; amount: string; method: string; reference: string | null; reason: string; refunded_at: string; refunded_by: string };
export type InvoiceStatus = "draft" | "issued" | "partially_paid" | "paid" | "credited";
export type InvoiceSummary = { id: string; invoice_number: string | null; status: InvoiceStatus; patient_id: string; patient_name: string; patient_number: string; branch_id: string; appointment_id: string | null; total: string; amount_due: string; issued_at: string | null; due_at: string | null; created_at: string };
export type Invoice = InvoiceSummary & {
  subtotal: string; tax_amount: string; amount_paid: string; amount_credited: string; amount_refunded: string; credit_balance: string; notes: string | null;
  items: InvoiceItem[]; payments: BillingPayment[]; credit_notes: CreditNote[]; refunds: Refund[];
  claims: { id: string; claim_number: string; status: string; claimed_amount: string; approved_amount: string | null; paid_amount: string }[];
};
export type StatementLine = { date: string; kind: string; reference: string; description: string; debit: string; credit: string; balance: string };
export type Statement = { patient_id: string; lines: StatementLine[]; balance: string };
export type CashUp = { date: string; branch_id: string | null; by_method: { method: string; count: number; received: string; refunded: string; net: string }[]; total_received: string; total_refunded: string; net: string; reversed_payments: BillingPayment[]; payments: BillingPayment[] };
export type Fund = { id: string; name: string; administrator: string | null; phone: string | null; email: string | null; claims_address: string | null; notes: string | null; is_active: boolean };
export type AidMembership = { id: string; patient_id: string; fund_id: string; fund_name: string; plan_name: string | null; membership_number: string; dependant_code: string | null; principal_member_name: string | null; principal_member_id_number: string | null; effective_from: string | null; effective_until: string | null; is_active: boolean; verification_status: string; verified_at: string | null };
export type ClaimStatus = "draft" | "ready" | "submitted" | "processing" | "accepted" | "rejected" | "partially_paid" | "paid" | "resubmission_required" | "cancelled";
export type Claim = {
  id: string; claim_number: string; status: ClaimStatus; invoice_id: string; invoice_number: string | null; patient_id: string; patient_name: string; fund_id: string; fund_name: string;
  membership_snapshot: Record<string, string | null>; diagnosis_codes: string[]; claimed_amount: string; approved_amount: string | null; paid_amount: string; patient_portion: string;
  fund_reference: string | null; submission_method: string | null; submitted_at: string | null; response_at: string | null; rejection_reason: string | null; created_at: string;
};
export type ClaimDetail = Claim & { events: { id: string; event_type: string; previous_status: string | null; new_status: string | null; message: string | null; details: Record<string, unknown>; actor_user_id: string; created_at: string }[] };

// --- Reports (Phase 6) ---
export type DayCounts = { date: string; booked: number; completed: number; cancelled: number; no_show: number; walk_in: number; online: number };
export type OperationalReport = {
  start: string; end: string; branch_id: string | null; totals: DayCounts;
  cancellation_rate_percent: string | null; no_show_rate_percent: string | null;
  average_wait_minutes: string | null; wait_sample: number; new_patients: number; consultations: number;
  daily: DayCounts[];
  by_provider: { provider_id: string; provider_name: string; booked: number; completed: number; no_show: number; booked_minutes: number; available_minutes: number; utilisation_percent: string | null }[];
  by_branch: { branch_id: string; branch_name: string; booked: number; completed: number; cancelled: number; no_show: number }[];
};
export type MoneyByKey = { key: string; label: string; count: number; amount: string };
export type FinancialReport = {
  start: string; end: string; branch_id: string | null; invoiced: string; invoice_count: number; credited: string; collected: string; refunded: string; net_collected: string;
  series: { period: string; invoiced: string; collected: string; refunded: string }[];
  collected_by_method: MoneyByKey[]; revenue_by_service: MoneyByKey[]; revenue_by_provider: MoneyByKey[];
  outstanding_total: string; aged_debt: { bucket: string; invoices: number; amount: string }[];
  claims: { status: ClaimStatus; count: number; claimed: string; paid: string }[]; claims_outstanding: string; claim_rejection_rate_percent: string | null;
};
