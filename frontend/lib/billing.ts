import type { ClaimStatus, InvoiceStatus } from "@/types/api";

export const INVOICE_STATUS: Record<InvoiceStatus, { label: string; cls: string }> = {
  draft: { label: "Draft", cls: "text-text-muted" },
  issued: { label: "Unpaid", cls: "text-warning-text" },
  partially_paid: { label: "Part paid", cls: "text-warning-text" },
  paid: { label: "Paid", cls: "text-success-text" },
  credited: { label: "Credited", cls: "text-text-muted" },
};

export const CLAIM_STATUS: Record<ClaimStatus, string> = {
  draft: "Draft", ready: "Ready for submission", submitted: "Submitted", processing: "Processing",
  accepted: "Accepted", rejected: "Rejected", partially_paid: "Partially paid", paid: "Paid",
  resubmission_required: "Resubmission required", cancelled: "Cancelled",
};

/** Mirrors the API's claim state machine (the API is the authority). */
export const CLAIM_NEXT: Record<ClaimStatus, ClaimStatus[]> = {
  draft: ["ready", "cancelled"], ready: ["submitted", "draft", "cancelled"],
  submitted: ["processing", "accepted", "rejected"], processing: ["accepted", "rejected"],
  accepted: [], partially_paid: [], rejected: ["resubmission_required", "cancelled"],
  resubmission_required: ["draft", "cancelled"], paid: [], cancelled: [],
};

export const CLAIM_ACTION: Partial<Record<ClaimStatus, string>> = {
  ready: "Mark ready for submission", draft: "Return to draft", submitted: "Record submission",
  processing: "Mark processing", accepted: "Record acceptance", rejected: "Record rejection",
  resubmission_required: "Needs resubmission", cancelled: "Cancel claim",
};

export const METHOD: Record<string, string> = { cash: "Cash", card: "Card", eft: "EFT", mobile: "Mobile money", medical_aid: "Medical aid" };
export const TAX_CATEGORY: Record<string, string> = { standard: "Standard", zero: "Zero-rated", exempt: "Exempt" };

/** "N$1,250.00" from a decimal string. */
export const nad = (value: string | number | null | undefined) =>
  value === null || value === undefined ? "—" : `N$${Number(value).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
