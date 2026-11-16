import clsx, { type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Teach tailwind-merge the custom "md" font size so `text-md` is not mistaken for a colour.
const twMerge = extendTailwindMerge({ extend: { theme: { text: ["md"] } } });

/** Join classes; later utilities override earlier conflicting ones (e.g. w-72 over w-full). */
export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
