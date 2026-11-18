import type { MovementType, POStatus } from "@/types/api";

export const MOVEMENT_LABEL: Record<MovementType, string> = {
  receipt: "Received",
  usage: "Used",
  transfer_out: "Transferred out",
  transfer_in: "Transferred in",
  count: "Stock count",
  write_off: "Written off",
};

export const PO_STATUS: Record<POStatus, string> = {
  draft: "Draft",
  ordered: "Ordered",
  partially_received: "Partly received",
  received: "Received",
  cancelled: "Cancelled",
};

/** Signed quantity for the ledger, e.g. "+200" or "−40". */
export const signed = (n: number) => (n > 0 ? `+${n}` : `−${Math.abs(n)}`);
