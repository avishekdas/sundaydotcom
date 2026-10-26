/** Dates in the viewer's timezone (A16, C8.2): instants are stored UTC and shown in the user's timezone. */
import { describe, expect, it } from "vitest";
import { formatInstant } from "./format";

describe("formatInstant", () => {
  it("AC-A16-1: 2026-10-24T18:00Z in Asia/Kolkata is 24 Oct 2026, 11:30 pm", () => {
    expect(formatInstant("2026-10-24T18:00:00Z", "Asia/Kolkata")).toBe("24 Oct 2026, 11:30 pm");
  });
  it("uses the given zone, including DST", () => {
    expect(formatInstant("2026-10-24T18:00:00Z", "America/New_York")).toBe("24 Oct 2026, 2:00 pm");
    expect(formatInstant("2026-11-02T14:05:00Z", "America/New_York")).toBe("2 Nov 2026, 9:05 am");
    expect(formatInstant("2026-10-24T00:00:00Z", "UTC")).toBe("24 Oct 2026, 12:00 am");
  });
});
