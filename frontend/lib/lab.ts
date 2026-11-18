import type { LabFlag, LabOrderStatus } from "@/types/api";

export const LAB_STATUS_LABEL: Record<LabOrderStatus, string> = {
  requested: "Requested",
  collected: "Specimen collected",
  sent: "Sent to laboratory",
  processing: "Processing",
  completed: "Results in — to review",
  reviewed: "Reviewed",
  cancelled: "Cancelled",
};

/** Progress steps a technician can take next (mirrors the API's transitions). */
export const NEXT_STEPS: Partial<Record<LabOrderStatus, ("collected" | "sent" | "processing" | "completed")[]>> = {
  requested: ["collected", "sent", "processing"],
  collected: ["sent", "processing", "completed"],
  sent: ["processing", "completed"],
  processing: ["completed"],
};

export const STEP_LABEL = {
  collected: "Specimen collected",
  sent: "Sent to laboratory",
  processing: "Laboratory processing",
  completed: "All results in",
} as const;

export const RESULTABLE: LabOrderStatus[] = ["collected", "sent", "processing", "completed", "reviewed"];

export const FLAG_LABEL: Record<LabFlag, string> = {
  none: "—",
  normal: "Normal",
  low: "Low",
  high: "High",
  critical_low: "Critically low",
  critical_high: "Critically high",
  abnormal: "Abnormal",
};

export const ABNORMAL: LabFlag[] = ["low", "high", "critical_low", "critical_high", "abnormal"];

export const LAB_GROUPS = [
  ["outstanding", "Outstanding"],
  ["to_review", "To review"],
  ["reviewed", "Reviewed"],
  ["cancelled", "Cancelled"],
  ["all", "All"],
] as const;
