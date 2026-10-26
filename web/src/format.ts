/**
 * Instants are stored UTC and shown in the viewer's timezone (A16, C8.2): "24 Oct 2026, 11:30 pm".
 * Built from Intl parts so the output does not depend on the browser's locale.
 */
export function formatInstant(iso: string, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone, day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true,
  }).formatToParts(new Date(iso));
  const get = (t: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === t)?.value ?? "";
  const hour = get("hour") === "0" ? "12" : get("hour");
  return `${get("day")} ${get("month")} ${get("year")}, ${hour}:${get("minute")} ${get("dayPeriod").toLowerCase()}`;
}
