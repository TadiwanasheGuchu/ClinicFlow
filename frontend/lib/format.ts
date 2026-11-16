const TZ = "Africa/Windhoek";

const dateFmt = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: TZ,
});
const timeFmt = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: TZ,
});

/** 16 Nov 2026 */
export const formatDate = (iso: string | null | undefined) =>
  iso ? dateFmt.format(new Date(iso)) : "—";

/** 16 Nov 2026, 14:30 */
export const formatDateTime = (iso: string | null | undefined) =>
  iso ? `${dateFmt.format(new Date(iso))}, ${timeFmt.format(new Date(iso))}` : "—";

/** N$1,250.00 */
export const formatNAD = (amount: number) =>
  `N$${amount.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export const shortId = (id: string | null | undefined) => (id ? id.slice(0, 8) : "—");

/** "member.roles_changed" -> "Member roles changed" */
export const humanise = (code: string) => {
  const text = code.replace(/[._]/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
};
