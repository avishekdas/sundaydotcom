/** Admin "Account settings" (A1.2): name, timezone, date format, week start, allowed invite domains. */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AccountSettings, type AccountApi, type Settings } from "./AccountSettings";

const initial: Settings = { name: "Tasklane", timezone: "UTC", date_format: "YYYY-MM-DD", week_start: "Mon", allowed_domains: [] };

function fakeApi(): AccountApi & { saved: Partial<Settings>[] } {
  let s = { ...initial };
  const saved: Partial<Settings>[] = [];
  return {
    saved,
    getSettings: vi.fn(async () => s),
    saveSettings: vi.fn(async (patch: Partial<Settings>) => { saved.push(patch); s = { ...s, ...patch }; return s; }),
  };
}

afterEach(cleanup);

describe("AccountSettings", () => {
  it("loads and saves the changed fields", async () => {
    const api = fakeApi();
    const onSaved = vi.fn();
    render(<AccountSettings api={api} onSaved={onSaved} />);
    const name = await screen.findByTestId("account-name");
    expect((name as HTMLInputElement).value).toBe("Tasklane");
    fireEvent.change(name, { target: { value: "Acme Inc" } });
    fireEvent.change(screen.getByTestId("account-domains"), { target: { value: "acme.com, acme.co.uk" } });
    fireEvent.change(screen.getByTestId("account-week-start"), { target: { value: "Sun" } });
    fireEvent.click(screen.getByTestId("account-save"));
    await waitFor(() => expect(api.saved).toHaveLength(1));
    expect(api.saved[0]).toEqual({ name: "Acme Inc", week_start: "Sun", allowed_domains: ["acme.com", "acme.co.uk"] });
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ name: "Acme Inc" }));
  });

  it("shows server validation errors", async () => {
    const api = fakeApi();
    api.saveSettings = vi.fn(async () => { throw new Error("timezone: an IANA timezone"); });
    render(<AccountSettings api={api} onSaved={() => {}} />);
    fireEvent.change(await screen.findByTestId("account-timezone"), { target: { value: "Mars/Base" } });
    fireEvent.click(screen.getByTestId("account-save"));
    expect((await screen.findByRole("alert")).textContent).toContain("IANA");
  });
});
