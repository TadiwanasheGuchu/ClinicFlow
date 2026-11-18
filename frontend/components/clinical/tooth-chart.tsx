import { CONDITION_CODE, CONDITION_LABEL, PERMANENT_ROWS, PRIMARY_ROWS } from "@/lib/dental";
import { cn } from "@/lib/cn";
import type { ChartEntry } from "@/types/api";

const ATTENTION = new Set(["caries", "fracture", "watch"]);
const ABSENT = new Set(["missing", "extracted"]);

/** Odontogram: each tooth shows its number and a text code for the latest finding, so the
 *  chart never depends on colour. Full detail is in the title and the list below it. */
function Tooth({ tooth, entries }: { tooth: number; entries: ChartEntry[] | undefined }) {
  const latest = entries?.[0];
  const summary = entries?.map((e) => `${CONDITION_LABEL[e.condition]}${e.surfaces ? ` (${e.surfaces})` : ""}`).join("; ");
  return (
    <div
      title={summary ? `Tooth ${tooth}: ${summary}` : `Tooth ${tooth}: nothing recorded`}
      className={cn(
        "flex h-14 w-10 flex-col items-center justify-between rounded-sm border py-1 text-xs",
        !latest && "border-border bg-surface text-text-muted",
        latest && ATTENTION.has(latest.condition) && "border-warning bg-warning-subtle text-warning-text font-semibold",
        latest && ABSENT.has(latest.condition) && "border-dashed border-border bg-surface-muted text-text-muted",
        latest && !ATTENTION.has(latest.condition) && !ABSENT.has(latest.condition) && "border-primary bg-primary-subtle text-primary",
      )}
    >
      <span className="font-mono">{tooth}</span>
      <span className="font-mono">{latest ? CONDITION_CODE[latest.condition] : ""}{latest?.surfaces ? <span className="block text-[10px] leading-none">{latest.surfaces}</span> : null}</span>
    </div>
  );
}

export function ToothChart({ teeth, primary = false }: { teeth: Record<string, ChartEntry[]>; primary?: boolean }) {
  const rows = primary ? PRIMARY_ROWS : PERMANENT_ROWS;
  return (
    <div className="overflow-x-auto">
      <div className="inline-flex flex-col gap-2" role="group" aria-label={primary ? "Primary teeth" : "Permanent teeth"}>
        {rows.map((row, i) => (
          <div key={i} className="flex gap-1">
            {row.map((t, j) => (
              <div key={t} className={cn(j === row.length / 2 && "ml-3 border-l border-border pl-3")}>
                <Tooth tooth={t} entries={teeth[String(t)]} />
              </div>
            ))}
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-text-muted">
        Viewed facing the patient. Codes: {Object.entries(CONDITION_CODE).map(([k, v]) => `${v} ${CONDITION_LABEL[k]}`).join(" · ")}
      </p>
    </div>
  );
}
