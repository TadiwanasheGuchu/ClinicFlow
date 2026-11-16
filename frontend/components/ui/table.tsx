import { cn } from "@/lib/cn";
import type { ComponentProps } from "react";

/** Dense data table: 36–40px rows, sticky header, flat 1px borders. */
export function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <div className="overflow-x-auto rounded border border-border bg-surface">
      <table className={cn("w-full border-collapse text-left text-base", className)} {...props} />
    </div>
  );
}

export function THead(props: ComponentProps<"thead">) {
  return <thead className="sticky top-0 z-10 bg-surface-muted" {...props} />;
}

export function TH({ className, align, ...props }: ComponentProps<"th"> & { align?: "right" }) {
  return (
    <th
      scope="col"
      className={cn(
        "h-9 border-b border-border px-3 text-xs font-medium tracking-wide text-text-muted uppercase",
        align === "right" && "text-right",
        className,
      )}
      {...props}
    />
  );
}

export function TR({ className, ...props }: ComponentProps<"tr">) {
  return (
    <tr
      className={cn("border-b border-border last:border-b-0 hover:bg-background", className)}
      {...props}
    />
  );
}

export function TD({
  className,
  align,
  mono,
  ...props
}: ComponentProps<"td"> & { align?: "right"; mono?: boolean }) {
  return (
    <td
      className={cn(
        "h-10 px-3 align-middle",
        align === "right" && "text-right",
        mono && "font-mono text-sm",
        className,
      )}
      {...props}
    />
  );
}
