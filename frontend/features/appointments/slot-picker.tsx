"use client";

import { useEffect, useState, useTransition } from "react";

import { timeOf } from "@/lib/time";
import type { Slot } from "@/types/api";

import { loadPortalSlots } from "@/features/portal/actions";

import { loadSlots } from "./actions";

/** Loads free start times for the chosen practitioner, branch, type and date. */
export function SlotPicker({
  providerId,
  branchId,
  typeId,
  date,
  name = "slot",
  portalSlug,
  large = false,
}: {
  providerId: string;
  branchId: string;
  typeId: string;
  date: string;
  name?: string;
  /** Load slots through the patient portal API (online-booking rules apply). */
  portalSlug?: string;
  large?: boolean;
}) {
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, startTransition] = useTransition();
  const ready = providerId && branchId && typeId && date;

  useEffect(() => {
    if (!ready) {
      setSlots(null);
      return;
    }
    startTransition(async () => {
      try {
        setError(null);
        const params = { providerId, branchId, typeId, date };
        setSlots(portalSlug ? await loadPortalSlots(portalSlug, params) : await loadSlots(params));
      } catch {
        setError("Could not load free times. Try again.");
      }
    });
  }, [ready, providerId, branchId, typeId, date, portalSlug]);

  if (!ready) return <p className="text-sm text-text-muted">Choose a practitioner, type and date to see free times.</p>;
  if (loading) return <p className="text-sm text-text-muted" aria-live="polite">Loading free times…</p>;
  if (error) return <p className="text-sm text-danger-text" role="alert">{error}</p>;
  if (!slots?.length)
    return <p className="text-sm text-text-muted" aria-live="polite">No free times on this day. Try another date or practitioner.</p>;

  return (
    <fieldset>
      <legend className="sr-only">Free times</legend>
      <div className="flex flex-wrap gap-1.5" aria-live="polite">
        {slots.map((s) => (
          <label key={s.start_at} className="cursor-pointer">
            <input type="radio" name={name} value={s.start_at} required className="peer sr-only" />
            <span className={`inline-flex ${large ? "h-11 w-20 text-md" : "h-8 w-16 text-sm"} items-center justify-center rounded-sm border border-border bg-surface font-mono peer-checked:border-primary peer-checked:bg-primary peer-checked:text-white peer-checked:hover:bg-primary-hover peer-focus-visible:outline-2 peer-focus-visible:outline-primary hover:bg-primary-subtle`}>
              {timeOf(s.start_at)}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
