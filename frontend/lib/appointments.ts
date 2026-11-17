import type { AppointmentStatus } from "@/types/api";

export const STATUS_LABEL: Record<AppointmentStatus, string> = {
  requested: "Requested",
  pending_confirmation: "Pending confirmation",
  confirmed: "Confirmed",
  checked_in: "Checked in",
  waiting: "Waiting",
  in_consultation: "In consultation",
  completed: "Completed",
  cancelled: "Cancelled",
  no_show: "No-show",
};

/** Mirrors the API state machine (the API is the authority). */
export const NEXT_STATUSES: Record<AppointmentStatus, AppointmentStatus[]> = {
  requested: ["pending_confirmation", "confirmed"],
  pending_confirmation: ["confirmed"],
  confirmed: ["checked_in", "no_show"],
  checked_in: ["waiting", "in_consultation"],
  waiting: ["in_consultation"],
  in_consultation: ["completed"],
  completed: [],
  cancelled: [],
  no_show: [],
};

export const ACTION_LABEL: Partial<Record<AppointmentStatus, string>> = {
  pending_confirmation: "Mark pending",
  confirmed: "Confirm",
  checked_in: "Check in",
  waiting: "Move to waiting",
  in_consultation: "Start consultation",
  completed: "Complete",
  no_show: "Mark no-show",
};

export const CANCELLABLE: AppointmentStatus[] = ["requested", "pending_confirmation", "confirmed", "checked_in", "waiting"];
export const RESCHEDULABLE: AppointmentStatus[] = ["requested", "pending_confirmation", "confirmed"];

export const VIOLATION_LABEL: Record<string, string> = {
  in_past: "The time is in the past",
  outside_availability: "Outside the practitioner’s working hours",
  provider_unavailable: "Practitioner on leave",
  provider_double_booked: "Practitioner already booked",
  patient_double_booked: "Patient already booked",
};

export const PROFESSIONS: Record<string, string> = {
  medical_practitioner: "Medical practitioner",
  dentist: "Dentist",
  physiotherapist: "Physiotherapist",
  nurse: "Nurse",
  pharmacist: "Pharmacist",
  laboratory_technician: "Laboratory technician",
  other_clinical: "Other clinical",
  administrative: "Administrative",
};
